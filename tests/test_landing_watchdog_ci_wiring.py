"""Guard: the landing watchdog's closing leg must stay wired into CI.

Corrected contract (cycle-17, r12): the closing leg HAS a caller since
#3341 — the agent-loop job's janitor step. The r11 receipt's "no caller /
zero pipeline references" claim was a truncated-grep false-negative and is
publicly corrected in the r12 receipt. The real failure layers behind the
ghost cohort are:

(a) cadence — the only caller fires daily (cron 06:00 UTC) while ghost
    mirrors accumulate hourly between runs;
(b) shallow blindness — that job's checkout is depth-1 while the census
    joins against the last 400 subjects (depth-1 clone repro: 1 subject
    visible, every landed slug invisible → the sweep closes nothing even
    when it fires).

This guard pins the wire itself against silent unwiring (the #4093 purge
class). The cadence + blindness fix-pins (sync-job step with a history
deepen, or a deepened agent-loop checkout) ride the r12 admin packet and
land with or after the fix.

বাংলা: r11-এর "no caller" দাবি ছিল ভ্রান্ত (কাটা grep-এর মিথ্যা নেগেটিভ) —
r12 রিসিটে তা সংশোধন করা হয়েছে। এই টেস্ট wire টিকে নীরবে খোলা থেকে রক্ষা
করে; ক্যাডেন্স ও শ্যালো-ব্লাইন্ডনেস ফিক্স admin packet-এর সাথে ল্যান্ড করবে।
"""

from __future__ import annotations

import pathlib

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PIPELINE = REPO_ROOT / ".github" / "workflows" / "pipeline.yml"
WATCHDOG = REPO_ROOT / "scripts" / "ci" / "bridge_landing_watchdog.py"
LOOP_JOB = "agent-loop"


def _job_steps(job_name: str) -> list[dict]:
    doc = yaml.safe_load(PIPELINE.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), "pipeline.yml is not a YAML mapping"
    jobs = doc.get("jobs")
    assert isinstance(jobs, dict) and job_name in jobs, (
        f"pipeline.yml lost the {job_name} job — the watchdog wire's home is gone"
    )
    steps = jobs[job_name].get("steps")
    assert isinstance(steps, list), f"{job_name} has no steps list"
    return [s for s in steps if isinstance(s, dict)]


def test_closing_leg_wired_into_agent_loop_janitor() -> None:
    found = [s for s in _job_steps(LOOP_JOB)
             if "bridge_landing_watchdog" in str(s.get("run", ""))]
    assert found, (
        "landing watchdog closing leg UNWIRED from the agent-loop janitor "
        "step — the #3341 wire regressed; landed WO mirrors would never be "
        "closed by any automation again (ghost class, r12 receipt)"
    )


def test_janitor_invocation_carries_closing_flag() -> None:
    found = [s for s in _job_steps(LOOP_JOB)
             if "bridge_landing_watchdog" in str(s.get("run", ""))]
    assert found and "--apply" in str(found[0]["run"]), (
        "janitor invokes the watchdog without its closing flag — a "
        "report-only census cannot close landed WO mirrors"
    )


def test_any_sync_job_watchdog_step_must_deepen() -> None:
    """Fix-pin: any watchdog invocation in a push-triggered job must deepen.

    The satellite sync job checks out depth-50; the census joins 400
    subjects. Vacuously green until the r12 admin packet lands the
    sync-job step — then it enforces the deepen forever.
    """
    doc = yaml.safe_load(PIPELINE.read_text(encoding="utf-8"))
    sync = doc.get("jobs", {}).get("satellite-dispatch-and-sync", {})
    for s in sync.get("steps", []):
        if isinstance(s, dict) and "bridge_landing_watchdog" in str(s.get("run", "")):
            assert "deepen" in str(s["run"]) or "unshallow" in str(s["run"]), (
                "sync-job watchdog step lost the history deepen — the "
                "shallow checkout blinds the 400-subject join to older "
                "landings (r12 layer-b diagnosis)"
            )


def test_census_shallow_self_heal_pinned_in_tool() -> None:
    """Fix-pin (r13/cycle-18, Job 486770): layer-b is healed INSIDE the tool.

    The agent-loop caller checks out depth-1 (actions/checkout default), so
    the census must deepen the clone itself and degrade loudly — a truncated
    join window is never silently trusted again. Live-proof on the exact
    depth-1 repro: 1 -> 400 subjects visible, 21/22 ghosts detected where
    the unfixed census saw zero.
    """
    src = WATCHDOG.read_text(encoding="utf-8")
    for needle, why in (
        ('"fetch", f"--deepen={depth}", "origin", "main"',
         "census lost the bounded deepen fetch — shallow checkouts go blind again"),
        ("::warning::landing-watchdog census",
         "census lost the loud ::warning:: degradation — a truncated join "
         "window would be silently trusted again"),
        ('.git" / "shallow',
         "census lost the shallow probe — truncation would be mistaken for "
         "genuinely short history"),
    ):
        assert needle in src, f"{needle!r} missing from the watchdog: {why}"
