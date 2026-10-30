#!/usr/bin/env python3
"""Pin + behavior: born-duplicate twin rows never mint duplicate dispatches.

Live 2026-10-31 (GLM Agent 09, Job 486738): the scout filer pipeline filed
byte-identical sibling rows #3698 + #3699 (same title, 21s apart — filer
retry/race). The loop dispatched the unclaimed twin #3699 while the claimed
twin #3698's work was already in flight → two agents, one finding, duplicate
receipts (U5 anti-stampede violation). No pick-side filter caught it: the
#2794 claim probe passes on an as-yet-unclaimed twin, the #3315 coverage probe
needs a citing receipt (none exists for a fresh refile), and the sentry
filters are family-specific.

Root cause: the filing plane got an exact-title dedup in #1997
(``create_blocker_issue.find_existing_blocker``), but the dispatch pick never
received the symmetric half — the same asymmetric-enforcement class as the
R61/#2318 board-lane vs PR-audit-lane U2 split (cycle-2 fix). One defect
class, two lanes, only one lane guarded.

Fix: ``_duplicate_twin_note()`` + a board-local demotion inside
``pick_next_issue`` (live mode only, same boundary as the sentry/coverage
filters). One identical-title family gets exactly ONE dispatch: a twin that
is claimed/leased means the finding is in flight; otherwise the OLDEST
dispatchable sibling is canonical and younger refiles are filer artifacts.
Fail-open, never-raise, window-preserving (demoted rows never burn a
pre-verify probe slot), ``--issue N`` override untouched.

Pins enforced here (zero gh/network dependency — in-memory boards):
  1. AST pin: ``_duplicate_twin_note`` exists as a module function.
  2. Wiring pin: "duplicate-twin demotion" rides inside pick_next_issue (live
     mode), and the loop source carries the demotion marker.
  3. Live shape: claimed twin #3698 + unclaimed twin #3699 + real row ⇒ #3699
     demoted (never probed), #3700 picked.
  4. Older-canonical: both twins unclaimed ⇒ younger demoted, older picked.
  5. Family of three ⇒ only the oldest survives.
  6. No twin ⇒ pick unchanged (no over-exclusion).
  7. Closed older sibling ⇒ younger refile servable (resolution happened).
  8. Case/whitespace variants of the same title still matched.
  9. Excluded-lane older twin (bridge:receipt) does NOT cover a claimable
     younger sibling — excluded rows can never receive the dispatch.
 10. Local lease on the twin ⇒ demoted; expired lease ⇒ not demoted.
 11. Malformed rows (missing title / non-numeric number) fail open.
 12. Pure mode (claim_probe=None): byte-identical pre-change contract.

Dual-mode: runs under both `python3 -m unittest` and `pytest`.
"""

from __future__ import annotations

import ast
import sys
import time
import unittest
import unittest.mock
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal

LOOP_SRC = (_ROOT / "scripts" / "agents" / "continuous_agent_loop.py").read_text(
    encoding="utf-8"
)

_FREE = (False, "no active claim on the feedback plane")

# The live #3698/#3699 filer-race shape (2026-10-30T19:08:53Z / 19:09:14Z).
_LIVE_TWIN_TITLE = (
    "scout(ops): post-sync primary container boots degraded-live with 4 residual "
    "error classes - 3 missing production secrets (BE-13), Supabase SSL "
    "self-signed chain + schema drift, Upstash 500k request quota exhausted "
    "(live probe 19:05-19:12Z 10-30)"
)


def _row(number: int, title: str, labels: list[str] | None = None) -> dict:
    return {
        "number": number,
        "title": title,
        "labels": [{"name": name} for name in (labels or [])],
        "state": "open",
    }


def _claimed_row(number: int, title: str) -> dict:
    return _row(number, title, labels=["status:claimed"])


def _real_row(number: int) -> dict:
    return _row(number, f"genuinely different work {number}")


