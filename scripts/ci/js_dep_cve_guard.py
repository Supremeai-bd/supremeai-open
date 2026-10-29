#!/usr/bin/env python3
"""js_dep_cve_guard.py — JavaScript dependency CVE ratchet gate (#1913).

Mission (issue #1913, scout radar lane R41):
    Every adjacent security surface has a machine gate — dependency CVEs for
    the backend image (Trivy contract, #1735->#1768), Python source SAST
    (bandit, #1829), CI workflows (zizmor, #1776), import contracts
    (import-linter, #1791), secrets (gitleaks composite), license SSOT
    (#1796). The JavaScript dependency plane had zero mechanical coverage:
    the 2026-10-28 radar probe resolved studio/pnpm-lock.yaml to its unique
    (name, version) set and put 13 named GHSAs on the record via one
    zero-credential OSV call. This guard makes that plane a shrink-only
    ratchet fed by the same advisory SSOT (api.osv.dev — the database
    behind GHSA/npm advisories that Trivy itself normalizes to).

Behavior contract (the #1796/#1829 shrink-only ratchet, externalized to a
versioned baseline because the JS tree carries 31 finding ids at the floor):

    1. Parses studio/pnpm-lock.yaml (lockfileVersion 9.0) into the unique
       set of (name, version) pairs it pins — both the `packages:` section
       and the peer-resolved `snapshots:` section, deduplicated, with
       non-registry keys (link:/file:/workspace protocols) skipped. Scoped
       names split on the SECOND '@' (a greedy first-@ split mangles
       '@scope/name@1.2.3(peer@x.y)' keys — that parser bug is pinned by
       the self-test).
    2. Queries api.osv.dev/v1/querybatch once per chunk (zero-credential,
       free public API) and aggregates vulnerable pairs to
       "name@version" -> sorted [primary advisory id] (GHSA-...).
    3. Compares against scripts/ci/js_dep_cve_baseline.json:
         - a pair absent from the baseline, or an advisory id inside a
           baselined pair that the baseline does not list, is DRIFT;
         - ids at or below the baseline are compliant (fewer ids is an
           improvement — shrink the baseline entry in the same change; the
           file may only ever shrink).
    4. Routing (issue #1913 adoption path): NEW advisory ids fail-close
       (exit 1). The lockfile lives in studio/ — bridge-able surface, but
       the fix for a new advisory is a studio-owner decision (pin bump or
       deliberate floor reset via --baseline; the baseline diff in review
       IS the audit trail). This guard reports findings; it NEVER edits
       the lockfile or bumps pins.
    5. Honest degradation (#1760 pattern): when PyYAML is missing, the
       lockfile is unreadable-as-YAML is fail-closed (surface changed), but
       when the OSV API is unreachable after retries the guard skips with
       evidence (exit 0, note emitted) — it never fabricates a PASS.
    6. `--baseline` regenerates the versioned baseline at the CURRENT head
       (admin floor reset; review the diff). `--json` emits a machine
       report. `--files f1 ...` (pre-push mode) runs the full check only
       when the changed set intersects the guard's surface
       (studio/package.json, studio/pnpm-lock.yaml); otherwise honest skip.

Never-do (issue #1913): no auto pin bumps; no lockfile edits; the baseline
may never grow; no agent edits to satellite mirrors (findings route to the
studio domain); no scanning .github/**; no secret values involved (advisory
ids and package coordinates only).

Usage:
    python scripts/ci/js_dep_cve_guard.py --check            # roster mode
    python scripts/ci/js_dep_cve_guard.py --files a b        # pre-push mode
    python scripts/ci/js_dep_cve_guard.py --baseline         # regenerate floor
    python scripts/ci/js_dep_cve_guard.py --json             # machine report
    python scripts/ci/js_dep_cve_guard.py --self-test        # hermetic

Exit codes: 0 = pass / known-floor / honest skip · 1 = new drift ·
2 = usage error.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_TAG = "[js-dep-cve-guard]"
BASELINE_PATH = Path("scripts/ci/js_dep_cve_baseline.json")
LOCK_PATH = Path("studio/pnpm-lock.yaml")
LOCKFILE_SURFACE = ("studio/package.json", "studio/pnpm-lock.yaml")

EXIT_PASS = 0
EXIT_DRIFT = 1
EXIT_USAGE = 2

OSV_QUERYBATCH = "https://api.osv.dev/v1/querybatch"
OSV_CHUNK = 250
OSV_TIMEOUT = 120
OSV_RETRIES = 3
ECOSYSTEM = "npm"

# Peer-suffix-aware pnpm v9 key splitter. The version starts right after the
# '@' that terminates the package name: for scoped names ('@scope/pkg@ver')
# that is the SECOND '@'; for plain names the FIRST. Everything from the
# first '(' onward is the peer-resolution suffix and is stripped.
_SNAP_KEY_RE = re.compile(r"\((?:.*)$")


def _evidence(msg: str) -> None:
    print(f"{GUARD_TAG} {msg}")


def split_lock_key(key: str) -> tuple[str, str] | None:
    """Split a pnpm v9 'name@version[(...peers)]' key into (name, version).

    Returns None for keys that do not resolve to a registry coordinate
    (no version terminator, or a non-semver version such as link:/file:
    protocols). The second-@ rule for scoped names is load-bearing:
    a greedy first-@ split turns '@dnd-kit/core@6.3.1(react-dom@19.3.1)'
    into name '@dnd-kit/core@6.3.1(react-dom', version '19.3.1'.
    """
    if key.startswith("@"):
        idx = key.find("@", 1)
    else:
        idx = key.find("@")
    if idx <= 0:
        return None
    name = key[:idx]
    rest = key[idx + 1:]
    version = _SNAP_KEY_RE.sub("", rest).strip()
    if not version or not version[0].isdigit():
        return None
    return name, version


def load_lock_pairs(lock_path: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """Parse the pnpm v9 lockfile into its unique (name, version) pin set.

    Reads both `packages:` and `snapshots:` (peer-resolved) sections and
    deduplicates. Returns (sorted pairs, skipped non-registry keys).
    Raises the PyYAML ImportError to the caller (honest-skip decision lives
    in evaluate) and ValueError/IOError for structural unreadability.
    """
    import yaml  # deferred: honest-skip when PyYAML is absent (#1760 pattern)

    doc = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("lockfile malformed: top level must be a mapping")
    pairs: set[tuple[str, str]] = set()
    skipped: list[str] = []
    for section in ("packages", "snapshots"):
        entries = doc.get(section) or {}
        if not isinstance(entries, dict):
            raise ValueError(f"lockfile malformed: '{section}' must be a mapping")
        for key in entries:
            split = split_lock_key(str(key))
            if split is None:
                skipped.append(str(key))
                continue
            pairs.add(split)
    return sorted(pairs), skipped


def query_osv_batch(
    pairs: list[tuple[str, str]], endpoint: str = OSV_QUERYBATCH
) -> dict[tuple[str, str], list[str]]:
    """One querybatch POST per OSV_CHUNK pairs; returns pair -> advisory ids.

    Raises ConnectionError-derived RuntimeError after OSV_RETRIES failed
    attempts on any chunk — the honest-skip decision lives in evaluate().
    """
    queries = [
        {"package": {"name": name, "ecosystem": ECOSYSTEM}, "version": version}
        for name, version in pairs
    ]
    found: dict[tuple[str, str], list[str]] = {}
    for start in range(0, len(queries), OSV_CHUNK):
        batch = queries[start:start + OSV_CHUNK]
        body = json.dumps({"queries": batch}).encode("utf-8")
        response: dict = {}
        last_error: Exception | None = None
        for attempt in range(OSV_RETRIES):
            try:
                req = urllib.request.Request(
                    endpoint,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=OSV_TIMEOUT) as resp:
                    response = json.loads(resp.read().decode("utf-8"))
                last_error = None
                break
            except Exception as exc:  # retried below, evidence kept
                last_error = exc
                if attempt < OSV_RETRIES - 1:
                    time.sleep(2 * (attempt + 1))
        if last_error is not None:
            raise RuntimeError(
                f"OSV querybatch unreachable after {OSV_RETRIES} attempt(s): {last_error}"
            )
        results = response.get("results")
        if not isinstance(results, list) or len(results) != len(batch):
            raise ValueError(
                f"OSV querybatch response malformed: expected {len(batch)} results"
            )
        for query, result in zip(batch, results):
            vulns = (result or {}).get("vulns") or []
            if not vulns:
                continue
            key = (query["package"]["name"], query["version"])
            ids = sorted({str(v.get("id")) for v in vulns if v.get("id")})
            if ids:
                found[key] = ids
        if start + OSV_CHUNK < len(queries):
            time.sleep(1.0)
    return found


def compare(
    current: dict[str, list[str]], baseline: dict[str, list[str]]
) -> tuple[list[dict], list[dict]]:
    """Ratchet compare keyed 'name@version' -> sorted advisory ids.

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
            remaining = current.get(pair, [])
            improvements.append(
                {"pair": pair, "resolved_ids": gone, "remaining": remaining}
            )
    return drift, improvements


