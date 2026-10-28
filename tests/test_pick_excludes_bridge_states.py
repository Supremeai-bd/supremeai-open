#!/usr/bin/env python3
"""Pin: pick_next_issue excludes bridge-plane states (verdict-blackout residue, #2100).

Dual-mode: runs under both `python3 -m unittest` and `pytest`.

The tower stamps bridge-state labels on WO mirrors: pr-opened/queued/in-gates are
in-flight (a bridge PR exists), rejected/idempotent-noop are terminal (rescue plane
scripts/ci/rejected_wo_rescue.py triages rejected comments separately). During the
#2100 verdict-plane blackout, LANDED WOs keep `bridge:queued` + empty verdict
history, so a pick surface that ignores bridge labels offers merged work as
claimable — live 2026-10-28: 20 of 27 non-excluded open rows were bridge:queued
mirrors (landed #2071/#2056 included), and a landed WO (#2071) sorted ahead of a
genuinely new finding (#2103) in a drained board.

AST-level pin (comment-immune, test_27 wiring-pin precedent): reads the loop
module's source and asserts the frozenset literal carries all five bridge labels,
then functionally proves exclusion via cal.pick_next_issue(issues=[...]) on an
in-memory board (zero gh/network dependency).
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

BRIDGE_STATES = {
    "bridge:pr-opened",
    "bridge:queued",
    "bridge:in-gates",
    "bridge:rejected",
    "bridge:idempotent-noop",
}


class TestExcludedLabelsSourcePin(unittest.TestCase):
    def test_frozenset_literal_carries_bridge_states(self):
        """AST pin: the EXCLUDED_LABELS assignment is a frozenset call whose
        literal args contain every bridge-plane state — immune to comment edits."""
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
        missing = BRIDGE_STATES - literals
        self.assertEqual(missing, set(), f"bridge states missing from literal: {missing}")


class TestPickExcludesBridgeStates(unittest.TestCase):
    def test_queued_mirror_not_pickable(self):
        """Landed-but-unstamped WO (bridge:queued, no status label) must never win."""
        board = [
            {"number": 2071, "title": "landed mirror", "labels": [{"name": "bridge:queued"}]},
            {"number": 2103, "title": "genuinely new", "labels": []},
        ]
        self.assertEqual(cal.pick_next_issue(issues=board), "2103")

    def test_all_five_bridge_states_excluded(self):
        for state in sorted(BRIDGE_STATES):
            board = [
                {"number": 1, "title": "x", "labels": [{"name": state}]},
                {"number": 2, "title": "y", "labels": []},
            ]
            self.assertEqual(
                cal.pick_next_issue(issues=board),
                "2",
                f"state {state} leaked into the pick surface",
            )

    def test_priority_still_wins_over_noop(self):
        """Bridge-label exclusion must not demote real priority work."""
        board = [
            {"number": 2100, "title": "real P2", "labels": [{"name": "P2-medium"}]},
            {"number": 2103, "title": "unlabeled", "labels": []},
        ]
        self.assertEqual(cal.pick_next_issue(issues=board), "2100")


if __name__ == "__main__":
    unittest.main()
