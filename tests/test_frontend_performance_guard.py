import unittest
from pathlib import Path
from scripts.ci.frontend_performance_guard import check_app_code_splitting, self_test


class TestFrontendPerformanceGuard(unittest.TestCase):
    def test_self_test(self):
        self.assertTrue(self_test())

    def test_active_app_tsx(self):
        app_path = Path("studio/src/App.tsx")
        if not app_path.exists():
            self.skipTest("studio/src/App.tsx not found in repository root")
        content = app_path.read_text(encoding="utf-8")
        violations = check_app_code_splitting(content)
        self.assertEqual(violations, [], f"Performance violations found: {violations}")


if __name__ == "__main__":
    unittest.main()
