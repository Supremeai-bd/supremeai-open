#!/usr/bin/env python3
"""Offline tests for test parity guard."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "ci"))

import test_parity_guard as tpg


class TestParityGuard(unittest.TestCase):
    def test_run_guard_on_real_repo_passes(self):
        ok, missing = tpg.run_guard(_ROOT)
        self.assertTrue(ok, f"missing tests: {missing}")

    def test_missing_script_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "scripts" / "agents").mkdir(parents=True)
            (root / "scripts" / "ci").mkdir(parents=True)
            (root / "scripts" / "agents" / "foo_bar.py").write_text(
                "# x", encoding="utf-8"
            )
            (root / "tests").mkdir()
            ok, missing = tpg.run_guard(root)
            self.assertFalse(ok)
            self.assertIn("scripts/agents/foo_bar.py", missing)

    def test_allowlisted_script_ok(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "scripts" / "agents").mkdir(parents=True)
            (root / "scripts" / "ci").mkdir(parents=True)
            (root / "scripts" / "agents" / "self_healing_reporter.py").write_text(
                "# x", encoding="utf-8"
            )
            ok, _missing = tpg.run_guard(root)
            self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