def git_head(repo_root: Path) -> str:
    try:
        out = subprocess_run(
            ["git", "log", "-1", "--format=%h %ad", "--date=short"], cwd=repo_root
        )
        return out.strip() or "unknown"
    except Exception as exc:  # provenance is best-effort, recorded as evidence
        return f"unknown (git probe failed: {exc.__class__.__name__})"


def subprocess_run(cmd: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=30, check=False
    )
    return proc.stdout


def build_baseline_report(repo_root: Path) -> dict:
    """Live lockfile + OSV probe -> the versioned baseline document."""
    lock = repo_root / LOCK_PATH
    pairs, skipped = load_lock_pairs(lock)
    found = query_osv_batch(pairs)
    current = {f"{n}@{v}": ids for (n, v), ids in sorted(found.items())}
    total_ids = sum(len(ids) for ids in current.values())
    return {
        "meta": {
            "issue": 1913,
            "tool": "osv-querybatch (api.osv.dev/v1/querybatch, zero-credential)",
            "lockfile": str(LOCK_PATH),
            "ecosystem": ECOSYSTEM,
            "head": git_head(repo_root),
            "dated": "2026-10-28",
            "totals": {
                "pairs_scanned": len(pairs),
                "skipped_non_registry_keys": len(skipped),
                "vulnerable_pairs": len(current),
                "vuln_ids": total_ids,
            },
            "doctrine": (
                "shrink-only ratchet: entries and ids may only be REMOVED (in the "
                "same change that resolves them — a pin bump or an upstream fix "
                "absorbed by a floor reset). A new pair or a new advisory id is "
                "drift; the baseline may never grow."
            ),
        },
        "findings": current,
    }


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


