#!/usr/bin/env python3
"""Offline tests for autonomous_audit (deterministic checks plane).

Parity companion for scripts/ci/autonomous_audit.py (added by #4377 without
its parity test — the test_parity_guard real-repo leg went red at 52218ca).
ROOT-CAUSE NOTE (2026-10-31, GLM Agent 28, Job 486832): নতুন guard parity
test ছাড়া জমা দিলে red census নোংরা হয় — #4311-এর একই শ্রেণি। এই ফাইল
deterministic_checks()-এর চুক্তি offline-ভাবে পিন করে (subprocess audit
plane নয় — সেটি নেটওয়ার্ক/টুল-নির্ভর)।
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "ci"))

import autonomous_audit as aa


class TestAutonomousAuditDeterministic(unittest.TestCase):
    def setUp(self):
        self._findings_before = list(aa.FINDINGS)
        aa.FINDINGS.clear()

    def tearDown(self):
        aa.FINDINGS[:] = self._findings_before

    def _scan_tmp(self, files: dict[str, str]) -> list[aa.Finding]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel, text in files.items():
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
            with patch.object(aa, "ROOT", root):
                aa.deterministic_checks()
            return list(aa.FINDINGS)

    def test_hardcoded_secret_flagged(self):
        findings = self._scan_tmp(
            {"src/app.py": 'API_KEY = "superreal-secret-key-1234567890"\n'}
        )
        rules = [f.rule_id for f in findings]
        self.assertIn("SECRET-HARDCODED", rules)
        hit = next(f for f in findings if f.rule_id == "SECRET-HARDCODED")
        self.assertEqual(hit.severity, "critical")
        self.assertTrue(hit.path.endswith("src/app.py"))

    def test_placeholder_values_skipped(self):
        findings = self._scan_tmp(
            {"src/app.py": 'API_KEY = "dummy-placeholder-value-123456"\n'}
        )
        self.assertFalse([f for f in findings if f.rule_id == "SECRET-HARDCODED"])

    def test_test_files_exempt(self):
        findings = self._scan_tmp(
            {"tests/test_app.py": 'API_KEY = "superreal-secret-key-1234567890"\n'}
        )
        self.assertFalse([f for f in findings if f.rule_id == "SECRET-HARDCODED"])

    def test_verify_false_flagged_high(self):
        findings = self._scan_tmp(
            {"src/client.py": "import requests\nrequests.get(url, verify=False)\n"}
        )
        hits = [f for f in findings if f.rule_id == "SEC-VERIFY-FALSE"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].severity, "high")

    def test_env_file_flagged(self):
        findings = self._scan_tmp({".env": "REAL_THING=1\n"})
        rules = [f.rule_id for f in findings]
        self.assertIn("SECRET-ENV-FILE", rules)


if __name__ == "__main__":
    unittest.main()
