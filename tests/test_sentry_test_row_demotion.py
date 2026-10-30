#!/usr/bin/env python3
"""Pin + behavior: sentry TEST-row demotion in the dispatch pick (U4 family).

Live anatomy witnessed 2026-10-30 15:04Z (GLM Agent 04, Job 486718): the
board carried #3371 "guard(platform): sentry c60 test row
sentry-c60-test-1-small" (body: "Sentry pass c60 connectivity test row -
harmless diagnostics note (GLM Agent 28)"), filed 13:35:32Z — one minute
before its real pass row #3376 (13:36:41Z), because the filer probed the
small-body issue-intake path while the ~9.8KB census body was WAF-blocked
(per the #3380 receipt). The existing stale-sentry demotion did NOT catch
the row: its title lacks the "sentry pass" family marker. So the picker
served it as the top pick and the dispatched solver would burn a full cycle
minting duplicate evidence of a pass already covered in-flight (#3376 +
open receipt WO #3380) — U4's founding class.

Fix: pick_next_issue filters EVERY sentry test row from the candidates in
live mode BEFORE the priority sort (no newest-member exemption — test rows
are pure artifacts; the filer/admin lane owns their disposition). The
judgment is board-local (title-phrase discriminator; zero network). Pure
mode keeps the pre-change label-only contract byte-identical for hermetic
callers — the same boundary the #2794/#3050/#3315 filters ride.

Pins enforced here (zero gh/network dependency):
  1. The live #3371 title is demoted, with the filer/admin disposition note.
  2. Real sentry PASS rows (no "test row" phrase) are never demoted by this
     filter — they stay in the stale-sentry family's jurisdiction.
  3. Rows where "sentry" FOLLOWS "test row" (real tasks ABOUT test-row
     machinery, e.g. "validate test row handling for sentry intake") are
     never demoted.
  4. Bridge mirror rows (🌉 prefix) and non-family rows never demoted.
  5. Malformed rows (None title, non-numeric number, non-dict) never raise
     and are served unchanged.
  6. Live-mode integration: the test row is filtered, real work is served,
     and the demotion is logged.
  7. Pure mode (claim_probe=None) serves the test row — pre-change contract.
  8. Source pin: the demotion block lives inside pick_next_issue (text pin).

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


def _test_row(number: int = 3371) -> dict:
    """The live 2026-10-30 #3371 anatomy (title + bare labels)."""
    return {
        "number": number,
        "title": "guard(platform): sentry c60 test row sentry-c60-test-1-small",
        "labels": [],
    }


def _pass_row(number: int) -> dict:
    return {
        "number": number,
        "title": f"guard(platform): sentry pass 13:33Z — sweep surface FLAPS BACK 12→33 rows",
        "labels": [],
    }


def _row(number: int, title: str | None = None) -> dict:
    return {
        "number": number,
        "title": title or f"report(guard): finding {number}",
        "labels": [],
    }


_LIVE = dict(claim_probe=lambda n: (False, "no active claim on the feedback plane"))


class TestSentryTestRowHelper(unittest.TestCase):
    def test_live_3371_title_demoted(self):
        note = cal._sentry_test_row_note(_test_row(3371))
        self.assertIsNotNone(note)
        self.assertIn("sentry connectivity test row", note or "")
        self.assertIn("U4 anti-stampede demotion", note or "")
        self.assertIn("filer/admin lane owns disposition", note or "")
        self.assertIn("#3371", note or "")

    def test_real_pass_rows_not_demoted(self):
        # No "test row" phrase — the stale-sentry family's jurisdiction, not ours.
        self.assertIsNone(cal._sentry_test_row_note(_pass_row(3376)))
        self.assertIsNone(
            cal._sentry_test_row_note(
                _row(2237, "guard(platform): provider sentry pass 18:43Z — 7/8 alive")
            )
        )

    def test_sentry_after_test_row_never_demoted(self):
        # Real tasks ABOUT test-row machinery must keep flowing to solvers.
        for title in (
            "guard(platform): validate test row handling for sentry intake",
            "guard(platform): fix test row dedup in sentry filer",
        ):
            self.assertIsNone(
                cal._sentry_test_row_note(_row(4000, title)),
                f"machinery task must not be demoted: {title!r}",
            )

    def test_non_family_titles_never_demoted(self):
        for title in (
            "🌉 Bridge Work Order — SENTRY c60 test row mirror (docs-only)",
            "report(guard): sentry test row cleanup",
            "guard(closure): closure-time live-state gate - R79",
            "row 3371",
        ):
            self.assertIsNone(
                cal._sentry_test_row_note(_row(3371, title)),
                f"non-family title must not be demoted: {title!r}",
            )

    def test_malformed_rows_fail_open(self):
        self.assertIsNone(cal._sentry_test_row_note({"number": 1}))
        self.assertIsNone(cal._sentry_test_row_note({"title": None, "number": 1}))
        self.assertIsNone(
            cal._sentry_test_row_note(
                {"title": "guard(platform): sentry c60 test row x", "number": "abc"}
            )
        )
        # Never raises even on junk containers.
        cal._sentry_test_row_note({"title": 42, "number": None})  # type: ignore[dict-item]


class _LeaseIsolated(unittest.TestCase):
    def setUp(self):
        patcher = unittest.mock.patch.object(
            cal, "load_issue_lease_store", lambda path=None: {}
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class TestPickIntegration(_LeaseIsolated):
    def test_test_row_filtered_real_work_served(self):
        board = [
            _test_row(3371),
            _pass_row(3376),  # newest open pass — carries the sentinel duty
            _row(3000),
        ]
        # #3371 filtered; among the survivors the age-first sort serves the
        # lowest number (real work #3000 outranks sentinel #3376 naturally).
        self.assertEqual(cal.pick_next_issue(issues=board, **_LIVE), "3000")

    def test_test_row_alone_leaves_next_work(self):
        board = [_test_row(3371), _row(3401)]
        self.assertEqual(cal.pick_next_issue(issues=board, **_LIVE), "3401")

    def test_demotion_logged(self):
        logs: list[str] = []
        cal.pick_next_issue(
            issues=[_test_row(3371), _row(3401)],
            **_LIVE,
            log_fn=lambda level, msg: logs.append(f"{level} {msg}"),
        )
        self.assertTrue(any("sentry-test-row demotion: #3371" in m for m in logs))

    def test_pure_mode_keeps_pre_change_contract(self):
        """claim_probe=None ⇒ label-only pick, zero demotion (hermetic callers)."""
        board = [_test_row(3371), _row(3401)]
        self.assertEqual(cal.pick_next_issue(issues=board), "3371")


class TestSourcePin(unittest.TestCase):
    def test_demotion_block_lives_in_pick_next_issue(self):
        src = Path(cal.__file__).read_text(encoding="utf-8")
        self.assertIn("sentry-test-row demotion", src)
        self.assertIn("_sentry_test_row_note(cand)", src)


if __name__ == "__main__":
    unittest.main()
