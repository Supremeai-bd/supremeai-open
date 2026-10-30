#!/usr/bin/env python3
"""Pin + behavior: stale-sentry demotion in the dispatch pick (#3050 family).

Live anatomy witnessed 2026-10-30 09:25Z (cycle 48, job 478334): the board
carried 20 open platform sentry passes (#2237..#3111, two title spellings,
label sets [] / status:unclaimed / platform-guardian+sentry). The age-first
priority sort served the OLDEST fossil — #2237, a 2-day-old pass — as the top
pick, while the live sentinel #3111 (that cycle's first-hand TELEGRAM-PRIMARY
DOWN finding) sorted last. Every fresh agent process re-offers the same fossil
(picker dedup is process-scoped, a45), burning picks on report-only rows whose
premise ("you are looking at the freshest evidence") is false.

Fix: pick_next_issue filters superseded family members from the candidates
BEFORE the priority sort, on the live path only (claim_probe wired) — the
judgment is board-local (max issue number among open rows sharing the family
shape; zero network, unlike the #3050 CI-incident probe). Pure mode keeps the
pre-change label-only contract byte-identical for hermetic callers — the same
boundary the #2794/#3050 probes ride.

Pins enforced here (zero gh/network dependency):
  1. Non-family titles are never demoted (bridge mirror rows carrying the
     words "sentry pass" do NOT start with the guard(platform): prefix).
  2. Both series spellings ("sentry pass", "provider sentry pass") join the
     family.
  3. Oldest fossil demoted; newest member served (pick integration, live
     mode): real work outranks the sentinel by natural sort order.
  4. A claimed newest sibling (excluded from candidates) still supersedes —
     the sentinel duty follows the newest OPEN pass.
  5. Only open rows compare: with no newer open sibling, the lone pass is
     served (fail-open).
  6. Malformed rows (None title, non-numeric number, non-dict entries) never
     raise and are served unchanged.
  7. Pure mode (claim_probe=None) serves the fossil — pre-change contract.
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


def _sentry(number: int, provider: bool = False, labels: list[str] | None = None) -> dict:
    stamp = f"2026-10-28 18:43Z" if provider else f"{8 + number % 10:02d}:45Z"
    kind = "provider sentry pass" if provider else "sentry pass"
    return {
        "number": number,
        # (n=…) suffix: production pass rows carry real distinct timestamps, so
        # byte-identical titles never occur in the family — the duplicate-twin
        # pick guard (U5) treats exact-title siblings as one finding. Fixture
        # titles stay prefix-conformant while being number-unique.
        "title": f"guard(platform): {kind} {stamp} — 7/8 alive (v0 EXCLUDED); sweep 31/33 (n={number})",
        "labels": [{"name": name} for name in (labels or [])],
    }


def _row(number: int, title: str | None = None, labels: list[str] | None = None) -> dict:
    return {
        "number": number,
        "title": title or f"report(guard): finding {number}",
        "labels": [{"name": name} for name in (labels or [])],
    }


_LIVE = dict(claim_probe=lambda n: (False, "no active claim on the feedback plane"))


class TestSentryFamilyHelpers(unittest.TestCase):
    def test_non_family_titles_never_demoted(self):
        newest = 3111
        for title in (
            "🌉 Bridge Work Order — Closure record for #2201 (docs-only): gen-8 provider sentry pass 2026",
            "report(guard): #2557 post-closure verification",
            "guard(closure): closure-time live-state gate - R79/#2925 Option A",
            "guard(platform) sentry pass 08:45Z",  # missing colon — different shape
            "row 3001",
        ):
            item = {"number": 2237, "title": title}
            self.assertIsNone(
                cal._sentry_superseded_note(item, newest),
                f"non-family title must not be demoted: {title!r}",
            )

    def test_both_spellings_join_family(self):
        newest = 3111
        for provider in (False, True):
            note = cal._sentry_superseded_note(_sentry(2237, provider=provider), newest)
            self.assertIsNotNone(note, f"provider={provider} spelling must join the family")
            self.assertIn("#3111", note or "")
            self.assertIn("stale-sentry demotion", note or "")

    def test_newest_member_served(self):
        self.assertIsNone(cal._sentry_superseded_note(_sentry(3111), 3111))

    def test_no_newer_open_sibling_serves(self):
        self.assertIsNone(cal._sentry_superseded_note(_sentry(2237), None))
        self.assertIsNone(cal._sentry_superseded_note(_sentry(2237), 2237))

    def test_malformed_rows_fail_open(self):
        self.assertIsNone(cal._sentry_superseded_note({"number": 1}, 3111))
        self.assertIsNone(cal._sentry_superseded_note({"title": None, "number": 1}, 3111))
        self.assertIsNone(
            cal._sentry_superseded_note({"title": "guard(platform): sentry pass x", "number": "abc"}, 3111)
        )
        self.assertIsNone(cal._sentry_pass_newest_open([None, "row", 42]))  # type: ignore[list-item]
        self.assertIsNone(
            cal._sentry_pass_newest_open([{"title": "guard(platform): sentry pass x", "number": "abc"}])
        )

    def test_newest_open_computed_over_all_rows(self):
        board = [
            _sentry(2237, provider=True),
            _sentry(2271),
            _row(3000),
            _sentry(3111),
            {"title": "🌉 Bridge Work Order — gen-8 provider sentry pass mirror", "number": 3126},
        ]
        self.assertEqual(cal._sentry_pass_newest_open(board), 3111)


class _LeaseIsolated(unittest.TestCase):
    def setUp(self):
        patcher = unittest.mock.patch.object(
            cal, "load_issue_lease_store", lambda path=None: {}
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class TestPickIntegration(_LeaseIsolated):
    def test_fossils_filtered_real_work_served(self):
        board = [
            _sentry(2237, provider=True, labels=["status:unclaimed"]),
            _sentry(2271, labels=["status:unclaimed"]),
            _sentry(2274, provider=True, labels=["platform-guardian", "sentry"]),
            _row(3000),
            _sentry(3111),
        ]
        self.assertEqual(cal.pick_next_issue(issues=board, **_LIVE), "3000")

    def test_newest_sentinel_served_when_only_family_exists(self):
        board = [_sentry(2237), _sentry(2271), _sentry(3111)]
        self.assertEqual(cal.pick_next_issue(issues=board, **_LIVE), "3111")

    def test_claimed_newest_sibling_still_supersedes(self):
        board = [
            _sentry(2237),
            _sentry(3111, labels=["status:claimed"]),
            _row(3000),
        ]
        # #3111 is excluded from candidates (claimed) but still open on the
        # board — the fossil must not resurface just because the sentinel is
        # actively worked.
        self.assertEqual(cal.pick_next_issue(issues=board, **_LIVE), "3000")

    def test_lone_pass_without_newer_sibling_served(self):
        board = [_sentry(2237), _row(3000)]
        self.assertEqual(cal.pick_next_issue(issues=board, **_LIVE), "2237")

    def test_pure_mode_keeps_pre_change_contract(self):
        """claim_probe=None ⇒ label-only pick, zero demotion (hermetic callers)."""
        board = [_sentry(2237), _sentry(3111), _row(3000)]
        self.assertEqual(cal.pick_next_issue(issues=board), "2237")


class TestSourcePin(unittest.TestCase):
    def test_demotion_block_lives_in_pick_next_issue(self):
        src = Path(cal.__file__).read_text(encoding="utf-8")
        self.assertIn("stale-sentry demotion", src)
        self.assertIn("_sentry_pass_newest_open(issues", src)


if __name__ == "__main__":
    unittest.main()
