#!/usr/bin/env python3
"""tests/test_js_dep_cve_guard.py — fail-closed behavioral suite for #1913.

Verifies the JavaScript dependency CVE ratchet gate delivered by #1913:

  - lockfile key splitter: the load-bearing pnpm v9 parsing contract —
    scoped names split on the SECOND '@' (a greedy first-@ split mangles
    '@scope/pkg@1.2.3(peer@x.y)' keys), peer suffixes stripped before the
    first '(', non-registry keys (link:/file:) skipped;
  - ratchet semantics: equal ids pass, a new pair and a new advisory id
    inside a known pair are drift, resolved ids and vanished pairs are
    improvements (shrink the baseline entry in the same change);
  - routing decision tree: NEW advisory ids fail-close (exit 1); a missing
    or malformed baseline fail-closes; a missing/changed lockfile surface
    fail-closes; an unreachable OSV API skips with evidence and NEVER
    fabricates a PASS (the #1760 honest-degradation pattern); --files mode
    with an off-surface changed set is an honest skip;
  - live baseline pin: on the real repo the dated floor passes --check
    (the landing state, network permitting — skipped with evidence when
    api.osv.dev is unreachable), and its meta provenance is intact;
  - wiring SSOT: the guard is present in the LIVE run_all_guards.py roster
    and the LIVE .githooks/pre-push hook (never duplicated here).

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_js_dep_cve_guard.py
  - stdlib:  python3 tests/test_js_dep_cve_guard.py   (plain runner)

Network-dependent paths are hermetic: query_osv_batch is monkeypatched with
fixture findings, so every structural test is offline and deterministic —
the same pattern as the guard's own --self-test and the #1829 suite. The
single live --check probe degrades to a skip when the OSV API is absent.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "ci" / "js_dep_cve_guard.py"
BASELINE = "scripts/ci/js_dep_cve_baseline.json"
TAG = "[js-dep-cve-guard]"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import js_dep_cve_guard as guard

FIXTURE_LOCK = """lockfileVersion: '9.0'

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


def _sandbox(tmp: Path, findings: dict[str, list[str]]) -> Path:
    """Sandbox repo: fixture lockfile + baseline of the given findings."""
    (tmp / "scripts" / "ci").mkdir(parents=True)
    (tmp / "studio").mkdir(parents=True)
    (tmp / guard.LOCK_PATH).write_text(FIXTURE_LOCK, encoding="utf-8")
    (tmp / guard.BASELINE_PATH).write_text(
        json.dumps({"meta": {"issue": 1913}, "findings": findings}), encoding="utf-8"
    )
    return tmp


def _run_guard_files_mode(files: list[str]) -> int:
    """Pre-push parity: the guard's --files mode exits green off-surface."""
    with tempfile.TemporaryDirectory(prefix="jsdep-files-") as td:
        root = _sandbox(Path(td), {"left-pad@1.3.0": ["GHSA-old"]})
        saved = guard.query_osv_batch
        guard.query_osv_batch = lambda pairs, endpoint=guard.OSV_QUERYBATCH: {
            ("left-pad", "1.3.0"): ["GHSA-old"]
        }
        try:
            code, _drift, _imp, notes = guard.evaluate(root, files=files)
            assert code == guard.EXIT_PASS, (code, notes)
        finally:
            guard.query_osv_batch = saved
    return guard.EXIT_PASS


# --------------------------------------------------------------------------- #
# Wiring SSOT: the live roster and the live hook carry the guard               #
# --------------------------------------------------------------------------- #

def test_guard_module_reachable_and_pinned() -> None:
    assert GUARD.is_file(), f"guard script missing: {GUARD}"
    src = GUARD.read_text(encoding="utf-8")
    assert BASELINE in src, "guard must name its versioned baseline file"
    assert "shrink-only" in src, "ratchet doctrine must be stated in the guard"
    assert TAG in src, "evidence tag must stay stable for CI grepping"
    assert "api.osv.dev" in src, "the OSV SSOT endpoint must be explicit"


