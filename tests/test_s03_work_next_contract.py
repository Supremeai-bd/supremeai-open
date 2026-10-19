#!/usr/bin/env python3
"""Dual-mode contract tests for S0.3 work.next() (task #458).

UNIT layer: offline, pure, against scripts/tower/work_next_reference.py.

Run: pytest tests/test_s03_work_next_contract.py  OR  python3 tests/test_s03_work_next_contract.py
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF_DIR = HERE.parent / "scripts" / "tower"
if str(REF_DIR) not in sys.path:
    sys.path.insert(0, str(REF_DIR))

import work_claim_reference as s01
import work_next_reference as s03

T0 = datetime(2026, 10, 17, 4, 0, 0, tzinfo=timezone.utc)


def claim(issue, agent, ts=T0, ttl=s01.TTL_MINUTES):
    return s01.Claim(issue=issue, agent=agent, ts=ts, ttl_minutes=ttl)


def row(num, title="task", **kw):
    base = dict(
        number=num,
        title=title,
        state="open",
        labels=("P1-high",),
        claim=None,
        has_inflight_wo=False,
        blocked_label=False,
        is_task_issue=True,
    )
    base.update(kw)
    return s03.IssueState(**base)


class UnitFilters(unittest.TestCase):
    def test_01_picks_unclaimed(self):
        res = s03.work_next([row(458)], "zai", now=T0)
        self.assertEqual(res.pick.issue, 458)
        self.assertEqual(res.pick.claim_decision, s03.GRANT_NEW)

    def test_02_closed_never_picked(self):
        with self.assertRaises(s03.WorkNextError) as ctx:
            s03.work_next([row(1, state="closed")], "zai", now=T0)
        self.assertEqual(ctx.exception.code, "E_QUEUE_EMPTY")
        self.assertEqual(ctx.exception.code, "E_QUEUE_EMPTY")

    def test_03_live_foreign_claim_excluded_strict(self):
        with self.assertRaises(s03.WorkNextError):
            s03.work_next([row(1, claim=claim(1, "other"))], "zai", now=T0)

    def test_04_expired_foreign_claim_takeover(self):
        stale = claim(1, "other", ts=T0 - timedelta(minutes=s01.TTL_MINUTES + 1))
        res = s03.work_next([row(1, claim=stale)], "zai", now=T0)
        self.assertEqual(res.pick.claim_decision, s03.GRANT_TAKEOVER)

    def test_05_expired_own_claim_renew(self):
        stale = claim(1, "zai", ts=T0 - timedelta(minutes=s01.TTL_MINUTES + 1))
        res = s03.work_next([row(1, claim=stale)], "zai", now=T0)
        self.assertEqual(res.pick.claim_decision, s03.GRANT_RENEW)

    def test_06_live_own_claim_is_resume(self):
        res = s03.work_next([row(1, claim=claim(1, "zai"))], "zai", now=T0)
        self.assertEqual(res.pick.claim_decision, "NOOP_SELF")

    def test_07_inflight_wo_excluded(self):
        with self.assertRaises(s03.WorkNextError) as ctx:
            s03.work_next([row(1, has_inflight_wo=True)], "zai", now=T0)
        self.assertEqual(ctx.exception.code, "E_QUEUE_EMPTY")

    def test_08_blocked_label_excluded(self):
        with self.assertRaises(s03.WorkNextError):
            s03.work_next([row(1, blocked_label=True)], "zai", now=T0)

    def test_09_bridge_wos_not_pickable(self):
        with self.assertRaises(s03.WorkNextError):
            s03.work_next([row(464, is_task_issue=False)], "zai", now=T0)

    def test_10_empty_snapshot_is_board_error(self):
        with self.assertRaises(s03.WorkNextError) as ctx:
            s03.work_next([], "zai", now=T0)
        self.assertEqual(ctx.exception.code, "E_BOARD_UNAVAILABLE")


class UnitRanking(unittest.TestCase):
    def test_11_p0_before_p1_before_p2(self):
        board = [
            row(1, labels=("P2-medium",)),
            row(2, labels=("P0-critical",)),
            row(3, labels=("P1-high",)),
        ]
        res = s03.work_next(board, "zai", now=T0)
        self.assertEqual(
            [res.pick.issue] + [p.issue for p in res.runner_ups][:2], [2, 3, 1]
        )

    def test_12_fifo_within_tier(self):
        board = [row(9), row(4), row(6)]
        res = s03.work_next(board, "zai", now=T0)
        self.assertEqual(res.pick.issue, 4)
        self.assertEqual([p.issue for p in res.runner_ups], [6, 9])

    def test_13_missing_priority_ranks_p3(self):
        board = [row(8, labels=()), row(2, labels=("P3-low",))]
        res = s03.work_next(board, "zai", now=T0)
        self.assertEqual(res.pick.issue, 2)  # same tier -> FIFO by number

    def test_14_runner_ups_max_three_and_no_pick(self):
        board = [row(n) for n in range(1, 8)]
        res = s03.work_next(board, "zai", now=T0)
        self.assertLessEqual(len(res.runner_ups), 3)
        all_issues = [res.pick.issue] + [p.issue for p in res.runner_ups]
        self.assertEqual(len(all_issues), len(set(all_issues)))

    def test_15_excluded_counts_shape(self):
        board = [
            row(1, state="closed"),
            row(2, has_inflight_wo=True),
            row(3, is_task_issue=False),
            row(4, claim=claim(4, "other")),
            row(5),
        ]
        res = s03.work_next(board, "zai", now=T0)
        self.assertEqual(
            res.excluded,
            {"closed": 1, "live_foreign_claim": 1, "inflight": 1, "non_task": 1},
        )
        self.assertEqual(res.evaluated, 5)


class UnitContract(unittest.TestCase):
    def test_16_determinism_same_snapshot(self):
        board = [row(n, labels=("P2-medium",)) for n in (3, 1, 2)]
        a = s03.work_next(board, "zai", now=T0)
        b = s03.work_next(board, "zai", now=T0)
        self.assertEqual(a.pick, b.pick)
        self.assertEqual(a.runner_ups, b.runner_ups)

    def test_17_input_never_mutated(self):
        board = [row(2), row(1)]
        before = [(i.number, i.state, i.labels) for i in board]
        s03.work_next(board, "zai", now=T0)
        self.assertEqual([(i.number, i.state, i.labels) for i in board], before)

    def test_18_priority_parse_from_label(self):
        self.assertEqual(row(1, labels=("P0-critical",)).priority, "P0")
        self.assertEqual(row(1, labels=("status:claimed",)).priority, "P3")

    def test_19_uses_s01_matrix_by_import(self):
        # SSOT guard: S0.3 must import the S0.1 decision matrix, not copy it
        self.assertIs(s03.evaluate_claim, s01.evaluate_claim)
        self.assertIs(s03.GRANT_RENEW, s01.GRANT_RENEW)

    def test_20_decision_codes_surface_in_pick(self):
        res = s03.work_next([row(1, claim=claim(1, "zai"))], "zai", now=T0)
        self.assertIn(
            res.pick.claim_decision,
            ("NOOP_SELF", s03.GRANT_RENEW, s03.GRANT_TAKEOVER, s03.GRANT_NEW),
        )


class LiveContract(unittest.TestCase):
    def test_21_reference_healthy(self):
        self.assertTrue(callable(s03.work_next))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
