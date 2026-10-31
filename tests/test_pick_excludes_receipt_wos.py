#!/usr/bin/env python3
"""Pin + behavior: receipt WOs (bridge:receipt) are never dispatchable tasks.

Live 2026-10-30T13:2xZ (GLM Agent 19, Job 486803): the live-mode pick
dispatched task-3345 — WO #3345, the intake receipt of Agent 05's submission
``bridge-20261030-sync-stall-2756`` — as a fresh IMPLEMENT coder task, although
its subject work had ALREADY landed (PR #3346, commit 6726949 on main). No
filter caught it: the #2794 claim probe passes (``latestClaim`` null), the
#3315 coverage probe looks OUTWARD (open WOs citing the candidate — a receipt
never cites itself), the #3050 incident probe and the item-15 premise probe
don't fire on receipt-shaped rows, and #2516's drain census had already priced
the class at 34/128 self-fulfilled receipt-WOs.

Root cause: the submission pipeline deterministically stamps every receipt /
report-only WO with ``bridge:receipt`` (mcp-control-plane
``src/tools/bridge.tools.ts`` ``BRIDGE_RECEIPT_LABEL`` — taskId
``/\\b(receipt|report-only)\\b/i`` ⇒ ``[bridge:receipt, report]``), but
``EXCLUDED_LABELS`` — the pick surface's single exclusion SSOT, built for
exactly this class in #2100 — never carried it.

Fix: add ``"bridge:receipt"`` to ``EXCLUDED_LABELS``. Same mechanism, same
SSOT, both modes (the label filter rides ``is_claimable()``, ahead of the
pure/live split), fail-closed against the pipeline's own marker. Minimal and
precise: generic ``report``-labeled scout/ops finding rows stay pickable —
only the pipeline-stamped receipt class is excluded.

Pins enforced here (zero gh/network dependency — in-memory boards):
  1. AST pin: the ``EXCLUDED_LABELS`` frozenset literal carries
     ``"bridge:receipt"`` (comment-immune, test_27 wiring-pin precedent).
  2. A ``bridge:receipt``-labeled open row is never picked (pure mode).
  3. Same in live mode (claim_probe wired) — excluded before probes burn.
  4. Over-exclusion guard: a real row without the label stays pickable.
  5. Mixed board: receipt row + real row ⇒ the real row wins.
  6. The #3345 live shape (receipt whose title cites another lane) excluded.
  7. Priority is irrelevant: a higher-priority receipt still loses.

Dual-mode: runs under both `python3 -m unittest` and `pytest`.
"""

from __future__ import annotations

import ast
import sys
import unittest
import unittest.mock
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal

LOOP_SRC = (_ROOT / "scripts" / "agents" / "continuous_agent_loop.py").read_text(
    encoding="utf-8"
)

_RECEIPT_TITLE = (
    "🌉 Bridge Work Order — report(ops) receipt for #2756: three-plane re-check "
    "(bridge-20261030-sync-stall-2756)"
)

_FREE = (False, "no active claim on the feedback plane")


def _receipt_row(number: int, title: str | None = None) -> dict:
    """A pipeline-stamped receipt WO row (#3345 live shape)."""
    return {
        "number": number,
        "title": title if title is not None else _RECEIPT_TITLE,
        "labels": [{"name": "report"}, {"name": "bridge:receipt"}],
        "state": "open",
    }


def _real_row(number: int, labels: list[str] | None = None) -> dict:
    return {
        "number": number,
        "title": f"genuinely new work {number}",
        "labels": [{"name": name} for name in (labels or [])],
        "state": "open",
    }


class _LeaseIsolated(unittest.TestCase):
    """Isolate pick_next_issue from THIS runtime's local dispatch-lease state.

    Same hermetic boundary as test_pick_receipt_coverage.py: ambient scheduler
    state must never contaminate pick assertions.
    """

    def setUp(self):
        patcher = unittest.mock.patch.object(
            cal, "load_issue_lease_store", lambda path=None: {}
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class _CaptureLog:
    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, level: str, msg: str) -> None:
        self.lines.append(f"{level}: {msg}")

    def joined(self) -> str:
        return "\n".join(self.lines)


