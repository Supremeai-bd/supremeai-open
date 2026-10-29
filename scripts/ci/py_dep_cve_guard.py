#!/usr/bin/env python3
"""py_dep_cve_guard.py — Python dependency CVE ratchet gate (#1969, radar R37).

Mission (issue #1969, scout radar lane R37):
    The #1950 doctrine says every adjacent security surface has a machine
    gate. Its own coverage map enumerated image CVEs (Trivy, #1735), Python
    SOURCE SAST (bandit, #1829), workflows (zizmor, #1776), import contracts
    (import-linter, #1791), secrets (gitleaks), license SSOT (#1796), JS deps
    (#1913) — and omitted exactly one plane: the Python dependency manifests
    that `pip install -r` consumes at image-build time. `.github/workflows/`
    has zero pip-audit/safety wiring; the in-tree consumers
    (scripts/ops/security/auto_vulnerability_scanner.py, sentinel_agent.py,
    dependency_manager_agent.py) are designed-but-never-fed (#1913 pattern).
    This guard closes that plane with the PyPA-blessed primitive: pip-audit
    (Apache-2.0, zero-credential, bare-runner requirements mode — no Docker,
    no admin lane, no env build).

Behavior contract (the #1796/#1829/#1913 shrink-only ratchet):

    1. Discovers every tracked `requirements*.txt` manifest in the tree
       (deterministic sorted walk; node_modules/.git/venv/build trees
       skipped) and runs `pip-audit -r <manifest> --format json` per file.
       pip-audit resolves range pins against PyPI itself — the guard never
       reimplements a resolver (alternative 1 in #1969, rejected).
    1b. Poetry runtime plane (#2101, radar R49): every tracked
       `pyproject.toml` with a `[tool.poetry.dependencies]` main group is
       ALSO on the surface — that plane is what `scripts/ci/run_tests.sh`
       actually executes against (`poetry run ruff/mypy/pytest`), while the
       requirements fragments the guard previously saw are 2-line test
       stubs with zero consumers. Poetry constraints are synthesized to
       pip specifier form (caret/tilde expanded per poetry's OWN
       documented semantics — caret bumps the leftmost NON-ZERO component,
       which differs from npm's caret) and handed to the same pip-audit
       requirements mode, so the resolver stays pip-audit's, never ours.
       The main group only is the deploy surface (mirrors the npm guard's
       dev:true skip); dev/custom groups, optional extras, and local/vcs
       sources are skipped WITH NOTES, never guessed. A PEP-621 pyproject
       without a poetry section is off-plane (skipped with a note).
       Malformed TOML on the poetry plane is fail-closed (the #1913
       unreadable-lockfile analog).
    2. Aggregates findings to
       "<manifest>:<name>@<version>" -> sorted advisory-id set, where the id
       set is the union of the advisory's primary id and its aliases
       (PYSEC/GHSA/CVE). Folding aliases makes the ratchet immune to
       pip-audit's primary-id selection flipping across versions (a flip
       keeps the union identical -> no false drift; a genuinely new advisory
       adds a new id -> drift fires). Duplicate advisory entries within one
       dependency (observed live: the same PYSEC id emitted twice) are
       deduplicated.
    3. Compares against scripts/ci/py_dep_cve_baseline.json:
         - a pair absent from the baseline, or an id inside a baselined
           pair that the baseline does not list, is DRIFT (fail-close);
         - ids at or below the baseline are compliant (fewer ids is an
           improvement — shrink the baseline entry in the same change; the
           file may only ever shrink).
    4. Routing (#1969 escalation contract): a NEW advisory id on any pin
       fails CI the day it appears; the fix for a pinned/range pin is a
       MAINTAINER bump decision — this guard reports findings and NEVER
       edits requirements files. The landing floor carries the live audit's
       finding (pytest 8.4.2 in core/client/supreme-node — PYSEC-2026-1845 /
       GHSA-6w46-j5rx-g56g / CVE-2025-71176, fix 9.0.3 requires raising the
       `<9.0` ceiling: maintainer lane), NOT the scout's assumed empty floor
       — the scout audited 6 of 10 manifests and assumed the rest identical;
       the full live sweep proved supreme-node carries 1 unique advisory.
       An empty floor would have landed a red CI and a fabricated verdict.
    5. Honest degradation (#1760 pattern): pip-audit absent, or any
       pip-audit run failing (network unreachable, unparseable output) =>
       skip with evidence (exit 0, note emitted) — it never fabricates a
       PASS. A manifest that exists but cannot be READ is a surface change
       and fail-closes (the #1913 unreadable-lockfile analog).
    6. Inline-install blindspot visibility (--dockerfile-scan, #2064 R43
       option D — the agent-safe lane): CLI `pip install` sites inside
       tracked Dockerfiles are structurally invisible to the manifest-plane
       ratchet (worst live case: gateway/Dockerfile's `|| fallback` installs
       unpinned packages and exits 0, so the build can never fail on a
       manifest error — the guard audits the manifest while the branch that
       actually runs on its failure is unaudited). This mode parses every
       tracked Dockerfile for pip-install occurrences, classifies each spec
       (pinned / unpinned / direct-ref / dynamic / local) and each site
       (manifest-backed / inline-pinned / inline-mixed / inline-unpinned),
       flags the gate-defeat shape, and prints a date-stamped report. It is
       REPORT-ONLY by contract: never blocking (always exit 0), never edits
       a Dockerfile (the #2042 agent never-do stands), never feeds the
       baseline (the floor may only shrink), and never scans .github/**.

Never-do (issue #1969): no auto bumps; no requirements edits; the baseline
may never grow; no scanning .github/**; no safety CLI (commercial DB breaks
zero-credential guard-time discipline); no trivy fs blur of the image-plane
vs source-plane boundary (#1735); no secret values involved (advisory ids
and package coordinates only).

Usage:
    python scripts/ci/py_dep_cve_guard.py --check            # roster mode
    python scripts/ci/py_dep_cve_guard.py --files a b        # pre-push mode
    python scripts/ci/py_dep_cve_guard.py --baseline         # regenerate floor
    python scripts/ci/py_dep_cve_guard.py --json             # machine report
    python scripts/ci/py_dep_cve_guard.py --self-test        # hermetic
    python scripts/ci/py_dep_cve_guard.py --dockerfile-scan  # blindspot report (R43)

Exit codes: 0 = pass / known-floor / honest skip / report-only scan ·
1 = new drift · 2 = usage error.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess  # nosec B404 — the guard runs pip-audit and git via list-argv only (#2081 audit)
import sys
import tempfile
import tomllib
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_TAG = "[py-dep-cve-guard]"
BASELINE_PATH = Path("scripts/ci/py_dep_cve_baseline.json")
MANIFEST_SURFACE = (
    "requirements*.txt (any tracked depth) + pyproject.toml "
    "[tool.poetry.dependencies] main group (any tracked depth)"
)

EXIT_PASS = 0
EXIT_DRIFT = 1
EXIT_USAGE = 2

PIP_AUDIT_BIN = "pip-audit"
PIP_AUDIT_TIMEOUT = 300  # seconds per manifest (cold PyPI resolution included)

# --- inline-install blindspot plane (#2064 R43 option D, report-only) ---
DOCKERFILE_SURFACE = "tracked Dockerfiles (Dockerfile, Dockerfile.*, *.Dockerfile)"
_PIP_INSTALL_RE = re.compile(r"\bpip3?\s+install\b")
# pip flags whose NEXT token is a value (target/path), not a package spec:
_PIP_VALUE_FLAGS = frozenset({
    "-r", "--requirement", "-e", "--editable", "-c", "--constraint",
    "-t", "--target", "-f", "--find-links", "-i", "--index-url",
    "--extra-index-url", "--prefix", "--src", "--root", "--platform",
    "--implementation", "--python-version", "--abi", "--proxy",
    "--trusted-host", "--timeout", "--retries", "--exists-action",
})
_PIP_NOVALUE_FLAGS_PREFIXES = ("--no-", "--upgrade", "-q", "--quiet", "-v",
                               "--verbose", "--disable-pip", "--isolated",
                               "--no-cache", "--only-binary", "--no-build")


def is_dockerfile_name(fn: str) -> bool:
    return fn == "Dockerfile" or fn.startswith("Dockerfile.") or fn.endswith(".Dockerfile")
SKIP_DIRS = frozenset(
    {".git", "node_modules", ".venv", "venv", "env", "dist", "build",
     "archives", ".pytest_cache", "__pycache__", ".tox", "site-packages"}
)


def _evidence(msg: str) -> None:
    print(f"{GUARD_TAG} {msg}")


def discover_manifests(repo_root: Path) -> list[str]:
    """Sorted repo-relative paths of every tracked requirements manifest.

    Deterministic walk of the working tree; SKIP_DIRS prunes vendored and
    virtual-environment trees so only first-party manifests are audited.
    """
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(repo_root, topdown=True):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in filenames:
            if fn.startswith("requirements") and fn.endswith(".txt"):
                found.append((Path(dirpath) / fn).relative_to(repo_root).as_posix())
    return sorted(found)


# --- poetry runtime plane (#2101, radar R49) -------------------------------

POETRY_SKIP_KEYS = frozenset({"python"})
_LOCAL_VCS_KEYS = ("path", "git", "url", "file")
_EXACT_VERSION_RE = re.compile(r"^v?\d+(?:\.\d+)*(?:(?:[ab]|rc|\.dev)\d+)?$")
_OPEN_SPEC_RE = re.compile(r"^(?:>=|<=|!=|>|<)\s*v?\d")


def discover_py_surface(repo_root: Path) -> list[str]:
    """Sorted repo-relative paths of the full Python audit surface:
    every tracked requirements*.txt PLUS every tracked pyproject.toml
    (poetry-plane membership is decided at audit time, so a PEP-621-only
    pyproject gets an honest skip note instead of silent divergence
    between the discovery and audit surfaces)."""
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(repo_root, topdown=True):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in filenames:
            is_req = fn.startswith("requirements") and fn.endswith(".txt")
            if is_req or fn == "pyproject.toml":
                found.append((Path(dirpath) / fn).relative_to(repo_root).as_posix())
    return sorted(found)


def _poetry_caret_upper(version: str) -> str:
    """Poetry caret upper bound: bump the leftmost NON-ZERO component.

    Poetry's own documented semantics (NOT npm's): ^12.3.0 -> <13.0.0,
    ^0.65b0 -> <0.66.0 (major is zero -> the MINOR is the bump slot),
    ^0.0.3 -> <0.0.4. When every SPECIFIED component is zero, the LAST
    specified component is the bump slot: ^0 -> <1.0.0, ^0.0 -> <0.1.0,
    ^0.0.0 -> <0.0.1. Returns "" for an unparseable version.
    """
    m = re.match(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", version)
    if not m:
        return ""
    major = int(m.group(1))
    minor = int(m.group(2)) if m.group(2) is not None else None
    patch = int(m.group(3)) if m.group(3) is not None else None
    if major > 0:
        return f"{major + 1}.0.0"
    if minor is not None and minor > 0:
        return f"0.{minor + 1}.0"
    if patch is not None and patch > 0:
        return f"0.0.{patch + 1}"
    if patch is not None:  # ^0.0.0
        return "0.0.1"
    if minor is not None:  # ^0.0
        return "0.1.0"
    return "1.0.0"  # ^0


def poetry_constraint_to_pip(name: str, constraint: str) -> tuple[str | None, str | None]:
    """One poetry constraint -> one pip specifier (or a skip reason).

    Caret/tilde expand per poetry's documented semantics; exact pins become
    ==; single comparison operators and comma composites pass through (pip
    is a superset for the forms this repo uses). `*` and anything
    unrecognised return a skip reason — the synthesizer never guesses.
    """
    c = constraint.strip()
    if c in ("", "*"):
        return None, "wildcard-any"
    if c.startswith("^"):
        hi = _poetry_caret_upper(c[1:])
        if not hi:
            return None, f"unparseable:{c}"
        return f"{name}>={c[1:]},<{hi}", None
    if c.startswith("~="):
        return f"{name}{c}", None  # PEP 440 compatible-release is pip-native
    if c.startswith("~"):
        m = re.match(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", c[1:])
        if not m:
            return None, f"unparseable:{c}"
        if m.group(3) is not None:
            hi = f"{m.group(1)}.{int(m.group(2)) + 1}.0"
        else:
            hi = f"{int(m.group(1)) + 1}.0"
        return f"{name}>={c[1:]},<{hi}", None
    if _EXACT_VERSION_RE.match(c):
        return f"{name}=={c}", None
    if _OPEN_SPEC_RE.match(c) or "," in c:
        # comma composites are AND in both ecosystems — pass through verbatim
        return f"{name}{c}", None
    return None, f"unrecognised:{c}"


def synthesize_poetry_requirements(pyproject: Path) -> tuple[str, list[str], dict]:
    """[tool.poetry.dependencies] main group -> pip requirements text.

    Returns (text, skip_notes, stats). The python key is excluded; dev and
    custom poetry groups are out of scope (deploy-surface doctrine, the
    npm guard's dev:true analog) and recorded in stats; local/vcs sources,
    optional extras, wildcard and dict-without-version constraints are
    skipped with notes — never guessed. Malformed TOML raises
    tomllib.TOMLDecodeError; evaluate() fail-closes on it.
    """
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    poetry = (data.get("tool", {}) or {}).get("poetry", {}) or {}
    deps = poetry.get("dependencies", {}) or {}
    specs: list[str] = []
    skips: list[str] = []
    stats = {
        "main_keys": len(deps),
        "python_key_excluded": 0,
        "dict_form": 0,
        "groups_out_of_scope": sorted((poetry.get("group", {}) or {}).keys()),
    }
    for name, con in sorted(deps.items()):
        if name in POETRY_SKIP_KEYS:
            stats["python_key_excluded"] += 1
            continue
        pip_name = name
        if isinstance(con, dict):
            stats["dict_form"] += 1
            extras = con.get("extras")
            if isinstance(extras, list) and extras:
                pip_name = f"{name}[{','.join(str(e) for e in extras)}]"
            if con.get("optional"):
                skips.append(f"{name}: optional extra (not on the default install path)")
                continue
            local = [k for k in _LOCAL_VCS_KEYS if k in con]
            if local:
                skips.append(
                    f"{name}: {'/'.join(local)} source — unresolvable offline, "
                    "maintainer lane to pin or manifest it"
                )
                continue
            if "version" not in con:
                skips.append(f"{name}: dict without version ({','.join(sorted(con))})")
                continue
            con = con["version"]
            if not isinstance(con, str):
                skips.append(f"{name}: non-string version ({con!r})")
                continue
        spec, why = poetry_constraint_to_pip(pip_name, str(con))
        if spec:
            specs.append(spec)
        elif why:
            skips.append(f"{name}: {why}")
    return "\n".join(specs) + ("\n" if specs else ""), skips, stats


def synth_poetry_plane(rel: str, repo_root: Path) -> tuple[Path | None, list[str]]:
    """pyproject.toml -> synthesized requirements temp file (caller unlinks),
    or (None, skips) when nothing is pip-synthesizable. Malformed TOML
    raises tomllib.TOMLDecodeError — the caller fail-closes."""
    text, skips, _stats = synthesize_poetry_requirements(repo_root / rel)
    if not text.strip():
        return None, skips
    fh = tempfile.NamedTemporaryFile(
        "w", suffix="-poetry-synth.txt", delete=False, encoding="utf-8"
    )
    with fh:
        fh.write(text)
    return Path(fh.name), skips


def parse_pip_audit_json(doc: dict) -> dict[str, list[str]]:
    """pip-audit --format json document -> "name@version" -> sorted id union.

    The document shape is {"dependencies": [{"name", "version", "vulns":
    [{"id", "aliases", ...}]}], "fixes": [...]}. Ids are the union of the
    primary id and aliases (primary-flip immunity); duplicates — pip-audit
    emitted the same PYSEC entry twice live — collapse in the set.
    """
    deps = doc.get("dependencies")
    if not isinstance(deps, list):
        raise ValueError("pip-audit JSON malformed: 'dependencies' must be a list")
    found: dict[str, list[str]] = {}
    for dep in deps:
        if not isinstance(dep, dict):
            raise ValueError("pip-audit JSON malformed: dependency must be an object")
        name, version = dep.get("name"), dep.get("version")
        if not name or not version:
            raise ValueError("pip-audit JSON malformed: dependency missing name/version")
        ids: set[str] = set()
        for vuln in dep.get("vulns") or []:
            if not isinstance(vuln, dict):
                raise ValueError("pip-audit JSON malformed: vuln must be an object")
            if vuln.get("id"):
                ids.add(str(vuln["id"]))
            for alias in vuln.get("aliases") or []:
                if alias:
                    ids.add(str(alias))
        if ids:
            key = f"{name}@{version}"
            prev = found.get(key, [])
            found[key] = sorted(set(prev) | ids)
    return found


def audit_manifest(manifest: Path) -> dict[str, list[str]]:
    """One pip-audit requirements-mode run -> "name@version" -> id union.

    Exit 0 (clean) and 1 (vulns found) are both valid outcomes parsed from
    stdout; anything else raises RuntimeError with the stderr tail — the
    honest-skip decision lives in evaluate().
    """
    proc = subprocess.run(  # nosec B603 — list-argv, no shell, pinned PIP_AUDIT_BIN invocation (#2081 audit)
        [PIP_AUDIT_BIN, "--progress-spinner", "off", "-r", str(manifest),
         "--format", "json"],
        capture_output=True, text=True, timeout=PIP_AUDIT_TIMEOUT, check=False,
    )
    if proc.returncode not in (0, 1):
        tail = (proc.stderr or proc.stdout or "")[-400:].strip()
        raise RuntimeError(
            f"pip-audit failed on {manifest} (exit {proc.returncode}): {tail}"
        )
    try:
        doc = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        tail = (proc.stderr or "")[-400:].strip()
        raise RuntimeError(
            f"pip-audit emitted unparseable JSON for {manifest}: {exc}; "
            f"stderr tail: {tail}"
        ) from exc
    return parse_pip_audit_json(doc)


def compare(
    current: dict[str, list[str]], baseline: dict[str, list[str]]
) -> tuple[list[dict], list[dict]]:
    """Ratchet compare keyed "<manifest>:name@version" -> sorted id union.

    drift: new pair, or an id inside a known pair that the baseline omits.
    improvements: baselined ids/pairs that disappeared (shrink-the-floor
    hints — the baseline entry may be removed in the same change).
    """
    drift: list[dict] = []
    improvements: list[dict] = []
    for pair in sorted(current):
        cur = list(current[pair])
        base = baseline.get(pair, [])
        new_ids = [i for i in cur if i not in base]
        if not base:
            drift.append({"pair": pair, "ids": new_ids, "kind": "new-pair"})
        elif new_ids:
            drift.append({"pair": pair, "ids": new_ids, "kind": "new-id"})
    for pair in sorted(baseline):
        gone = [i for i in baseline[pair] if i not in current.get(pair, [])]
        if gone or pair not in current:
            improvements.append(
                {"pair": pair, "resolved_ids": gone,
                 "remaining": current.get(pair, [])}
            )
    return drift, improvements


def load_baseline(repo_root: Path) -> tuple[dict[str, list[str]], dict]:
    """Load the versioned baseline. Unreadable baseline is fail-closed drift."""
    path = repo_root / BASELINE_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"baseline missing: {BASELINE_PATH} (run --baseline to create)"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    findings = data.get("findings")
    if not isinstance(findings, dict):
        raise ValueError("baseline malformed: 'findings' must be an object")
    clean: dict[str, list[str]] = {}
    for pair, ids in findings.items():
        if not isinstance(pair, str) or not isinstance(ids, list):
            raise ValueError("baseline malformed: findings must be pair -> id list")
        clean[pair] = [str(i) for i in ids]
    return clean, data.get("meta", {})


def build_baseline_report(repo_root: Path) -> dict:
    """Live surface + pip-audit sweep -> the versioned baseline document."""
    manifests = discover_py_surface(repo_root)
    findings: dict[str, list[str]] = {}
    pairs_total = 0
    for rel in manifests:
        path = repo_root / rel
        tmp: Path | None = None
        if path.name == "pyproject.toml":
            # admin flow: malformed poetry TOML fails the baseline loudly
            tmp, skips = synth_poetry_plane(rel, repo_root)
            if tmp is None:
                continue
        try:
            per_manifest = audit_manifest(tmp if tmp is not None else path)
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
        pairs_total += len(per_manifest)
        for key, ids in per_manifest.items():
            findings[f"{rel}:{key}"] = ids
    return {
        "meta": {
            "issue": "1969 (initial floor), 2101 (poetry-plane widening)",
            "tool": (
                "pip-audit (PyPA, Apache-2.0) requirements mode --format json; "
                "PyPI Advisory DB / OSV SSOT, zero-credential"
            ),
            "scanner_version": "2.10.1",
            "surface": MANIFEST_SURFACE,
            "dated": "2026-10-28",
            "totals": {
                "manifests_scanned": len(manifests),
                "resolved_vulnerable_deps": pairs_total,
                "vulnerable_pairs": len(findings),
                "vuln_ids": sum(len(v) for v in findings.values()),
            },
            "doctrine": (
                "shrink-only ratchet: entries and ids may only be REMOVED (in the "
                "same change that resolves them — a maintainer pin/range bump or an "
                "upstream fix absorbed by a floor reset). A new pair or a new "
                "advisory id is drift; the baseline may never grow. Escalation "
                "routing: findings on a pinned/range pin are maintainer bump "
                "decisions — this guard never edits requirements files."
            ),
        },
        "findings": findings,
    }


def evaluate(
    repo_root: Path, files: list[str] | None = None
) -> tuple[int, list[dict], list[dict], list[str]]:
    """Single decision tree. Returns (exit, drift, improvements, notes)."""
    notes: list[str] = []
    manifests = discover_py_surface(repo_root)
    poetry_on_surface = sum(1 for m in manifests if m.endswith("pyproject.toml"))
    notes.append(
        f"surface: {len(manifests)} tracked manifest(s) "
        f"({len(manifests) - poetry_on_surface} requirements + {poetry_on_surface} pyproject)"
    )

    if files is not None:
        touched = sorted(set(files) & set(manifests))
        if not touched:
            notes.append(
                "changed set does not touch the Python dependency surface "
                f"({MANIFEST_SURFACE}) — nothing to check"
            )
            return EXIT_PASS, [], [], notes
        manifests = touched
        notes.append(f"--files mode: checking {', '.join(touched)}")

    if shutil.which(PIP_AUDIT_BIN) is None:
        notes.append(
            "pip-audit not installed — skipped with evidence (honest "
            "degradation, #1760 pattern; pip install pip-audit to enable)"
        )
        return EXIT_PASS, [], [], notes

    try:
        baseline, _meta = load_baseline(repo_root)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return (
            EXIT_DRIFT,
            [{"pair": str(BASELINE_PATH), "ids": ["BASELINE"], "kind": "baseline",
              "detail": str(exc)}],
            [],
            notes,
        )

    current: dict[str, list[str]] = {}
    for rel in manifests:
        path = repo_root / rel
        try:
            path.read_text(encoding="utf-8")
        except Exception as exc:  # unreadable surface is fail-closed, never a skip
            return (
                EXIT_DRIFT,
                [{"pair": rel, "ids": ["MANIFEST"], "kind": "unreadable-manifest",
                  "detail": str(exc)}],
                [],
                notes,
            )
        tmp: Path | None = None
        audit_label = rel
        if path.name == "pyproject.toml":
            try:
                tmp, synth_skips = synth_poetry_plane(rel, repo_root)
            except tomllib.TOMLDecodeError as exc:
                # malformed poetry manifest = surface defect, fail-closed
                # (the #1913 unreadable-lockfile analog)
                return (
                    EXIT_DRIFT,
                    [{"pair": rel, "ids": ["POETRY-MANIFEST"],
                      "kind": "malformed-poetry-manifest", "detail": str(exc)}],
                    [],
                    notes,
                )
            if tmp is None:
                notes.append(
                    f"{rel}: nothing pip-synthesizable from "
                    f"[tool.poetry.dependencies] — skipped "
                    f"({'; '.join(synth_skips) or 'empty main group'})"
                )
                continue
            for s in synth_skips:
                notes.append(f"{rel}: skip | {s}")
            audit_label = f"{rel} (synthesized from [tool.poetry.dependencies])"
            notes.append(f"{rel}: audited as {audit_label}")
        try:
            try:
                per_manifest = audit_manifest(tmp if tmp is not None else path)
            except (RuntimeError, ValueError, subprocess.SubprocessError) as exc:
                notes.append(
                    f"pip-audit unreachable/failed on {audit_label} — skipped with "
                    f"evidence (honest degradation, #1760 pattern; never a "
                    f"fabricated PASS): {exc}"
                )
                return EXIT_PASS, [], [], notes
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
        for key, ids in per_manifest.items():
            current[f"{rel}:{key}"] = ids

    notes.append(
        f"pip-audit: {len(current)} vulnerable pair(s), "
        f"{sum(len(i) for i in current.values())} advisory id(s) on the current tree"
    )
    drift, improvements = compare(current, baseline)
    if drift:
        return EXIT_DRIFT, drift, improvements, notes
    return EXIT_PASS, [], improvements, notes


def render(drift: list[dict], improvements: list[dict], notes: list[str]) -> None:
    for note in notes:
        _evidence(f"note | {note}")
    for d in drift:
        _evidence(
            f"NEW-DRIFT (fail-closed) | {d['pair']} | {d['kind']} | ids: {', '.join(d['ids'])}"
        )
    for imp in improvements:
        _evidence(
            f"IMPROVED (remove the baseline entry in the same change) | {imp['pair']} | "
            f"resolved: {', '.join(imp['resolved_ids']) or '(pair gone)'} | "
            f"remaining: {', '.join(imp['remaining']) or 'none'}"
        )
    if not drift and not improvements:
        _evidence("ratchet clean: no new advisory ids on the Python dependency plane")


def _classify_spec(spec: str) -> str:
    """One pip-install spec -> pinned | unpinned | direct | dynamic | local."""
    s = spec.strip().strip('"').strip("'")
    if s in (".", "./") or s.startswith("./") or s.startswith("file://"):
        return "local"
    if "${" in s:
        return "dynamic"
    if "://" in s or s.startswith("git+"):
        return "direct"
    if "==" in s:
        return "pinned"
    return "unpinned"


def _logical_shell_lines(text: str) -> list[tuple[int, str]]:
    """Dockerfile content -> [(start_line, logical_line)] with backslash
    continuations joined (RUN blocks span lines) and full-line comments and
    blank lines dropped (comments must never parse as install sites)."""
    out: list[tuple[int, str]] = []
    buf = ""
    start = 0
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\n")
        if buf:
            buf += " " + line.strip()
            if buf.endswith("\\"):
                buf = buf[:-1]
                continue
        else:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            start = i
            if stripped.endswith("\\"):
                buf = stripped[:-1]
                continue
            buf = stripped
        out.append((start, buf))
        buf = ""
    return out


def _split_shell_segments(logical: str) -> list[str]:
    """Split on shell control operators, keeping track of || positions so the
    gate-defeat shape (a pip install in the survive-on-failure branch) can be
    flagged. Full-line comments were already dropped; inline ` #` tails are
    stripped (URL fragments contain no space-delimited ' #')."""
    if " #" in logical:
        logical = logical.split(" #", 1)[0]
    import re as _re
    parts = _re.split(r"&&|\|\||;|\|", logical)
    return [p for p in (x.strip() for x in parts) if p]


def parse_pip_install_sites(text: str) -> list[dict]:
    """Dockerfile content -> ordered pip-install occurrence records.

    Each record: {line, occurrence, class, specs:[{spec,class}],
    manifest_refs, gate_defeat_shape}. Deterministic; comment lines and
    pip-flag noise are excluded; `-r`/`--requirement` targets are recorded
    as manifest_refs (that plane is already ratcheted) and `-e` targets as
    local installs.
    """
    sites: list[dict] = []
    for start, logical in _logical_shell_lines(text):
        segments = _split_shell_segments(logical)
        if not any(_PIP_INSTALL_RE.search(s) for s in segments):
            continue
        gate_defeat = ("||" in logical
                       and any("unpinned" == sp["class"]
                               for s in segments
                               for sp in _segment_specs(s)["specs"]))
        occurrence = 0
        for seg in segments:
            m = _PIP_INSTALL_RE.search(seg)
            if not m:
                continue
            occurrence += 1
            parsed = _segment_specs(seg)
            sites.append({
                "line": start,
                "occurrence": occurrence,
                "class": parsed["class"],
                "specs": parsed["specs"],
                "manifest_refs": parsed["manifest_refs"],
                "gate_defeat_shape": gate_defeat,
            })
    return sites


def _segment_specs(seg: str) -> dict:
    m = _PIP_INSTALL_RE.search(seg)
    tokens = seg[m.end():].split()
    specs: list[dict] = []
    manifest_refs: list[str] = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            if tok.lower().endswith(".txt") or tok.lower().endswith(".in"):
                manifest_refs.append(tok)
            skip_next = False
            continue
        low = tok.lower()
        if low in ("-r", "--requirement"):
            manifest_refs.append("(next-token)")
            skip_next = True
            continue
        if low in ("-e", "--editable"):
            specs.append({"spec": tok, "class": "local"})
            skip_next = True
            continue
        if tok.startswith("-"):
            if low in _PIP_VALUE_FLAGS:
                skip_next = True
            continue
        specs.append({"spec": tok, "class": _classify_spec(tok)})
    _risky = ("unpinned", "direct", "dynamic")
    has_pinned = any(sp["class"] == "pinned" for sp in specs)
    has_risky = any(sp["class"] in _risky for sp in specs)
    if manifest_refs and not specs:
        site_class = "manifest-backed"
    elif has_pinned and has_risky:
        site_class = "inline-mixed"
    elif has_risky:
        site_class = "inline-unpinned"
    elif specs:
        site_class = "inline-pinned"
    else:
        site_class = "unparsed"
    return {"class": site_class, "specs": specs, "manifest_refs": manifest_refs}


def scan_inline_pip_installs(repo_root: Path) -> dict:
    """Report-only blindspot scan across tracked Dockerfiles (#2064 option D).

    Non-blocking by contract: anomalies (unreadable Dockerfile) are reported
    as records, never raised; the caller always exits 0. Deterministic
    sorted walk, same SKIP_DIRS pruning as the manifest plane.
    """
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(repo_root, topdown=True):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in filenames:
            if is_dockerfile_name(fn):
                files.append((Path(dirpath) / fn).relative_to(repo_root).as_posix())
    files.sort()
    sites: list[dict] = []
    anomalies: list[dict] = []
    for rel in files:
        try:
            text = (repo_root / rel).read_text(encoding="utf-8")
        except Exception as exc:  # report-only: an anomaly is a record, not a raise
            anomalies.append({"file": rel, "kind": "unreadable", "detail": str(exc)[:160]})
            continue
        for parsed in parse_pip_install_sites(text):
            sites.append({"file": rel, **parsed})
    blindspot_sites = [s for s in sites if s["class"] in ("inline-unpinned", "inline-mixed")]
    spec_counts: dict[str, int] = {}
    for s in sites:
        for sp in s["specs"]:
            spec_counts[sp["class"]] = spec_counts.get(sp["class"], 0) + 1
    return {
        "report": (
            "inline pip-install blindspot scan (report-only, non-blocking; "
            "#2064 R43 option D) — CLI installs inside Dockerfiles are "
            "structurally invisible to the manifest-plane ratchet"
        ),
        "dated": "2026-10-28",
        "surface": DOCKERFILE_SURFACE,
        "dockerfiles_scanned": len(files),
        "dockerfiles_with_sites": len({s['file'] for s in sites}),
        "sites": sites,
        "anomalies": anomalies,
        "summary": {
            "pip_install_sites": len(sites),
            "manifest_backed_sites": sum(1 for s in sites if s["class"] == "manifest-backed"),
            "inline_unpinned_sites": sum(1 for s in sites if s["class"] == "inline-unpinned"),
            "inline_mixed_sites": sum(1 for s in sites if s["class"] == "inline-mixed"),
            "gate_defeat_sites": sum(1 for s in sites if s.get("gate_defeat_shape")),
            "spec_classes": dict(sorted(spec_counts.items())),
        },
    }


def render_dockerfile_report(doc: dict) -> None:
    _evidence(f"dockerfile-scan (report-only, non-blocking) | {doc['dated']} | "
              f"{doc['dockerfiles_scanned']} dockerfile(s) scanned, "
              f"{doc['summary']['pip_install_sites']} pip-install site(s)")
    s = doc["summary"]
    _evidence(
        f"summary | manifest-backed: {s['manifest_backed_sites']} · "
        f"inline-unpinned (blindspot): {s['inline_unpinned_sites']} · "
        f"gate-defeat shape: {s['gate_defeat_sites']} · "
        f"spec classes: {json.dumps(s['spec_classes'])}"
    )
    for site in doc["sites"]:
        gd = (" | GATE-DEFEAT: build survives manifest-install failure via ||"
              if site.get("gate_defeat_shape") else "")
        specs = ", ".join(
            f"{sp['spec']}[{sp['class']}]" for sp in site["specs"]) or "-"
        if site["class"] in ("inline-unpinned", "inline-mixed"):
            _evidence(
                f"BLINDSPOT | {site['file']}:{site['line']} (occ {site['occurrence']}) | "
                f"{site['class']}{gd} | specs: {specs}"
            )
        elif site["class"] == "manifest-backed":
            refs = ", ".join(site["manifest_refs"]) or "-"
            _evidence(f"ok | {site['file']}:{site['line']} | manifest-backed ({refs}) "
                      f"— already inside the ratchet plane{gd}")
        else:
            _evidence(f"ok | {site['file']}:{site['line']} | {site['class']}{gd} "
                      f"| specs: {specs}")
    for a in doc["anomalies"]:
        _evidence(f"ANOMALY (report-only) | {a['file']} | {a['kind']} | {a['detail']}")
    if not any(s["class"] in ("inline-unpinned", "inline-mixed") for s in doc["sites"]):
        _evidence("no inline-unpinned blindspot on the scanned dockerfile plane")


def self_test() -> bool:
    """Hermetic guard-the-guard (offline; fixtures, monkeypatched audits)."""
    print("[self-test] Running Python dependency CVE guard tests...")
    import py_dep_cve_guard as g

    # 1. The load-bearing pip-audit JSON parser: id-union folding, dedup of
    #    duplicate advisory entries (observed live), empty-vuln skip.
    doc = {
        "dependencies": [
            {"name": "fastapi", "version": "0.162.0", "vulns": []},
            {"name": "pytest", "version": "8.4.2", "vulns": [
                {"id": "PYSEC-2026-1845", "aliases": [
                    "GHSA-6w46-j5rx-g56g", "CVE-2025-71176"]},
                {"id": "PYSEC-2026-1845", "aliases": [
                    "GHSA-6w46-j5rx-g56g", "CVE-2025-71176"]},
            ]},
        ],
        "fixes": [],
    }
    found = g.parse_pip_audit_json(doc)
    if not (found == {
        "pytest@8.4.2": ["CVE-2025-71176", "GHSA-6w46-j5rx-g56g", "PYSEC-2026-1845"]
    }):
        raise AssertionError(found)
    print("  PASS | parser: alias union folded, duplicate advisories deduped")
    try:
        g.parse_pip_audit_json({"dependencies": [{"name": "x"}]})
        raise SystemExit("malformed dependency must raise")
    except ValueError:
        pass
    print("  PASS | parser: missing version fails loudly (never silent)")
    # 2. Ratchet compare: equal/new-pair/new-id/shrunk/disappeared.
    baseline = {"m:a@1.0.0": ["PYSEC-1"], "m:b@2.0.0": ["PYSEC-2", "PYSEC-3"]}
    drift, improvements = g.compare(dict(baseline), baseline)
    if not (not drift and not improvements):
        raise AssertionError()
    drift, _ = g.compare({"m:c@3.0.0": ["PYSEC-9"]}, baseline)
    if not (drift and drift[0]["kind"] == "new-pair"):
        raise AssertionError()
    drift, _ = g.compare({"m:a@1.0.0": ["PYSEC-1", "PYSEC-new"]}, baseline)
    if not (drift and drift[0]["kind"] == "new-id" and drift[0]["ids"] == ["PYSEC-new"]):
        raise AssertionError()
    _, improvements = g.compare({"m:a@1.0.0": ["PYSEC-1"]}, baseline)
    if not (improvements and improvements[0]["pair"] == "m:b@2.0.0"):
        raise AssertionError()
    print("  PASS | ratchet: equal/new-pair/new-id/shrunk/disappeared semantics")
    # 3. Decision tree on a sandbox repo: drift exit 1, honest skip when
    #    pip-audit is missing or failing, unreadable manifest fail-closed.
    with tempfile.TemporaryDirectory(prefix="py-dep-cve-guard-") as td:
        root = Path(td)
        (root / "scripts" / "ci").mkdir(parents=True)
        (root / "gateway" / "services" / "x").mkdir(parents=True)
        (root / "gateway" / "requirements.txt").write_text(
            "fastapi>=0.110\n", encoding="utf-8"
        )
        (root / "gateway" / "services" / "x" / "requirements.txt").write_text(
            "pytest>=7.4,<9.0\n", encoding="utf-8"
        )
        (root / BASELINE_PATH).write_text(
            json.dumps({
                "meta": {"issue": 1969},
                "findings": {
                    "gateway/services/x/requirements.txt:pytest@8.4.2": [
                        "PYSEC-old", "PYSEC-gone"
                    ]
                },
            }),
            encoding="utf-8",
        )
        saved_audit = g.audit_manifest
        # Hermetic invariant: the sandbox cases below assert SPECIFIC routing
        # outcomes, but evaluate() short-circuits on its pip-audit presence
        # check (shutil.which) BEFORE reaching the patched audit_manifest. On
        # hosts without pip-audit installed every decision-tree case came back
        # EXIT_PASS "not installed" and the whole --self-test went red (live:
        # 4 decision-tree cases + the pytest self-test probe on a bare venv),
        # while runners that happen to carry pip-audit stayed green — an
        # environment-coupled suite, not a hermetic one. Force the binary
        # "present" for the entire block; the dedicated "missing" case
        # re-patches which->None inside and restores to THIS patch.
        real_which = g.shutil.which
        g.shutil.which = (
            lambda name, _bin=PIP_AUDIT_BIN, _real=real_which: (
                "/usr/local/bin/" + _bin if name == _bin else _real(name)
            )
        )
        try:
            g.audit_manifest = lambda p: {
                "pytest@8.4.2": ["PYSEC-old"],
                "fastapi@0.162.0": ["PYSEC-fresh"],
            }
            code, drift, _imp, _notes = g.evaluate(root)
            if not (code == EXIT_DRIFT and drift[0]["pair"] == (
                "gateway/requirements.txt:fastapi@0.162.0"
            )):
                raise AssertionError((code, drift))
            print("  PASS | decision tree: new advisory pair fail-closes")
            g.audit_manifest = lambda p: (
                {"pytest@8.4.2": ["PYSEC-old"]} if "services" in str(p) else {}
            )
            code, drift, imp, _ = g.evaluate(root)
            if not (code == EXIT_PASS and drift == [] and imp):
                raise AssertionError((code, imp))
            if not (imp[0]["resolved_ids"] == ["PYSEC-gone"]):
                raise AssertionError()
            print("  PASS | shrink path: resolved id routes to baseline-shrink hint")

            def _boom(p):
                raise RuntimeError("PyPI unreachable (simulated)")

            g.audit_manifest = _boom
            code, drift, _imp, notes = g.evaluate(root)
            if not (code == EXIT_PASS and not drift):
                raise AssertionError()
            if not (any("pip-audit unreachable" in n for n in notes)):
                raise AssertionError(notes)
            print("  PASS | pip-audit failure -> skip with evidence, never a fake PASS")

            real_which = g.shutil.which
            g.shutil.which = lambda name: None
            try:
                code, drift, _imp, notes = g.evaluate(root)
                if not (code == EXIT_PASS):
                    raise AssertionError()
                if not (any("pip-audit not installed" in n for n in notes)):
                    raise AssertionError(notes)
            finally:
                g.shutil.which = real_which
            print("  PASS | pip-audit missing -> skip with evidence")
            g.audit_manifest = lambda p: (
                {"pytest@8.4.2": ["PYSEC-old"]} if "services" in str(p) else {}
            )
            (root / "gateway" / "requirements.txt").chmod(0)
            try:
                code, drift, _imp, _ = g.evaluate(root)
                if not (code == EXIT_DRIFT and drift[0]["kind"] == "unreadable-manifest"):
                    raise AssertionError()
            finally:
                (root / "gateway" / "requirements.txt").chmod(0o644)
            print("  PASS | unreadable manifest -> fail-closed")
            (root / BASELINE_PATH).write_text("{not json", encoding="utf-8")
            code, drift, _imp, _ = g.evaluate(root)
            if not (code == EXIT_DRIFT and drift[0]["ids"] == ["BASELINE"]):
                raise AssertionError()
            print("  PASS | malformed baseline -> fail-closed")
            g.audit_manifest = lambda p: (
                {"pytest@8.4.2": ["PYSEC-old"]} if "services" in str(p) else {}
            )
            (root / BASELINE_PATH).write_text(
                json.dumps({
                    "meta": {"issue": 1969},
                    "findings": {
                        "gateway/services/x/requirements.txt:pytest@8.4.2": ["PYSEC-old"]
                    },
                }),
                encoding="utf-8",
            )
            code, drift, _imp, notes = g.evaluate(root, files=["README.md"])
            if not (code == EXIT_PASS and any("nothing to check" in n for n in notes)):
                raise AssertionError()
            code, drift, _imp, _ = g.evaluate(
                root, files=["gateway/services/x/requirements.txt"]
            )
            if not (code == EXIT_PASS and not drift):
                raise AssertionError()
            print("  PASS | --files mode: off-surface skip, on-surface full check")
        finally:
            g.shutil.which = real_which
            g.audit_manifest = saved_audit
    # 6. Spec classification: pinned / extras-pinned / unpinned / direct /
    #    dynamic / local — the vocabulary the report uses (#2064).
    if not (g._classify_spec("torch==2.4.1") == "pinned"):
        raise AssertionError()
    if not (g._classify_spec('"uvicorn[standard]==0.34.0"') == "pinned"):
        raise AssertionError()
    if not (g._classify_spec("wheel") == "unpinned"):
        raise AssertionError()
    if not (g._classify_spec("nats-py") == "unpinned"):
        raise AssertionError()
    if not (g._classify_spec("git+https://x/y.git") == "direct"):
        raise AssertionError()
    if not (g._classify_spec("https://x/y.whl") == "direct"):
        raise AssertionError()
    if not (g._classify_spec("${PIP_EXTRAS}") == "dynamic"):
        raise AssertionError()
    if not (g._classify_spec("./local") == "local"):
        raise AssertionError()
    print("  PASS | spec classification: pinned/unpinned/direct/dynamic/local")

    # 7. Parser: gateway `||` fallback (gate-defeat shape + 5 unpinned),
    #    swarm continuation line (2 occurrences), ci partial pin (mixed),
    #    quoted+extras pinned line stays inline-pinned, comment lines and
    #    -r manifests never count as blindspots.
    gw = g.parse_pip_install_sites(
        "FROM python:3.11-slim\n"
        "# RUN pip install commented-out must not parse\n"
        "RUN pip install --no-cache-dir -r requirements.txt || "
        "pip install --no-cache-dir fastapi uvicorn httpx pydantic pyyaml\n"
    )
    if not (len(gw) == 2):
        raise AssertionError(gw)
    if not (gw[0]["class"] == "manifest-backed" and gw[0]["manifest_refs"]):
        raise AssertionError()
    if not (gw[0]["gate_defeat_shape"] is True):
        raise AssertionError("first branch sits on a || line")
    if not (gw[1]["class"] == "inline-unpinned"):
        raise AssertionError()
    if not ([sp["spec"] for sp in gw[1]["specs"]] == [
        "fastapi", "uvicorn", "httpx", "pydantic", "pyyaml"]):
        raise AssertionError()
    if not (gw[1]["gate_defeat_shape"] is True):
        raise AssertionError()
    swarm = g.parse_pip_install_sites(
        "RUN pip install --upgrade pip && \\\n"
        "    pip install --no-cache-dir nats-py pydantic litellm langchain\n"
    )
    if not (len(swarm) == 2):
        raise AssertionError(swarm)
    if not (all(s["class"] == "inline-unpinned" for s in swarm)):
        raise AssertionError()
    ci = g.parse_pip_install_sites(
        "RUN pip install --no-cache-dir setuptools==68.0.0 wheel\n"
    )
    if not (len(ci) == 1 and ci[0]["class"] == "inline-mixed"):
        raise AssertionError(ci)
    if not ([sp["class"] for sp in ci[0]["specs"]] == ["pinned", "unpinned"]):
        raise AssertionError()
    eco = g.parse_pip_install_sites(
        'RUN pip install --no-cache-dir fastapi==0.115.6 '
        '"uvicorn[standard]==0.34.0"\n'
    )
    if not (len(eco) == 1 and eco[0]["class"] == "inline-pinned"):
        raise AssertionError(eco)
    print("  PASS | parser: gate-defeat || fallback, continuations, mixed pin, "
          "quoted extras pin, comment skip")

    # 8. Report-only semantics on a sandbox tree: exit contract lives in
    #    main() (always EXIT_PASS); the scan itself must surface every
    #    blindspot deterministically and treat an unreadable Dockerfile as a
    #    recorded anomaly, never an exception.
    with tempfile.TemporaryDirectory(prefix="pydep-df-") as td:
        root = Path(td)
        (root / "gateway").mkdir()
        (root / "gateway" / "Dockerfile").write_text(
            "RUN pip install -r requirements.txt || pip install fastapi uvicorn\n",
            encoding="utf-8",
        )
        (root / "core" / "docker").mkdir(parents=True)
        (root / "core" / "docker" / "swarm-worker.Dockerfile").write_text(
            "RUN pip install --upgrade pip && \\\n"
            "    pip install --no-cache-dir nats-py pydantic litellm langchain\n",
            encoding="utf-8",
        )
        (root / "node_modules" / "x").mkdir(parents=True)
        (root / "node_modules" / "x" / "Dockerfile").write_text(
            "RUN pip install nodejunk\n", encoding="utf-8")
        doc = g.scan_inline_pip_installs(root)
        if not (doc["dockerfiles_scanned"] == 2):
            raise AssertionError(doc["dockerfiles_scanned"])
        if not (doc["summary"]["pip_install_sites"] == 4):
            raise AssertionError(doc["summary"])
        if not (doc["summary"]["manifest_backed_sites"] == 1):
            raise AssertionError()
        if not (doc["summary"]["inline_unpinned_sites"] == 3):
            raise AssertionError()
        if not (doc["summary"]["gate_defeat_sites"] == 2):
            raise AssertionError()
        blind = {(s["file"], s["line"]) for s in doc["sites"]
                 if s["class"] == "inline-unpinned"}
        if not (blind == {("gateway/Dockerfile", 1),
                         ("core/docker/swarm-worker.Dockerfile", 1)}):
            raise AssertionError(blind)
        (root / "gateway" / "Dockerfile").chmod(0)
        try:
            doc2 = g.scan_inline_pip_installs(root)
            if not (doc2["anomalies"] and doc2["anomalies"][0]["kind"] == "unreadable"):
                raise AssertionError()
            if not (doc2["dockerfiles_scanned"] == 2):
                raise AssertionError()
        finally:
            (root / "gateway" / "Dockerfile").chmod(0o644)
    print("  PASS | report-only scan: SKIP_DIRS pruned, blindspots surfaced, "
          "unreadable -> recorded anomaly (never raises)")

    # 10. Poetry-plane synthesis (#2101): caret semantics, tilde, exact,
    #     dict-form handling, python-key exclusion, skip classes, discovery.
    if g._poetry_caret_upper("12.3.0") != "13.0.0":
        raise AssertionError("caret ^12.3.0 must bump major")
    if g._poetry_caret_upper("0.65b0") != "0.66.0":
        raise AssertionError("caret ^0.65b0 must bump minor (poetry, NOT npm)")
    if g._poetry_caret_upper("0.0.3") != "0.0.4":
        raise AssertionError("caret ^0.0.3 must bump patch")
    if g._poetry_caret_upper("0") != "1.0.0":
        raise AssertionError("caret ^0 -> <1.0")
    if g._poetry_caret_upper("garbage!!") != "":
        raise AssertionError("unparseable caret version must return empty")
    spec, why = g.poetry_constraint_to_pip("infisical-python", "2.3.5")
    if not (spec == "infisical-python==2.3.5" and why is None):
        raise AssertionError((spec, why))
    spec, why = g.poetry_constraint_to_pip("click", ">=8.3.3")
    if not (spec == "click>=8.3.3" and why is None):
        raise AssertionError((spec, why))
    spec, why = g.poetry_constraint_to_pip("x", "~1.2.3")
    if not (spec == "x>=1.2.3,<1.3.0" and why is None):
        raise AssertionError((spec, why))
    spec, why = g.poetry_constraint_to_pip("x", "~1.2")
    if not (spec == "x>=1.2,<2.0" and why is None):
        raise AssertionError((spec, why))
    spec, why = g.poetry_constraint_to_pip("x", "*")
    if not (spec is None and why == "wildcard-any"):
        raise AssertionError((spec, why))
    print("  PASS | poetry synthesis: caret/tilde/exact/open/wildcard semantics")

    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        proj = Path(td) / "pyproject.toml"
        proj.write_text(
            '[tool.poetry.dependencies]\n'
            'python = "^3.11"\n'
            'pillow = "^12.3.0"\n'
            'fastapi = "^0.136.0"\n'
            'infisical-python = "2.3.5"\n'
            'redis = { version = "^5.2.1", extras = ["redis"] }\n'
            'litellm = { path = "../local" }\n'
            'otel-extra = { version = "^1.0.0", optional = true }\n'
            'loose = "*"\n'
            '\n'
            '[tool.poetry.group.dev.dependencies]\n'
            'pytest = "^8.0.0"\n',
            encoding="utf-8",
        )
        text, skips, stats = g.synthesize_poetry_requirements(proj)
        want = {
            "fastapi>=0.136.0,<0.137.0",
            "infisical-python==2.3.5",
            "pillow>=12.3.0,<13.0.0",
            "redis[redis]>=5.2.1,<6.0.0",
        }
        got = {ln for ln in text.splitlines() if ln.strip()}
        if got != want:
            raise AssertionError(f"synthesis mismatch: {sorted(got)} != {sorted(want)}")
        joined = "; ".join(skips)
        for marker in ("litellm: path", "otel-extra: optional", "loose: wildcard-any"):
            if marker not in joined:
                raise AssertionError(f"missing skip note: {marker} in {joined}")
        if stats["python_key_excluded"] != 1 or stats["dict_form"] != 3:
            raise AssertionError(stats)
        if stats["groups_out_of_scope"] != ["dev"]:
            raise AssertionError(stats)
        # PEP-621-only pyproject -> honest empty plane, no specs
        pep621 = Path(td) / "other" / "pyproject.toml"
        pep621.parent.mkdir()
        pep621.write_text('[project]\nname = "x"\ndependencies = ["requests"]\n', encoding="utf-8")
        text2, skips2, stats2 = g.synthesize_poetry_requirements(pep621)
        if text2.strip() != "":
            raise AssertionError(f"PEP-621 pyproject must synthesize empty: {text2!r}")
    print("  PASS | poetry synthesis: fixture text, extras, skips, groups, PEP-621 off-plane")

    with _tf.TemporaryDirectory() as td:
        root = Path(td)
        (root / "core").mkdir()
        (root / "core" / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\npython = "^3.11"\nrequests = "^2.28.0"\n',
            encoding="utf-8",
        )
        (root / "core" / "requirements.txt").write_text("requests>=2.28.0\n", encoding="utf-8")
        surface = g.discover_py_surface(root)
        if surface != ["core/pyproject.toml", "core/requirements.txt"]:
            raise AssertionError(surface)
        tmp, skips3 = g.synth_poetry_plane("core/pyproject.toml", root)
        try:
            if tmp is None or "requests>=2.28.0,<3.0.0" not in tmp.read_text(encoding="utf-8"):
                raise AssertionError(tmp)
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
        (root / "core" / "broken.toml").unlink(missing_ok=True)
        bad = root / "core" / "pyproject.toml"
        good = bad.read_text(encoding="utf-8")
        bad.write_text("[tool.poetry.dependencies\npython = oops", encoding="utf-8")
        try:
            g.synth_poetry_plane("core/pyproject.toml", root)
            raise SystemExit("malformed TOML must raise")
        except tomllib.TOMLDecodeError:
            pass
        bad.write_text(good, encoding="utf-8")
    print("  PASS | poetry plane: discovery includes pyproject, synth tmp file, "
          "malformed TOML raises (fail-closed path)")

    # 9. Live wiring: roster + pre-push carry the guard (when run inside the repo).
    roster = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"
    if roster.is_file():
        if not ("scripts/ci/py_dep_cve_guard.py" in roster.read_text(encoding="utf-8")):
            raise AssertionError("guard missing from run_all_guards roster")
    hook = REPO_ROOT / ".githooks" / "pre-push"
    if hook.is_file():
        if not ("py_dep_cve_guard.py" in hook.read_text(encoding="utf-8")):
            raise AssertionError("guard missing from pre-push hook")
    print("  PASS | roster + pre-push wiring present (when run inside the repo)")
    # 5. Baseline provenance sanity (when run inside the repo).
    bl_path = REPO_ROOT / BASELINE_PATH
    if bl_path.is_file():
        meta = json.loads(bl_path.read_text(encoding="utf-8")).get("meta", {})
        if not ("pip-audit" in str(meta.get("tool", ""))):
            raise AssertionError("baseline must record the pip-audit SSOT")
        if not (meta.get("doctrine", "").startswith("shrink-only")):
            raise AssertionError()
    print("[self-test] Python dependency CVE guard self-tests PASSED (12 test cases)!")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Python dependency CVE ratchet gate (#1969, pip-audit)"
    )
    parser.add_argument(
        "--check", action="store_true",
        help="roster mode: full-surface ratchet compare",
    )
    parser.add_argument(
        "--files", nargs="*",
        help="pre-push mode: full check only when the changed set touches a requirements manifest",
    )
    parser.add_argument(
        "--baseline", action="store_true",
        help="regenerate the versioned baseline at current head (admin)",
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable report on stdout"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="hermetic self-test suite (offline)"
    )
    parser.add_argument(
        "--dockerfile-scan", action="store_true",
        help="report-only inline pip-install blindspot scan across tracked "
             "Dockerfiles (non-blocking; #2064 R43 option D)",
    )
    args = parser.parse_args()

    if args.self_test:
        return EXIT_PASS if self_test() else EXIT_DRIFT

    if args.baseline:
        doc = build_baseline_report(REPO_ROOT)
        out = REPO_ROOT / BASELINE_PATH
        out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        _evidence(
            f"baseline regenerated at {BASELINE_PATH} | "
            f"{doc['meta']['totals']['manifests_scanned']} manifest(s) | "
            f"{doc['meta']['totals']['vulnerable_pairs']} vulnerable pair(s) / "
            f"{doc['meta']['totals']['vuln_ids']} id(s) — review the diff; "
            f"the file may only shrink; pin fixes are maintainer decisions"
        )
        return EXIT_PASS

    if args.dockerfile_scan:
        doc = scan_inline_pip_installs(REPO_ROOT)
        note = (
            "report-only by contract (#2064 option D): never blocking, never "
            "edits a Dockerfile, never feeds the baseline — pin/manifest "
            "remediation (requirements.fallback.txt, worker manifest, pin "
            "completions) is the maintainer lane per the #2042 never-do"
        )
        doc["contract_note"] = note
        if args.json:
            print(json.dumps(doc, indent=2, ensure_ascii=False))
        else:
            render_dockerfile_report(doc)
            _evidence(note)
        return EXIT_PASS

    code, drift, improvements, notes = evaluate(
        REPO_ROOT, files=args.files if args.files is not None else None
    )
    if args.json:
        print(
            json.dumps(
                {
                    "guard": "py_dep_cve_guard",
                    "mode": "files" if args.files is not None else "check",
                    "exit": code,
                    "scanner": PIP_AUDIT_BIN,
                    "surface": MANIFEST_SURFACE,
                    "new_drift": drift,
                    "improvements_shrink_hints": improvements,
                    "notes": notes,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        render(drift, improvements, notes)
    if code == EXIT_DRIFT:
        print(
            f"{GUARD_TAG} ❌ NEW Python dependency advisory drift: resolve it "
            f"(pin/range bumps are maintainer decisions) or re-floor the baseline "
            f"deliberately — the baseline may never grow.",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
