#!/usr/bin/env python3
"""#3574 Step-1 Preflight Observability Audit — contract pins (Zero-Blindspot).

Founder mandate (#762/#3564 lane): every boot of continuous_agent_loop.py MUST
run an unconditional preflight audit — failed open PRs + open P0 architectural
blockers — surfaced with the Admin priority order (manual P0 > pipeline/CI >
normal). The pre-change audit lived inside the board-available dispatch branch
only: envelope mode, cadence mode, and board-dark boots never saw it, so a red
merge lane could sit unowned behind a different execution path.

Pins:
1. P0 rows surface with numbers and the supreme-priority phrasing; zero-P0
   prints the honest zero line (live board plane).
2. Board-dark ⇒ P0 scan UNSEEN warning — never a zero assurance (U2).
3. Offline ⇒ failed-PR scan honestly skipped (UNSEEN, not zero) and the PR
   scanner is NOT called (no network on the offline plane).
4. Envelope mode routes every line to STDERR — stdout stays byte-empty
   (SPEC §4b pipe/parse purity).
5. Dispatch mode routes to STDOUT (marker-counting contract unchanged).
6. PR-scanner failure ⇒ honest dark line, no raise (the audit never kills
   the dispatch).
7. Source pins: the audit call sits in run_dispatch_cycle AFTER the board
   fetch and BEFORE the envelope block; the old conditional call inside the
   board-available else-branch is gone (unconditional ≠ duplicated).

All tests are offline: list_failed_open_prs is stubbed at the module boundary.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal  # noqa: E402

LOOP_SOURCE = (cal.REPO_ROOT / "scripts" / "agents" / "continuous_agent_loop.py").read_text(
    encoding="utf-8"
)


def _row(number: int, title: str, labels: list[str]) -> dict:
    return {
        "number": number,
        "title": title,
        "labels": [{"name": l} for l in labels],
    }


def _run_audit(**kwargs) -> tuple[str, str]:
    """Run the audit with list_failed_open_prs stubbed; return (stdout, stderr)."""
    kwargs.setdefault("raw_rows", [])
    kwargs.setdefault("board_unavailable", False)
    kwargs.setdefault("offline", False)
    kwargs.setdefault("envelope_mode", False)
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(cal, "list_failed_open_prs", return_value=[]):
        with redirect_stdout(out), redirect_stderr(err):
            cal.preflight_observability_audit(**kwargs)
    return out.getvalue(), err.getvalue()


class TestP0BlockerScan(unittest.TestCase):
    """Plane (1): open P0 architectural blockers, the Admin directive order."""

    def test_p0_rows_surface_with_numbers_and_priority(self) -> None:
        rows = [
            _row(900, "arch: gateway split blocker", ["P0-critical", "repo:open"]),
            _row(901, "normal row", ["P2-medium"]),
        ]
        out, _ = _run_audit(raw_rows=rows)
        self.assertIn("1 open P0 architectural blocker(s)", out)
        self.assertIn("supreme priority", out)
        self.assertIn("#900: arch: gateway split blocker", out)
        self.assertNotIn("#901", out)

    def test_p0_match_is_label_prefix_insensitive_case(self) -> None:
        rows = [_row(905, "p0 lane", ["p0-critical"]), _row(906, "p-something", ["P3-low"])]
        out, _ = _run_audit(raw_rows=rows)
        self.assertIn("#905", out)
        self.assertNotIn("#906", out)

    def test_zero_p0_prints_honest_zero_on_live_board(self) -> None:
        out, _ = _run_audit(raw_rows=[_row(910, "normal", ["P2-medium"])])
        self.assertIn("zero open P0 architectural blockers", out)

    def test_board_dark_never_prints_zero_assurance(self) -> None:
        out, _ = _run_audit(board_unavailable=True)
        self.assertNotIn("zero open P0", out)
        self.assertIn("UNSEEN", out)
        self.assertIn("board plane dark", out)


class TestFailedPrScanRouting(unittest.TestCase):
    """Plane (2): the U2-honest failed-PR scanner, mode-aware channel."""

    def test_offline_skips_pr_scan_and_warns_unseen(self) -> None:
        with mock.patch.object(cal, "report_failed_open_prs") as rep:
            out, _ = _run_audit(offline=True)
        rep.assert_not_called()
        self.assertIn("honestly skipped (--offline)", out)
        self.assertIn("UNSEEN", out)

    def test_scanner_failure_prints_honest_dark_never_raises(self) -> None:
        with mock.patch.object(
            cal, "report_failed_open_prs", side_effect=RuntimeError("gh exploded")
        ):
            out, _ = _run_audit()  # must not raise
        self.assertIn("preflight failed-PR scan error", out)
        self.assertIn("gh exploded", out)

    def test_envelope_mode_routes_to_stderr_stdout_pure(self) -> None:
        fixture = [{"number": 7, "branch": "b", "failed_checks": ["verify"]}]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cal, "list_failed_open_prs", return_value=fixture):
            with redirect_stdout(out), redirect_stderr(err):
                cal.preflight_observability_audit(
                    raw_rows=[_row(900, "p0", ["P0-critical"])],
                    board_unavailable=False,
                    offline=False,
                    envelope_mode=True,
                )
        self.assertEqual(out.getvalue(), "", "SPEC §4b: envelope stdout must stay pure JSON")
        self.assertIn("found 1 open PR(s) with failing checks", err.getvalue())
        self.assertIn("#900: p0", err.getvalue())

    def test_dispatch_mode_routes_to_stdout(self) -> None:
        out, _ = _run_audit(envelope_mode=False)
        self.assertIn("zero open PRs with failing checks", out)


class TestUnconditionalWiring(unittest.TestCase):
    """The blindspot class itself: the wiring must be unconditional."""

    def test_call_site_sits_before_envelope_block(self) -> None:
        # The audit call must precede the envelope branch so --task-envelope
        # boots run it (the pre-change gap: the envelope path returned before
        # any audit).
        call_idx = LOOP_SOURCE.find("preflight_observability_audit(\n        raw_rows=raw")
        self.assertGreater(call_idx, -1, "unconditional audit call missing")
        env_idx = LOOP_SOURCE.find("if envelope_mode:")
        self.assertGreater(env_idx, call_idx, "audit must run BEFORE the envelope branch")
        fetch_idx = LOOP_SOURCE.find("_tower_board_rows()")
        self.assertGreater(call_idx, fetch_idx, "audit must run AFTER the board fetch/fallback")

    def test_old_conditional_call_site_removed(self) -> None:
        # The board-available else-branch must no longer carry its own audit
        # call — unconditional means exactly once, at Step 1.
        self.assertNotIn(
            "report_failed_open_prs(repo=UPSTREAM_REPO, limit=30)\n\n        picked",
            LOOP_SOURCE,
            "the old conditional call inside the else-branch survived",
        )
        self.assertEqual(
            LOOP_SOURCE.count("preflight_observability_audit("),
            2,
            "exactly one definition + one call site",
        )

    def test_reporter_default_channel_unchanged(self) -> None:
        # test_failed_pr_audit_honesty captures STDOUT with no log_fn — the
        # default must stay the stdout log().
        import inspect

        sig = inspect.signature(cal.report_failed_open_prs)
        self.assertIs(sig.parameters["log_fn"].default, None)
        out, _ = self._capture_report_direct([])
        self.assertIn("zero open PRs with failing checks", out)

    def _capture_report_direct(self, stub: object) -> tuple[str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cal, "list_failed_open_prs", return_value=stub):
            with redirect_stdout(out), redirect_stderr(err):
                cal.report_failed_open_prs(repo="r/x", limit=30)
        return out.getvalue(), err.getvalue()


if __name__ == "__main__":
    unittest.main()
