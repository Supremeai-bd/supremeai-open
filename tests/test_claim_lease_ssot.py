"""Claim-lease SSOT pins (#57 wiring → #3573 regime).

Locks the anti-stampede lease SSOT to scripts/agents/claim_thresholds.py so
the release<->re-claim flip-flop-war fix (#57) stays wired:
- stale_claim_releaser.py derives TTL_MINUTES_DEFAULT from the SSOT and
  enforces the fresh-claim idempotency floor in release_plan();
- continuous_agent_loop.py carries NO dispatch time-gate since #3573 (the
  live claim probe + the atomic work_claim decide claimability) — the SSOT
  import there feeds only the machine-local dispatch JOURNAL retention
  (hygiene-only prune, never a gate).

Fully offline, stdlib-only, dual-mode (unittest + pytest).
"""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "agents"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "ci"))

import claim_thresholds as ct
import continuous_agent_loop as cal
import stale_claim_releaser as releaser


def _snap(ts: str, ttl: str = "1m") -> dict:
    return {
        "issues": [
            {
                "number": 1,
                "labels": ["status:claimed"],
                "comments": [
                    {
                        "ts": ts,
                        "body": (
                            f"<!-- atomic-claim:issue=1,agent=a,ts={ts},"
                            f"ttl={ttl} -->"
                        ),
                    }
                ],
                "last_push_at": None,
                "pr_opened_at": None,
            }
        ]
    }


class ClaimLeaseSSOTPins(unittest.TestCase):
    def test_01_loop_has_no_dispatch_time_gate(self):
        # #3573: the loop's local 30-minute dispatch lease is REMOVED — no
        # clock decides claimability; the live claim probe (#2794 fix (1)) and
        # the atomic work_claim own that decision. The #57 SSOT import remains
        # only for the dispatch JOURNAL retention (hygiene-only).
        self.assertFalse(hasattr(cal, "ISSUE_LEASE_SECONDS"))
        self.assertEqual(
            cal.DISPATCH_JOURNAL_RETENTION_SECONDS,
            ct.ORPHAN_RELEASE_MINUTES * 60.0,
        )

    def test_02_loop_source_has_no_time_gate_and_keeps_ssot_lineage(self):
        src = Path(cal.__file__).read_text(encoding="utf-8")
        self.assertNotIn("ISSUE_LEASE_SECONDS", src)
        self.assertIn("claim_thresholds", src)
        pick_src = inspect.getsource(cal.pick_next_issue)
        self.assertNotIn("leased_at", pick_src)
        self.assertNotIn("ISSUE_LEASE", pick_src)

    def test_03_releaser_ttl_derived_from_ssot(self):
        self.assertEqual(releaser.TTL_MINUTES_DEFAULT, ct.ORPHAN_RELEASE_MINUTES)
        self.assertEqual(releaser.TTL_MINUTES_DEFAULT, 30)
        self.assertIn("claim_thresholds", Path(releaser.__file__).read_text(encoding="utf-8"))

    def test_04_floor_blocks_release_of_fresh_claim(self):
        # ttl=1m marker, sweep at claim+2min: stale by marker, but the #57
        # floor (5 min) must win -> keep, never release (war evidence: ~16s).
        plan = releaser.release_plan(_snap("2026-10-28T05:00:00Z"), releaser.parse_ts("2026-10-28T05:02:00Z"))
        self.assertEqual(plan["releases"], [])
        self.assertEqual(len(plan["keeps"]), 1)
        self.assertEqual(plan["keeps"][0]["reason"], "fresh_claim_floor")

    def test_05_floor_passes_then_ttl_release_allowed(self):
        # same ttl=1m marker at claim+6min: floor passed, ttl expired -> release
        plan = releaser.release_plan(_snap("2026-10-28T05:00:00Z"), releaser.parse_ts("2026-10-28T05:06:00Z"))
        self.assertEqual(len(plan["releases"]), 1)
        self.assertEqual(plan["releases"][0]["reason"], "stale_lease_expired")

    def test_06_default_ttl_never_trips_floor(self):
        # 30m default at 29m: not stale, and the floor must not alter this
        plan = releaser.release_plan(_snap("2026-10-28T05:00:00Z", ttl="30m"), releaser.parse_ts("2026-10-28T05:29:00Z"))
        self.assertEqual(plan["releases"], [])
        self.assertEqual(plan["keeps"][0]["reason"], "lease_active")

    def test_07_ssot_constants_unchanged(self):
        # Guard the SSOT file itself against accidental threshold edits:
        self.assertEqual(ct.ORPHAN_RELEASE_MINUTES, 30)
        self.assertEqual(ct.MIN_CLAIM_AGE_BEFORE_RELEASE_MINUTES, 5)


if __name__ == "__main__":
    unittest.main()
