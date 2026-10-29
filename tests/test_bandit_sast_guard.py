#!/usr/bin/env python3
"""tests/test_bandit_sast_guard.py — fail-closed behavioral suite for #1809.

Verifies the Python source static-security ratchet gate delivered by #1809:

  - exclusion predicate: the exact #1809 exclusion set (test-pattern files,
    the labeled teaching sample core/examples/sample_buggy.py, paths outside
    the scan targets, never .github/**);
  - aggregation: bandit JSON reports aggregate to (path, test_id) -> count
    with the exclusions applied and counts preserved;
  - ratchet semantics: equal counts pass, grown counts and new (path, id)
    pairs are drift, shrunk counts are improvements (shrink the baseline
    entry in the same change);
  - routing decision tree: NEW drift under scripts/** is fail-closed
    (exit 1 — the agent-bridge-able surface), drift under the satellite
    mirrors (core/, gateway/, browser/, ...) is report-only (exit 0) per the
    #1809 never-do (agents never edit the mirrors); a missing or malformed
    baseline fail-closes; a missing bandit binary skips with evidence and
    NEVER fabricates a PASS (the #1760 honest-degradation pattern);
  - live baseline pin: on the real repo the dated floor passes --check
    (the landing state), and its meta provenance is intact;
  - wiring SSOT: the guard is present in the LIVE run_all_guards.py roster
    and the LIVE .githooks/pre-push hook (never duplicated here).

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_bandit_sast_guard.py
  - stdlib:  python3 tests/test_bandit_sast_guard.py   (plain runner)

Scanner-dependent paths are hermetic: run_bandit_json / bandit_version are
monkeypatched with fixture reports, so every test is offline and
deterministic — the same pattern as the guard's own --self-test.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "ci" / "bandit_sast_guard.py"
BASELINE = "scripts/ci/bandit_sast_baseline.json"
TAG = "[bandit-sast-guard]"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import bandit_sast_guard as guard

# --------------------------------------------------------------------------- #
# Wiring SSOT: the live roster and the live hook carry the guard               #
# --------------------------------------------------------------------------- #

def test_guard_module_reachable_and_pinned() -> None:
    assert GUARD.is_file(), f"guard script missing: {GUARD}"
    src = GUARD.read_text(encoding="utf-8")
    assert BASELINE in src, "guard must name its versioned baseline file"
    assert "shrink-only" in src, "ratchet doctrine must be stated in the guard"
    assert TAG in src, "evidence tag must stay stable for CI grepping"
    assert guard.PINNED_BANDIT == "1.9.4", "scanner pin must stay explicit"


def test_live_roster_and_hook_wiring() -> None:
    roster = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"
    assert roster.is_file(), "run_all_guards.py must exist"
    assert "scripts/ci/bandit_sast_guard.py" in roster.read_text(encoding="utf-8"), (
        "guard missing from the run_all_guards roster"
    )
    hook = REPO_ROOT / ".githooks" / "pre-push"
    assert hook.is_file(), ".githooks/pre-push must exist"
    htext = hook.read_text(encoding="utf-8")
    assert "bandit_sast_guard.py" in htext, "guard missing from the pre-push hook"
    assert "BANDIT SAST GUARD (#1809)" in htext, "hook section must document the guard"


# --------------------------------------------------------------------------- #
# Exclusion predicate + aggregation                                            #
# --------------------------------------------------------------------------- #

def test_exclusion_predicate_is_the_1809_set() -> None:
    assert not guard.is_test_path("scripts/ci/bandit_sast_guard.py")
    assert guard.is_test_path("core/tests/test_x.py")
    assert guard.is_test_path("scripts/agents/test_foo.py")
    assert guard.is_test_path("core/api/conftest.py")
    assert guard.is_test_path("gateway/tests/unit/deep_test.py")
    assert not guard.is_test_path("scripts/ci/data/fixture.py")
    assert guard.in_scan_targets("core/api/x.py")
    assert not guard.in_scan_targets("studio/src/x.ts")
    assert not guard.in_scan_targets(".github/workflows/ci.yml")


def test_aggregation_applies_exclusions_and_counts() -> None:
    fake = {
        "results": [
            {"filename": "scripts/a.py", "test_id": "B602"},
            {"filename": "scripts/a.py", "test_id": "B602"},
            {"filename": "scripts/test_a.py", "test_id": "B101"},
            {"filename": "core/examples/sample_buggy.py", "test_id": "B102"},
            {"filename": "core/b.py", "test_id": "B324"},
            {"filename": "studio/outside.py", "test_id": "B101"},
            {"filename": "", "test_id": "B101"},
        ]
    }
    agg, raw, skipped = guard.aggregate(fake)
    assert raw == 7 and skipped == 4, (raw, skipped)
    assert agg == {"scripts/a.py": {"B602": 2}, "core/b.py": {"B324": 1}}, agg


# --------------------------------------------------------------------------- #
# Ratchet semantics                                                            #
# --------------------------------------------------------------------------- #

def test_ratchet_equal_grown_shrunk_new_pair() -> None:
    baseline = {"scripts/a.py": {"B602": 2}, "core/b.py": {"B324": 1}}
    drift, improvements, _ = guard.compare(
        {"scripts/a.py": {"B602": 2}, "core/b.py": {"B324": 1}}, baseline
    )
    assert not drift and not improvements, (drift, improvements)
    drift, _, _ = guard.compare({"scripts/new.py": {"B105": 1}}, baseline)
    assert len(drift) == 1 and drift[0]["path"] == "scripts/new.py"
    drift, _, _ = guard.compare({"scripts/a.py": {"B602": 3}}, baseline)
    assert len(drift) == 1 and drift[0]["current"] == 3 and drift[0]["baseline"] == 2
    _, improvements, _ = guard.compare({"scripts/a.py": {"B602": 1}}, baseline)
    assert len(improvements) == 1 and improvements[0]["current"] == 1


# --------------------------------------------------------------------------- #
# Decision tree (hermetic: scanner seams monkeypatched)                        #
# --------------------------------------------------------------------------- #

def _sandbox_repo(tmp: Path, baseline_findings: dict) -> Path:
    root = tmp
    (root / "scripts" / "ci").mkdir(parents=True, exist_ok=True)
    (root / BASELINE).write_text(
        json.dumps({"meta": {"issue": 1809, "tool": "bandit"}, "findings": baseline_findings}),
        encoding="utf-8",
    )
    return root


def test_decision_tree_scripts_failclosed_satellite_reportonly() -> None:
    with tempfile.TemporaryDirectory(prefix="bandit-guard-test-") as td:
        root = _sandbox_repo(Path(td), {"core/b.py": {"B324": 1}})
        saved_run, saved_ver = guard.run_bandit_json, guard.bandit_version
        try:
            guard.bandit_version = lambda: "1.9.4"
            guard.run_bandit_json = lambda paths, cwd: {
                "results": [
                    {"filename": "scripts/new.py", "test_id": "B602"},
                    {"filename": "core/b.py", "test_id": "B324"},
                    {"filename": "core/c.py", "test_id": "B324"},
                ]
            }
            code, drift, report_only, _notes = guard.evaluate(root)
            assert code == 1, (code, drift)
            assert [d["path"] for d in drift] == ["scripts/new.py"], drift
            assert [d["path"] for d in report_only] == ["core/c.py"], report_only
            assert not any(d["path"] == "core/b.py" for d in drift + report_only), (
                "an at-baseline satellite pair must stay silent"
            )
        finally:
            guard.run_bandit_json, guard.bandit_version = saved_run, saved_ver


def test_files_mode_honest_skip_for_off_target_changes() -> None:
    with tempfile.TemporaryDirectory(prefix="bandit-guard-test-") as td:
        root = _sandbox_repo(Path(td), {})
        saved_ver = guard.bandit_version
        try:
            guard.bandit_version = lambda: "1.9.4"
            code, drift, _ro, notes = guard.evaluate(root, files=["README.md", "studio/x.py"])
            assert code == 0 and not drift
            assert any("nothing to scan" in n for n in notes), notes
        finally:
            guard.bandit_version = saved_ver


def test_missing_bandit_skips_with_evidence_never_fake_pass() -> None:
    with tempfile.TemporaryDirectory(prefix="bandit-guard-test-") as td:
        root = _sandbox_repo(Path(td), {})
        saved_ver = guard.bandit_version
        try:
            guard.bandit_version = lambda: None
            code, drift, _ro, notes = guard.evaluate(root)
            assert code == 0 and not drift, (code, drift)
            assert any("not installed" in n for n in notes), notes
            assert any("skipped with evidence" in n for n in notes), notes
        finally:
            guard.bandit_version = saved_ver


def test_missing_or_malformed_baseline_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="bandit-guard-test-") as td:
        root = Path(td)  # no baseline file at all
        (root / "scripts" / "ci").mkdir(parents=True)
        saved_run, saved_ver = guard.run_bandit_json, guard.bandit_version
        try:
            guard.bandit_version = lambda: "1.9.4"
            code, drift, _, _ = guard.evaluate(root)
            assert code == 1 and drift and drift[0]["test_id"] == "BASELINE", (code, drift)
            (root / BASELINE).write_text("{not json", encoding="utf-8")
            code2, drift2, _, _ = guard.evaluate(root)
            assert code2 == 1 and drift2[0]["test_id"] == "BASELINE"
        finally:
            guard.run_bandit_json, guard.bandit_version = saved_run, saved_ver


# --------------------------------------------------------------------------- #
# Live baseline pin (the dated floor at the landing head)                      #
# --------------------------------------------------------------------------- #

def test_live_baseline_meta_provenance() -> None:
    bl_path = REPO_ROOT / BASELINE
    assert bl_path.is_file(), "the versioned baseline must be landed with the guard"
    data = json.loads(bl_path.read_text(encoding="utf-8"))
    meta = data["meta"]
    assert meta["tool"] == "bandit" and meta["tool_version"] == guard.PINNED_BANDIT
    assert meta["issue"] == 1809
    assert meta["doctrine"].startswith("shrink-only")
    assert isinstance(data["findings"], dict) and data["findings"], "floor must be non-empty"


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
