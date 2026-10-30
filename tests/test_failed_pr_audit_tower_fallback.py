#!/usr/bin/env python3
"""U6 Zero-Recurrence guard — PR-audit tower fallback (R78-mirror symmetry).

The 2026-10-31 defect: R78 gave the board path a gh-absent tower fallback,
but the failed-PR audit path kept collapsing into plane-dark on every boot of
the documented gh-less external-agent runtime — live proof: the same run
printed "plane dark — open PRs UNSEEN" while tower's github.list_prs showed
10 open PRs (including an 8.5h unmerged receipt-PR pile: the dark plane was
also hiding landing-train state from operators).

Contract pinned here (mirrors test_failed_pr_audit_honesty's philosophy):

1. Dark plane + tower fallback success ⇒ 🔍 revived line with per-PR census;
   per-PR check status stays UNSEEN (tower payload has no statusCheckRollup);
   NO "✅" and NO "zero open PRs" substring can ever ride the revived branch
   (failing subset is unknown, not certified clean).
2. Dark plane + tower fallback failure ⇒ the original ⚠ dark line (with the
   fallback note appended); still honest UNSEEN.
3. The fallback probe is never allowed to raise or hang into the audit — an
   exploding probe degrades to the honest dark line.
4. Caller contract unchanged: returns a list in every branch.
5. Default channel pin: log_fn default stays None (stdout log), matching
   test_preflight_observability_audit's reporter-channel pin.

All tests are offline: _tower_open_prs / list_failed_open_prs are stubbed at
the module boundary — zero network, zero gh dependency.
"""

from __future__ import annotations

import inspect
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal  # noqa: E402


def _capture_report(tower_stub: object, list_stub: object = None) -> tuple[list, str]:
    """Run report_failed_open_prs with the dark plane + tower probe stubbed.

    #3772 evolution: the dark branch now also runs the board-plane assurance
    layer, so this helper stubs it dark too — the "fallback failure ⇒ dark
    line" contracts below stay byte-identical without any network access.
    """
    buf = io.StringIO()
    with mock.patch.object(cal, "list_failed_open_prs", return_value=list_stub):
        with mock.patch.object(cal, "_tower_open_prs", return_value=tower_stub):
            with mock.patch.object(
                cal, "_tower_board_rows", return_value=([], "board probe stubbed dark")
            ):
                with redirect_stdout(buf):
                    failed = cal.report_failed_open_prs(repo="r/x", limit=30)
    return failed, buf.getvalue()


class TestTowerPrFallbackRevived(unittest.TestCase):
    """Fallback success ⇒ plane census visible, honesty pins survive."""

    def test_revived_line_shows_census_and_unseen(self) -> None:
        rows = [
            {"number": 3546, "title": "feat(bridge): triage(ci) …", "url": "https://github.com/r/x/pull/3546"},
            {"number": 3540, "title": "feat(bridge): fix(ci) …", "url": "https://github.com/r/x/pull/3540"},
        ]
        failed, out = _capture_report((rows, "tower PR fallback: 2 open PR(s) visible"))
        self.assertEqual(failed, [])
        self.assertIn("Read-only failed PR audit", out)
        self.assertIn("revived via tower PR fallback: 2 open PR(s) visible", out)
        self.assertIn("UNSEEN", out)
        self.assertIn("PR #3546", out)
        self.assertIn("PR #3540", out)
        # U2: a revived plane must never masquerade as a certified-clean one.
        self.assertNotIn("✅", out)
        self.assertNotIn("zero open PRs", out)

    def test_revived_with_zero_visible_rows_still_unseen(self) -> None:
        # Tower alive but 0 open PRs: check status is STILL unseen (the tower
        # payload cannot classify checks) — no ✅/zero-assurance may appear.
        failed, out = _capture_report(([], "tower PR fallback: 0 open PR(s) visible"))
        self.assertEqual(failed, [])
        self.assertIn("UNSEEN", out)
        self.assertNotIn("✅", out)
        self.assertNotIn("zero open PRs", out)


