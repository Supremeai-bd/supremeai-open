#!/usr/bin/env python3
"""Offline contract tests for the self-healing board (#470).

Covers the #470 verification contract, tier 2:
- Rule 9:  30-minute stale claim expiry calculation (stale_claim_releaser)
- Rule 16: dedup-guard issue generation (self_healing_reporter)
- Rule 26: 3-strike quarantine counter logic (self_healing_reporter)

Pure stdlib. No network. Deterministic. 100% purity per contract.
Run: python3 -m unittest test_self_healing_pipeline -v
"""

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "ci"))

import self_healing_reporter as healer
import stale_claim_releaser as releaser


def ts(s: str) -> datetime:
    return releaser.parse_ts(s)


class Rule9StaleExpiry(unittest.TestCase):
    def test_01_exactly_ttl_is_not_stale(self):
        self.assertFalse(
            releaser.is_stale(
                ts("2026-10-17T05:00:00Z"), ts("2026-10-17T05:30:00Z"), 30
            )
        )

    def test_02_one_second_past_ttl_is_stale(self):
        self.assertTrue(
            releaser.is_stale(
                ts("2026-10-17T05:00:00Z"), ts("2026-10-17T05:30:01Z"), 30
            )
        )

    def test_03_within_ttl_not_stale(self):
        self.assertFalse(
            releaser.is_stale(
                ts("2026-10-17T05:00:00Z"), ts("2026-10-17T05:29:59Z"), 30
            )
        )

    def test_04_typed_marker_parsed(self):
        claims = releaser.parse_atomic_claims(
            [
                {
                    "ts": "2026-10-17T05:35:55Z",
                    "body": "<!-- atomic-claim:issue=470,agent=zai-web:web,ts=2026-10-17T05:35:55Z,ttl=30m -->",
                }
            ]
        )
        self.assertEqual(claims[0]["agent"], "zai-web:web")
        self.assertEqual(claims[0]["ttl_minutes"], 30)
        self.assertEqual(claims[0]["marker"], "typed")

    def test_05_stale_claim_released_after_31m_no_activity(self):
        snap = {
            "issues": [
                {
                    "number": 1,
                    "labels": ["status:claimed"],
                    "comments": [
                        {
                            "ts": "2026-10-17T05:00:00Z",
                            "body": "<!-- atomic-claim:issue=1,agent=a,ts=2026-10-17T05:00:00Z,ttl=30m -->",
                        }
                    ],
                    "last_push_at": None,
                    "pr_opened_at": None,
                }
            ]
        }
        plan = releaser.release_plan(snap, ts("2026-10-17T05:31:00Z"))
        self.assertEqual(len(plan["releases"]), 1)
        rel = plan["releases"][0]
        self.assertEqual(rel["agent"], "a")
        self.assertEqual(rel["reason"], "stale_lease_expired")

    def test_06_active_lease_kept(self):
        snap = {
            "issues": [
                {
                    "number": 1,
                    "labels": ["status:claimed"],
                    "comments": [
                        {
                            "ts": "2026-10-17T05:00:00Z",
                            "body": "<!-- atomic-claim:issue=1,agent=a,ts=2026-10-17T05:00:00Z,ttl=30m -->",
                        }
                    ],
                    "last_push_at": None,
                    "pr_opened_at": None,
                }
            ]
        }
        plan = releaser.release_plan(snap, ts("2026-10-17T05:20:00Z"))
        self.assertFalse(plan["releases"])
        self.assertEqual(plan["keeps"][0]["reason"], "lease_active")

    def test_07_push_after_claim_keeps_claim(self):
        snap = {
            "issues": [
                {
                    "number": 2,
                    "labels": ["status:claimed"],
                    "comments": [
                        {
                            "ts": "2026-10-17T05:00:00Z",
                            "body": "<!-- atomic-claim:issue=2,agent=b,ts=2026-10-17T05:00:00Z,ttl=30m -->",
                        }
                    ],
                    "last_push_at": "2026-10-17T05:45:00Z",
                    "pr_opened_at": None,
                }
            ]
        }
        plan = releaser.release_plan(snap, ts("2026-10-17T06:30:00Z"))
        self.assertFalse(plan["releases"])
        self.assertEqual(plan["keeps"][0]["reason"], "activity_after_claim")

    def test_08_pr_opened_after_claim_keeps_claim(self):
        snap = {
            "issues": [
                {
                    "number": 3,
                    "labels": ["status:claimed"],
                    "comments": [
                        {
                            "ts": "2026-10-17T05:00:00Z",
                            "body": "<!-- atomic-claim:issue=3,agent=c,ts=2026-10-17T05:00:00Z,ttl=30m -->",
                        }
                    ],
                    "last_push_at": None,
                    "pr_opened_at": "2026-10-17T05:59:00Z",
                }
            ]
        }
        plan = releaser.release_plan(snap, ts("2026-10-17T06:40:00Z"))
        self.assertFalse(plan["releases"])

    def test_09_unclaimed_issue_ignored(self):
        snap = {
            "issues": [
                {
                    "number": 4,
                    "labels": ["status:unclaimed"],
                    "comments": [],
                    "last_push_at": None,
                    "pr_opened_at": None,
                }
            ]
        }
        plan = releaser.release_plan(snap, ts("2026-10-17T06:00:00Z"))
        self.assertFalse(plan["releases"])
        self.assertFalse(plan["keeps"])

    def test_10_latest_claim_wins(self):
        snap = {
            "issues": [
                {
                    "number": 5,
                    "labels": ["status:claimed"],
                    "comments": [
                        {
                            "ts": "2026-10-17T04:00:00Z",
                            "body": "<!-- atomic-claim:issue=5,agent=old,ts=2026-10-17T04:00:00Z,ttl=30m -->",
                        },
                        {
                            "ts": "2026-10-17T06:00:00Z",
                            "body": "<!-- atomic-claim:issue=5,agent=new,ts=2026-10-17T06:00:00Z,ttl=30m -->",
                        },
                    ],
                    "last_push_at": None,
                    "pr_opened_at": None,
                }
            ]
        }
        plan = releaser.release_plan(snap, ts("2026-10-17T06:31:00Z"))
        self.assertEqual(plan["releases"][0]["agent"], "new")

    def test_11_fail_closed_on_bad_snapshot(self):
        with self.assertRaises(ValueError):
            releaser.release_plan({"nope": True}, ts("2026-10-17T05:00:00Z"))
        with self.assertRaises(ValueError):
            releaser.release_plan(
                {"issues": [{"number": "x"}]}, ts("2026-10-17T05:00:00Z")
            )

    def test_12_fail_closed_on_clock_skew(self):
        with self.assertRaises(ValueError):
            releaser.is_stale(
                ts("2026-10-17T05:00:00Z"), ts("2026-10-17T04:00:00Z"), 30
            )


