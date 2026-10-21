#!/usr/bin/env python3
"""Offline tests for execution executor."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import execution_bridge as eb
import execution_executor as ee


def _intent():
    return eb.build_dispatch_record(
        eb._valid_envelope()
        if hasattr(eb, "_valid_envelope")
        else {
            "task_envelope": {
                "task_id": "task-1",
                "role": "coder",
                "objective": "do thing",
                "specialist_prompt": "implement smallest safe change",
                "scope": {"touching_files": ["a.py"], "forbidden_paths": []},
                "acceptance": ["tests pass"],
                "verification": ["python -c \"print('ok')\""],
                "submission": {"base_branch": "main"},
            }
        },
        dry_run=True,
    )


class TestLoadIntent(unittest.TestCase):
    def test_load_valid(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "i.json"
            p.write_text(json.dumps(_intent()), encoding="utf-8")
            self.assertIsNotNone(ee.load_intent(p))

    def test_load_bad_schema(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "i.json"
            p.write_text(json.dumps({"schema": "nope"}), encoding="utf-8")
            self.assertIsNone(ee.load_intent(p))

    def test_load_missing(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "nope.json"
            self.assertIsNone(ee.load_intent(p))


class TestExecutors(unittest.TestCase):
    def test_null_executor(self):
        res = ee.execute(_intent(), "null", Path("."))
        self.assertIsNotNone(res)
        self.assertTrue(res["passed"])
        self.assertEqual(res["executor"], "null")

    def test_verify_executor_pass(self):
        res = ee.execute(_intent(), "verify", Path("."))
        self.assertIsNotNone(res)
        self.assertTrue(res["passed"])

    def test_verify_executor_fail(self):
        intent = _intent()
        intent["verification"] = ['python -c "import sys; sys.exit(1)"']
        res = ee.execute(intent, "verify", Path("."))
        self.assertIsNotNone(res)
        self.assertFalse(res["passed"])

    def test_unknown_executor(self):
        res = ee.execute(_intent(), "mcp", Path("."))
        self.assertIsNone(res)

    def test_invalid_executor_name(self):
        res = ee.execute(_intent(), "bogus", Path("."))
        self.assertIsNone(res)


class TestRun(unittest.TestCase):
    def test_run_null_writes_result(self):
        with tempfile.TemporaryDirectory() as td:
            q = Path(td) / "intents"
            q.mkdir()
            ip = q / "intent.json"
            ip.write_text(json.dumps(_intent()), encoding="utf-8")
            rd = Path(td) / "results"
            out = ee.run(ip, rd, "null", Path(td))
            self.assertIsNotNone(out)
            self.assertTrue(Path(out).is_file())

    def test_run_missing_intent(self):
        with tempfile.TemporaryDirectory() as td:
            ip = Path(td) / "nope.json"
            out = ee.run(ip, Path(td) / "results", "null", Path(td))
            self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
