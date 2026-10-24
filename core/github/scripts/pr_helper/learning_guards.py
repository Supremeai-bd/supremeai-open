#!/usr/bin/env python3
"""
PR Helper — Learning Guards (governance + type-gate)
=====================================================

ඉගෙනුම්-පාදක (learning-based) guards. Each guard encodes a REAL regression
class that previously reached `main` because the 5-step lifecycle only had
backend pytest + ruff intelligence and auto-classified frontend-only PRs as
"pure-improvement" (Step 3: "no backend changes").

LEARNINGS → GUARDS
------------------
L1  Frontend type-gate .......... learning: #1028 (fix #972) shipped
    `isLoading` referencing an undefined identifier (TS2304) in
    GlobalHeader.tsx. vite build does NOT type-check, so the broken bundle
    shipped; at runtime the header crashed (ReferenceError → error boundary)
    and 3 auth-smoke E2E tests failed deterministically on main for 15+
    consecutive commits. Guard: when frontend sources changed, run
    `tsc -b tsconfig.app.json --noEmit`; a type error inside a file the PR
    touches is a BLOCK; errors in untouched files are warnings (pre-existing
    debt, e.g. stale *.test.ts path errors tracked in #465).

L2  Test-file deletion guard .... learning: PR #1038 deleted 8 test files
    (1,758 lines) to make CI green → #1042 governance regression; AGENTS.md:
    "Do not delete tests, audits, plans, safeguards, or required
    documentation without explicit instruction" + "must not knowingly reduce
    existing test coverage". Guard: deleted files matching test-path patterns
    BLOCK the PR unless the PR body carries an explicit
    `ALLOW-TEST-DELETION: #<issue>` marker.

L3  Honest-CI skip guard ........ learning: #1011 (82 skipped tests debt);
    c6a0856b re-added `@pytest.mark.skip(reason="Failing in CI, skipped by
    auto-remediation")` — fake-green. Guard: ADDED skip/xfail/fixme markers
    in any test surface BLOCK the PR (removals are fine — that is the fix
    direction). Conditional+documented `skipif`/`skipIf` remain allowed.

L4  Plans/docs deletion guard ... learning: same AGENTS.md clause as L2;
    docs/plans/ deletion was explicitly forbidden in #1042. Guard: deleted
    files under docs/plans|master_docs|security, audit_reports BLOCK unless
    `ALLOW-DOCS-DELETION: #<issue>` marker present.

L5  CI-suppression guard ........ learning: the fake-green era leaned on
    `continue-on-error: true` in workflows. Guard: ADDED occurrences in
    .github/workflows/** produce WARNINGS (visibility; not a block — some
    legacy steps legitimately use it).

Output: JSON report (+ markdown summary), GitHub ::error:: annotations,
exit 1 when any BLOCK violation exists (fail-closed).

Usage:
  python3 learning_guards.py --base <sha> --head <sha> \
      [--output-json out.json] [--summary out.md] \
      [--allow-test-deletion "#123"] [--allow-docs-deletion "#124"] \
      [--scope-only] [--skip-tsc]

`--scope-only` prints {"frontend_changed": bool, "backend_changed": bool}
and exits 0 (used by the workflow to conditionally provision Node before
the full run, which executes tsc internally when needed).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Path classification patterns
# ─────────────────────────────────────────────────────────────────────────────

TEST_PATH_PATTERNS = [
    "backend/tests/**",
    "backend/conftest.py",
    "conftest.py",
    "**/conftest.py",
    "**/test_*.py",
    "**/*_test.py",
    "frontend/e2e/**",
    "frontend/src/test/**",
    "frontend/src/setupTests*",
    "**/*.test.ts",
    "**/*.test.tsx",
    "**/*.test.js",
    "**/*.test.jsx",
    "**/*.test.mjs",
    "**/*.spec.ts",
    "**/*.spec.tsx",
    "**/*.spec.js",
    "**/*.spec.jsx",
    "frontend/playwright.config.ts",
    "frontend/vitest.config.ts",
]

PROTECTED_DOCS_PATTERNS = [
    "docs/plans/**",
    "docs/master_docs/**",
    "docs/security/**",
    "audit_reports/**",
]

FRONTEND_SOURCE_PATTERNS = [
    "frontend/src/**",
    "frontend/e2e/**",
    "frontend/index.html",
    "frontend/vite.config.ts",
    "frontend/vitest.config.ts",
    "frontend/tsconfig*.json",
    "frontend/tailwind.config.js",
    "frontend/package.json",
    "frontend/*.json",
]

# Added-line skip markers (BLOCK). NOTE: `pytest.mark.skipif` and
# `unittest.skipIf` are intentionally NOT listed — conditional, documented
# skips are an accepted honest-CI pattern; blanket skips are not.
SKIP_LINE_PATTERNS = [
    (re.compile(r"@pytest\.mark\.skip(?!if)"), "pytest blanket skip"),
    (re.compile(r"@pytest\.mark\.xfail"), "pytest xfail"),
    (re.compile(r"\bpytest\.skip\("), "pytest.skip() call"),
    (re.compile(r"@unittest\.skip(?!If)"), "unittest blanket skip"),
    (re.compile(r"@unittest\.expectedFailure"), "unittest expectedFailure"),
    (re.compile(r"\bit\.skip\("), "vitest/jest it.skip"),
    (re.compile(r"\btest\.skip\("), "vitest/jest test.skip"),
    (re.compile(r"\bdescribe\.skip\("), "vitest/jest describe.skip"),
    (re.compile(r"\bit\.fixme\("), "vitest/jest it.fixme"),
    (re.compile(r"\btest\.fixme\("), "vitest/jest test.fixme"),
    (re.compile(r"\bxit\("), "xit()"),
    (re.compile(r"\bxdescribe\("), "xdescribe()"),
]

# Added-line CI suppression markers (WARNING)
CI_SUPPRESSION_PATTERNS = [
    (re.compile(r"continue-on-error:\s*true"), "continue-on-error: true added in workflow"),
]

TSC_LINE_RE = re.compile(
    r"^(?P<file>[^(\s]+)\((?P<line>\d+),(?P<col>\d+)\):\s+"
    r"(?P<sev>error|warning)\s+(?P<code>\S+):\s+(?P<msg>.*)$"
)

BLOCK = "block"
WARNING = "warning"


def _git(args: List[str]) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()[:400]}")
    return result.stdout


def _matches(path: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


def _is_test_path(path: str) -> bool:
    return _matches(path, TEST_PATH_PATTERNS)


def _is_protected_docs(path: str) -> bool:
    return _matches(path, PROTECTED_DOCS_PATTERNS)


def _is_frontend_source(path: str) -> bool:
    return _matches(path, FRONTEND_SOURCE_PATTERNS)


def run_tsc(frontend_dir: str = "frontend") -> Tuple[int, str]:
    """Run tsc project build-check; return (exit_code, combined_output)."""
    tsc = shutil.which("tsc")
    base_cmd: List[str]
    if shutil.which("pnpm"):
        base_cmd = ["pnpm", "exec", "tsc", "-b", "tsconfig.app.json", "--noEmit"]
    elif tsc:
        base_cmd = [tsc, "-b", "tsconfig.app.json", "--noEmit"]
    else:
        base_cmd = [os.path.join(frontend_dir, "node_modules", ".bin", "tsc"),
                    "-b", "tsconfig.app.json", "--noEmit"]
    proc = subprocess.run(
        base_cmd, cwd=frontend_dir, capture_output=True, text=True, check=False
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def parse_tsc(output: str) -> List[Dict[str, object]]:
    entries: List[Dict[str, object]] = []
    for raw in output.splitlines():
        m = TSC_LINE_RE.match(raw.strip())
        if not m:
            continue
        entries.append(
            {
                "file": m.group("file").replace("\\", "/"),
                "line": int(m.group("line")),
                "severity": m.group("sev"),
                "code": m.group("code"),
                "message": m.group("msg"),
            }
        )
    return entries


def collect_diff(base: str, head: str) -> Dict[str, object]:
    changed = [f for f in _git(["diff", "--name-only", f"{base}...{head}"]).splitlines() if f]
    deleted = [f for f in _git(["diff", "--diff-filter=D", "--name-only", f"{base}...{head}"]).splitlines() if f]

    # Added lines with file + new-file line numbers (unified diff, U0).
    added: List[Tuple[str, int, str]] = []
    current_file: Optional[str] = None
    new_line = 0
    for raw in _git(["diff", "-U0", f"{base}...{head}"]).splitlines():
        if raw.startswith("+++ b/"):
            current_file = raw[6:]
        elif raw.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", raw)
            if m and current_file:
                new_line = int(m.group(1))
        elif raw.startswith("+") and not raw.startswith("+++") and current_file:
            added.append((current_file, new_line, raw[1:]))
            new_line += 1
    return {"changed": changed, "deleted": deleted, "added": added}


def guard_learning_guards(
    base: str,
    head: str,
    allow_test_deletion: Optional[str],
    allow_docs_deletion: Optional[str],
    tsc_report: Optional[List[Dict[str, object]]],
    tsc_scoped: bool,
) -> Dict[str, object]:
    diff = collect_diff(base, head)
    changed: List[str] = diff["changed"]  # type: ignore[assignment]
    deleted: List[str] = diff["deleted"]  # type: ignore[assignment]
    added: List[Tuple[str, int, str]] = diff["added"]  # type: ignore[assignment]

    violations: List[Dict[str, object]] = []
    warnings: List[Dict[str, object]] = []

    frontend_changed = any(_is_frontend_source(f) for f in changed)
    backend_changed = any(
        f.startswith("backend/") or f.startswith("scripts/ci/") for f in changed
    )

    # ── L2: test-file deletion ────────────────────────────────────────────
    deleted_tests = sorted(f for f in deleted if _is_test_path(f))
    if deleted_tests and not allow_test_deletion:
        for f in deleted_tests:
            violations.append(
                {
                    "guard": "L2-test-deletion",
                    "severity": BLOCK,
                    "file": f,
                    "detail": "Test file deleted. AGENTS.md forbids deleting tests to "
                              "make builds pass (learnings: #1038 deleted 8 test files / "
                              "1,758 lines → #1042 governance regression; #1011 skip debt).",
                    "remediation": "Repair the test instead of deleting it, or obtain an "
                                   "explicit issue and add `ALLOW-TEST-DELETION: #<issue>` "
                                   "to the PR body.",
                }
            )

    # ── L4: protected docs/plans deletion ─────────────────────────────────
    deleted_docs = sorted(f for f in deleted if _is_protected_docs(f))
    if deleted_docs and not allow_docs_deletion:
        for f in deleted_docs:
            violations.append(
                {
                    "guard": "L4-docs-deletion",
                    "severity": BLOCK,
                    "file": f,
                    "detail": "Protected plan/audit/security doc deleted (AGENTS.md: "
                              "no deletion of plans, audits, safeguards or required "
                              "documentation without explicit instruction).",
                    "remediation": "Restore the document, or add `ALLOW-DOCS-DELETION: "
                                   "#<issue>` to the PR body with an approved issue.",
                }
            )

    # ── L3: honest-CI skip guard (added lines only) ───────────────────────
    # Scope: TEST surfaces only (same path patterns as L2). Rationale learned
    # from validation FPs: (a) docs quoting the markers verbatim
    # (SECURITY_GUARDIAN.md), (b) the guard's own regex definitions inside
    # .github/scripts tooling. Blanket skips that make CI fake-green live in
    # test files — that is the regression class (#1011 / c6a0856b).
    skip_hits: List[Dict[str, object]] = []
    for path, lineno, text in added:
        if not _is_test_path(path):
            continue
        for rx, label in SKIP_LINE_PATTERNS:
            if rx.search(text):
                skip_hits.append(
                    {"file": path, "line": lineno, "kind": label, "snippet": text.strip()[:160]}
                )
                break
    for hit in skip_hits:
        violations.append(
            {
                "guard": "L3-skip-readd",
                "severity": BLOCK,
                "file": f"{hit['file']}:{hit['line']}",
                "detail": f"Skip marker ADDED ({hit['kind']}): {hit['snippet']} — "
                          "fake-green regression class from #1011 / c6a0856b.",
                "remediation": "Fix the underlying failure. Conditional+documented "
                               "skipif/skipIf is allowed; blanket skips are not.",
            }
        )

    # ── L5: CI suppression (added lines, warning) ─────────────────────────
    for path, lineno, text in added:
        if not path.startswith(".github/workflows/"):
            continue
        for rx, label in CI_SUPPRESSION_PATTERNS:
            if rx.search(text):
                warnings.append(
                    {
                        "guard": "L5-ci-suppression",
                        "severity": WARNING,
                        "file": f"{path}:{lineno}",
                        "detail": f"{label}: `{text.strip()[:120]}`",
                    }
                )

    # ── L1: frontend type-gate (tsc, changed-file scoped) ─────────────────
    if tsc_report is not None:
        changed_frontend_rel = {f[len("frontend/"):] for f in changed if f.startswith("frontend/")}
        for entry in tsc_report:
            tsc_file = str(entry["file"])
            in_changed = (
                tsc_file in changed_frontend_rel
                or f"frontend/{tsc_file}" in changed
            )
            record = {
                "guard": "L1-type-gate",
                "severity": BLOCK if (in_changed and entry["severity"] == "error") else WARNING,
                "file": f"{tsc_file}:{entry['line']}",
                "detail": f"{entry['code']}: {entry['message']}",
            }
            if record["severity"] == BLOCK:
                violations.append(record)
            else:
                warnings.append(record)
    if tsc_scoped:
        warnings.append(
            {
                "guard": "L1-type-gate",
                "severity": WARNING,
                "file": "-",
                "detail": "tsc ran scoped to PR-changed files; untouched-file type errors "
                          "are reported as warnings (pre-existing debt, cf. #465).",
            }
        )

    status = "fail" if any(v["severity"] == BLOCK for v in violations) else "pass"
    return {
        "guard": "learning_guards",
        "base": base,
        "head": head,
        "status": status,
        "frontend_changed": frontend_changed,
        "backend_changed": backend_changed,
        "counts": {
            "blocks": sum(1 for v in violations if v["severity"] == BLOCK),
            "warnings": len(warnings),
        },
        "violations": violations,
        "warnings": warnings,
        "changed_files_considered": len(changed),
        "deleted_test_files": deleted_tests,
        "deleted_protected_docs": deleted_docs,
    }


def write_summary_md(report: Dict[str, object], path: str) -> None:
    lines: List[str] = []
    status = report["status"]
    icon = "✅ PASS" if status == "pass" else "⛔ FAIL"
    counts = report["counts"]
    lines.append("## 🛡️ PR Helper — Learning Guards")
    lines.append("")
    lines.append(f"**Result: {icon}** — blocks: **{counts['blocks']}**, warnings: **{counts['warnings']}**")
    lines.append("")
    lines.append("| Guard | Learning it encodes | Verdict |")
    lines.append("|---|---|---|")
    l1 = "BLOCK" if any(v["guard"] == "L1-type-gate" and v["severity"] == BLOCK for v in report["violations"]) else "clean"
    l2 = "BLOCK" if any(v["guard"] == "L2-test-deletion" for v in report["violations"]) else "clean"
    l3 = "BLOCK" if any(v["guard"] == "L3-skip-readd" for v in report["violations"]) else "clean"
    l4 = "BLOCK" if any(v["guard"] == "L4-docs-deletion" for v in report["violations"]) else "clean"
    l5 = "warn" if any(w["guard"] == "L5-ci-suppression" for w in report["warnings"]) else "clean"
    lines.append(f"| L1 frontend type-gate | #1028 GlobalHeader TS2304 runtime crash | {l1} |")
    lines.append(f"| L2 test-file deletion | #1038 → #1042 governance regression | {l2} |")
    lines.append(f"| L3 skip re-add (honest CI) | #1011 — 82 skipped-test debt | {l3} |")
    lines.append(f"| L4 plans/docs deletion | AGENTS.md no-deletion clause | {l4} |")
    lines.append(f"| L5 CI suppression | fake-green era `continue-on-error` | {l5} |")

    if report["violations"]:
        lines.append("")
        lines.append("### ⛔ Blocking violations")
        for v in report["violations"]:
            lines.append(f"- **`{v['file']}`** — {v['detail']}")
            if v.get("remediation"):
                lines.append(f"  - ↳ *Remediation:* {v['remediation']}")
    if report["warnings"]:
        lines.append("")
        lines.append("### ⚠️ Warnings (non-blocking)")
        for w in report["warnings"][:20]:
            lines.append(f"- `{w['file']}` — {w['detail']}")
    lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def emit_annotations(report: Dict[str, object]) -> None:
    for v in report["violations"]:
        print(f"::error file={v['file']}::[learning-guards {v['guard']}] {v['detail']}")
    for w in report["warnings"][:10]:
        print(f"::warning file={w['file']}::[learning-guards {w['guard']}] {w['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="PR Helper learning guards")
    parser.add_argument("--base", help="base sha (merge-base)")
    parser.add_argument("--head", help="head sha")
    parser.add_argument("--output-json")
    parser.add_argument("--summary")
    parser.add_argument("--allow-test-deletion", default=None,
                        help="issue ref present in PR body, e.g. '#123'")
    parser.add_argument("--allow-docs-deletion", default=None)
    parser.add_argument("--scope-only", action="store_true",
                        help="print frontend/backend change flags and exit")
    parser.add_argument("--skip-tsc", action="store_true",
                        help="do not run tsc even if frontend changed (local runs)")
    args = parser.parse_args()

    if args.scope_only:
        if not (args.base and args.head):
            print("{}", end="")
            return 0
        diff = collect_diff(args.base, args.head)
        changed = diff["changed"]
        print(json.dumps({
            "frontend_changed": any(_is_frontend_source(f) for f in changed),
            "backend_changed": any(
                f.startswith("backend/") or f.startswith("scripts/ci/") for f in changed
            ),
        }))
        return 0

    if not (args.base and args.head):
        parser.error("--base and --head are required (unless --scope-only)")

    # ── L1: run tsc when frontend sources changed ─────────────────────────
    tsc_report: Optional[List[Dict[str, object]]] = None
    tsc_scoped = False
    pre = collect_diff(args.base, args.head)
    frontend_changed = any(_is_frontend_source(f) for f in pre["changed"])
    if frontend_changed and not args.skip_tsc and os.path.isdir("frontend"):
        code, output = run_tsc()
        tsc_report = parse_tsc(output)
        tsc_scoped = True
        if code not in (0, 1, 2):
            # tsc infra failure must NOT silently pass the gate (fail-closed)
            violations_tmp = [{
                "guard": "L1-type-gate", "severity": BLOCK, "file": "frontend",
                "detail": f"tsc failed to run (exit {code}) — fail-closed: {output.strip()[:200]}",
            }]
            report = guard_learning_guards(
                args.base, args.head, args.allow_test_deletion,
                args.allow_docs_deletion, None, False,
            )
            report["violations"].extend(violations_tmp)  # type: ignore[union-attr]
            report["status"] = "fail"  # type: ignore[index]
            report["counts"]["blocks"] = len(report["violations"])  # type: ignore[index]
            _finish(report, args)
            return 1
    else:
        tsc_report = None if args.skip_tsc else None

    report = guard_learning_guards(
        args.base, args.head,
        args.allow_test_deletion, args.allow_docs_deletion,
        tsc_report, tsc_scoped,
    )
    _finish(report, args)
    return 1 if report["status"] == "fail" else 0


def _finish(report: Dict[str, object], args: argparse.Namespace) -> None:
    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
    if args.summary:
        write_summary_md(report, args.summary)
    emit_annotations(report)
    counts = report["counts"]
    print(
        f"[learning-guards] status={report['status']} "
        f"blocks={counts['blocks']} warnings={counts['warnings']} "
        f"frontend_changed={report['frontend_changed']}"
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print(f"::error::[learning-guards] infra failure — fail-closed: {exc}")
        sys.exit(1)