class _LeaseIsolated(unittest.TestCase):
    """Isolate pick_next_issue from THIS runtime's local dispatch-lease state.

    Same hermetic boundary as test_pick_excludes_receipt_wos.py: ambient
    scheduler state must never contaminate pick assertions.
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


class TestTwinGuardSourcePins(unittest.TestCase):
    def test_helper_function_exists(self):
        """AST pin: ``_duplicate_twin_note`` is a module-level def."""
        tree = ast.parse(LOOP_SRC)
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertIn("_duplicate_twin_note", names)

    def test_wiring_marker_present(self):
        """The demotion rides inside the pick pipeline (marker string)."""
        self.assertIn("duplicate-twin demotion", LOOP_SRC)
        self.assertIn("_duplicate_twin_note(", LOOP_SRC)


class TestDuplicateTwinDemotion(_LeaseIsolated):
    def test_live_shape_claimed_twin_demotes_unclaimed_twin(self):
        """The exact 2026-10-31 shape: #3698 claimed, #3699 unclaimed twin —
        #3699 must be demoted before any probe burns, real row picked."""
        calls: list[int | str] = []

        def probe(n):
            calls.append(n)
            return _FREE

        board = [
            _claimed_row(3698, _LIVE_TWIN_TITLE),
            _row(3699, _LIVE_TWIN_TITLE),
            _real_row(3700),
        ]
        log = _CaptureLog()
        picked = cal.pick_next_issue(
            issues=board, claim_probe=probe, log_fn=log
        )
        self.assertEqual(picked, "3700")
        self.assertNotIn(3699, calls, "demoted twin must not burn a probe slot")
        self.assertIn("duplicate-twin demotion: #3699 skipped", log.joined())
        self.assertIn("#3698", log.joined())

    def test_older_canonical_survives_younger_refile_demoted(self):
        """Both twins unclaimed: the older sibling is canonical; the younger
        refile is a filer artifact and is demoted in the same run."""
        board = [
            _row(100, _LIVE_TWIN_TITLE),
            _row(101, _LIVE_TWIN_TITLE),
        ]
        log = _CaptureLog()
        picked = cal.pick_next_issue(
            issues=board,
            claim_probe=lambda n: _FREE,
            log_fn=log,
        )
        self.assertEqual(picked, "100")
        self.assertIn("duplicate-twin demotion: #101 skipped", log.joined())
        self.assertIn("canonical row", log.joined())

    def test_family_of_three_only_oldest_survives(self):
        board = [
            _row(100, _LIVE_TWIN_TITLE),
            _row(101, _LIVE_TWIN_TITLE),
            _row(102, _LIVE_TWIN_TITLE),
        ]
        log = _CaptureLog()
        picked = cal.pick_next_issue(
            issues=board,
            claim_probe=lambda n: _FREE,
            log_fn=log,
        )
        self.assertEqual(picked, "100")
        joined = log.joined()
        self.assertIn("duplicate-twin demotion: #101 skipped", joined)
        self.assertIn("duplicate-twin demotion: #102 skipped", joined)

    def test_no_twin_pick_unchanged(self):
        """Over-exclusion guard: a lone row with a unique title is untouched."""
        board = [_real_row(2500)]
        self.assertEqual(
            cal.pick_next_issue(
                issues=board, claim_probe=lambda n: _FREE, log_fn=_CaptureLog()
            ),
            "2500",
        )

    def test_closed_older_sibling_is_not_coverage(self):
        """A refile AFTER the original resolved is servable — closed rows are
        not family members (the finding's work is done, not in flight)."""
        closed = _row(100, _LIVE_TWIN_TITLE)
        closed["state"] = "closed"
        board = [closed, _row(101, _LIVE_TWIN_TITLE)]
        picked = cal.pick_next_issue(
            issues=board,
            claim_probe=lambda n: _FREE,
            log_fn=_CaptureLog(),
        )
        self.assertEqual(picked, "101")

    def test_case_and_whitespace_variants_caught(self):
        """Normalization is whitespace-collapse + casefold: 'Fix  Thing' vs
        'fix thing' is the same family (filer retries often reflow text)."""
        board = [
            _row(100, "Fix  Broken Widget\non main"),
            _row(101, "fix broken widget on main"),
        ]
        log = _CaptureLog()
        picked = cal.pick_next_issue(
            issues=board,
            claim_probe=lambda n: _FREE,
            log_fn=log,
        )
        self.assertEqual(picked, "100")
        self.assertIn("duplicate-twin demotion: #101 skipped", log.joined())

    def test_excluded_lane_twin_does_not_cover_claimable_sibling(self):
        """An older twin parked in an excluded lane (bridge:receipt mirror)
        can never receive the dispatch, so it must not demote the claimable
        younger sibling. (Claimed/leased twins still cover — tested below.)"""
        board = [
            _row(100, _LIVE_TWIN_TITLE, labels=["report", "bridge:receipt"]),
            _row(101, _LIVE_TWIN_TITLE),
        ]
        picked = cal.pick_next_issue(
            issues=board,
            claim_probe=lambda n: _FREE,
            log_fn=_CaptureLog(),
        )
        self.assertEqual(picked, "101")

    def test_claimed_excluded_lane_twin_still_covers(self):
        """A claimed twin covers the family regardless of its own lane: the
        finding's work is in flight wherever the claim sits."""
        board = [
            _row(100, _LIVE_TWIN_TITLE, labels=["status:claimed", "report"]),
            _row(101, _LIVE_TWIN_TITLE),
        ]
        picked = cal.pick_next_issue(
            issues=board,
            claim_probe=lambda n: _FREE,
            log_fn=_CaptureLog(),
        )
        self.assertIsNone(picked)

    def test_pure_mode_contract_unchanged(self):
        """claim_probe=None (hermetic callers): the pre-change label-only
        contract is byte-identical — priority sort picks the lowest number,
        no demotion machinery runs."""
        board = [
            _row(100, _LIVE_TWIN_TITLE),
            _row(101, _LIVE_TWIN_TITLE),
        ]
        self.assertEqual(cal.pick_next_issue(issues=board), "100")


