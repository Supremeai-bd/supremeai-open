#!/usr/bin/env python3
"""Offline tests for pr_preflight_guard (parity ratchet close-out).

# বাংলা: pr_preflight_guard.py প্রি-সাবমিশন গার্ড — এর জন্য কোনো ডেডিকেটেড
# টেস্ট ছিল না, ফলে test parity guard লাল হয়ে ছিল (red #12, GLM Agent 19-এর
# census)। এই ফাইল সেই ঋণ শোধ করে: প্রতিটি পিওর ফাংশন (check_branch,
# check_issue_ref, check_lint) অফলাইনে পিন করা হলো।
# Zero-Recurrence Invariant: guard নিজে এখন guard-এর আওতায়।
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "ci"))

import pr_preflight_guard as ppg


class TestCheckBranch(unittest.TestCase):
    def test_valid_branch_names_pass(self):
        for branch in ("feat/foo-bar", "fix/auth-login", "bridge/task-1234",
                       "ci/guards", "test/preflight", "chore/x_1",
                       "hotfix/urgent-fix"):
            self.assertEqual(ppg.check_branch(branch), [], branch)

    def test_main_and_master_are_exempt(self):
        self.assertEqual(ppg.check_branch("main"), [])
        self.assertEqual(ppg.check_branch("master"), [])

    def test_invalid_branch_names_fail(self):
        for branch in ("badbranch", "feat/Upper-Case", "feat/",
                       "feat/with space"):
            self.assertTrue(ppg.check_branch(branch), branch)


class TestCheckIssueRef(unittest.TestCase):
    def test_well_formed_body_passes(self):
        body = "Closes #123\n## Reflection Evidence\n3-Tier Verify passed"
        self.assertEqual(ppg.check_issue_ref(body), [])

    def test_all_error_kinds_reported(self):
        errs = ppg.check_issue_ref("no marker here")
        self.assertEqual(len(errs), 3)

    def test_each_missing_signature_reported(self):
        self.assertEqual(len(ppg.check_issue_ref("Fixes #9")), 2)
        body = "Resolves #5\n## Reflection Evidence\n- why: x"
        errs = ppg.check_issue_ref(body)
        self.assertEqual(len(errs), 1)
        self.assertIn("3-Tier", errs[0])


class TestCheckLint(unittest.TestCase):
    def test_good_python_passes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "good.py"
            p.write_text("x = 1\n", encoding="utf-8")
            self.assertEqual(ppg.check_lint([str(p)]), [])

    def test_broken_python_fails(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.py"
            p.write_text("def broken(: pass\n", encoding="utf-8")
            errs = ppg.check_lint([str(p)])
            self.assertEqual(len(errs), 1)
            self.assertIn("syntax error", errs[0])

    def test_broken_json_fails(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text("{not json", encoding="utf-8")
            errs = ppg.check_lint([str(p)])
            self.assertEqual(len(errs), 1)
            self.assertIn("json", errs[0])

    def test_empty_file_list_passes(self):
        self.assertEqual(ppg.check_lint([]), [])


class TestSelfTest(unittest.TestCase):
    def test_builtin_self_test_zero_failures(self):
        # pr_preflight_guard.self_test এর নিজস্ব অ্যাসারশন-চেইন; ০ = সব পাস
        rc = ppg.self_test()
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
