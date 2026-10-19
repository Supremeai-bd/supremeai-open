#!/usr/bin/env python3
"""Offline tests for execution bridge."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import execution_bridge as eb


def _valid_envelope():
    return {
        "task_envelope": {
            "task_id": "task-1",
            "role": "coder",
            "objective": "do thing",
            "specialist_prompt": "implement smallest safe change",
            "scope": {"touching_files": ["a.py"], "forbidden_paths": []},
            "acceptance": ["tests pass"],
            "verification": ["py_compile"],
            "submission": {"base_branch": "main"},
        }
    }


class TestValidation(unittest.TestCase):
    def test_valid_envelope(self):
        self.assertEqual(eb.validate_envelope(_valid_envelope()), [])

    def test_missing_task_envelope(self):
        errs = eb.validate_envelope({"foo": 1})
        self.assertIn("E_NO_TASK_ENVELOPE", errs)

    def test_missing_keys(self):
        env = {"task_envelope": {"task_id": "x"}}
        errs = eb.validate_envelope(env)
        self.assertTrue(any(e.startswith("E_MISSING_") for e in errs))

    def test_empty_prompt(self):
        env = _valid_envelope()
        env["task_envelope"]["specialist_prompt"] = "   "
        errs = eb.validate_envelope(env)
        self.assertIn("E_EMPTY_PROMPT", errs)

    def test_scope_too_wide(self):
        env = _valid_envelope()
        env["task_envelope"]["scope"]["touching_files"] = [f"f{i}.py" for i in range(31)]
        errs = eb.validate_envelope(env)
        self.assertIn("E_SCOPE_TOO_WIDE", errs)

    def test_bad_scope_type(self):
        env = _valid_envelope()
        env["task_envelope"]["scope"] = "not-a-dict"
        errs = eb.validate_envelope(env)
        self.assertIn("E_BAD_SCOPE", errs)


class TestLoadEnvelope(unittest.TestCase):
    def test_load_valid(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "env.json"
            p.write_text(json.dumps(_valid_envelope()), encoding="utf-8")
            self.assertIsNotNone(eb.load_envelope(p))

    def test_load_missing(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "nope.json"
            self.assertIsNone(eb.load_envelope(p))

    def test_load_invalid_json(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text("{not json", encoding="utf-8")
            self.assertIsNone(eb.load_envelope(p))


class TestDispatch(unittest.TestCase):
    def test_dry_run_records(self):
        with tempfile.TemporaryDirectory() as td:
            q = Path(td) / "queue"
            path = eb.dispatch(_valid_envelope(), q, dry_run=True, execute=False)
            self.assertIsNotNone(path)
            self.assertTrue(Path(path).is_file())
            rec = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertTrue(rec["dry_run"])
            self.assertEqual(rec["status"], "queued")
            self.assertEqual(rec["role"], "coder")

    def test_invalid_envelope_no_record(self):
        with tempfile.TemporaryDirectory() as td:
            q = Path(td) / "queue"
            path = eb.dispatch({"task_envelope": {"task_id": "x"}}, q)
            self.assertIsNone(path)
            self.assertFalse(q.exists() and any(q.iterdir()))

    def test_execute_refuses_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            q = Path(td) / "queue"
            path = eb.dispatch(_valid_envelope(), q, execute=True)
            self.assertIsNone(path)


if __name__ == "__main__":
    unittest.main()
