#!/usr/bin/env python3
"""Offline tests for the Bridge Intake gate streak watchdog (#2792 guard 5).

The RCA (docs/reports/INTAKE_RCA_2792_2026-10-30.md) proved the detection
gap — the #327-#329 intake failure streak ran for >14h before any scout
note existed because "the sentry window relied on manual observation".
Guard 5 ("fail-loud alerting on 2+ consecutive intake failures") is the
mechanical detector these tests pin:

  - the streak model (failure/success/inconclusive/in-flight semantics —
    cancelled between failures is NOT a recovery, the #3050 doctrine
    inverted for streaks);
  - the verdict decision core (2+ = exit 1, single = warn exit 0, the
    threshold boundary; strict-stale opt-in; report-only suppression);
  - the workflow-name needle (unicode display suffix must not break it);
  - tolerant payload parsing and honest-unknown age math;
  - the roster wiring (run_all_guards.py) and the honest-skip exit code.

Zero network. Dual-mode (pytest + stdlib runner), mirroring
test_bridge_landing_watchdog.py.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = REPO_ROOT / "scripts" / "ci" / "bridge_intake_gate_watchdog.py"
ROSTER = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"

PASS = 0
FAIL = 1


def _load_watchdog_module():
    spec = importlib.util.spec_from_file_location("bridge_intake_gate_watchdog", WATCHDOG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(num, status="completed", conclusion="success",
         created="2026-10-30T08:43:11Z",
         name="Bridge Intake (public work orders → private gates)"):
    return {"id": num, "run_number": num, "name": name, "status": status,
            "conclusion": conclusion, "created_at": created}


def test_roster_wiring():
    src = ROSTER.read_text(encoding="utf-8")
    assert ('["python", "scripts/ci/bridge_intake_gate_watchdog.py", "--self-test"]' in src), \
        "watchdog missing from run_all_guards.py GUARDS roster"


def test_contract_pins():
    mod = _load_watchdog_module()
    # RCA guard-5 contract text: 2+ consecutive failures fail loud.
    assert mod.DEFAULT_STREAK_THRESHOLD == 2
    # The private repo is read-only observed through the Tower; agents never
    # write there (AGENTS.md invariant 2) — pin the constant so a drift to
    # the open repo (whose runs would be a different plane) fails loudly.
    assert mod.INTAKE_REPO == "Supremeai-bd/supremeai"
    # Zero-credential Tower surface, not api.github.com (anonymous 60/h cap
    # is a documented field trap, CONTRIBUTING §11).
    assert mod.TOWER.startswith("https://supremeai-mcp-tower.onrender.com")
    # The needle must be lowercase-comparable and survive display-suffix
    # renames ("Bridge Intake (public work orders → private gates)").
    assert mod.WORKFLOW_NEEDLE == "bridge intake"
    # Verdict tokens are the model's SSOT for every consumer.
    src = WATCHDOG.read_text(encoding="utf-8")
    for token in ("ALERT_STREAK", "SINGLE_FAILURE", "HEALTHY"):
        assert token in src, f"verdict token missing: {token}"


def test_streak_matrix():
    mod = _load_watchdog_module()
    # The live #327-#329 shape: 3 failures newest-first, then a success.
    runs = [_run(329, conclusion="failure"), _run(328, conclusion="failure"),
            _run(327, conclusion="failure"), _run(326, conclusion="success")]
    s = mod.summarize_streak(runs)
    assert s["streak"] == 3
    assert s["first_failure"]["run_number"] == 329
    assert s["last_success"]["run_number"] == 326

    # Newest success stops the scan (efficiency + semantics).
    runs = [_run(332, conclusion="success"), _run(331, conclusion="success"),
            _run(329, conclusion="failure")]
    s = mod.summarize_streak(runs)
    assert s["streak"] == 0 and s["last_success"]["run_number"] == 332
    assert s["scanned"] == 1, "scan must stop at the newest success"

    # In-flight top run: reported, never counted, streak reads below it.
    runs = [_run(341, status="in_progress", conclusion=None),
            _run(340, conclusion="failure"), _run(339, conclusion="failure"),
            _run(338, conclusion="success")]
    s = mod.summarize_streak(runs)
    assert s["streak"] == 2 and s["in_flight"]["run_number"] == 341

    # Cancelled between failures: inconclusive — neither red nor recovery.
    runs = [_run(342, conclusion="failure"), _run(341, conclusion="cancelled"),
            _run(340, conclusion="failure"), _run(339, conclusion="success")]
    s = mod.summarize_streak(runs)
    assert s["streak"] == 2 and s["inconclusive_skipped"] == 1

    # timed_out joins cancelled in the inconclusive class.
    runs = [_run(342, conclusion="failure"), _run(341, conclusion="timed_out"),
            _run(340, conclusion="failure"), _run(339, conclusion="success")]
    s = mod.summarize_streak(runs)
    assert s["streak"] == 2 and s["inconclusive_skipped"] == 1

    # Empty board edge: honest zeros, never a crash.
    s = mod.summarize_streak([])
    assert s["streak"] == 0 and s["last_run"] is None and s["in_flight"] is None


def test_verdict_core():
    mod = _load_watchdog_module()
    # Threshold boundary: 2+ loud, exactly-1 warn.
    s2 = mod.summarize_streak([_run(2, conclusion="failure"),
                               _run(1, conclusion="failure")])
    v, code = mod.verdict_for(s2, 2, mod.DEFAULT_STALE_HOURS, 0.0)
    assert v == "ALERT_STREAK" and code == 1
    s1 = mod.summarize_streak([_run(2, conclusion="failure"),
                               _run(1, conclusion="success")])
    v, code = mod.verdict_for(s1, 2, mod.DEFAULT_STALE_HOURS, 0.0)
    assert v == "SINGLE_FAILURE" and code == 0
    s0 = mod.summarize_streak([_run(2, conclusion="success")])
    v, code = mod.verdict_for(s0, 2, mod.DEFAULT_STALE_HOURS, 0.0)
    assert v == "HEALTHY" and code == 0
    # Threshold override (opt-in stricter sentry lane).
    v, code = mod.verdict_for(s1, 1, mod.DEFAULT_STALE_HOURS, 0.0)
    assert code == 1
    # Strict-stale opt-in: starvation goes loud only when asked.
    runs = [_run(1, conclusion="success", created="2026-10-28T08:43:11Z")]
    s = mod.summarize_streak(runs)
    now = 1793436191.0  # ~2026-10-31T08:43Z — >48h past the run
    v, code = mod.verdict_for(s, 2, mod.DEFAULT_STALE_HOURS, now, strict_stale=True)
    assert v == "STALE_RUN" and code == 1
    v, code = mod.verdict_for(s, 2, mod.DEFAULT_STALE_HOURS, now, strict_stale=False)
    assert v == "HEALTHY" and code == 0
    # Unparseable last-run age must not fake a strict-stale red (honest-unknown).
    runs = [_run(1, conclusion="success", created="garbage")]
    s = mod.summarize_streak(runs)
    v, code = mod.verdict_for(s, 2, mod.DEFAULT_STALE_HOURS, now, strict_stale=True)
    assert v == "HEALTHY" and code == 0


def test_needle_and_parsing():
    mod = _load_watchdog_module()
    # Display-suffix unicode must not break the join; foreign workflows drop.
    runs = [_run(1), _run(2, name="🔧 Nightly Ops & Maintenance"),
            _run(3, name="bridge intake (renamed suffix)")]
    assert [r["run_number"] for r in mod.filter_intake_runs(runs)] == [1, 3]
    # Tolerant parsing: junk text, wrapper shapes, non-dict rows.
    assert mod.parse_runs("not json") == []
    assert mod.parse_runs('{"workflow_runs": [1, {"name": "x"}]}') == [{"name": "x"}]
    # Honest-unknown age math.
    assert mod.age_hours("junk", 0.0) is None
    assert mod.age_hours(None, 0.0) is None
    h = mod.age_hours("2026-10-30T08:43:11Z", 1793436191.0)
    assert h is not None and 23.9 < h < 24.1
    # Window-exhaustion honesty: no intake rows -> LookupError (exit 2 lane),
    # never a fake green.
    try:
        mod.fetch_intake_summary(fetch_text=lambda n, a: '{"workflow_runs": []}',
                                 per_page=5)
        raised = False
    except LookupError:
        raised = True
    assert raised, "empty intake window must raise the honest-skip error, not pass"


def test_honest_skip_exit():
    # Transport failure -> exit 2 (honest skip), never 0 (#1760 doctrine).
    script = str(WATCHDOG)
    proc = subprocess.run(
        [sys.executable, script, "--per-page", "3"],
        env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent",
             "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0"},
        capture_output=True, text=True, timeout=180,
    )
    # In this offline sandbox the Tower may be unreachable (exit 2) or the
    # live window may answer (0/1) — the forbidden outcome is ONLY a silent
    # pass that claims a verdict without a runs plane (exit 2 prints SKIP).
    combined = (proc.stdout + proc.stderr).lower()
    if proc.returncode == 2:
        assert "skip" in combined, "exit 2 must print an honest SKIP line"
    else:
        assert proc.returncode in (0, 1), \
            f"unexpected exit code {proc.returncode}: {combined[:200]}"


def test_self_test_roster_mode():
    proc = subprocess.run(
        [sys.executable, str(WATCHDOG), "--self-test"],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "self-test cases PASS" in proc.stdout


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"[ RUN ] {name}")
            try:
                fn()
                print(f"[  OK ] {name}")
            except AssertionError as e:
                failures += 1
                print(f"[ FAIL] {name}: {e}")
    total = sum(1 for n in globals() if n.startswith("test_") and callable(globals()[n]))
    print(f"\n==== {total - failures}/{total} PASS ====")
    sys.exit(FAIL if failures else PASS)
