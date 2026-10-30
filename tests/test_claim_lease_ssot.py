"""Claim-lease SSOT pins (#57 wiring → #3573 regime).

Locks the anti-stampede lease SSOT to scripts/agents/claim_thresholds.py so
the release<->re-claim flip-flop-war fix (#57) stays wired:
- stale_claim_releaser.py derives TTL_MINUTES_DEFAULT from the SSOT and
  enforces the fresh-claim idempotency floor in release_plan();
- continuous_agent_loop.py carries NO dispatch time-gate on the claimability
  path since #3573 (the live claim probe + the atomic work_claim decide
  claimability) — the SSOT import there feeds the machine-local dispatch JOURNAL
  retention (hygiene-only prune, never a gate) and, since the landed #3738
  twin-guard contract, the SAME SSOT-derived value aliased as ISSUE_LEASE_SECONDS
  for the born-duplicate demotion's in-flight input (demotion-only: it removes a
  duplicate dispatch, it never gates or delays a candidate).

Fully offline, stdlib-only, dual-mode (unittest + pytest).
"""

from __future__ import annotations

import ast
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
        # #3573: the loop's local 30-minute dispatch lease is REMOVED from the
        # claimability path — no clock decides whether a candidate is dispatchable;
        # the live claim probe (#2794 fix (1)) and the atomic work_claim own that
        # decision. Since the landed #3738 twin-guard contract, ISSUE_LEASE_SECONDS
        # survives ONLY as the born-duplicate demotion's in-flight input name,
        # aliased to the SAME #57 SSOT-derived journal retention (one value, two
        # contract names, zero independent magic numbers, zero artificial gates).
        self.assertEqual(cal.ISSUE_LEASE_SECONDS, cal.DISPATCH_JOURNAL_RETENTION_SECONDS)
        self.assertEqual(
            cal.DISPATCH_JOURNAL_RETENTION_SECONDS,
            ct.ORPHAN_RELEASE_MINUTES * 60.0,
        )

    def test_02_loop_source_has_no_time_gate_and_keeps_ssot_lineage(self):
        src = Path(cal.__file__).read_text(encoding="utf-8")
        self.assertIn("claim_thresholds", src)
        # #3738 reconciliation: the twin-guard alias must be a verbatim alias of
        # the SSOT-derived retention — never a second, independently-set number.
        self.assertIn("ISSUE_LEASE_SECONDS = DISPATCH_JOURNAL_RETENTION_SECONDS", src)
        pick_src = inspect.getsource(cal.pick_next_issue)
        self.assertNotIn("leased_at", pick_src)
        # The candidate gate itself (nested is_claimable) is clock-free: AST name
        # scan, comment-immune — the lease/ISSUE_LEASE names may only live in the
        # twin-demote input, never inside the claimability gate.
        tree = ast.parse(pick_src)
        gates = [
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "is_claimable"
        ]
        self.assertEqual(len(gates), 1)
        gate_tokens = set()
        for node in ast.walk(gates[0]):
            if isinstance(node, ast.Name):
                gate_tokens.add(node.id)
            elif isinstance(node, ast.Attribute):
                gate_tokens.add(node.attr)
        for tok in gate_tokens:
            self.assertNotIn("LEASE", tok.upper())

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
