#!/usr/bin/env python3
"""PR Improvement & Zero-Regression Evaluator — S07 (task #486).

The definitive deterministic pre-merge gate for Supremeai-bd/supremeai-open
(wired into pipeline.yml as a PR gate and landing.yml as the final
pre-squash barrier — integration hunks in docs/S07_PR_EVALUATOR_SPEC.md).
A PR is certified only when BOTH hold:

  Beneficial       — scope contract alignment, positive test gain,
                     schema validation when contracts are touched, and
                     rejection of cosmetic churn (whitespace/comment/
                     docstring-only or pure-rename diffs).
  Zero-Regression  — zero test suppression, zero scope leakage,
                     zero dependency bloat, backward compatibility
                     preserved unless a migration note is approved.

Design invariants:
- Zero third-party dependencies, no network, offline (<3s) — stdlib only.
- Fail-closed: malformed input or undecidable checks reject the PR.
- Deterministic: same evaluation request -> same verdict, always.
- Data-only input: the CI workflow supplies git diff facts; this module
  performs the lexical analysis and emits the verdict. It never shells
  out, so the logic is fully testable offline.

Self-test: python3 pr_improvement_regression_guard.py --self-test
CLI: python3 pr_improvement_regression_guard.py --evaluate request.json
Exit codes: 0 = PASS, 2 = FAIL (fail-closed includes input errors).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# --- Single sources of truth (imported by the test suite; never copy) ------
PASS = "PASS"
FAIL = "FAIL"

ASSERTION_RE = re.compile(
    r"\bassert\b|expect\s*\(|self\.assert|\bit\s*\(|unittest\.[\w.]*assert")
SUPPRESSION_RE = re.compile(
    r"unittest\.skip|pytest\.mark\.skip|@unittest\.skip|it\.skip|test\.skip|"
    r"\.skip\(|xfail")
COMMENTED_ASSERTION_RE = re.compile(
    r"#\s*\w*\.?(assert|expect)\b|//\s*\w*\.?(assert|expect)\b")
DEPENDENCY_MANIFESTS = ("package.json", "requirements", "pyproject.toml",
                        "go.mod", "Cargo.toml", "Gemfile")
HARD_PROTECTED = (".github/", ".env", "*.pem", "*.key", "id_rsa",
                  "*credential*", "*.p12")
PUBLIC_API_REMOVAL_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?def\s+([A-Za-z_]\w*)|"
    r"^\s*(?:export\s+)?function\s+([A-Za-z_]\w*)|"
    r"^\s*export\s+(?:const|class|interface)\s+([A-Za-z_]\w*)|"
    r"^\s*class\s+([A-Za-z_]\w*)|"
    r"(@\w+\.route\()|"
    r"add_argument\(\s*['\"]([\w-]+)['\"]")
DEP_BLOCK_RE = re.compile(r'"(dependencies|devDependencies)"\s*:')
_DEP_LINE_RE = re.compile(r'"[^"]+"\s*:\s*"[^"]*"')
_IDENT = r"[A-Za-z_$][\w$]*"
_TOKEN_RE = re.compile(r"[A-Za-z_$][\w$]*|\d[\w.]*|\S")


def is_test_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (path.startswith(("tests/", "test/", "spec/"))
            or name.startswith("test_") or name.endswith("_test.ts")
            or name.endswith(".test.ts") or name.endswith("_test.js")
            or name.endswith(".test.js") or name.startswith("test"))


def is_dependency_manifest(path: str) -> bool:
    return any(m in path for m in DEPENDENCY_MANIFESTS)


def is_hard_protected(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if path.startswith(".github/") or path == ".env" or name == ".env":
        return True
    for pat in HARD_PROTECTED:
        if pat.startswith("*") and name.endswith(pat[1:]):
            return True
        if not pat.startswith("*") and (path == pat or path.startswith(pat)):
            return True
    return False


def _tokens(line: str) -> List[str]:
    return _TOKEN_RE.findall(line)


def _is_pure_rename(removed: str, added: str) -> bool:
    """Equal structure, differing identifiers only, no new operators."""
    ra, aa = _tokens(removed), _tokens(added)
    if len(ra) != len(aa) or not ra:
        return False
    kw_ops = {"def", "return", "if", "else", "elif", "for", "while", "import",
              "from", "class", "const", "let", "var", "function", "export",
              "=", "==", "=>", "+", "-", "*", "/", "(", ")", ":", ",", "."}
    ident_like = re.compile(_IDENT + r"$")
    diff = 0
    for a, b in zip(ra, aa):
        if a == b:
            continue
        if a in kw_ops or b in kw_ops:
            return False
        if not (ident_like.match(a) and ident_like.match(b)):
            return False
        diff += 1
    return diff > 0


def _strip_semantics(line: str) -> Optional[str]:
    """None when the line carries no semantic payload (churn candidate)."""
    s = line.strip()
    if not s:
        return None
    if s.startswith(("#", "//", "/*", "*", '"""', "'''", "<!--")):
        return None
    if s in ("*/", "-->",):
        return None
    return s