class TestDuplicateTwinNoteUnit(unittest.TestCase):
    """Direct helper pins: note text, lease window, fail-open contract."""

    def test_claimed_twin_note_names_twin_and_invariant(self):
        note = cal._duplicate_twin_note(
            _row(3699, _LIVE_TWIN_TITLE),
            [_claimed_row(3698, _LIVE_TWIN_TITLE), _row(3699, _LIVE_TWIN_TITLE)],
        )
        self.assertIsNotNone(note)
        self.assertIn("#3698", note)
        self.assertIn("U5", note)

    def test_older_twin_note_names_canonical(self):
        note = cal._duplicate_twin_note(
            _row(101, _LIVE_TWIN_TITLE),
            [_row(100, _LIVE_TWIN_TITLE), _row(101, _LIVE_TWIN_TITLE)],
        )
        self.assertIsNotNone(note)
        self.assertIn("#100", note)
        self.assertIn("canonical", note)

    def test_younger_twin_does_not_demote_older(self):
        note = cal._duplicate_twin_note(
            _row(100, _LIVE_TWIN_TITLE),
            [_row(100, _LIVE_TWIN_TITLE), _row(101, _LIVE_TWIN_TITLE)],
        )
        self.assertIsNone(note)

    def test_active_lease_demotes_expired_lease_does_not(self):
        """The lease rule's unique coverage: a YOUNGER twin holding an active
        local lease demotes the older candidate (family in flight on this very
        runner); an EXPIRED lease falls away and the older sibling survives."""
        now = time.time()
        item = _row(200, _LIVE_TWIN_TITLE)
        younger_twin = _row(201, _LIVE_TWIN_TITLE)
        active = cal._duplicate_twin_note(
            item, [item, younger_twin], lease_store={"201": now - 60}, now_ts=now
        )
        self.assertIsNotNone(active)
        self.assertIn("active dispatch lease", active)
        expired = cal._duplicate_twin_note(
            item,
            [item, younger_twin],
            lease_store={"201": now - cal.ISSUE_LEASE_SECONDS - 10},
            now_ts=now,
        )
        self.assertIsNone(expired)

    def test_active_lease_on_older_twin_uses_lease_note(self):
        """A leased OLDER twin reports the lease reason (in-flight wins over
        the canonical-sibling wording — the finding is actively owned)."""
        now = time.time()
        item = _row(201, _LIVE_TWIN_TITLE)
        older_twin = _row(200, _LIVE_TWIN_TITLE)
        note = cal._duplicate_twin_note(
            item, [older_twin, item], lease_store={"200": now - 60}, now_ts=now
        )
        self.assertIsNotNone(note)
        self.assertIn("active dispatch lease", note)
        self.assertIn("#200", note)

    def test_missing_title_fails_open(self):
        self.assertIsNone(cal._duplicate_twin_note({"number": 1}, []))
        self.assertIsNone(
            cal._duplicate_twin_note({"number": 1, "title": ""}, [_real_row(2)])
        )

    def test_non_numeric_number_fails_open(self):
        self.assertIsNone(
            cal._duplicate_twin_note(
                {"number": "abc", "title": _LIVE_TWIN_TITLE},
                [_row(100, _LIVE_TWIN_TITLE)],
            )
        )

    def test_never_raises_on_garbage_board(self):
        """Never-raise contract: garbage rows must not break the probe."""
        board = [None, "garbage", 42, {"title": _LIVE_TWIN_TITLE}, _real_row(7)]
        try:
            note = cal._duplicate_twin_note(_row(100, _LIVE_TWIN_TITLE), board)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"_duplicate_twin_note raised {type(exc).__name__}")
        self.assertIsNone(note)

    def test_demoted_twin_exhaustion_note_emitted(self):
        """All candidates twins of a claimed sibling ⇒ honest no-pick note,
        never a silent None (U2 honesty: dark ≠ zero)."""
        board = [
            _claimed_row(100, _LIVE_TWIN_TITLE),
            _row(101, _LIVE_TWIN_TITLE),
        ]
        log = _CaptureLog()
        picked = cal.pick_next_issue(
            issues=board,
            claim_probe=lambda n: _FREE,
            log_fn=log,
        )
        self.assertIsNone(picked)
        self.assertIn("no clean pick this run", log.joined())


if __name__ == "__main__":
    unittest.main()
