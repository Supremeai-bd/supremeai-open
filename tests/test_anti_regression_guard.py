from __future__ import annotations

from scripts.ci.anti_regression_guard import is_fix_pr, validate_anti_regression


def test_is_fix_pr_detection():
    assert is_fix_pr("fix(ci): fix flaky timeout") is True
    assert is_fix_pr("hotfix: emergency patch") is True
    assert is_fix_pr("feat(bridge): new feature") is False
    assert is_fix_pr("docs(api): update spec") is False


def test_validate_anti_regression_requires_test_file():
    passed, reasons = validate_anti_regression(
        title="fix(core): memory leak in worker pool",
        changed_files=["core/worker.py"],
        body="## Reflection Evidence\n- **why:** worker leak\n- **alternatives_rejected:** none",
    )
    assert passed is False
    assert any("tests/" in r for r in reasons)


def test_validate_anti_regression_passes_with_test_file():
    passed, reasons = validate_anti_regression(
        title="fix(core): memory leak in worker pool",
        changed_files=["core/worker.py", "tests/test_worker_pool_regression.py"],
        body="## Reflection Evidence\n- **why:** worker leak\n- **alternatives_rejected:** none",
    )
    assert passed is True
    assert len(reasons) == 0


def test_validate_anti_regression_exempt_labels():
    passed, _ = validate_anti_regression(
        title="fix(docs): typo in README",
        changed_files=["README.md"],
        body="typo",
        labels=["guard-exempt"],
    )
    assert passed is True