def _semantic_units(changed: Dict[str, List[str]]) -> Tuple[List[str], List[str]]:
    """Classify one file's diff into semantic and churn unit pairs."""
    semantic: List[str] = []
    removed = [_strip_semantics(x) for x in changed.get("removed", [])]
    added = [_strip_semantics(x) for x in changed.get("added", [])]
    rem_alive = [x for x in removed if x is not None]
    add_alive = [x for x in added if x is not None]
    # pair pure whitespace-only and rename units
    used = [False] * len(rem_alive)
    for a in add_alive:
        for i, r in enumerate(rem_alive):
            if used[i]:
                continue
            if r == a or r.strip() == a.strip():
                used[i] = True  # whitespace-only move
                break
            if _is_pure_rename(r, a):
                used[i] = True  # rename unit
                break
    unmatched_removed = [r for i, r in enumerate(rem_alive) if not used[i]]
    unmatched_added = [a for a in add_alive]
    semantic.extend(unmatched_removed)
    semantic.extend(unmatched_added)
    return semantic, []


def _assertions_added(path: str, added: List[str]) -> int:
    if not is_test_file(path):
        return 0
    return sum(1 for line in added if ASSERTION_RE.search(line))


def _check_scope(changed_paths: List[str], declared: List[str],
                 violations: List[dict]) -> None:
    declared_set = set(declared)
    for path in changed_paths:
        if path not in declared_set:
            violations.append({
                "check": "scope_contract_alignment", "severity": "block",
                "evidence": f"file {path} is outside the declared Touching Files"})
        if is_hard_protected(path):
            violations.append({
                "check": "zero_scope_leakage", "severity": "block",
                "evidence": f"hard-protected path {path} touched (declaration cannot override)"})


def _check_churn(changed_files: List[dict], violations: List[dict]) -> int:
    semantic_total = 0
    for cf in changed_files:
        removed_raw = cf.get("removed", [])
        added_raw = cf.get("added", [])
        rem = [x for x in (_strip_semantics(l) for l in removed_raw) if x]
        add = [x for x in (_strip_semantics(l) for l in added_raw) if x]
        used = [False] * len(rem)
        semantic_here = 0
        for a in add:
            matched = False
            for i, r in enumerate(rem):
                if not used[i]:
                    if r == a or r.strip() == a.strip() or _is_pure_rename(r, a):
                        used[i] = True
                        matched = True
                        break
            if not matched:
                semantic_here += 1
        semantic_here += sum(1 for u in used if not u)
        semantic_total += semantic_here
    if semantic_total == 0:
        violations.append({
            "check": "rejection_of_cosmetic_churn", "severity": "block",
            "evidence": "diff is whitespace/comment/docstring-only or pure renames"})
    return semantic_total


def _removed_symbol(line: str) -> Optional[str]:
    m = PUBLIC_API_REMOVAL_RE.match(line)
    if not m:
        return None
    name = next((g for g in m.groups() if g), None)
    if name is None:
        return None
    if name.startswith("@"):
        return name.rstrip("(")  # route decorator, e.g. @app.route
    return name


