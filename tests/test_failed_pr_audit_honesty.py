#!/usr/bin/env python3
"""U6 Zero-Recurrence guard — failed-PR audit honesty (dark ≠ zero).

The 2026-10-31 defect: on a gh-absent runtime (documented external-agent
runtime) the dispatch-path PR audit printed
"✅ Read-only failed PR audit: zero open PRs with failing checks."
while the very same run honestly reported "gh CLI not found on PATH" on the
board path. Error-space (query failed ⇒ PRs UNSEEN) had collapsed into
result-space (live query ⇒ zero failing) inside list_failed_open_prs(): both
returned [], so the reporter emitted a false-assurance line (U2 violation,
same class run_verify's docstring documents for unconditional PASS).

These tests pin the root-cause contract so the collapse can never recur:

1. run_cmd failure (gh absent ⇒ exit 127) ⇒ list_failed_open_prs() returns
   None (plane dark), never [].
2. Unparseable stdout on exit 0 ⇒ None (honest ignorance), never [].
3. Live plane with a real empty result ⇒ [] (true zero) — pre-change behavior
   preserved for the honest path.
4. Live plane with failing checks ⇒ parsed list, shape unchanged.
5. report_failed_open_prs() NEVER emits the "✅ … zero …" line when the plane
   is dark — it emits the UNSEEN warning instead.
6. Caller signature unchanged: report_failed_open_prs() still returns a list
   in every branch (dispatch-path call site relies on no return value, but
   the contract stays list-typed).

All tests are offline: run_cmd / list_failed_open_prs are stubbed at the
module boundary — zero network, zero gh dependency.
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


def _capture_report(repo_stub: object) -> tuple[list, str]:
    """Run report_failed_open_prs with list_failed_open_prs stubbed.

    #3772 evolution: the dark branch now also runs the board-plane assurance
    layer, so this helper stubs it dark — the U2 pins below stay honest and
    hermetic (no board probe reaches the network from these tests).
    """
    buf = io.StringIO()
    with mock.patch.object(cal, "list_failed_open_prs", return_value=repo_stub):
        with mock.patch.object(
            cal, "_tower_board_rows", return_value=([], "board probe stubbed dark")
        ):
            with redirect_stdout(buf):
                failed = cal.report_failed_open_prs(repo="r/x", limit=30)
    return failed, buf.getvalue()


class TestListFailedOpenPrsHonesty(unittest.TestCase):
    """Root-cause pin: error-space (None) vs result-space ([]) separation."""

    def test_gh_absent_returns_none_never_empty_list(self) -> None:
        # run_cmd's documented FileNotFoundError contract: (127, "", "Binary not found…")
        with mock.patch.object(cal, "run_cmd", return_value=(127, "", "Binary not found: 'gh'")):
            self.assertIsNone(cal.list_failed_open_prs(repo="r/x"))

    def test_nonzero_exit_returns_none(self) -> None:
        # Any query failure (auth, network, rate-limit) is plane-dark, not clean.
        with mock.patch.object(cal, "run_cmd", return_value=(1, "", "gh: auth error")):
            self.assertIsNone(cal.list_failed_open_prs(repo="r/x"))

    def test_unparseable_stdout_returns_none(self) -> None:
        # Exit 0 but garbage stdout ⇒ result unknown ⇒ honest ignorance (None).
        with mock.patch.object(cal, "run_cmd", return_value=(0, "not json at all", "")):
            self.assertIsNone(cal.list_failed_open_prs(repo="r/x"))

    def test_live_empty_result_returns_true_zero(self) -> None:
        # gh JSON mode prints "[]" for an empty result — the honest zero path
        # keeps its pre-change [] return (behavior unchanged).
        with mock.patch.object(cal, "run_cmd", return_value=(0, "[]", "")):
            self.assertEqual(cal.list_failed_open_prs(repo="r/x"), [])

    def test_live_failing_prs_shape_unchanged(self) -> None:
        payload = [
            {
                "number": 42,
                "title": "fix(open): t",
                "headRefName": "bridge/task",
                "url": "https://github.com/r/x/pull/42",
                "statusCheckRollup": [
                    {"name": "verify", "conclusion": "FAILURE"},
                    {"name": "lint", "conclusion": "SUCCESS"},
                ],
            },
            {
                "number": 43,
                "title": "docs: t",
                "headRefName": "docs/task",
                "url": "https://github.com/r/x/pull/43",
                "statusCheckRollup": [{"name": "ci", "conclusion": "SUCCESS"}],
            },
        ]
        import json as _json

        with mock.patch.object(
            cal, "run_cmd", return_value=(0, _json.dumps(payload), "")
        ):
            failed = cal.list_failed_open_prs(repo="r/x")
        self.assertIsInstance(failed, list)
        assert failed is not None
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["number"], 42)
        self.assertEqual(failed[0]["failed_checks"], ["verify"])

    def test_empty_stdout_with_exit_zero_is_true_zero(self) -> None:
        # Defensive pin of the pre-change branch: exit 0 + blank stdout stays []
        # (true-zero), it must NOT regress into None.
        with mock.patch.object(cal, "run_cmd", return_value=(0, "", "")):
            self.assertEqual(cal.list_failed_open_prs(repo="r/x"), [])


class TestReportFailedOpenPrsHonesty(unittest.TestCase):
    """U2 pin: the ✅-zero line can never ride on a dark plane."""

    def test_dark_plane_never_prints_zero_assurance(self) -> None:
        failed, out = _capture_report(None)
        self.assertEqual(failed, [])
        self.assertNotIn("✅", out)
        self.assertNotIn("zero open PRs", out)
        self.assertIn("UNSEEN", out)
        self.assertIn("Read-only failed PR audit", out)

    def test_live_zero_still_prints_zero_assurance(self) -> None:
        failed, out = _capture_report([])
        self.assertEqual(failed, [])
        self.assertIn("zero open PRs with failing checks", out)

    def test_live_failures_still_print_findings(self) -> None:
        fixture = [
            {
                "number": 7,
                "branch": "agent/task",
                "failed_checks": ["verify", "guard"],
            }
        ]
        failed, out = _capture_report(fixture)
        self.assertEqual(failed, fixture)
        self.assertIn("found 1 open PR(s) with failing checks", out)
        self.assertIn("PR #7 (agent/task): [verify, guard]", out)

    def test_caller_signature_returns_list_in_every_branch(self) -> None:
        # The dispatch-path call site (run_dispatch_cycle) uses no return value,
        # but the contract stays list-typed in all three branches.
        for stub in (None, [], [{"number": 1, "branch": "b", "failed_checks": ["c"]}]):
            failed, _ = _capture_report(stub)
            self.assertIsInstance(failed, list)


if __name__ == "__main__":
    unittest.main()