class TestReceiptLabelSourcePin(unittest.TestCase):
    def test_frozenset_literal_carries_bridge_receipt(self):
        """AST pin: ``bridge:receipt`` is a literal of EXCLUDED_LABELS —
        immune to comment edits (test_pick_excludes_bridge_states precedent)."""
        tree = ast.parse(LOOP_SRC)
        found = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "EXCLUDED_LABELS"
                for t in node.targets
            ):
                found = node
                break
        self.assertIsNotNone(found, "EXCLUDED_LABELS assignment missing")
        call = found.value
        self.assertIsInstance(call, ast.Call, "EXCLUDED_LABELS must stay a frozenset(...)")
        literals = {
            elt.value
            for arg in call.args
            if isinstance(arg, ast.Set)
            for elt in arg.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        }
        self.assertIn("bridge:receipt", literals)
        # The #2100 five-state family must stay intact alongside the addition.
        for state in (
            "bridge:pr-opened",
            "bridge:queued",
            "bridge:in-gates",
            "bridge:rejected",
            "bridge:idempotent-noop",
        ):
            self.assertIn(state, literals)


class TestPickExcludesReceiptWOs(_LeaseIsolated):
    def test_receipt_wo_not_pickable_pure_mode(self):
        """The #3345 shape: landed receipt WO still open must never win."""
        board = [_receipt_row(3345), _real_row(3399)]
        self.assertEqual(cal.pick_next_issue(issues=board), "3399")

    def test_receipt_wo_not_pickable_live_mode(self):
        """Live mode: excluded by the label BEFORE the claim probe burns a slot."""
        calls: list[int | str] = []

        def probe(n):
            calls.append(n)
            return _FREE

        board = [_receipt_row(3345), _real_row(3399)]
        picked = cal.pick_next_issue(
            issues=board, claim_probe=probe, log_fn=_CaptureLog(),
        )
        self.assertEqual(picked, "3399")
        self.assertNotIn(3345, calls)
        self.assertIn(3399, calls)

    def test_no_over_exclusion_without_label(self):
        """A finding row carrying only `report` (no pipeline stamp) stays pickable."""
        # 2026-10-31 (#3860-পরবর্তী reconciliation): fixture-এ আগে "report-only"
        # label ছিল — কিন্তু #3860 "report-only"-কে EXCLUDED_LABELS-এ যুক্ত করেছে
        # (SSOT), তাই ওই fixture নিজের docstring-ই ভাঙত ("carrying only `report`")।
        # ওভার-এক্সক্লুশন গার্ডের উদ্দেশ্য অক্ষত রেখে plain "report" label-এ সরানো
        # হল — pipeline-stamp ছাড়া সাধারণ finding রো এখনও pickable।
        board = [
            _real_row(2538, labels=["status:unclaimed", "report", "ops"]),
        ]
        self.assertEqual(cal.pick_next_issue(issues=board), "2538")

    def test_receipt_alone_returns_none(self):
        board = [_receipt_row(3345)]
        self.assertIsNone(cal.pick_next_issue(issues=board))

    def test_receipt_row_without_explicit_state_excluded(self):
        """gh-present rows carry no `state` key (defaults open) — still excluded."""
        row = _receipt_row(3345)
        row.pop("state")
        board = [row, _real_row(3399)]
        self.assertEqual(cal.pick_next_issue(issues=board), "3399")

    def test_higher_priority_receipt_still_loses(self):
        board = [
            _receipt_row(3345),
            {"number": 3399, "title": "real P2", "labels": [{"name": "P2-medium"}], "state": "open"},
        ]
        self.assertEqual(cal.pick_next_issue(issues=board), "3399")

    def test_receipt_title_citing_other_lane_excluded(self):
        """Coverage-probe blind spot pinned: the receipt cites #2756, itself
        cites nothing about its own number — exclusion is label-based."""
        board = [
            _receipt_row(3345, title="🌉 Bridge Work Order — report(ops) receipt for #2756: re-check"),
            _real_row(3399),
        ]
        self.assertEqual(cal.pick_next_issue(issues=board), "3399")

    def test_malformed_rows_fail_open(self):
        board = [None, "garbage", _receipt_row(3345), _real_row(3399)]
        self.assertEqual(cal.pick_next_issue(issues=board), "3399")


if __name__ == "__main__":
    unittest.main()