class Rule16DedupGuard(unittest.TestCase):
    EV = {"repo": "supremeai-open", "kind": "ci_failure", "key": "guard-392"}

    def test_13_fingerprint_deterministic(self):
        self.assertEqual(
            healer.fingerprint_event(self.EV), healer.fingerprint_event(dict(self.EV))
        )

    def test_14_different_kind_different_fingerprint(self):
        self.assertNotEqual(
            healer.fingerprint_event(self.EV),
            healer.fingerprint_event({**self.EV, "kind": "dead_link"}),
        )

    def test_15_fail_closed_on_bad_event(self):
        with self.assertRaises(ValueError):
            healer.fingerprint_event({"kind": "ci_failure", "key": "k"})
        with self.assertRaises(ValueError):
            healer.fingerprint_event({**self.EV, "kind": "nonsense"})

    def test_16_new_event_opens_issue_with_marker(self):
        d = healer.dedup_guard([self.EV], [])
        self.assertEqual(len(d["to_open"]), 1)
        self.assertIn("heal-fp:", d["to_open"][0]["body_marker"])
        self.assertEqual(d["to_open"][0]["kind"], "ci_failure")

    def test_17_same_fingerprint_suppressed_against_open_issue(self):
        fp = healer.fingerprint_event(self.EV)
        existing = [
            {"number": 42, "state": "open", "body": f"alert <!-- heal-fp:{fp} -->"}
        ]
        d = healer.dedup_guard([self.EV], existing)
        self.assertFalse(d["to_open"])
        self.assertEqual(d["suppressed"][0]["issue"], 42)

    def test_18_closed_issue_fingerprint_does_not_dedup(self):
        fp = healer.fingerprint_event(self.EV)
        existing = [
            {"number": 42, "state": "closed", "body": f"alert <!-- heal-fp:{fp} -->"}
        ]
        d = healer.dedup_guard([self.EV], existing)
        self.assertEqual(len(d["to_open"]), 1)

    def test_19_in_batch_duplicates_dedup(self):
        d = healer.dedup_guard([self.EV, dict(self.EV)], [])
        self.assertEqual(len(d["to_open"]), 1)
        self.assertEqual(len(d["suppressed"]), 1)


