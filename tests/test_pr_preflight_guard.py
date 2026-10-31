#!/usr/bin/env python3
"""tests/test_pr_preflight_guard.py — contract tests for scripts/ci/pr_preflight_guard.py.

The guard (branch-naming contract, PR-body verification signatures, python/json
lint preflight) existed with NO test face — flagged by the test parity guard's
fail-closed sweep and triaged as agent-lane work in
docs/reports/TRIAGE_REDS_LADDER_BLINDSPOT_2026-10-31.md (red #12).

Pins the pure contracts hermetically (no network, no repo mutations):
  - check_branch: conventional branch regex, main/master exempt;
  - check_issue_ref: the three PR-body signatures (issue ref, Tower
    Reflection Evidence header, 3-Tier/Test Evidence section);
  - check_lint: python and json syntax detection via tmp files;
  - self_test(): the guard's built-in smoke exits 0.

Fully offline, stdlib-only, dual mode (unittest + pytest).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "ci"))

import pr_preflight_guard as ppg  # noqa: E402


class BranchContract(unittest.TestCase):
    def test_01_conventional_branches_pass(self):
        for b in ("feat/foo-bar", "fix/loop-cadence", "bridge/bridge-20261031-x",
                  "chore/ci.step", "test/a/b_c", "hotfix/urgent-1"):
            self.assertEqual(ppg.check_branch(b), [], b)

    def test_02_invalid_branches_rejected(self):
        for b in ("badbranch", "Feat/x", "feat/", "feat/UPPER", "wip; rm -rf"):
            self.assertTrue(ppg.check_branch(b), b)

    def test_03_main_master_exempt(self):
        self.assertEqual(ppg.check_branch("main"), [])
        self.assertEqual(ppg.check_branch("master"), [])


class IssueRefContract(unittest.TestCase):
    GOOD = "Closes #123\n## Reflection Evidence\n3-Tier Verify passed"

    def test_04_complete_body_passes(self):
        self.assertEqual(ppg.check_issue_ref(self.GOOD), [])

    def test_05_missing_issue_ref(self):
        errs = ppg.check_issue_ref("## Reflection Evidence\nTest Evidence: ok")
        self.assertTrue(any("issue reference" in e for e in errs))

    def test_06_missing_reflection_signature(self):
        errs = ppg.check_issue_ref("Closes #1\n3-Tier Verify passed")
        self.assertTrue(any("Reflection Evidence" in e for e in errs))

    def test_07_missing_verify_section(self):
        errs = ppg.check_issue_ref("Closes #1\n## Reflection Evidence")
        self.assertTrue(any("3-Tier" in e or "Test Evidence" in e for e in errs))


class LintPreflight(unittest.TestCase):
    def test_08_python_syntax(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.py"
            bad.write_text("def broken(: pass\n", encoding="utf-8")
            good = Path(d) / "good.py"
            good.write_text("x = 1\n", encoding="utf-8")
            self.assertTrue(ppg.check_lint([str(bad)]))
            self.assertEqual(ppg.check_lint([str(good)]), [])

    def test_09_json_syntax(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            good = Path(d) / "good.json"
            good.write_text('{"ok": true}\n', encoding="utf-8")
            self.assertTrue(ppg.check_lint([str(bad)]))
            self.assertEqual(ppg.check_lint([str(good)]), [])

    def test_10_missing_file_ignored(self):
        self.assertEqual(ppg.check_lint(["does/not/exist.py"]), [])


class SelfTestSmoke(unittest.TestCase):
    def test_11_builtin_self_test_exits_zero(self):
        self.assertEqual(ppg.self_test(), 0)


if __name__ == "__main__":
    unittest.main()
