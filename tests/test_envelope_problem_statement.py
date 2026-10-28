#!/usr/bin/env python3
"""Offline contract tests for task-envelope problem_statement (SPEC §2).

Covers the #1712-follow-up honesty fixes:
  1. problem_statement.body is hydrated when the issue payload carries it
     (gh issue view --json ...,state,body) — agents must see acceptance
     criteria, not dispatch blind.
  2. A missing body is an honest ABSENT key, never a fake empty string.
  3. A label-less issue keeps its whole problem_statement (the old
     `if labels:` gate silently dropped it — SPEC §2 is issue-based).
  4. Both hydrate commands in the loop source request `body` from gh.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal

LOOP_SOURCE = (_ROOT / "scripts" / "agents" / "continuous_agent_loop.py").read_text(encoding="utf-8")


class TestProblemStatementBody(unittest.TestCase):
    def test_body_hydrated_when_present(self):
        issue = {
            "number": 63,
            "title": "fix: something real",
            "state": "open",
            "body": "## Acceptance criteria\n- MUST block on mutation",
            "labels": [{"name": "P1-high"}, {"name": "repo:mcp"}],
        }
        env = cal.build_task_envelope(issue)["task_envelope"]
        ps = env["problem_statement"]
        self.assertEqual(ps["id"], "63")
        self.assertEqual(ps["title"], "fix: something real")
        self.assertIn("MUST block on mutation", ps["body"])
        self.assertEqual(ps["labels"], ["p1-high", "repo:mcp"])
        self.assertEqual(ps["state"], "open")

    def test_missing_body_is_absent_key_not_fake_empty(self):
        issue = {"number": 7, "title": "t", "state": "open", "labels": []}
        ps = cal.build_task_envelope(issue)["task_envelope"]["problem_statement"]
        self.assertNotIn("body", ps, "absent body must stay absent (honest absence)")

    def test_empty_body_is_absent_key_not_fake_empty(self):
        issue = {"number": 7, "title": "t", "state": "open", "body": "", "labels": []}
        ps = cal.build_task_envelope(issue)["task_envelope"]["problem_statement"]
        self.assertNotIn("body", ps)

    def test_label_less_issue_keeps_problem_statement(self):
        # Old code: `if labels:` — a label-less issue lost the ENTIRE
        # problem_statement. SPEC §2 is issue-based, not label-based.
        issue = {"number": 9, "title": "no labels", "state": "open", "body": "b"}
        env = cal.build_task_envelope(issue)["task_envelope"]
        ps = env["problem_statement"]
        self.assertEqual(ps["id"], "9")
        self.assertEqual(ps["labels"], [])
        self.assertEqual(ps["body"], "b")

    def test_adhoc_envelope_has_no_problem_statement(self):
        env = cal.build_task_envelope(None)["task_envelope"]
        self.assertNotIn("problem_statement", env)

    def test_board_note_still_emitted(self):
        issue = {"number": 5, "title": "t", "state": "open", "body": "", "labels": ["x"]}
        env = cal.build_task_envelope(issue, board_note="gh issue view 5 failed: 1")["task_envelope"]
        self.assertEqual(env["board_note"], "gh issue view 5 failed: 1")


class TestHydrationRequestsBody(unittest.TestCase):
    def test_both_gh_issue_view_commands_request_body(self):
        # The --issue path (v_cmd) and the auto-pick path (h_cmd) must both
        # fetch body — a title-only hydrate dispatches agents blind.
        self.assertEqual(
            LOOP_SOURCE.count('"number,title,labels,state,body"'),
            2,
            "both gh issue view --json payloads must include body",
        )
        self.assertNotIn(
            '"number,title,labels,state"',
            LOOP_SOURCE,
            "no hydrate command may remain body-less",
        )

    def test_envelope_output_remains_json_serializable(self):
        issue = {"number": 11, "title": "t", "state": "open", "body": "unicode: বাংলা ✓", "labels": []}
        env = cal.build_task_envelope(issue)
        self.assertIn("বাংলা", json.dumps(env, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
