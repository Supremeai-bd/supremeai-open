#!/usr/bin/env python3
"""Pin + behavior: #3315 — dispatch pick receipt-coverage demotion.

Live 2026-10-30T12:20-12:38Z (GLM Agent 20, Job 486804): the live-mode pick
re-emitted rows whose work was already in flight on the SAME board —
#2360 was dispatched 4 minutes after receipt WO #3272 ("Evidence refresh for
audit row 2360") was filed, #2633 was dispatched 10 minutes after receipt WO
#3281 ("r+2 capability census receipt for scout row #2633"), and #1676 was
dispatched while WO #3292 ("#1676 detection half") was open. In every case
`latestClaim` was null, so the #2794 claim probe passed; the premise probe
(item 15/§6ak) only cross-scans MERGED landing receipts, so open (unmerged)
receipt WOs are invisible to every existing filter. In a 10+ agent fleet
draining the board in minutes, label-only dispatch deterministically
re-emits freshly-covered rows and burns the receiving agent's cycle.

Fix: `pick_next_issue()` live mode (claim_probe wired) demotes a candidate
BEFORE the priority sort when any OTHER open Bridge-WO-shaped board row
references the candidate number via word-bounded patterns (`#N`, `row N`,
`bridge-YYYYMMDD-N`). Same skip-and-advance shape as the #3050 sentry
demotion; the filter can only REMOVE a dispatch, never block one; explicit
`--issue N` override stays the escape hatch. Pure mode (claim_probe=None)
keeps the byte-identical pre-#3315 label-only contract.

Pins enforced here (zero gh/network dependency — in-memory boards):
  1. An open WO receipt citing `#N` demotes candidate N; pick advances.
  2. `row N` prose pattern demotes.
  3. `bridge-YYYYMMDD-N` taskId pattern demotes.
  4. Substring safety: candidate #263 is NOT demoted by a `#2633` citation.
  5. Issuer gate: a plain (non-Bridge-WO) issue citing #N does NOT demote.
  6. A closed covering row does NOT demote (tower rows carry state verbatim).
  7. Pure mode keeps the pre-#3315 contract (no demotion, no network).
  8. All candidates covered ⇒ None + honest exhausted-window note.
  9. Malformed board rows fail open (never raise).
 10. A row never covers itself.

Dual-mode: runs under both `python3 -m unittest` and `pytest`.
"""

from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal


def _row(number: int, labels: list[str] | None = None, title: str | None = None,
         state: str | None = None) -> dict:
    row: dict = {
        "number": number,
        "title": title if title is not None else f"row {number}",
        "labels": [{"name": name} for name in (labels or [])],
    }
    if state is not None:
        row["state"] = state
    return row


def _wo(number: int, cites: int, state: str | None = "open") -> dict:
    """A Bridge-WO-shaped row citing another issue number."""
    return _row(
        number,
        labels=["bridge:queued"],
        title=(
            f"🌉 Bridge Work Order — docs(bridge): receipt for target #{cites} "
            f"(bridge-20261030-receipt-{cites})"
        ),
        state=state,
    )


_FREE = (False, "no active claim on the feedback plane")