class Rule26ThreeStrikeQuarantine(unittest.TestCase):
    def test_20_two_strikes_no_quarantine(self):
        hist = [
            {"issue": 9, "outcome": "fail", "ts": "T1"},
            {"issue": 9, "outcome": "fail", "ts": "T2"},
        ]
        self.assertEqual(healer.compute_strikes(hist, 9), 2)
        self.assertFalse(healer.quarantine_decisions(hist)["quarantine"])

    def test_21_three_consecutive_failures_quarantine(self):
        hist = [
            {"issue": 9, "outcome": "fail", "ts": "T1"},
            {"issue": 9, "outcome": "unclaim", "ts": "T2"},
            {"issue": 9, "outcome": "fail", "ts": "T3"},
        ]
        q = healer.quarantine_decisions(hist)["quarantine"]
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["strikes"], 3)
        self.assertEqual(q[0]["label"], "status:quarantine")

    def test_22_pass_resets_strikes(self):
        hist = [
            {"issue": 9, "outcome": "fail", "ts": "T1"},
            {"issue": 9, "outcome": "fail", "ts": "T2"},
            {"issue": 9, "outcome": "pass", "ts": "T3"},
            {"issue": 9, "outcome": "fail", "ts": "T4"},
        ]
        self.assertEqual(healer.compute_strikes(hist, 9), 1)

    def test_23_quarantine_idempotent(self):
        hist = [
            {"issue": 9, "outcome": "fail", "ts": "T1"},
            {"issue": 9, "outcome": "fail", "ts": "T2"},
            {"issue": 9, "outcome": "fail", "ts": "T3"},
        ]
        q1 = healer.quarantine_decisions(hist)
        q2 = healer.quarantine_decisions(hist, quarantined={9})
        self.assertEqual(len(q1["quarantine"]), 1)
        self.assertFalse(q2["quarantine"])

    def test_24_unclaim_counts_as_strike(self):
        hist = [
            {"issue": 11, "outcome": "unclaim", "ts": "T1"},
            {"issue": 11, "outcome": "unclaim", "ts": "T2"},
            {"issue": 11, "outcome": "unclaim", "ts": "T3"},
        ]
        self.assertEqual(healer.compute_strikes(hist, 11), 3)

    def test_25_fail_closed_on_bad_outcome_and_issue(self):
        hist = [{"issue": 9, "outcome": "banana", "ts": "T1"}]
        with self.assertRaises(ValueError):
            healer.compute_strikes(hist, 9)
        with self.assertRaises(ValueError):
            healer.compute_strikes([], "x")


class CombinedPlan(unittest.TestCase):
    def test_26_report_plan_combines_rule16_and_rule26(self):
        ev = {"repo": "supremeai-open", "kind": "probe_alert", "key": "gateway-401"}
        plan = healer.report_plan(
            events=[ev],
            existing_issues=[],
            history=[
                {"issue": 7, "outcome": "fail", "ts": "T1"},
                {"issue": 7, "outcome": "fail", "ts": "T2"},
                {"issue": 7, "outcome": "fail", "ts": "T3"},
            ],
        )
        self.assertEqual(len(plan["to_open"]), 1)
        self.assertEqual(len(plan["quarantine"]), 1)
        self.assertEqual(plan["quarantine"][0]["issue"], 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