class TestTowerPrFallbackDark(unittest.TestCase):
    """Fallback failure ⇒ the original honest dark line, never a crash."""

    def test_fallback_failure_keeps_dark_line_with_note(self) -> None:
        failed, out = _capture_report((None, "tower PR fallback failed (URLError)"))
        self.assertEqual(failed, [])
        self.assertIn("plane dark", out)
        self.assertIn("tower PR fallback failed (URLError)", out)
        self.assertIn("UNSEEN", out)
        self.assertNotIn("✅", out)

    def test_exploding_probe_never_raises_into_audit(self) -> None:
        # The probe itself exploding must degrade to the honest dark line.
        buf = io.StringIO()
        with mock.patch.object(cal, "list_failed_open_prs", return_value=None):
            with mock.patch.object(
                cal, "_tower_open_prs", side_effect=RuntimeError("probe exploded")
            ):
                with redirect_stdout(buf):
                    failed = cal.report_failed_open_prs(repo="r/x", limit=30)
        self.assertEqual(failed, [])
        self.assertIn("UNSEEN", buf.getvalue())


class TestTowerPrFailureClassification(unittest.TestCase):
    """U6 Zero-Recurrence guard — RBAC-denial must never read as "no JSON list".

    Live defect (GLM Agent 24, 2026-10-31T20:24Z): on the anonymous/viewer
    lane tower's github.list_prs answers with a JSON-RPC-OK envelope whose
    MCP result carries isError=true and content[0].text =
    "Forbidden: role 'viewer' has no repository read access for
    'github.list_prs'." The old probe ignored isError, failed to parse the
    denial text as a JSON list, and reported the false cause note
    "tower PR payload carried no JSON list" — masking a permanent
    access-control state as a payload/format problem on every gh-absent
    boot, and baiting later agents into pointless retries (U6 violation).
    """

    LIVE_DENIAL_TEXT = (
        "Forbidden: role 'viewer' has no repository read access for 'github.list_prs'."
    )

    def test_rbac_denial_gets_truthful_permanent_state_note(self) -> None:
        note = cal._classify_tower_pr_failure(self.LIVE_DENIAL_TEXT)
        self.assertIn("RBAC-forbidden", note)
        self.assertIn("permanent access-control state", note)
        self.assertIn(self.LIVE_DENIAL_TEXT, note)
        # The old false-cause note must never ride an RBAC denial again.
        self.assertNotIn("no JSON list", note)

    def test_rbac_denial_shape_variants_classified(self) -> None:
        for shape in (
            "Forbidden: role 'viewer' has no repository read access for 'github.list_prs'.",
            "rbac denied: role 'viewer' lacks access",
            "Forbidden",
        ):
            note = cal._classify_tower_pr_failure(shape)
            self.assertIn("RBAC-forbidden", note, shape)

    def test_rpc_error_gets_tool_call_error_note(self) -> None:
        note = cal._classify_tower_pr_failure("Tool github.list_prs not found")
        self.assertIn("tower PR tool-call error:", note)
        self.assertIn("Tool github.list_prs not found", note)
        self.assertNotIn("no JSON list", note)

    def test_empty_error_text_gets_generic_tool_call_note(self) -> None:
        note = cal._classify_tower_pr_failure("")
        self.assertIn("no error text returned", note)

    def test_probe_wiring_pins_is_error_branch(self) -> None:
        # Structural pins: if someone removes the isError/RPC-error handling
        # from _probe() again, these trip before the false note can return.
        source = Path(cal.__file__).read_text(encoding="utf-8")
        self.assertIn("result.get(\"isError\")", source)
        self.assertIn("_classify_tower_pr_failure(", source)
        self.assertIn("rpc_error_msg", source)


class TestFallbackWiringContract(unittest.TestCase):
    """Structural pins so the symmetry cannot silently regress."""

    def test_caller_returns_list_in_every_branch(self) -> None:
        for stub in (([], "n"), (None, "n"), ([{"number": 1}], "n")):
            failed, _ = _capture_report(stub)
            self.assertIsInstance(failed, list)

    def test_default_channel_stays_stdout_log(self) -> None:
        sig = inspect.signature(cal.report_failed_open_prs)
        self.assertIs(sig.parameters["log_fn"].default, None)

    def test_probe_helper_exists_beside_board_fallback(self) -> None:
        source = Path(cal.__file__).read_text(encoding="utf-8")
        self.assertIn("def _tower_open_prs(", source)
        # The fallback must be reached from the dark branch of the reporter.
        self.assertIn("_tower_open_prs(limit=limit)", source)


if __name__ == "__main__":
    unittest.main()
