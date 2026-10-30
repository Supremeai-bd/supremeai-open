#!/usr/bin/env python3
"""U6 Zero-Recurrence guard — PR-audit board-plane partial assurance (#3772).

The 2026-10-31 defect (viewer-era RBAC): P0 #3663's correct remediation made
the anonymous lane role ``viewer``, which permanently darkened the failed-PR
audit's PR planes — gh is absent on the documented runtime AND tower
``github.list_prs`` answers Forbidden. The reporter then fell straight to the
⚠ dark line on every zero-credential boot, so the landing cohort (rows in
gates) stayed invisible to operators — scout #3772 recorded this as the
actionable agent-side half of its disposition (option b: update the loop's
scan-B to a viewer-allowed surface).

Contract pinned here:

1. Dark PR-plane + board fallback success ⇒ 🔍 partial-assurance line carrying
   the in-gates count (bridge:in-gates label) and the board note; NO "✅" and
   NO "zero open PRs" substring can ever ride the partial branch (an in-gates
   count cannot classify per-PR checks — U2 honesty pin survives).
2. Dark PR-plane + board fallback failure ⇒ the original ⚠ dark line (now
   carrying both failure notes); still honest UNSEEN.
3. The board probe is never allowed to raise or hang into the audit — an
   exploding probe degrades to the honest dark line.
4. Label-shape tolerance: rows may carry dict labels (tower fallback shape)
   or string labels; only the exact "bridge:in-gates" name counts.
5. Caller contract unchanged: returns a list in every branch.

All tests are offline: list_failed_open_prs / _tower_open_prs /
_tower_board_rows are stubbed at the module boundary — zero network, zero gh
dependency.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal  # noqa: E402

PR_NOTE = "tower PR probe: RBAC-forbidden (permanent access-control state)"


def _capture_report(
    tower_stub: object = (None, PR_NOTE),
    board_stub: object = None,
    list_stub: object = None,
) -> tuple[list, str]:
    """Run report_failed_open_prs with dark PR planes and the board probe stubbed."""
    buf = io.StringIO()
    with mock.patch.object(cal, "list_failed_open_prs", return_value=list_stub):
        with mock.patch.object(cal, "_tower_open_prs", return_value=tower_stub):
            with mock.patch.object(cal, "_tower_board_rows", return_value=board_stub):
                with redirect_stdout(buf):
                    failed = cal.report_failed_open_prs(repo="r/x", limit=30)
    return failed, buf.getvalue()


def _board_row(number: int, labels: list) -> dict:
    return {"number": number, "title": f"row {number}", "labels": labels}


class TestBoardPartialAssurance(unittest.TestCase):
    """Board fallback success ⇒ landing cohort visible, honesty pins survive."""

    def test_partial_line_carries_in_gates_count(self) -> None:
        rows = [
            _board_row(1, [{"name": "bridge:in-gates"}]),
            _board_row(2, [{"name": "bridge:receipt"}]),
            _board_row(3, [{"name": "bridge:in-gates"}, {"name": "report"}]),
            _board_row(4, []),
        ]
        failed, out = _capture_report(board_stub=(rows, "tower board fallback: 4 rows"))
        self.assertEqual(failed, [])
        self.assertIn("Read-only failed PR audit", out)
        self.assertIn("PR-plane dark (viewer RBAC", out)
        self.assertIn("board-plane partial assurance via tower board fallback: 4 rows", out)
        self.assertIn("2 row(s) in gates", out)
        self.assertIn("UNSEEN", out)
        self.assertNotIn("✅", out)
        self.assertNotIn("zero open PRs", out)

    def test_zero_in_gates_still_partial_never_clean(self) -> None:
        # Board alive but 0 in-gates rows: the cohort is empty, yet per-PR
        # checks are still unseen — no ✅/zero-assurance may appear.
        rows = [_board_row(1, [{"name": "bridge:receipt"}])]
        failed, out = _capture_report(board_stub=(rows, "tower board fallback: 1 rows"))
        self.assertEqual(failed, [])
        self.assertIn("0 row(s) in gates", out)
        self.assertIn("UNSEEN", out)
        self.assertNotIn("✅", out)
        self.assertNotIn("zero open PRs", out)

    def test_string_label_rows_counted(self) -> None:
        # Shape tolerance: board rows with plain-string labels (gh shape).
        rows = [
            _board_row(1, ["bridge:in-gates"]),
            _board_row(2, ["report"]),
        ]
        failed, out = _capture_report(board_stub=(rows, "tower board fallback: 2 rows"))
        self.assertEqual(failed, [])
        self.assertIn("1 row(s) in gates", out)

    def test_exact_label_name_required(self) -> None:
        # A near-miss label must not inflate the count.
        rows = [_board_row(1, [{"name": "bridge:in-gates-old"}])]
        failed, out = _capture_report(board_stub=(rows, "tower board fallback: 1 rows"))
        self.assertEqual(failed, [])
        self.assertIn("0 row(s) in gates", out)


class TestBoardFallbackFailure(unittest.TestCase):
    """Board failure ⇒ the original honest dark line, never a crash."""

    def test_both_planes_dark_keep_dark_line(self) -> None:
        failed, out = _capture_report(
            board_stub=([], "tower board fallback failed (URLError)")
        )
        self.assertEqual(failed, [])
        self.assertIn("plane dark", out)
        self.assertIn(PR_NOTE, out)
        self.assertIn("tower board fallback failed (URLError)", out)
        self.assertIn("UNSEEN", out)
        self.assertNotIn("✅", out)

    def test_exploding_board_probe_never_raises_into_audit(self) -> None:
        buf = io.StringIO()
        with mock.patch.object(cal, "list_failed_open_prs", return_value=None):
            with mock.patch.object(cal, "_tower_open_prs", return_value=(None, PR_NOTE)):
                with mock.patch.object(
                    cal, "_tower_board_rows", side_effect=RuntimeError("probe exploded")
                ):
                    with redirect_stdout(buf):
                        failed = cal.report_failed_open_prs(repo="r/x", limit=30)
        self.assertEqual(failed, [])
        self.assertIn("UNSEEN", buf.getvalue())
        self.assertIn("board probe raised (RuntimeError)", buf.getvalue())


class TestWiringContract(unittest.TestCase):
    """Structural pins so the new layer cannot silently regress."""

    def test_caller_returns_list_in_every_branch(self) -> None:
        for board_stub in (([], "n"), ([_board_row(1, [{"name": "bridge:in-gates"}])], "n"), None):
            failed, _ = _capture_report(board_stub=board_stub)
            self.assertIsInstance(failed, list)

    def test_board_probe_reached_from_dark_branch(self) -> None:
        source = Path(cal.__file__).read_text(encoding="utf-8")
        self.assertIn("_tower_board_rows(timeout_s=20.0)", source)
        self.assertIn("board-plane partial assurance", source)
        self.assertIn('== "bridge:in-gates"', source)

    def test_board_probe_is_viewer_allowed_surface(self) -> None:
        # The probe must ride the same viewer-allowed transport as the board
        # fallback (bridge.work_queue), not another github.* read.
        source = Path(cal.__file__).read_text(encoding="utf-8")
        self.assertIn('"bridge.work_queue"', source)


if __name__ == "__main__":
    unittest.main()
