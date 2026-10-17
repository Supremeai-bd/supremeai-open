#!/usr/bin/env python3
"""Offline contract tests for the PR Improvement & Zero-Regression
Evaluator (#486, S07).

Asserts the landing.yml pre-squash gate contract: beneficial criteria
(scope alignment, test gain, schema validation, churn rejection) and
zero-regression criteria (suppression, leakage, dependency bloat,
backward compatibility), plus fail-closed input validation.

Pure stdlib. Run: python3 -m unittest test_s07_pr_evaluator -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "ci"))

import pr_improvement_regression_guard as guard  # noqa: E402


def cf(path, added=(), removed=()):
    return {"path": path, "added": list(added), "removed": list(removed)}


def req(files, declared=None, **kw):
    base = {"changed_files": files,
            "declared_files": (declared if declared is not None
                               else [f["path"] for f in files])}
    base.update(kw)
    return base


GOOD_FUNC = cf("scripts/ci/guard.py", ["def check(x):", "    return x > 0"])
GOOD_TEST = cf("tests/test_guard.py",
               ["def test_check():", "    assert check(1) is True"])


class BeneficialCriteria(unittest.TestCase):
    def test_01_valid_pr_passes(self):
        r = guard.evaluate(req([GOOD_FUNC, GOOD_TEST]))
        self.assertEqual(r["verdict"], guard.PASS)
        self.assertEqual(r["stats"]["assertions_added"], 1)

    def test_02_expect_style_assertion_counts(self):
        files = [cf("src/tool.ts", ["export const f = (x) => x"]),
                 cf("src/tool.test.ts", ["it('works', () => {", "  expect(f(1)).toBe(1);", "});"])]
        self.assertEqual(guard.evaluate(req(files))["verdict"], guard.PASS)

    def test_03_self_assert_style_counts(self):
        files = [cf("scripts/ci/g.py", ["x = 1"]),
                 cf("tests/test_g.py", ["self.assertEqual(x, 1)"])]
        self.assertEqual(guard.evaluate(req(files))["verdict"], guard.PASS)

    def test_04_no_test_gain_fails(self):
        r = guard.evaluate(req([cf("scripts/ci/g.py", ["x = 1"])]))
        self.assertEqual(r["verdict"], guard.FAIL)
        checks = {v["check"] for v in r["violations"]}
        self.assertIn("positive_test_gain", checks)

    def test_05_fixed_failing_test_satisfies_gain(self):
        r = guard.evaluate(req([cf("scripts/ci/g.py", ["x = 1"])],
                               fixed_failing_tests=["tests/test_g.py::test_x"]))
        self.assertEqual(r["verdict"], guard.PASS)

    def test_06_whitespace_only_fails_as_churn(self):
        r = guard.evaluate(req([cf("scripts/ci/g.py", ["x = 1  "], ["x = 1"])]))
        self.assertEqual(r["verdict"], guard.FAIL)
        checks = {v["check"] for v in r["violations"]}
        self.assertIn("rejection_of_cosmetic_churn", checks)

    def test_07_comment_only_fails_as_churn(self):
        r = guard.evaluate(req([cf("scripts/ci/g.py", ["# nice comment"], ["x = 1"])]))
        self.assertEqual(r["verdict"], guard.FAIL)

    def test_08_docstring_fence_only_fails_as_churn(self):
        r = guard.evaluate(req([cf("scripts/ci/g.py", ['"""docstring line"""'], ["x = 1"])]))
        self.assertEqual(r["verdict"], guard.FAIL)

    def test_09_pure_rename_fails_as_churn(self):
        r = guard.evaluate(req([cf("scripts/ci/g.py", ["total = count + 1"],
                                               ["sum_ = count + 1"])]))
        self.assertEqual(r["verdict"], guard.FAIL)

    def test_10_rename_plus_logic_passes_churn(self):
        files = [cf("scripts/ci/g.py", ["total = count + step"], ["sum_ = count + 1"]),
                 GOOD_TEST]
        self.assertEqual(guard.evaluate(req(files))["verdict"], guard.PASS)

    def test_11_mixed_whitespace_and_code_is_not_churn(self):
        files = [cf("scripts/ci/g.py", ["x = 1  ", "y = x * 2"], ["x = 1"]),
                 GOOD_TEST]
        self.assertEqual(guard.evaluate(req(files))["verdict"], guard.PASS)

    def test_12_schema_touch_requires_verification(self):
        files = [cf("api-schemas/gateway.openapi.yaml", ["  new: true"]), GOOD_TEST]
        r = guard.evaluate(req(files))
        self.assertEqual(r["verdict"], guard.FAIL)
        files2 = req(files, schema_validation="verified")
        self.assertEqual(guard.evaluate(files2)["verdict"], guard.PASS)


class ZeroRegressionCriteria(unittest.TestCase):
    def test_13_unittest_skip_fails(self):
        files = [cf("tests/test_g.py",
                    ["@unittest.skip('flaky')", "def test_x():", "    assert True"])]
        r = guard.evaluate(req(files))
        checks = {v["check"] for v in r["violations"]}
        self.assertIn("zero_test_suppression", checks)
        self.assertEqual(r["verdict"], guard.FAIL)

    def test_14_pytest_mark_skip_fails(self):
        files = [cf("tests/test_g.py",
                    ["@pytest.mark.skip(reason='later')", "def test_x():", "    assert True"])]
        self.assertEqual(guard.evaluate(req(files))["verdict"], guard.FAIL)

    def test_15_js_it_skip_fails(self):
        files = [cf("src/tool.test.ts", ["it.skip('x', () => {})", "assert(true)"])]
        r = guard.evaluate(req(files))
        self.assertEqual(r["verdict"], guard.FAIL)

    def test_16_commented_out_assertion_fails(self):
        files = [cf("tests/test_g.py", ["# assert check(1) is True"])]
        r = guard.evaluate(req(files))
        self.assertEqual(r["verdict"], guard.FAIL)

    def test_17_assertion_deletion_fails(self):
        files = [cf("tests/test_g.py",
                    ["def test_x():"],
                    ["def test_x():", "    assert check(1)"])]
        r = guard.evaluate(req(files))
        self.assertEqual(r["verdict"], guard.FAIL)

    def test_18_assertion_relocation_allowed_alongside_real_work(self):
        files = [cf("scripts/ci/g.py", ["def f():", "    return 2"],
                    ["def f():", "    return 1"]),
                 cf("tests/test_g.py",
                    ["def test_x():", "    assert check(1)"],
                    ["def test_x():", "    assert check(1)"])]
        r = guard.evaluate(req(files))
        self.assertEqual(r["verdict"], guard.PASS)
        checks = {v["check"] for v in r["violations"]}
        self.assertNotIn("zero_test_suppression", checks)

    def test_18b_pure_relocation_only_diff_is_churn(self):
        files = [cf("scripts/ci/g.py",
                    ["def f():", "    return 1"],
                    ["def f():", "    return 1"])]
        r = guard.evaluate(req(files))
        checks = {v["check"] for v in r["violations"]}
        self.assertIn("rejection_of_cosmetic_churn", checks)
        self.assertEqual(r["verdict"], guard.FAIL)

    def test_19_out_of_scope_file_fails(self):
        r = guard.evaluate(req([GOOD_FUNC], declared=["scripts/ci/other.py"]))
        checks = {v["check"] for v in r["violations"]}
        self.assertIn("scope_contract_alignment", checks)
        self.assertEqual(r["verdict"], guard.FAIL)

    def test_20_strict_subset_scope_passes(self):
        r = guard.evaluate(req([GOOD_FUNC, GOOD_TEST],
                               declared=["scripts/ci/guard.py",
                                         "tests/test_guard.py",
                                         "docs/unused.md"]))
        self.assertEqual(r["verdict"], guard.PASS)

    def test_21_hard_protected_paths_fail_even_if_declared(self):
        for p in (".github/workflows/pipeline.yml", ".env", "server.pem",
                  "id_rsa", "creds.json.key"):
            r = guard.evaluate(req([cf(p, ["x = 1"])]))
            self.assertEqual(r["verdict"], guard.FAIL, p)
            checks = {v["check"] for v in r["violations"]}
            self.assertIn("zero_scope_leakage", checks, p)

    def test_22_npm_dependency_addition_fails(self):
        files = [cf("package.json",
                    ['"dependencies": {', '  "left-pad": "^1.3.0"', "}"]),
                 GOOD_TEST]
        r = guard.evaluate(req(files))
        checks = {v["check"] for v in r["violations"]}
        self.assertIn("zero_dependency_bloat", checks)

    def test_23_requirements_addition_fails(self):
        files = [cf("requirements.txt", ["requests==2.0.0"]), GOOD_TEST]
        self.assertEqual(guard.evaluate(req(files))["verdict"], guard.FAIL)

    def test_24_allow_new_dependencies_flag_skips_check(self):
        files = [cf("requirements.txt", ["requests==2.0.0"]), GOOD_TEST]
        r = guard.evaluate(req(files, allow_new_dependencies=True))
        self.assertEqual(r["verdict"], guard.PASS)

    def test_25_public_api_removal_fails_without_note(self):
        files = [cf("scripts/ci/g.py", [], ["def old_check(x):", "    return x"]),
                 GOOD_TEST]
        r = guard.evaluate(req(files))
        checks = {v["check"] for v in r["violations"]}
        self.assertIn("backward_compatibility", checks)

    def test_26_migration_note_allows_removal(self):
        files = [cf("scripts/ci/g.py", [], ["def old_check(x):", "    return x"]),
                 GOOD_TEST]
        r = guard.evaluate(req(files, migration_notes=["old_check -> new_check"]))
        self.assertEqual(r["verdict"], guard.PASS)

    def test_27_symbol_relocation_allows_removal(self):
        files = [cf("scripts/ci/g.py",
                    ["def old_check(x):", "    return x"],
                    ["def old_check(x):", "    return x"]),
                 GOOD_TEST]
        self.assertEqual(guard.evaluate(req(files))["verdict"], guard.PASS)

    def test_28_route_removal_fails(self):
        files = [cf("src/app.py", [], ["@app.route('/items')", "def items():", "    pass"]),
                 GOOD_TEST]
        r = guard.evaluate(req(files))
        self.assertEqual(r["verdict"], guard.FAIL)


class FailClosedAndContract(unittest.TestCase):
    def test_29_verdict_constants(self):
        self.assertEqual(guard.PASS, "PASS")
        self.assertEqual(guard.FAIL, "FAIL")

    def test_30_malformed_requests_raise(self):
        for bad in (None, "x", 42, {}, {"changed_files": "x"},
                    {"changed_files": [{"added": []}]},
                    {"changed_files": [{"path": "a.py", "added": "x"}],
                     "declared_files": ["a.py"]},
                    {"changed_files": [{"path": "a.py"}], "declared_files": None}):
            with self.assertRaises(ValueError):
                guard.evaluate(bad)

    def test_31_migration_notes_bad_type_raises(self):
        with self.assertRaises(ValueError):
            guard.evaluate(req([GOOD_TEST], migration_notes="nope"))

    def test_32_verdict_shape(self):
        r = guard.evaluate(req([GOOD_FUNC, GOOD_TEST]))
        for key in ("verdict", "beneficial", "zero_regression", "violations",
                    "stats", "evaluated_at"):
            self.assertIn(key, r)
        self.assertIn("passed", r["beneficial"])
        self.assertIn("failed_checks", r["zero_regression"])

    def test_33_empty_diff_is_churn_fail(self):
        r = guard.evaluate(req([cf("scripts/ci/g.py")]))
        self.assertEqual(r["verdict"], guard.FAIL)

    def test_34_stats_fields(self):
        r = guard.evaluate(req([GOOD_FUNC, GOOD_TEST]))
        for key in ("files_changed", "assertions_added", "semantic_lines",
                    "failing_tests_fixed"):
            self.assertIn(key, r["stats"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
