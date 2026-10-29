#!/usr/bin/env python3
"""Offline contract tests for the boundary-honest ACTION template (#2738 evidence lane).

The solver-pick ACTION text is the last instruction an autonomous agent reads before
deciding whether a merged PR may auto-close the picked issue. These pins hold the
template to its contract: the auto-close grant (Closes #N) is scoped to remedies that
are fully inside the open repo, out-of-envelope remedies get an explicit evidence-only
no-auto-close route, and closure authority is routed to the verdict plane/admin.

This is the mechanism-level fix for the documented false-closure family (#2211 closed
"completed" while 2 of 3 named services were still broken; residual became #2225;
#2225 closed under materially identical conditions and challenged by #2738; #2608
flagged by #2615). Scope guard: the template must NOT implement #2794 item (2)
(lane:admin pick exclusion — owner-pending), so audit:finding rows stay dispatchable.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal  # noqa: E402


class TestActionTemplateBoundary(unittest.TestCase):
    def test_mentions_the_picked_number_in_both_roles(self) -> None:
        # The number is load-bearing in two roles: pick identity ("issue = #N")
        # and the scoped auto-close grant ("'Closes #N'"). Role-based pins (not
        # counts) — when the picked number itself appears in the evidence-family
        # citation (e.g. picking #2738), a count pin would be fragile.
        for picked in (2738, "42"):
            text = cal.action_instruction(picked)
            self.assertIn(f"issue = #{picked}", text)
            self.assertIn(f"'Closes #{picked}'", text)

    def test_auto_close_grant_is_scoped_to_in_repo_remedies(self) -> None:
        text = cal.action_instruction(42)
        self.assertIn("ONLY when the remedy is fully inside", text)
        self.assertIn("closes the issue truthfully", text)

    def test_out_of_envelope_route_is_explicit(self) -> None:
        text = cal.action_instruction(42)
        for token in ("HITL", "service redeploys", "satellite repos", "protected paths"):
            self.assertIn(token, text)
        self.assertIn("do NOT auto-close", text)

    def test_report_only_rows_get_the_evidence_route(self) -> None:
        text = cal.action_instruction(42)
        self.assertIn("report-only evidence", text)
        self.assertIn("audit:finding", text)

    def test_closure_authority_routed_to_verdict_plane(self) -> None:
        text = cal.action_instruction(42)
        self.assertIn("verdict plane/admin", text)

    def test_false_closure_family_cited_as_evidence(self) -> None:
        text = cal.action_instruction(42)
        for ref in ("#2211", "#2225", "#2738", "#2608", "#2615"):
            self.assertIn(ref, text)

    def test_no_blanket_close_it_on_merge_grant(self) -> None:
        # The old unconditional grant phrase is the exact sentence an agent
        # followed when it auto-closed the not-recovered #2225 (the #2738
        # challenge's mechanism finding). It must not survive in the template.
        text = cal.action_instruction(42)
        self.assertNotIn("to close it on merge", text)

    def test_scope_guard_keeps_pick_surface_unchanged(self) -> None:
        # Template honesty only — #2794 item (2) is owner-pending, so the loop
        # must NOT start excluding audit:finding rows at the pick: the label is
        # absent from EXCLUDED_LABELS (it flagged #2794 itself, which was
        # legitimately fixed in-repo by #2815).
        self.assertNotIn("audit:finding", cal.EXCLUDED_LABELS)

    def test_source_dispatch_routes_through_the_function(self) -> None:
        # Source-level contract: the solver dispatch surface must print
        # action_instruction(picked) — a raw inline f-string with an
        # unconditional Closes grant would silently regress the fix.
        src = (_ROOT / "scripts" / "agents" / "continuous_agent_loop.py").read_text(encoding="utf-8")
        self.assertIn("print(action_instruction(picked))", src)
        self.assertNotIn("in PR description to close it on merge", src)


if __name__ == "__main__":
    unittest.main()
