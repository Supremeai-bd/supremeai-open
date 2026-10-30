#!/usr/bin/env python3
"""Pin + behavior: #2794 fix (1) — dispatch pick live-claim pre-verify.

Live 2026-10-29 19:43-19:57Z (#2794): the revived tower-board dispatch path
re-emitted rows another agent already owned — #1776 claimed 19:50:14Z,
#2597 claimed 19:43:56Z, #2738 claimed 19:51:33Z, all dispatched on stale
`status:unclaimed` labels (queue labels lag live claims by up to the 30-min
claim TTL). Each burn ended in an atomic-claim rejection the STALE-CLAIM
advisory could only catch agent-side, after the cycle was already spent.

Fix (1) (the filer-scoped solver-lane item; item (2)'s lane:admin convention
is explicitly owner-blessing-pending): pick_next_issue accepts an optional
claim_probe; run_dispatch_cycle passes the live bridge_read_feedback probe.
An actively-claimed row is skipped IN THE SAME RUN (advance to the next
candidate), a dark probe degrades to label-only behavior (never raises,
never hangs — same never-raise contract as _tower_queue_floor), and an
exhausted top-N window returns None with an honest note instead of
dispatching a known-owned row one rank lower.

Pins enforced here (zero gh/network dependency — probes are injected fakes):
  1. Pure mode (claim_probe=None) keeps the exact pre-#2794 label-only pick.
  2. Active claim on the top candidate ⇒ pick advances to the next candidate.
  3. An expired latestClaim (age >= ttl) does NOT skip the row.
  4. A dark/timed-out probe degrades to the label-only pick.
  5. A raising probe degrades to the label-only pick.
  6. All top-N actively claimed ⇒ None (no blind dispatch below the window).
  7. Probing is bounded to FEEDBACK_PREVERIFY_TOPN candidates.
  8. Priority order still governs which candidates get probed first.

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


def _row(number: int, labels: list[str] | None = None) -> dict:
    return {
        "number": number,
        "title": f"row {number}",
        "labels": [{"name": name} for name in (labels or [])],
    }


def _active(agent: str = "other-agent", ttl: int = 30) -> tuple[bool, str]:
    return (True, f"live claim by {agent} (ttl {ttl}m)")


_FREE = (False, "no active claim on the feedback plane")


class _LeaseIsolated(unittest.TestCase):
    """Isolate pick_next_issue from THIS runtime's local dispatch journal.

    The loop persists a machine-local dispatch journal (mark_issue_leased)
    outside the repo (#3573: observability-only — the old 30-minute lease
    exclusion is gone, but tests still isolate from ambient files); a test run
    on an agent machine that was just dispatched row N would see N in the
    journal — contaminating assertions with ambient scheduler state (live hit:
    #2597 was journaled locally at 20:50Z when these tests first ran).
    Hermetic ⇒ empty store.
    """

    def setUp(self):
        patcher = unittest.mock.patch.object(
            cal, "load_issue_lease_store", lambda path=None: {}
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class TestPureModeContract(_LeaseIsolated):
    def test_no_probe_keeps_label_only_pick(self):
        """claim_probe=None ⇒ exact pre-#2794 behavior (hermetic callers)."""
        board = [_row(3001, ["status:unclaimed"]), _row(3002)]
        self.assertEqual(cal.pick_next_issue(issues=board), "3001")

    def test_no_probe_still_excludes_and_sorts(self):
        board = [
            _row(3001, ["bridge:queued"]),
            _row(2000, ["P1-major"]),
            _row(1999),
        ]
        self.assertEqual(cal.pick_next_issue(issues=board), "2000")


class TestLiveClaimPreverify(_LeaseIsolated):
    def test_active_claim_advances_to_next_candidate(self):
        """The #2794 live shape: top row claimed 8s ago, labels still unclaimed."""
        board = [_row(2597), _row(2738)]
        probe = lambda n: _active() if str(n) == "2597" else _FREE  # noqa: E731
        self.assertEqual(
            cal.pick_next_issue(issues=board, claim_probe=probe), "2738"
        )

    def test_expired_claim_does_not_skip(self):
        """A TTL-expired latestClaim is not an active claim (lease released)."""
        board = [_row(2597), _row(2738)]
        probe = lambda n: (  # noqa: E731
            (False, "latestClaim by zai-glm-agent-cron-484748-c46 expired (67m age > 30m ttl)")
            if str(n) == "2597"
            else _FREE
        )
        self.assertEqual(
            cal.pick_next_issue(issues=board, claim_probe=probe), "2597"
        )

    def test_dark_probe_degrades_to_label_only(self):
        """Feedback plane dark ⇒ behavior unchanged, pick proceeds on labels."""
        board = [_row(2597), _row(2738)]
        for note in (
            "feedback plane dark (McpTowerTimeoutError: connect)",
            "feedback probe timed out after 6s",
            "latestClaim present but unparseable (at=None, ttl=None)",
        ):
            probe = lambda n, _note=note: (False, _note)  # noqa: E731
            self.assertEqual(
                cal.pick_next_issue(issues=board, claim_probe=probe),
                "2597",
                f"dark probe note must not skip: {note}",
            )

    def test_raising_probe_degrades_to_label_only(self):
        """A broken probe must not break the pick (never-raise contract)."""
        board = [_row(2597), _row(2738)]

        def probe(n):
            raise RuntimeError("boom")

        self.assertEqual(
            cal.pick_next_issue(issues=board, claim_probe=probe), "2597"
        )

    def test_all_topn_claimed_returns_none(self):
        """Exhausted window ⇒ honest None, never a blind dispatch below it."""
        board = [_row(3000 + i) for i in range(1, 7)]
        probe = lambda n: _active()  # noqa: E731
        self.assertIsNone(cal.pick_next_issue(issues=board, claim_probe=probe))

    def test_probing_bounded_to_topn(self):
        """Rows beyond FEEDBACK_PREVERIFY_TOPN are never probed (bounded hot path)."""
        probed: list[str] = []
        board = [_row(3000 + i) for i in range(1, 7)]

        def probe(n):
            probed.append(str(n))
            return _active()

        self.assertIsNone(cal.pick_next_issue(issues=board, claim_probe=probe))
        self.assertEqual(len(probed), cal.FEEDBACK_PREVERIFY_TOPN)

    def test_priority_order_governs_probe_order(self):
        """P0 sorts ahead and gets probed first; skip advances in priority order."""
        board = [_row(3001), _row(2000, ["P0"])]
        probe = lambda n: _active() if str(n) == "2000" else _FREE  # noqa: E731
        self.assertEqual(
            cal.pick_next_issue(issues=board, claim_probe=probe), "3001"
        )

    def test_empty_board_with_probe_still_none(self):
        self.assertIsNone(cal.pick_next_issue(issues=[], claim_probe=lambda n: _FREE))


class TestDefaultProbeWiring(unittest.TestCase):
    def test_loop_source_wires_live_probe_at_both_dispatch_sites(self):
        """AST pin: both dispatch surfaces pass claim_probe=_feedback_claim_active.

        Comment-immune source check (wiring-pin precedent): the two
        pick_next_issue call sites in run_dispatch_cycle must carry the live
        probe kwarg, so the pre-verify cannot silently regress to prose-only.

        #2899-heal: the exact-substring pin (count of
        "pick_next_issue(issues=raw, claim_probe=_feedback_claim_active)")
        was born-red when the stdout-purity fix added a third kwarg
        (log_fn=_stderr_log) to the envelope-mode call site — the probe
        wiring was intact, only the signature evolved. The pin now counts
        pick_next_issue Call nodes whose keywords include
        claim_probe=_feedback_claim_active (signature-robust, still
        comment-immune), so future kwarg additions cannot fake a regression
        nor mask a real one.
        """
        src = cal.__file__
        self.assertTrue(src.endswith("continuous_agent_loop.py"))
        loop_src = Path(src).read_text(encoding="utf-8")
        tree = ast.parse(loop_src)
        wired = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fname = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            if fname != "pick_next_issue":
                continue
            for kw in node.keywords:
                if (
                    kw.arg == "claim_probe"
                    and isinstance(kw.value, ast.Name)
                    and kw.value.id == "_feedback_claim_active"
                ):
                    wired += 1
        self.assertEqual(
            wired,
            2,
            "both dispatch surfaces (envelope + dispatch print) must wire the live probe",
        )


if __name__ == "__main__":
    unittest.main()