def _check_suppression(changed_files: List[dict], violations: List[dict]) -> None:
    for cf in changed_files:
        path = cf.get("path", "")
        added = cf.get("added", [])
        removed = cf.get("removed", [])
        for line in added:
            if SUPPRESSION_RE.search(line):
                violations.append({
                    "check": "zero_test_suppression", "severity": "block",
                    "evidence": f"{path}: skip/xfail added: {line.strip()[:80]}"})
            if is_test_file(path) and COMMENTED_ASSERTION_RE.search(line):
                violations.append({
                    "check": "zero_test_suppression", "severity": "block",
                    "evidence": f"{path}: assertion commented out: {line.strip()[:80]}"})
        if is_test_file(path):
            added_set = {x.strip() for x in added}
            for line in removed:
                if ASSERTION_RE.search(line) and line.strip() not in added_set:
                    violations.append({
                        "check": "zero_test_suppression", "severity": "block",
                        "evidence": f"{path}: assertion deleted: {line.strip()[:80]}"})


def _check_dependencies(changed_files: List[dict], allow_new: bool,
                        violations: List[dict]) -> None:
    if allow_new:
        return
    for cf in changed_files:
        path = cf.get("path", "")
        added = cf.get("added", [])
        if not is_dependency_manifest(path):
            continue
        in_dep_block = False
        for line in added:
            s = line.strip()
            if not s or s.startswith(("#", "//")):
                continue
            if path.endswith("package.json"):
                if DEP_BLOCK_RE.search(line):
                    in_dep_block = True
                    continue
                if in_dep_block and _DEP_LINE_RE.search(s):
                    violations.append({
                        "check": "zero_dependency_bloat", "severity": "block",
                        "evidence": f"{path}: new npm dependency: {s[:80]}"})
                    continue
                if in_dep_block and s.startswith("}"):
                    in_dep_block = False
                continue
            if "requirements" in path:
                violations.append({
                    "check": "zero_dependency_bloat", "severity": "block",
                    "evidence": f"{path}: new pip dependency: {s[:80]}"})
            elif path.endswith(("pyproject.toml", "go.mod", "Cargo.toml", "Gemfile")):
                violations.append({
                    "check": "zero_dependency_bloat", "severity": "block",
                    "evidence": f"{path}: new dependency declaration: {s[:80]}"})


def _check_backward_compat(changed_files: List[dict], migration_notes: List[str],
                           violations: List[dict]) -> None:
    removed_names: List[str] = []
    added_text: List[str] = []
    for cf in changed_files:
        if is_test_file(cf.get("path", "")):
            continue
        for line in cf.get("removed", []):
            name = _removed_symbol(line)
            if name:
                removed_names.append(name)
        added_text.extend(cf.get("added", []))
    added_blob = "\n".join(added_text)
    for name in removed_names:
        if re.search(rf"\b{re.escape(name)}\b", added_blob):
            continue  # relocated, not removed
        if any(name in note for note in migration_notes):
            continue  # approved migration
        violations.append({
            "check": "backward_compatibility", "severity": "block",
            "evidence": f"public symbol removed/renamed without migration note: {name}"})