def test_guard_in_roster_and_pre_push() -> None:
    roster = (REPO_ROOT / "scripts" / "ci" / "run_all_guards.py").read_text(encoding="utf-8")
    assert "scripts/ci/js_dep_cve_guard.py" in roster, "guard missing from roster"
    hook = (REPO_ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")
    assert "js_dep_cve_guard.py" in hook, "guard missing from pre-push hook"
    assert "13. JS-DEP CVE GUARD" in hook, "pre-push section header drifted"


# --------------------------------------------------------------------------- #
# The load-bearing parsing contract (radar premise + greedy-split bug pin)     #
# --------------------------------------------------------------------------- #

def test_split_scoped_second_at() -> None:
    # A greedy first-@ split would yield name '@dnd-kit/core@6.3.1(react-dom'.
    assert guard.split_lock_key("@dnd-kit/core@6.3.1(react-dom@19.3.1)(react@19.3.1)") == (
        "@dnd-kit/core",
        "6.3.1",
    )
    assert guard.split_lock_key("@vitest/mocker@3.2.7(vitest@3.2.7)") == (
        "@vitest/mocker",
        "3.2.7",
    )


def test_split_plain_and_peer_suffix() -> None:
    assert guard.split_lock_key("react@19.3.1") == ("react", "19.3.1")
    assert guard.split_lock_key("vite@7.3.7(@types/node@24.19.2)(jiti@2.7.0)") == ("vite", "7.3.7")
    assert guard.split_lock_key("@scope/pkg@1.2.3-beta.4(peer@2.0.0)") == ("@scope/pkg", "1.2.3-beta.4")


def test_split_skips_non_registry_keys() -> None:
    assert guard.split_lock_key("@supremeai/studio@link:../studio") is None
    assert guard.split_lock_key("some-pkg@file:./local") is None
    assert guard.split_lock_key("no-version-here") is None
    assert guard.split_lock_key("@unterminated") is None


def test_lock_parse_dedupes_packages_and_snapshots() -> None:
    with tempfile.TemporaryDirectory(prefix="jsdep-parse-") as td:
        lock = Path(td) / "pnpm-lock.yaml"
        lock.write_text(FIXTURE_LOCK, encoding="utf-8")
        pairs, skipped = guard.load_lock_pairs(lock)
        assert ("left-pad", "1.3.0") in pairs
        assert ("helper", "0.0.1") in pairs  # snapshot-only entry captured
        assert ("right-pad", "2.1.0") in pairs
        assert len(pairs) == len(set(pairs)), "pairs must be deduplicated"
        assert skipped == [], f"fixture has no non-registry keys: {skipped}"


# --------------------------------------------------------------------------- #
# Ratchet semantics                                                            #
# --------------------------------------------------------------------------- #

def test_ratchet_equal_state_is_clean() -> None:
    baseline = {"a@1.0.0": ["GHSA-aaa"], "b@2.0.0": ["GHSA-b1", "GHSA-b2"]}
    drift, improvements = guard.compare(dict(baseline), baseline)
    assert not drift and not improvements


def test_ratchet_new_pair_and_new_id_are_drift() -> None:
    baseline = {"a@1.0.0": ["GHSA-aaa"]}
    drift, _ = guard.compare({"c@3.0.0": ["GHSA-ccc"]}, baseline)
    assert drift and drift[0]["kind"] == "new-pair" and drift[0]["ids"] == ["GHSA-ccc"]
    drift, _ = guard.compare({"a@1.0.0": ["GHSA-aaa", "GHSA-new"]}, baseline)
    assert drift and drift[0]["kind"] == "new-id" and drift[0]["ids"] == ["GHSA-new"]


def test_ratchet_resolved_ids_are_improvements() -> None:
    baseline = {"a@1.0.0": ["GHSA-aaa", "GHSA-gone"], "b@2.0.0": ["GHSA-b1"]}
    drift, improvements = guard.compare({"a@1.0.0": ["GHSA-aaa"]}, baseline)
    assert not drift
    assert improvements and improvements[0]["resolved_ids"] == ["GHSA-gone"]
    drift, improvements = guard.compare({"a@1.0.0": ["GHSA-aaa"]}, {"a@1.0.0": ["GHSA-aaa"], "b@2.0.0": ["GHSA-b1"]})
    assert not drift
    assert any(i["pair"] == "b@2.0.0" for i in improvements), "vanished pair is a shrink hint"


# --------------------------------------------------------------------------- #
# Decision tree (hermetic: query_osv_batch monkeypatched)                      #
# --------------------------------------------------------------------------- #

def test_decision_tree_new_advisory_fail_closes() -> None:
    with tempfile.TemporaryDirectory(prefix="jsdep-tree-") as td:
        root = _sandbox(Path(td), {"left-pad@1.3.0": ["GHSA-old"]})
        saved = guard.query_osv_batch
        guard.query_osv_batch = lambda pairs, endpoint=guard.OSV_QUERYBATCH: {
            ("left-pad", "1.3.0"): ["GHSA-old"],
            ("right-pad", "2.1.0"): ["GHSA-fresh"],
        }
        try:
            code, drift, _imp, _notes = guard.evaluate(root)
            assert code == guard.EXIT_DRIFT, "new advisory pair must fail-close"
            assert drift[0]["pair"] == "right-pad@2.1.0" and drift[0]["kind"] == "new-pair"
        finally:
            guard.query_osv_batch = saved


def test_decision_tree_unreachable_osv_skips_with_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="jsdep-skip-") as td:
        root = _sandbox(Path(td), {"left-pad@1.3.0": ["GHSA-old"]})
        saved = guard.query_osv_batch

        def _boom(pairs, endpoint=guard.OSV_QUERYBATCH):
            raise RuntimeError("api.osv.dev unreachable (simulated)")

        guard.query_osv_batch = _boom
        try:
            code, drift, _imp, notes = guard.evaluate(root)
            assert code == guard.EXIT_PASS and not drift
            assert any("OSV API unreachable" in n for n in notes), notes
        finally:
            guard.query_osv_batch = saved


