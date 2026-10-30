#!/usr/bin/env python3
"""Pin: lane-declared rows never reach the coder pick surface as silent solver work.

Dual-mode: runs under both `python3 -m unittest` and `pytest`.

Two-layer contract (2026-10-30, live board #2360-class and report-only rows):

Layer 1 (label plane): rows labeled `report-only` declare themselves non-solver
work ("report-only, no closure request; Recovery: N/A" — live #2756/#2766/#2804/
#2811). Before the fix, pick_next_issue() dispatched them as coder envelopes,
so every cycle either produced a skip-loop or a duplicate-receipt treadmill,
and genuinely codeable rows sat buried behind them. The label now lives in the
EXCLUDED_LABELS SSOT (guard 7 parity: adding a loop-side label is the
waste-direction change — warn, not fail; pipeline.yml CLAIMABLE sync is
admin-lane).

Layer 2 (declaration plane, fail-open): #2360 carries NO report-only label but
its own body says "Options (all admin-lane; auditor files evidence only)" and
"Never-do: no fixes attempted". Labels cannot carry that signal, so the pick
still happens (the hermetic pick contract is untouched — pick_next_issue() is
NOT blocked), but build_task_envelope() attaches an honest `lane_hint` and a
LANE HINT line in specialist_prompt so the receiving agent reaches the
lane-verdict in one glance instead of burning a cycle discovering it.

AST-level pin (comment-immune, test_pick_excludes_bridge_states precedent) plus
functional pick tests on an in-memory board and envelope tests (zero gh/network
dependency).
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal

LOOP_SRC = (_ROOT / "scripts" / "agents" / "continuous_agent_loop.py").read_text(
    encoding="utf-8"
)

REPORT_ONLY = "report-only"


class TestExcludedLabelsSourcePin(unittest.TestCase):
    def test_frozenset_literal_carries_report_only(self):
        """AST pin: the EXCLUDED_LABELS frozenset literal contains 'report-only'."""
        tree = ast.parse(LOOP_SRC)
        found = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "EXCLUDED_LABELS"
                for t in node.targets
            ):
                found = node
                break
        self.assertIsNotNone(found, "EXCLUDED_LABELS assignment missing")
        call = found.value
        self.assertIsInstance(call, ast.Call, "EXCLUDED_LABELS must stay a frozenset(...)")
        literals = {
            elt.value
            for arg in call.args
            if isinstance(arg, ast.Set)
            for elt in arg.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        }
        self.assertIn(
            REPORT_ONLY,
            literals,
            "report-only lane declaration missing from EXCLUDED_LABELS literal",
        )


class TestPickExcludesReportOnly(unittest.TestCase):
    def test_report_only_row_not_pickable(self):
        """A report-only row must never win the pick over a codeable row."""
        board = [
            {
                "number": 2756,
                "title": "report(ops): stale sync",
                "labels": [{"name": "report-only"}, {"name": "P4-minor"}],
            },
            {"number": 2854, "title": "triage(ci): real codeable work", "labels": []},
        ]
        self.assertEqual(cal.pick_next_issue(issues=board), "2854")

    def test_report_only_leaks_nowhere_even_alone(self):
        board = [
            {
                "number": 2766,
                "title": "report(guard): evidence refresh",
                "labels": [{"name": "report-only"}],
            },
            {"number": 2804, "title": "report(guard): recovery triage", "labels": []},
        ]
        self.assertEqual(cal.pick_next_issue(issues=board), "2804")


class TestDetectLaneHint(unittest.TestCase):
    def test_title_prefix_report(self):
        hint = cal.detect_lane_hint("report(ops): #2225 family", "some body")
        self.assertIsNotNone(hint)
        self.assertEqual(hint["lane"], "report-only")
        self.assertIn("title prefix", hint["evidence"])

    def test_title_prefix_guard(self):
        hint = cal.detect_lane_hint("guard(platform): sentry pass 08:45Z", "")
        self.assertIsNotNone(hint)
        self.assertEqual(hint["lane"], "report-only")

    def test_body_marker_admin_lane(self):
        hint = cal.detect_lane_hint(
            "audit(federation): CI follow-through gap",
            "## Options (all admin-lane; auditor files evidence only)\nNever-do: no fixes attempted",
        )
        self.assertIsNotNone(hint)
        self.assertEqual(hint["evidence"], "body marker 'admin-lane'")

    def test_codeable_row_gets_no_hint(self):
        self.assertIsNone(
            cal.detect_lane_hint(
                "feat(studio): add cockpit gauge", "implement the gauge component"
            )
        )
        self.assertIsNone(cal.detect_lane_hint("", ""))

    def test_body_marker_word_not_pretitled(self):
        """A body merely MENTIONING a report lane must not false-positive via title."""
        hint = cal.detect_lane_hint(
            "feat(ci): wire report-only rows into the guard roster",
            "the guard reads rows labeled report-only",
        )
        # Title starts with 'feat(' so no title-prefix hit; body contains the
        # marker — the hint fires with the body evidence, which is correct
        # fail-open behavior (informational only, pick is never blocked).
        self.assertIsNotNone(hint)
        self.assertIn("body marker", hint["evidence"])


class TestEnvelopeLaneHint(unittest.TestCase):
    def test_envelope_carries_lane_hint_for_declared_row(self):
        issue = {
            "number": 2360,
            "title": "audit(federation): CI follow-through gap",
            "state": "open",
            "labels": [{"name": "p2-medium"}, {"name": "status:unclaimed"}],
            "body": "Options (all admin-lane; auditor files evidence only). Never-do: no fixes attempted.",
        }
        env = cal.build_task_envelope(issue)["task_envelope"]
        self.assertIn("lane_hint", env, "declared-lane row must carry lane_hint")
        self.assertEqual(env["lane_hint"]["lane"], "report-only")
        self.assertIn("LANE HINT", env["specialist_prompt"])

    def test_envelope_has_no_lane_hint_key_when_absent(self):
        issue = {
            "number": 1,
            "title": "feat(core): real fix",
            "state": "open",
            "labels": [{"name": "P2"}],
            "body": "plain implementable body",
        }
        env = cal.build_task_envelope(issue)["task_envelope"]
        self.assertNotIn("lane_hint", env, "honest absence: no empty lane_hint key")
        self.assertNotIn("LANE HINT", env["specialist_prompt"])


if __name__ == "__main__":
    unittest.main()
