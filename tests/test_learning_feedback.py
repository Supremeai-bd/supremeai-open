#!/usr/bin/env python3
"""Offline tests for learning feedback loop."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import learning_feedback as lf


class TestRecord(unittest.TestCase):
    def test_record_and_load(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "sol.jsonl"
            rec = lf.record_verified_solution(
                42, ["a.py", "b.py"], digests={"a.py": "sha256:abc"}, path=p
            )
            self.assertIsNotNone(rec)
            self.assertEqual(rec["issue_ref"], 42)
            sols = lf.load_verified_solutions(p)
            self.assertEqual(len(sols), 1)
            self.assertEqual(sols[0]["scope_paths"], ["a.py", "b.py"])

    def test_load_missing_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "nope.jsonl"
            self.assertEqual(lf.load_verified_solutions(p), [])

    def test_load_skips_malformed(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "sol.jsonl"
            p.write_text(
                '{"schema":"verified-solution/1","issue_ref":1}\nnot json\n',
                encoding="utf-8",
            )
            sols = lf.load_verified_solutions(p)
            self.assertEqual(len(sols), 1)

    def test_record_id_deterministic_shape(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "sol.jsonl"
            rec = lf.record_verified_solution(7, [], path=p)
            self.assertEqual(len(rec["record_id"]), 16)
            self.assertTrue(all(c in "0123456789abcdef" for c in rec["record_id"]))


class TestPromote(unittest.TestCase):
    def test_promote_creates_skill_md(self):
        with tempfile.TemporaryDirectory() as td:
            staging = Path(td) / "staging"
            sol = {"issue_ref": 9, "scope_paths": ["x.py"], "reflection_why": "because"}
            path = lf.promote_to_skill_draft(sol, "my-skill", staging)
            self.assertIsNotNone(path)
            self.assertTrue(Path(path).is_file())
            text = Path(path).read_text(encoding="utf-8")
            self.assertIn("name: my-skill", text)
            self.assertIn("issue #9", text)

    def test_promote_rejects_empty(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(lf.promote_to_skill_draft({}, "", Path(td)))
            self.assertIsNone(lf.promote_to_skill_draft(None, "x", Path(td)))


if __name__ == "__main__":
    unittest.main()