def test_decision_tree_missing_lockfile_fail_closes() -> None:
    with tempfile.TemporaryDirectory(prefix="jsdep-lock-") as td:
        root = _sandbox(Path(td), {"left-pad@1.3.0": ["GHSA-old"]})
        (root / guard.LOCK_PATH).unlink()
        code, drift, _imp, _notes = guard.evaluate(root)
        assert code == guard.EXIT_DRIFT and drift[0]["kind"] == "missing-lockfile"


def test_decision_tree_malformed_baseline_fail_closes() -> None:
    with tempfile.TemporaryDirectory(prefix="jsdep-base-") as td:
        root = _sandbox(Path(td), {"left-pad@1.3.0": ["GHSA-old"]})
        (root / guard.BASELINE_PATH).write_text("{not json", encoding="utf-8")
        code, drift, _imp, _notes = guard.evaluate(root)
        assert code == guard.EXIT_DRIFT and drift[0]["ids"] == ["BASELINE"]


def test_files_mode_off_surface_is_honest_skip() -> None:
    with tempfile.TemporaryDirectory(prefix="jsdep-off-") as td:
        root = _sandbox(Path(td), {"left-pad@1.3.0": ["GHSA-old"]})
        saved = guard.query_osv_batch
        guard.query_osv_batch = lambda pairs, endpoint=guard.OSV_QUERYBATCH: {
            ("left-pad", "1.3.0"): ["GHSA-old"]
        }
        try:
            code, _drift, _imp, notes = guard.evaluate(root, files=["README.md", "core/x.py"])
            assert code == guard.EXIT_PASS
            assert any("nothing to check" in n for n in notes), notes
        finally:
            guard.query_osv_batch = saved


# --------------------------------------------------------------------------- #
# Live baseline pin (landing state; honest-skip when OSV is unreachable)       #
# --------------------------------------------------------------------------- #

def test_live_baseline_provenance() -> None:
    bl = REPO_ROOT / BASELINE
    assert bl.is_file(), "the versioned baseline must be committed"
    data = json.loads(bl.read_text(encoding="utf-8"))
    meta = data["meta"]
    assert "osv" in str(meta.get("tool", "")), "baseline must record the OSV SSOT"
    assert meta.get("doctrine", "").startswith("shrink-only"), "ratchet doctrine required"
    assert meta.get("issue") == 1913
    assert isinstance(data["findings"], dict) and data["findings"], "floor must be non-empty"
    for pair, ids in data["findings"].items():
        assert "@" in pair, f"pair key must be name@version: {pair}"
        assert ids and all(str(i).startswith("GHSA-") for i in ids), f"ids must be advisory ids: {pair}"


def test_live_check_passes_at_landing_head() -> None:
    probe = subprocess.run(
        [sys.executable, str(GUARD), "--check"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=600, check=False,
    )
    combined = (probe.stdout or "") + (probe.stderr or "")
    if "OSV API unreachable" in combined:
        print("SKIP(with evidence): OSV API unreachable — honest degradation honored")
        return
    assert probe.returncode == guard.EXIT_PASS, (
        f"live --check must pass at the landing head\n{combined[:2000]}"
    )


def test_guard_self_test_suite_passes() -> None:
    r = subprocess.run(
        [sys.executable, str(GUARD), "--self-test"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, check=False,
    )
    assert r.returncode == 0, f"guard --self-test failed:\n{r.stdout}\n{r.stderr}"


# --------------------------------------------------------------------------- #
# stdlib plain runner (no pytest required)                                     #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS | {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL | {fn.__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} tests passed")
    sys.exit(1 if failed else 0)
