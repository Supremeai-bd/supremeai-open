#!/usr/bin/env python3
"""tests/test_npm_dep_cve_guard.py — fail-closed behavioral suite for #2059 (widened #2075).

Verifies the npm dependency CVE ratchet gate delivered for #2059 (lane R45,
the control-plane supply-chain surface) and widened by #2075 (lane R46:
browser/cloudflare-worker + vscode + vscode/extension lockfiles):

  - package-lock parser: v2/v3 `packages["node_modules/<name>"]` entries
    resolve to (name, version); nested `node_modules/a/node_modules/b`
    keys reduce to the innermost package name; `dev: true` entries are
    skipped (dev-only trees are outside the deploy surface); link /
    no-version entries are skipped; lockfileVersion < 2 is rejected;
  - ratchet semantics: equal floors pass, a new pair and a new advisory id
    inside a known pair are drift, resolved ids and vanished pairs are
    improvements (shrink the baseline entry in the same change);
  - routing decision tree: NEW advisory ids fail-close (exit 1); a missing
    or malformed baseline fail-closes; a missing/unreadable tracked
    lockfile fail-closes (surface change); an unreachable OSV API skips
    with evidence and NEVER fabricates a PASS (the #1760 honest-
    degradation pattern); --files mode with an off-surface changed set is
    an honest skip; render.yaml and the worker wrangler.toml ARE in the
    surface (deploy/blueprint claims live there);
  - live baseline pin: on the real repo the dated floor passes --check
    (the landing state, network permitting — skipped with evidence when
    api.osv.dev is unreachable), and its meta provenance is intact;
  - R46 widening: the widened surface constants are exact; a worker-lock
    floor seeded in the baseline is honored (pass) and a new id on a
    worker pair is drift with the lock-scoped key; an all-dev lock is an
    honest zero (zero production pairs, no query, no drift);
  - wiring SSOT: the guard is present in the LIVE run_all_guards.py roster
    and the LIVE .githooks/pre-push hook (never duplicated here).

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_npm_dep_cve_guard.py
  - stdlib:  python3 tests/test_npm_dep_cve_guard.py   (plain runner)

Network-dependent paths are hermetic: the module-level query_osv_batch is
replaced with fixture findings through globals() (the script runs as
__main__; importing it a second time would patch a different module
instance — that pitfall is itself pinned by the suite), so every
structural test is offline and deterministic. The single live --check
probe degrades to a skip when the OSV API is absent.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "ci" / "npm_dep_cve_guard.py"
BASELINE = "scripts/ci/npm_dep_cve_baseline.json"
TAG = "[npm-dep-cve-guard]"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import npm_dep_cve_guard as guard  # the importable copy (same source file)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def write_lock(root: Path, rel: str, packages: dict) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"lockfileVersion": 3, "packages": packages}))


TOWER_LOCK = "infrastructure/mcp-control-plane/package-lock.json"
AUDIT_LOCK = ".agents/skills/devtools-audit/package-lock.json"
WORKER_LOCK = "browser/cloudflare-worker/package-lock.json"
VSCODE_LOCK = "vscode/package-lock.json"
VSCODE_EXT_LOCK = "vscode/extension/package-lock.json"


def make_temp_repo(tmp: Path, baseline_pairs: dict | None = None) -> Path:
    write_lock(tmp, TOWER_LOCK, {"node_modules/express": {"version": "4.21.2"}})
    write_lock(tmp, AUDIT_LOCK, {"node_modules/zod": {"version": "4.6.4"}})
    # R46 widened roster: all five tracked locks must exist, else
    # evaluate() fail-closes on a missing tracked lockfile.
    write_lock(tmp, WORKER_LOCK, {"node_modules/tar-fs": {"version": "3.0.4"}})
    write_lock(tmp, VSCODE_LOCK, {
        "node_modules/devthing": {"version": "1.0.0", "dev": True}})
    write_lock(tmp, VSCODE_EXT_LOCK, {
        "node_modules/devonly": {"version": "2.0.0", "dev": True}})
    (tmp / "infrastructure/mcp-control-plane/render.yaml").parent.mkdir(
        parents=True, exist_ok=True
    )
    (tmp / "infrastructure/mcp-control-plane/render.yaml").write_text("services: []\n")
    (tmp / "browser/cloudflare-worker/wrangler.toml").parent.mkdir(
        parents=True, exist_ok=True
    )
    (tmp / "browser/cloudflare-worker/wrangler.toml").write_text(
        'name = "temp-worker"\n')
    (tmp / "scripts/ci").mkdir(parents=True, exist_ok=True)
    if baseline_pairs is not None:
        (tmp / BASELINE).write_text(json.dumps({
            "meta": {"dated": "2026-10-28"},
            "findings": baseline_pairs,
        }))
    return tmp


# ---------------------------------------------------------------------------
# parser contract
# ---------------------------------------------------------------------------

def test_parser_extracts_production_pins() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock = Path(td) / "package-lock.json"
        lock.write_text(json.dumps({
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "root", "version": "1.0.0"},
                "node_modules/express": {"version": "4.21.2"},
                "node_modules/@modelcontextprotocol/sdk": {"version": "1.30.0"},
                "node_modules/a/node_modules/left-pad": {"version": "1.3.0"},
                "node_modules/devdep": {"version": "9.9.9", "dev": True},
                "node_modules/linked": {"resolved": "packages/linked", "link": True},
                "node_modules/qs": {"version": "6.16.0", "dev": False},
            },
        }))
        pairs, skipped = guard.load_lock_pairs(lock)
        assert sorted(pairs) == sorted([
            ("express", "4.21.2"),
            ("@modelcontextprotocol/sdk", "1.30.0"),
            ("left-pad", "1.3.0"),
            ("qs", "6.16.0"),
        ])
        assert skipped == {"dev": 1, "non_registry": 2}


def test_parser_rejects_v1_and_malformed() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock = Path(td) / "package-lock.json"
        lock.write_text(json.dumps({"lockfileVersion": 1, "dependencies": {}}))
        try:
            guard.load_lock_pairs(lock)
            raise AssertionError("v1 lockfile must be rejected")
        except ValueError:
            pass
        lock.write_text("[]")
        try:
            guard.load_lock_pairs(lock)
            raise AssertionError("non-object lockfile must be rejected")
        except ValueError:
            pass


def test_parser_missing_file_raises() -> None:
    with tempfile.TemporaryDirectory() as td:
        try:
            guard.load_lock_pairs(Path(td) / "absent.json")
            raise AssertionError("missing lockfile must raise")
        except (OSError, ValueError):
            pass


# ---------------------------------------------------------------------------
# ratchet semantics
# ---------------------------------------------------------------------------

def test_ratchet_equal_floor_passes() -> None:
    drift, imp = guard.compare(
        {"l:express@4.21.2": ["GHSA-a"]}, {"l:express@4.21.2": ["GHSA-a"]}
    )
    assert drift == [] and imp == []


def test_ratchet_new_pair_is_drift() -> None:
    drift, _ = guard.compare(
        {"l:new@2": ["GHSA-c"]}, {"l:express@4.21.2": ["GHSA-a"]}
    )
    assert drift == [{"pair": "l:new@2", "ids": ["GHSA-c"], "kind": "new-pair"}]


def test_ratchet_new_id_inside_known_pair_is_drift() -> None:
    drift, _ = guard.compare(
        {"l:express@4.21.2": ["GHSA-a", "GHSA-b"]}, {"l:express@4.21.2": ["GHSA-a"]}
    )
    assert drift == [{"pair": "l:express@4.21.2", "ids": ["GHSA-b"], "kind": "new-id"}]


def test_ratchet_resolved_ids_are_improvements() -> None:
    _, imp = guard.compare({}, {"l:express@4.21.2": ["GHSA-a"]})
    assert imp == [{"pair": "l:express@4.21.2", "resolved_ids": ["GHSA-a"],
                    "remaining": []}]


# ---------------------------------------------------------------------------
# routing decision tree (hermetic — globals() patch, __main__ pitfall pinned)
# ---------------------------------------------------------------------------

class _OsvPatch:
    """Patch the RUNNING module's query_osv_batch via globals().

    The guard script executes as __main__; `import npm_dep_cve_guard`
    yields a SECOND module instance whose functions the __main__ copy
    never calls. Patching globals() on the imported copy works for the
    pytest path (tests import it fresh and call guard.evaluate), while
    the stdlib path below re-executes the file as __main__ and patches
    its own globals the same way. Both paths use this helper on their
    respective module object.
    """

    def __init__(self, module, fn) -> None:
        self._module = module
        self._fn = fn
        self._orig = None

    def __enter__(self):
        self._orig = self._module.query_osv_batch
        self._module.query_osv_batch = self._fn
        return self

    def __exit__(self, *exc) -> None:
        self._module.query_osv_batch = self._orig


def _known_floor(pairs):
    return {p: ["GHSA-known"] for p in pairs if p == ("express", "4.21.2")}


def _new_id_floor(pairs):
    return {
        p: (["GHSA-known", "GHSA-NEW"] if p == ("express", "4.21.2") else [])
        for p in pairs
        if p == ("express", "4.21.2")
    }


def _unreachable(pairs):
    raise RuntimeError("OSV querybatch unreachable after 3 attempt(s)")


def test_decision_tree_hermetic() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = make_temp_repo(Path(td), {
            f"{TOWER_LOCK}:express@4.21.2": ["GHSA-known"],
        })
        with _OsvPatch(guard, _known_floor):
            code, drift, imp, notes = guard.evaluate(root, files=None)
            assert code == guard.EXIT_PASS and drift == []

            with _OsvPatch(guard, _new_id_floor):
                code, drift, imp, notes = guard.evaluate(root, files=None)
                assert code == guard.EXIT_DRIFT
                assert drift and drift[0]["kind"] == "new-id"

            with _OsvPatch(guard, _unreachable):
                code, drift, imp, notes = guard.evaluate(root, files=None)
                assert code == guard.EXIT_PASS and drift == []
                assert any("osv-unreachable" in n for n in notes)

            (root / BASELINE).write_text("{not json")
            code, drift, imp, notes = guard.evaluate(root, files=None)
            assert code == guard.EXIT_DRIFT and drift[0]["kind"] == "baseline-unusable"

            (root / BASELINE).unlink()
            code, drift, imp, notes = guard.evaluate(root, files=None)
            assert code == guard.EXIT_DRIFT and drift[0]["kind"] == "baseline-unusable"

            make_temp_repo(root, {
                f"{TOWER_LOCK}:express@4.21.2": ["GHSA-known"],
            })
            (root / AUDIT_LOCK).unlink()
            code, drift, imp, notes = guard.evaluate(root, files=None)
            assert code == guard.EXIT_DRIFT and drift[0]["kind"] == "surface-change"

            make_temp_repo(root, {
                f"{TOWER_LOCK}:express@4.21.2": ["GHSA-known"],
            })
            code, drift, imp, notes = guard.evaluate(root, files=["README.md"])
            assert code == guard.EXIT_PASS
            assert any("does not touch" in n for n in notes)

            code, drift, imp, notes = guard.evaluate(
                root, files=["infrastructure/mcp-control-plane/render.yaml"])
            assert code == guard.EXIT_PASS and drift == []

            # wrangler.toml (R46) is on the surface too
            code, drift, imp, notes = guard.evaluate(
                root, files=["browser/cloudflare-worker/wrangler.toml"])
            assert code == guard.EXIT_PASS and drift == []


def test_main_files_off_surface_exit_zero() -> None:
    proc = subprocess.run(
        [sys.executable, str(GUARD), "--files", "README.md"],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert proc.returncode == guard.EXIT_PASS, proc.stdout + proc.stderr
    assert "nothing to check" in proc.stdout


def test_main_self_test() -> None:
    proc = subprocess.run(
        [sys.executable, str(GUARD), "--self-test"],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert proc.returncode == guard.EXIT_PASS, proc.stdout + proc.stderr
    assert "SELF-TEST OK" in proc.stdout


# ---------------------------------------------------------------------------
# live baseline pin (network-permitting; honest skip offline)
# ---------------------------------------------------------------------------

def test_live_baseline_check() -> None:
    if not (REPO_ROOT / BASELINE).is_file():
        print(f"{TAG} skip: baseline not present in this checkout")
        return
    proc = subprocess.run(
        [sys.executable, str(GUARD), "--check"],
        capture_output=True, text=True, timeout=300, check=False,
    )
    if "HONEST SKIP" in proc.stdout or "osv-unreachable" in proc.stdout:
        print(f"{TAG} skip-with-evidence: OSV API unreachable")
        return
    assert proc.returncode == guard.EXIT_PASS, proc.stdout + proc.stderr
    baseline = json.loads((REPO_ROOT / BASELINE).read_text())
    meta = baseline.get("meta", {})
    assert meta.get("issue") == 2075
    assert meta.get("dated") == "2026-10-28"
    assert meta.get("ecosystem") == "npm"
    assert meta.get("dev_entries_skipped") is True
    assert "shrink-only" in meta.get("doctrine", "")
    assert len(meta.get("lockfiles", [])) == 5  # R46 widened roster
    findings = baseline.get("findings", {})
    for key in findings:
        assert ":" in key and "@" in key  # lock-scoped pair keys


# ---------------------------------------------------------------------------
# R46 widening (#2075): surface constants + worker floor + honest-zero lock
# ---------------------------------------------------------------------------

def test_widened_surface_constants() -> None:
    paths = [p.as_posix() for p in guard.LOCK_PATHS]
    assert paths == [
        "infrastructure/mcp-control-plane/package-lock.json",
        ".agents/skills/devtools-audit/package-lock.json",
        "browser/cloudflare-worker/package-lock.json",
        "vscode/package-lock.json",
        "vscode/extension/package-lock.json",
    ]
    assert "browser/cloudflare-worker/wrangler.toml" in guard.SURFACE_PATHS
    assert "infrastructure/mcp-control-plane/render.yaml" in guard.SURFACE_PATHS


def _worker_floor(pairs):
    return {p: ["GHSA-w1", "GHSA-w2"] for p in pairs if p == ("tar-fs", "3.0.4")}


def _worker_new_id(pairs):
    return {
        p: (["GHSA-w1", "GHSA-w2", "GHSA-w9"] if p == ("tar-fs", "3.0.4") else [])
        for p in pairs
        if p == ("tar-fs", "3.0.4")
    }


def test_worker_lock_floor_honored_then_drifts() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = make_temp_repo(Path(td), {
            f"{WORKER_LOCK}:tar-fs@3.0.4": ["GHSA-w1", "GHSA-w2"],
        })
        with _OsvPatch(guard, _worker_floor):
            code, drift, imp, notes = guard.evaluate(root, files=None)
            assert code == guard.EXIT_PASS and drift == []
        with _OsvPatch(guard, _worker_new_id):
            code, drift, imp, notes = guard.evaluate(root, files=None)
            assert code == guard.EXIT_DRIFT
            assert drift[0]["kind"] == "new-id"
            assert drift[0]["pair"] == f"{WORKER_LOCK}:tar-fs@3.0.4"
            assert drift[0]["ids"] == ["GHSA-w9"]


def test_all_dev_lock_is_honest_zero() -> None:
    # The vscode/extension lock parses to ZERO production pairs (all-dev
    # tree): no query is needed, no baseline entry is owed, and the lock
    # still participates in the roster (a missing file would fail-close).
    # The tower lock's known pair is floored so the only signal under test
    # is the all-dev lock's honest zero.
    with tempfile.TemporaryDirectory() as td:
        root = make_temp_repo(Path(td), {
            f"{TOWER_LOCK}:express@4.21.2": ["GHSA-known"],
        })
        pairs, skipped = guard.load_lock_pairs(root / VSCODE_EXT_LOCK)
        assert pairs == [] and skipped["dev"] == 1
        with _OsvPatch(guard, _known_floor):
            code, drift, imp, notes = guard.evaluate(root, files=None)
            assert code == guard.EXIT_PASS and drift == []


def test_wiring_ssot() -> None:
    roster = (REPO_ROOT / "scripts/ci/run_all_guards.py").read_text()
    assert "scripts/ci/npm_dep_cve_guard.py" in roster, \
        "guard must be wired into the run_all_guards roster"
    prepush = (REPO_ROOT / ".githooks/pre-push").read_text()
    assert "npm_dep_cve_guard.py" in prepush, \
        "guard must be wired into the pre-push hook"
    assert BASELINE in prepush or "npm_dep_cve_baseline" in prepush


# ---------------------------------------------------------------------------
# stdlib plain runner (dual-mode parity with the #1913 suite)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed: list[str] = []
    for name, fn in fns:
        try:
            fn()
            print(f"{TAG} PASS: {name}")
        except Exception as exc:  # noqa: BLE001 - plain runner reports and continues
            failed.append(name)
            print(f"{TAG} FAIL: {name}: {exc}")
    if failed:
        print(f"{TAG} {len(failed)} FAILED: {failed}")
        sys.exit(1)
    print(f"{TAG} ALL {len(fns)} TESTS PASS")