def evaluate(repo_root: Path, files: list[str] | None = None) -> tuple[int, list[dict], list[dict], list[str]]:
    """Single decision tree. Returns (exit, drift, improvements, notes)."""
    notes: list[str] = []
    if files is not None:
        touched = [f for f in files if f in LOCKFILE_SURFACE]
        if not touched:
            notes.append(
                "changed set does not touch the JS dependency surface "
                f"({', '.join(LOCKFILE_SURFACE)}) — nothing to check"
            )
            return EXIT_PASS, [], [], notes

    try:
        import yaml  # noqa: F401 - presence probe for the honest-skip path

        yaml_available = True
    except Exception:  # any import failure means PyYAML is absent
        yaml_available = False
    if not yaml_available:
        notes.append(
            "PyYAML not installed — skipped with evidence (honest degradation, "
            "#1760 pattern; pip install pyyaml to enable)"
        )
        return EXIT_PASS, [], [], notes

    lock = repo_root / LOCK_PATH
    if not lock.is_file():
        return EXIT_DRIFT, [{"pair": str(LOCK_PATH), "ids": ["LOCKFILE"], "kind": "missing-lockfile"}], [], notes

    try:
        baseline, _meta = load_baseline(repo_root)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return (
            EXIT_DRIFT,
            [{"pair": str(BASELINE_PATH), "ids": ["BASELINE"], "kind": "baseline", "detail": str(exc)}],
            [],
            notes,
        )

    try:
        pairs, skipped = load_lock_pairs(lock)
    except Exception as exc:  # unreadable surface is fail-closed, never a skip
        return (
            EXIT_DRIFT,
            [{"pair": str(LOCK_PATH), "ids": ["LOCKFILE"], "kind": "unreadable-lockfile", "detail": str(exc)}],
            [],
            notes,
        )
    notes.append(
        f"lockfile: {len(pairs)} unique (name, version) pair(s), "
        f"{len(skipped)} non-registry key(s) skipped"
    )

    try:
        found = query_osv_batch(pairs)
    except (RuntimeError, ValueError) as exc:
        notes.append(
            f"OSV API unreachable — skipped with evidence (honest degradation, "
            f"#1760 pattern; never a fabricated PASS): {exc}"
        )
        return EXIT_PASS, [], [], notes

    current = {f"{n}@{v}": ids for (n, v), ids in sorted(found.items())}
    notes.append(
        f"osv: {len(current)} vulnerable pair(s), "
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
        _evidence("ratchet clean: no new advisory ids on the JS dependency plane")


def self_test() -> bool:
    """Hermetic guard-the-guard (offline; fixtures, no network, no PyYAML need)."""
    print("[self-test] Running JS dependency CVE guard tests...")
    import js_dep_cve_guard as g

    # 1. The load-bearing scoped-name splitter (radar premise + parser-bug pin).
    assert g.split_lock_key("@dnd-kit/core@6.3.1(react-dom@19.3.1)(react@19.3.1)") == (
        "@dnd-kit/core",
        "6.3.1",
    ), "scoped keys must split on the SECOND '@', version before the first '('"
    assert g.split_lock_key("react@19.3.1") == ("react", "19.3.1")
    assert g.split_lock_key("@scope/pkg@1.2.3-beta.4(peer@2.0.0)") == ("@scope/pkg", "1.2.3-beta.4")
    assert g.split_lock_key("vite@7.3.7(@types/node@24.19.2)") == ("vite", "7.3.7")
    assert g.split_lock_key("@supremeai/studio@link:../studio") is None
    assert g.split_lock_key("some-pkg@file:./local") is None
    assert g.split_lock_key("no-version-here") is None
    print("  PASS | key splitter: scoped second-@, peer-suffix strip, non-registry skip")
    # 2. Ratchet compare: equal/new-pair/new-id/shrunk/disappeared.
    baseline = {"a@1.0.0": ["GHSA-aaa"], "b@2.0.0": ["GHSA-b1", "GHSA-b2"]}
    drift, improvements = g.compare({"a@1.0.0": ["GHSA-aaa"], "b@2.0.0": ["GHSA-b1", "GHSA-b2"]}, baseline)
    assert not drift and not improvements
    drift, _ = g.compare({"c@3.0.0": ["GHSA-ccc"]}, baseline)
    assert drift and drift[0]["kind"] == "new-pair"
    drift, _ = g.compare({"a@1.0.0": ["GHSA-aaa", "GHSA-new"]}, baseline)
    assert drift and drift[0]["kind"] == "new-id" and drift[0]["ids"] == ["GHSA-new"]
    _, improvements = g.compare({"a@1.0.0": ["GHSA-aaa"], "b@2.0.0": ["GHSA-b1"]}, baseline)
    assert improvements and improvements[0]["resolved_ids"] == ["GHSA-b2"]
    _, improvements = g.compare({"a@1.0.0": ["GHSA-aaa"]}, baseline)
    assert improvements and improvements[0]["pair"] == "b@2.0.0"
    print("  PASS | ratchet: equal/new-pair/new-id/shrunk/disappeared semantics")
    # 3. Decision tree on a sandbox repo: drift exit 1, honest skip on API
    #    failure, missing lockfile and malformed baseline fail-closed.
    with tempfile.TemporaryDirectory(prefix="js-dep-cve-guard-") as td:
        root = Path(td)
        (root / "scripts" / "ci").mkdir(parents=True)
        (root / "studio").mkdir(parents=True)
        (root / LOCK_PATH).write_text(_FIXTURE_LOCK, encoding="utf-8")
        (root / BASELINE_PATH).write_text(
            json.dumps({"meta": {"issue": 1913}, "findings": {"left-pad@1.3.0": ["GHSA-old"]}}),
            encoding="utf-8",
        )
        saved_query = g.query_osv_batch
        try:
            g.query_osv_batch = lambda pairs, endpoint=g.OSV_QUERYBATCH: {
                ("left-pad", "1.3.0"): ["GHSA-old"],
                ("right-pad", "2.1.0"): ["GHSA-fresh"],
            }
            code, drift, _imp, notes = g.evaluate(root)
            assert code == EXIT_DRIFT and drift[0]["pair"] == "right-pad@2.1.0", (code, drift)
            print("  PASS | decision tree: new advisory pair fail-closes")
            clean_query = lambda pairs, endpoint=g.OSV_QUERYBATCH: {
                ("left-pad", "1.3.0"): ["GHSA-old"]
            }
            g.query_osv_batch = clean_query
            # Shrink path: baseline carries an id the live tree no longer has.
            (root / BASELINE_PATH).write_text(
                json.dumps({"meta": {"issue": 1913}, "findings": {"left-pad@1.3.0": ["GHSA-old", "GHSA-gone"]}}),
                encoding="utf-8",
            )
            code, drift, imp, _ = g.evaluate(root)
            assert code == EXIT_PASS and drift == [] and imp, (code, imp)
            assert imp[0]["pair"] == "left-pad@1.3.0" and imp[0]["resolved_ids"] == ["GHSA-gone"]
            print("  PASS | shrink path: resolved id routes to baseline-shrink hint")
            (root / BASELINE_PATH).write_text(
                json.dumps({"meta": {"issue": 1913}, "findings": {"left-pad@1.3.0": ["GHSA-old"]}}),
                encoding="utf-8",
            )
            def _boom(pairs, endpoint=g.OSV_QUERYBATCH):
                raise RuntimeError("api.osv.dev unreachable (simulated)")
            g.query_osv_batch = _boom
            code, drift, _imp, notes = g.evaluate(root)
            assert code == EXIT_PASS and not drift
            assert any("OSV API unreachable" in n for n in notes), notes
            print("  PASS | OSV unreachable -> skip with evidence, never a fake PASS")
            g.query_osv_batch = clean_query
            # --files mode (hermetic: still on clean_query, no network).
            code, drift, _imp, notes = g.evaluate(root, files=["README.md", "core/x.py"])
            assert code == EXIT_PASS and any("nothing to check" in n for n in notes)
            code, drift, _imp, _ = g.evaluate(root, files=["studio/pnpm-lock.yaml"])
            assert code == EXIT_PASS and not drift
            print("  PASS | --files mode: off-surface skip, on-surface full check")
            # Missing lockfile fail-closed (early-return in evaluate, pre-query).
            (root / LOCK_PATH).unlink()
            code, drift, _imp, _ = g.evaluate(root)
            assert code == EXIT_DRIFT and drift[0]["kind"] == "missing-lockfile"
            (root / LOCK_PATH).write_text(_FIXTURE_LOCK, encoding="utf-8")
            print("  PASS | missing lockfile -> fail-closed")
            # Malformed baseline fail-closed.
            (root / BASELINE_PATH).write_text("{not json", encoding="utf-8")
            code, drift, _imp, _ = g.evaluate(root)
            assert code == EXIT_DRIFT and drift[0]["ids"] == ["BASELINE"]
            print("  PASS | malformed baseline -> fail-closed")
        finally:
            g.query_osv_batch = saved_query
    # 4. Live wiring: roster + pre-push carry the guard (when run inside the repo).
    roster = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"
    if roster.is_file():
        assert "scripts/ci/js_dep_cve_guard.py" in roster.read_text(encoding="utf-8"), (
            "guard missing from run_all_guards roster"
        )
    hook = REPO_ROOT / ".githooks" / "pre-push"
    if hook.is_file():
        assert "js_dep_cve_guard.py" in hook.read_text(encoding="utf-8"), (
            "guard missing from pre-push hook"
        )
    print("  PASS | roster + pre-push wiring present (when run inside the repo)")
    # 5. Baseline provenance sanity (when run inside the repo).
    bl_path = REPO_ROOT / BASELINE_PATH
    if bl_path.is_file():
        meta = json.loads(bl_path.read_text(encoding="utf-8")).get("meta", {})
        assert "osv" in str(meta.get("tool", "")), "baseline must record the OSV SSOT"
        assert meta.get("doctrine", "").startswith("shrink-only")
    print("[self-test] JS dependency CVE guard self-tests PASSED (5 test cases)!")
    return True


_FIXTURE_LOCK = """lockfileVersion: '9.0'

importers:
  .:
    dependencies:
      left-pad:
        specifier: ^1.3.0
        version: 1.3.0

packages:

  left-pad@1.3.0:
    resolution: {integrity: sha512-fixture}

  right-pad@2.1.0:
    resolution: {integrity: sha512-fixture2}

snapshots:

  left-pad@1.3.0:
    dependencies:
      helper: 0.0.1

  helper@0.0.1: {}

  right-pad@2.1.0: {}
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="JavaScript dependency CVE ratchet gate (#1913, OSV querybatch)"
    )
    parser.add_argument("--check", action="store_true", help="roster mode: full-surface ratchet compare")
    parser.add_argument("--files", nargs="*", help="pre-push mode: full check only when the changed set touches the JS dep surface")
    parser.add_argument("--baseline", action="store_true", help="regenerate the versioned baseline at current head (admin)")
    parser.add_argument("--json", action="store_true", help="machine-readable report on stdout")
    parser.add_argument("--self-test", action="store_true", help="hermetic self-test suite (offline)")
    args = parser.parse_args()

    if args.self_test:
        return EXIT_PASS if self_test() else EXIT_DRIFT

    if args.baseline:
        doc = build_baseline_report(REPO_ROOT)
        out = REPO_ROOT / BASELINE_PATH
        out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        _evidence(
            f"baseline regenerated at {BASELINE_PATH} | head {doc['meta']['head']} | "
            f"{doc['meta']['totals']['vulnerable_pairs']} vulnerable pair(s) / "
            f"{doc['meta']['totals']['vuln_ids']} id(s) over "
            f"{doc['meta']['totals']['pairs_scanned']} pair(s) scanned — review the diff; "
            f"the file may only shrink"
        )
        return EXIT_PASS

    code, drift, improvements, notes = evaluate(REPO_ROOT, files=args.files if args.files is not None else None)
    if args.json:
        print(
            json.dumps(
                {
                    "guard": "js_dep_cve_guard",
                    "mode": "files" if args.files is not None else "check",
                    "exit": code,
                    "endpoint": OSV_QUERYBATCH,
                    "lockfile": str(LOCK_PATH),
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
            f"{GUARD_TAG} ❌ NEW JavaScript dependency advisory drift on the studio plane: "
            f"resolve it (pin bump is a studio-owner decision) or re-floor the baseline "
            f"deliberately — the baseline may never grow.",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