def evaluate(request: dict) -> dict:
    """Deterministic evaluation. Fail-closed on malformed input."""
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    changed_files = request.get("changed_files")
    if not isinstance(changed_files, list):
        raise ValueError("changed_files must be a list")
    for cf in changed_files:
        if not isinstance(cf, dict) or not isinstance(cf.get("path"), str):
            raise ValueError("each changed file needs a string path")
        if not isinstance(cf.get("added", []), list) or not isinstance(cf.get("removed", []), list):
            raise ValueError("added/removed must be line lists")
    declared = request.get("declared_files")
    if not isinstance(declared, list):
        raise ValueError("declared_files must be a list")
    migration_notes = request.get("migration_notes") or []
    if not isinstance(migration_notes, list):
        raise ValueError("migration_notes must be a list")
    allow_new = request.get("allow_new_dependencies") is True

    violations: List[dict] = []
    paths = [cf["path"] for cf in changed_files]
    _check_scope(paths, declared, violations)

    assertions = sum(_assertions_added(cf["path"], cf.get("added", []))
                     for cf in changed_files)
    fixed = request.get("fixed_failing_tests") or []
    if assertions < 1 and not fixed:
        violations.append({
            "check": "positive_test_gain", "severity": "block",
            "evidence": "no verified test assertion added and no failing test fixed"})

    semantic = _check_churn(changed_files, violations)

    schemas_touched = any(p.startswith("api-schemas/") for p in paths)
    if schemas_touched and request.get("schema_validation") != "verified":
        violations.append({
            "check": "contract_schema_validation", "severity": "block",
            "evidence": "api-schemas/ touched but schema_validation != verified"})

    _check_suppression(changed_files, violations)
    _check_dependencies(changed_files, allow_new, violations)
    _check_backward_compat(changed_files, migration_notes, violations)

    by_family: Dict[str, List[str]] = {}
    for v in violations:
        by_family.setdefault(v["check"], []).append(v["evidence"])
    beneficial_checks = {"scope_contract_alignment", "positive_test_gain",
                         "contract_schema_validation", "rejection_of_cosmetic_churn"}
    regression_checks = set(by_family) - beneficial_checks
    beneficial_ok = not (set(by_family) & beneficial_checks)
    regression_ok = not regression_checks
    verdict = PASS if (beneficial_ok and regression_ok) else FAIL
    return {
        "verdict": verdict,
        "beneficial": {"passed": beneficial_ok,
                       "failed_checks": sorted(set(by_family) & beneficial_checks)},
        "zero_regression": {"passed": regression_ok,
                            "failed_checks": sorted(regression_checks)},
        "violations": violations,
        "stats": {"files_changed": len(paths),
                  "assertions_added": assertions,
                  "semantic_lines": semantic,
                  "failing_tests_fixed": len(fixed)},
        "evaluated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _self_test() -> int:
    def cf(path, added=(), removed=()):
        return {"path": path, "added": list(added), "removed": list(removed)}

    def req(files, declared=None, **kw):
        base = {"changed_files": files,
                "declared_files": declared if declared is not None
                else [f["path"] for f in files]}
        base.update(kw)
        return base

    # Tier 1 case 1: valid PR (adds test + functional code) -> PASS
    good = req([cf("scripts/ci/guard.py", ["def check(x):\n    return x > 0"]),
                cf("tests/test_guard.py", ["def test_check():", "    assert check(1) is True"])])
    r = evaluate(good)
    assert r["verdict"] == PASS, r
    assert r["stats"]["assertions_added"] == 1, r

    # Tier 1 case 2: cosmetic churn (comments/whitespace only) -> FAIL
    churn = req([cf("scripts/ci/guard.py",
                    ["# a new shiny comment", "x = 1  "],
                    ["x = 1"])])
    r = evaluate(churn)
    assert r["verdict"] == FAIL and any(
        v["check"] == "rejection_of_cosmetic_churn" for v in r["violations"]), r

    # rename-only diff also fails as churn
    ren = req([cf("scripts/ci/guard.py", ["total = count + 1"], ["sum_ = count + 1"])])
    r = evaluate(ren)
    assert r["verdict"] == FAIL, r

    # Tier 1 case 3: test suppression -> FAIL
    sup = req([cf("tests/test_guard.py",
                  ["@unittest.skip(\"flaky\")", "def test_check():", "    assert check(1)"])])
    r = evaluate(sup)
    assert r["verdict"] == FAIL and any(
        v["check"] == "zero_test_suppression" for v in r["violations"]), r

    # deleting an existing assertion -> FAIL
    dele = req([cf("tests/test_guard.py",
                   ["def test_check():"],
                   ["def test_check():", "    assert check(1)"])])
    r = evaluate(dele)
    assert r["verdict"] == FAIL, r

    # Tier 1 case 4: out-of-scope file -> FAIL
    leak = req([cf("scripts/ci/guard.py", ["assert True"])], declared=["scripts/ci/other.py"])
    r = evaluate(leak)
    assert r["verdict"] == FAIL and any(
        v["check"] == "scope_contract_alignment" for v in r["violations"]), r

    # hard-protected path fails even when declared
    hard = req([cf(".github/workflows/pipeline.yml", ["+ tweak"])])
    r = evaluate(hard)
    assert r["verdict"] == FAIL and any(
        v["check"] == "zero_scope_leakage" for v in r["violations"]), r

    # dependency bloat -> FAIL
    dep = req([cf("package.json", ['"dependencies": {', '  "left-pad": "^1.3.0"']),
               cf("tests/test_guard.py", ["assert True"])])
    r = evaluate(dep)
    assert r["verdict"] == FAIL and any(
        v["check"] == "zero_dependency_bloat" for v in r["violations"]), r

    # requirements.txt additions rejected
    pip = req([cf("requirements.txt", ["requests==2.0.0"]),
               cf("tests/test_guard.py", ["assert True"])])
    r = evaluate(pip)
    assert r["verdict"] == FAIL, r

    # public API removal without migration note -> FAIL
    api = req([cf("scripts/ci/guard.py", [], ["def old_check(x):", "    return x"]),
               cf("tests/test_guard.py", ["assert True"])])
    r = evaluate(api)
    assert r["verdict"] == FAIL and any(
        v["check"] == "backward_compatibility" for v in r["violations"]), r
    # ...but allowed with a migration note naming the symbol
    api2 = req([cf("scripts/ci/guard.py", [], ["def old_check(x):", "    return x"]),
                cf("tests/test_guard.py", ["assert True"])],
               migration_notes=["old_check replaced by new_check (#486)"])
    r = evaluate(api2)
    assert r["verdict"] == PASS, r
    # ...and relocation (name re-added) is fine
    api3 = req([cf("scripts/ci/guard.py",
                   ["def old_check(x):  # moved", "    return x"],
                   ["def old_check(x):", "    return x"]),
                cf("tests/test_guard.py", ["assert True"])])
    assert evaluate(api3)["verdict"] == PASS

    # schema contract: api-schemas touched without verification -> FAIL
    sch = req([cf("api-schemas/gateway.openapi.yaml", ["  new: true"]),
               cf("tests/test_guard.py", ["assert True"])])
    r = evaluate(sch)
    assert r["verdict"] == FAIL and any(
        v["check"] == "contract_schema_validation" for v in r["violations"]), r
    sch2 = req([cf("api-schemas/gateway.openapi.yaml", ["  new: true"]),
                cf("tests/test_guard.py", ["assert True"])],
               schema_validation="verified")
    assert evaluate(sch2)["verdict"] == PASS

    # no test gain and no fixed failing test -> FAIL; with fixed list -> PASS
    nt = req([cf("scripts/ci/guard.py", ["def f():\n    return 1"])])
    r = evaluate(nt)
    assert r["verdict"] == FAIL and any(
        v["check"] == "positive_test_gain" for v in r["violations"]), r
    nt2 = req([cf("scripts/ci/guard.py", ["def f():\n    return 1"])],
              fixed_failing_tests=["tests/test_guard.py::test_f"])
    assert evaluate(nt2)["verdict"] == PASS

    # fail-closed malformed inputs
    for bad in (None, {}, {"changed_files": "x"},
                {"changed_files": [{}]},
                {"changed_files": [{"path": "a.py"}], "declared_files": "x"}):
        try:
            evaluate(bad)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
    print("self-test OK: pr_improvement_regression_guard")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    if len(sys.argv) == 3 and sys.argv[1] == "--evaluate":
        with open(sys.argv[2], encoding="utf-8") as fh:
            req = json.load(fh)
        try:
            verdict = evaluate(req)
        except ValueError as exc:
            print(json.dumps({"verdict": FAIL, "violations": [
                {"check": "input_validation", "severity": "block",
                 "evidence": str(exc)}]}, indent=2))
            sys.exit(2)
        print(json.dumps(verdict, indent=2))
        sys.exit(0 if verdict["verdict"] == PASS else 2)
    print(__doc__)
    sys.exit(2)
