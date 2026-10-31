#!/usr/bin/env python3
"""tests/test_line_budget_guard.py — contract tests for scripts/ci/line_budget_guard.py.

The anti-bloat budget guard landed in PR #4311 with NO test face - flagged
by the test parity guard's fail-closed sweep, the same defect family as
parity red #12 (pr_preflight_guard.py, closed in PR #4159) and
run_face_tests.py (closed in PR #4313).

Pins the pure contracts hermetically (no network, no repo mutations):
  - BUDGETS: positive integer limits; every budgeted path exists on disk
    (drift guard: renaming a core script fails HERE, not silently);
  - check_budgets(): violation only when the live line count exceeds the
    budget; missing files are skipped, unreadable files surface as ERROR
    rows; budget-adjacent file at exactly max lines passes;
  - self_test(): exits 0 on the real repo (all budgeted files within
    limits) and 1 when a violation exists;
  - main(): --self-test routes to self_test(), default run enforces the
    real budgets; exit codes propagate verbatim.

Fully offline, stdlib-only, dual mode (unittest + pytest).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "ci"))

import line_budget_guard as lbg  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestBudgetManifest(unittest.TestCase):
    def test_budgets_positive_integers(self):
        for rel, limit in lbg.BUDGETS.items():
            self.assertIsInstance(limit, int, rel)
            self.assertGreater(limit, 0, rel)

    def test_budgeted_files_exist_on_disk(self):
        for rel in lbg.BUDGETS:
            self.assertTrue((REPO_ROOT / rel).is_file(), f"budgeted file missing: {rel}")

    def test_budgeted_files_currently_within_limits(self):
        violations = lbg.check_budgets()
        self.assertEqual(
            violations, [],
            f"live repo violates its own budget contract: {violations}",
        )


class TestCheckBudgets(unittest.TestCase):
    def _guard_on(self, tmp: str) -> None:
        patcher = mock.patch.object(lbg, "REPO_ROOT", Path(tmp))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_over_budget_file_violates(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._guard_on(tmp)
            target = Path(tmp) / "bloated.py"
            target.write_text("\n".join("#" * 10 for _ in range(6)), encoding="utf-8")
            with mock.patch.dict(lbg.BUDGETS, {"bloated.py": 5}):
                violations = lbg.check_budgets()
        self.assertEqual(len(violations), 1)
        self.assertIn("LINE_BUDGET_EXCEEDED", violations[0])
        self.assertIn("bloated.py", violations[0])

    def test_exact_budget_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._guard_on(tmp)
            target = Path(tmp) / "exact.py"
            target.write_text("\n".join("x = 1" for _ in range(5)), encoding="utf-8")
            with mock.patch.dict(lbg.BUDGETS, {"exact.py": 5}):
                self.assertEqual(lbg.check_budgets(), [])

    def test_missing_file_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._guard_on(tmp)
            with mock.patch.dict(lbg.BUDGETS, {"ghost.py": 10}):
                self.assertEqual(lbg.check_budgets(), [])

    def test_unreadable_file_surfaces_error_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._guard_on(tmp)
            target = Path(tmp) / "bad.py"
            target.write_text("x = 1", encoding="utf-8")
            with mock.patch.dict(lbg.BUDGETS, {"bad.py": 5}), \
                 mock.patch.object(Path, "read_text", side_effect=OSError("boom")):
                violations = lbg.check_budgets()
        self.assertEqual(len(violations), 1)
        self.assertTrue(violations[0].startswith("ERROR reading"), violations[0])


class TestSelfTestAndMain(unittest.TestCase):
    def test_self_test_passes_on_real_repo(self):
        self.assertEqual(lbg.self_test(), 0)

    def test_self_test_fails_when_violation_exists(self):
        with mock.patch.object(lbg, "check_budgets",
                               return_value=["LINE_BUDGET_EXCEEDED: fake"]):
            self.assertEqual(lbg.self_test(), 1)

    def _run_main(self, *argv: str) -> int:
        with mock.patch.object(sys, "argv", ["line_budget_guard.py", *argv]):
            return lbg.main()

    def test_main_self_test_flag_routes_to_self_test(self):
        with mock.patch.object(lbg, "self_test", return_value=0) as m:
            rc = self._run_main("--self-test")
        self.assertEqual(rc, 0)
        m.assert_called_once_with()

    def test_main_default_enforces_budgets(self):
        with mock.patch.object(lbg, "check_budgets", return_value=[]) as m:
            rc = self._run_main()
        self.assertEqual(rc, 0)
        m.assert_called_once_with()

    def test_main_propagates_violation_exit_code(self):
        with mock.patch.object(lbg, "check_budgets",
                               return_value=["LINE_BUDGET_EXCEEDED: fake"]):
            self.assertEqual(self._run_main(), 1)


if __name__ == "__main__":
    unittest.main()