class _LeaseIsolated(unittest.TestCase):
    """Isolate pick_next_issue from THIS runtime's local dispatch-lease state.

    Same hermetic boundary as test_pick_feedback_preverify.py: the loop
    persists 30-min local leases outside the repo; ambient scheduler state
    must never contaminate pick assertions.
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


class TestReceiptCoveredNote(unittest.TestCase):
    """Direct unit coverage of the pure probe."""

    def test_hash_citation_hits(self):
        cand = _row(2633)
        board = [_wo(3281, 2633)]
        note = cal._receipt_covered_note(cand, board)
        self.assertIsNotNone(note)
        self.assertIn("#3281", note)
        self.assertIn("anti-stampede U5", note)

    def test_row_prose_pattern_hits(self):
        cand = _row(2360)
        board = [_row(3272, title="🌉 Bridge Work Order — Evidence refresh for audit row 2360, report-only")]
        self.assertIsNotNone(cal._receipt_covered_note(cand, board))

    def test_taskid_pattern_hits(self):
        cand = _row(2360)
        board = [_row(3273, title="🌉 Bridge Work Order — some receipt (bridge-20261030-2360-evidence-refresh-r1)")]
        self.assertIsNotNone(cal._receipt_covered_note(cand, board))

    def test_substring_no_false_positive(self):
        # #263 must NOT match a citation of #2633 (word-bounded patterns).
        cand = _row(263)
        board = [_wo(3281, 2633)]
        self.assertIsNone(cal._receipt_covered_note(cand, board))

    def test_issuer_gate_plain_issue_does_not_demote(self):
        cand = _row(2633)
        board = [_row(2900, title="fix: something that cites #2633 in prose")]
        self.assertIsNone(cal._receipt_covered_note(cand, board))

    def test_closed_covering_row_ignored(self):
        cand = _row(2633)
        board = [_wo(3281, 2633, state="closed")]
        self.assertIsNone(cal._receipt_covered_note(cand, board))

    def test_row_never_covers_itself(self):
        cand = _wo(3281, 2633)
        self.assertIsNone(cal._receipt_covered_note(cand, [cand]))

    def test_malformed_inputs_fail_open(self):
        self.assertIsNone(cal._receipt_covered_note({}, []))
        self.assertIsNone(cal._receipt_covered_note({"number": None}, [_wo(1, 2)]))
        self.assertIsNone(cal._receipt_covered_note({"number": "not-a-number"}, [_wo(1, 2)]))
        # malformed board rows are skipped, good rows still hit
        cand = _row(2633)
        board = [None, "garbage", 42, _wo(3281, 2633)]
        self.assertIsNotNone(cal._receipt_covered_note(cand, board))

    def test_no_hits_returns_none(self):
        cand = _row(9999)
        self.assertIsNone(cal._receipt_covered_note(cand, [_wo(3281, 2633)]))
        self.assertIsNone(cal._receipt_covered_note(cand, []))


class TestPickReceiptCoverageDemotion(_LeaseIsolated):
    """Behavior: the live-mode pick advances past covered candidates."""

    def test_covered_candidate_skipped_next_served(self):
        board = [
            _row(2633, labels=["P2-medium", "status:unclaimed"]),
            _wo(3281, 2633),
            _row(2999, labels=["P2-medium", "status:unclaimed"]),
        ]
        log = _CaptureLog()
        picked = cal.pick_next_issue(
            issues=board, claim_probe=lambda n: _FREE, log_fn=log,
        )
        self.assertEqual(picked, "2999")
        self.assertIn("receipt-coverage demotion: #2633 skipped", log.joined())

    def test_all_covered_returns_none_with_honest_note(self):
        board = [
            _row(2633, labels=["P2-medium", "status:unclaimed"]),
            _wo(3281, 2633),
        ]
        log = _CaptureLog()
        picked = cal.pick_next_issue(
            issues=board, claim_probe=lambda n: _FREE, log_fn=log,
        )
        self.assertIsNone(picked)
        self.assertIn("no clean pick this run", log.joined())

    def test_pure_mode_unchanged(self):
        # Pre-#3315 contract: without a live claim_probe the covered candidate
        # is served exactly as before (label-only pick, zero demotion).
        board = [
            _row(2633, labels=["P2-medium", "status:unclaimed"]),
            _wo(3281, 2633),
        ]
        log = _CaptureLog()
        picked = cal.pick_next_issue(issues=board, claim_probe=None, log_fn=log)
        self.assertEqual(picked, "2633")
        self.assertNotIn("receipt-coverage demotion", log.joined())

    def test_closed_covering_row_serves_candidate(self):
        board = [
            _row(2633, labels=["P2-medium", "status:unclaimed"]),
            _wo(3281, 2633, state="closed"),
        ]
        picked = cal.pick_next_issue(
            issues=board, claim_probe=lambda n: _FREE, log_fn=_CaptureLog(),
        )
        self.assertEqual(picked, "2633")

    def test_malformed_board_rows_fail_open(self):
        board = [
            None,
            "garbage",
            _row(2633, labels=["P2-medium", "status:unclaimed"]),
            _wo(3281, 2633),
        ]
        picked = cal.pick_next_issue(
            issues=board, claim_probe=lambda n: _FREE, log_fn=_CaptureLog(),
        )
        self.assertIsNone(picked)  # 2633 demoted; no other candidate exists

    def test_demotion_window_preserved_for_live_probes(self):
        # The demotion runs BEFORE the priority sort, so the top-N live-claim
        # window is not burned on a covered candidate (sentry-precedent shape).
        calls: list[int | str] = []

        def probe(n):
            calls.append(n)
            return _FREE

        board = [
            _row(2633, labels=["P2-medium", "status:unclaimed"]),
            _wo(3281, 2633),
            _row(2999, labels=["P2-medium", "status:unclaimed"]),
        ]
        picked = cal.pick_next_issue(
            issues=board, claim_probe=probe, log_fn=_CaptureLog(),
        )
        self.assertEqual(picked, "2999")
        self.assertNotIn(2633, calls)
        self.assertIn(2999, calls)


if __name__ == "__main__":
    unittest.main()
