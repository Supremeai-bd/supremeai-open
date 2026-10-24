import os

def replace_in_file(filepath, old_text, new_text):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    if old_text in content:
        content = content.replace(old_text, new_text)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")
    else:
        print(f"Could not find text in {filepath}")

old_ci_inputs = '''  workflow_dispatch:
    inputs:
      force_backend:
        description: 'Force Backend Run/Deploy'
        type: boolean
        default: false
      force_frontend:
        description: 'Force Frontend Run/Deploy'
        type: boolean
        default: false
      force_infra:
        description: 'Force Edge/Infra Run/Deploy'
        type: boolean
        default: false'''

new_ci_inputs = '''  workflow_dispatch:
    inputs:
      force_backend:
        description: 'Force Backend Run/Deploy'
        type: boolean
        default: false
      force_frontend:
        description: 'Force Frontend Run/Deploy'
        type: boolean
        default: false
      force_infra:
        description: 'Force Edge/Infra Run/Deploy'
        type: boolean
        default: false
      run_backend_overall:
        description: 'Run full backend test suite'
        type: boolean
        default: false'''

replace_in_file(r'.github/workflows/ci.yml', old_ci_inputs, new_ci_inputs)

old_tests_step = '''      - name: Run tests with coverage
        env:
          DATABASE_URL: postgresql://test_user:test_password@localhost:5432/supremeai_test
          ENV: test
          JWT_SECRET: test-secret-key-for-ci-minimum-32-chars-padding-for-length
          SUPREMEAI_JWT_SECRET: test-supremeai-jwt-secret-key-for-ci-minimum-64-chars-padding-1234
          ALLOW_TEST_AUTH_BYPASS: "true"
          USER_CORS_ORIGINS: http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173  # is_local()
          ADMIN_CORS_ORIGINS: http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173  # is_local()
        run: |
            poetry run pytest tests/ \\
            --cov=core \\
            --cov=api \\
            --cov=services \\
            --cov=tools \\
            --cov-report=xml \\
            --cov-report=json \\
            --cov-report=term-missing \\
            -v \\
            --tb=short \\
            --timeout=30 \\
            --timeout-method=thread \\
            -m "not requires_network and not e2e and not chaos"'''

new_tests_step = '''      - name: Run Critical backend tests
        env:
          DATABASE_URL: postgresql://test_user:test_password@localhost:5432/supremeai_test
          ENV: test
          JWT_SECRET: test-secret-key-for-ci-minimum-32-chars-padding-for-length
          SUPREMEAI_JWT_SECRET: test-supremeai-jwt-secret-key-for-ci-minimum-64-chars-padding-1234
          ALLOW_TEST_AUTH_BYPASS: "true"
          USER_CORS_ORIGINS: http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173  # is_local()
          ADMIN_CORS_ORIGINS: http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173  # is_local()
        run: |
          poetry run pytest tests/ \\
            --cov=core --cov=api --cov=services --cov=tools \\
            --cov-report=term-missing \\
            --cov-append \\
            -m "critical and not requires_network and not e2e and not chaos" \\
            -v \\
            --tb=short \\
            --timeout=30 \\
            --timeout-method=thread

      - name: Run Important backend tests
        env:
          DATABASE_URL: postgresql://test_user:test_password@localhost:5432/supremeai_test
          ENV: test
          JWT_SECRET: test-secret-key-for-ci-minimum-32-chars-padding-for-length
          SUPREMEAI_JWT_SECRET: test-supremeai-jwt-secret-key-for-ci-minimum-64-chars-padding-1234
          ALLOW_TEST_AUTH_BYPASS: "true"
          USER_CORS_ORIGINS: http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173  # is_local()
          ADMIN_CORS_ORIGINS: http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173  # is_local()
        run: |
          poetry run pytest tests/ \\
            --cov=core --cov=api --cov=services --cov=tools \\
            --cov-append \\
            --cov-report=json \\
            --cov-report=term-missing \\
            -m "important and not requires_network and not e2e and not chaos" \\
            -v \\
            --tb=short \\
            --timeout=30 \\
            --timeout-method=thread

      - name: Run Overall backend tests
        if: ${{ github.ref == 'refs/heads/main' || github.event.inputs.run_backend_overall == 'true' }}
        env:
          DATABASE_URL: postgresql://test_user:test_password@localhost:5432/supremeai_test
          ENV: test
          JWT_SECRET: test-secret-key-for-ci-minimum-32-chars-padding-for-length
          SUPREMEAI_JWT_SECRET: test-supremeai-jwt-secret-key-for-ci-minimum-64-chars-padding-1234
          ALLOW_TEST_AUTH_BYPASS: "true"
          USER_CORS_ORIGINS: http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173  # is_local()
          ADMIN_CORS_ORIGINS: http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173  # is_local()
        run: |
          poetry run pytest tests/ \\
            --cov=core --cov=api --cov=services --cov=tools \\
            --cov-report=xml \\
            --cov-report=json \\
            --cov-report=term-missing \\
            -v \\
            --tb=short \\
            --timeout=30 \\
            --timeout-method=thread \\
            -m "not requires_network and not e2e and not chaos"'''

replace_in_file(r'.github/workflows/ci.yml', old_tests_step, new_tests_step)

replace_in_file(r'.github/workflows/ci.yml', '# Use pyyaml to parse the policy, checking overall, critical and important tiers', '# On PRs this evaluates the Critical+Important execution slice;\n          # on main it evaluates the full Overall run.\n          # Use pyyaml to parse the policy, checking overall, critical and important tiers')

replace_in_file(r'.github/workflows/ci.yml', "if: ${{ needs.changes.outputs.backend == 'true' && needs.backend-tests.result == 'success' }}", "if: ${{ needs.changes.outputs.backend == 'true' && needs.backend-tests.result == 'success' && (github.ref == 'refs/heads/main' || github.event.inputs.run_backend_overall == 'true') }}")

old_pyproject = '''python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]'''

new_pyproject = '''python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
markers = [
    "critical: fast, merge-blocking tests for core production paths",
    "important: important backend regression tests for normal PR validation",
    "overall: full backend test-suite classification marker",
]'''

replace_in_file(r'backend/pyproject.toml', old_pyproject, new_pyproject)

old_conftest = '''# ============================================================
# SupremeAI - Test Configuration & Shared Fixtures
# Production-Ready pytest Configuration
# ============================================================
import asyncio
import os
import sys
import uuid
import warnings
from typing import AsyncGenerator'''

new_conftest = '''# ============================================================
# SupremeAI - Test Configuration & Shared Fixtures
# Production-Ready pytest Configuration
# ============================================================
import asyncio
from pathlib import Path
import os
import sys
import uuid
import warnings
from typing import AsyncGenerator'''

replace_in_file(r'backend/tests/conftest.py', old_conftest, new_conftest)

conftest_hook_old = '''os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("TESTING", "true")


class CustomAssertions:'''

conftest_hook_new = '''os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("TESTING", "true")


# ============================================================
# CI TEST TIER CLASSIFICATION
# ============================================================
# Keep tiering in one place so CI can run a fast Critical/Important
# subset without maintaining a large file list in GitHub Actions.
# Critical paths mirror the production coverage policy.

_TEST_ROOT = Path(__file__).resolve().parent

_CRITICAL_TEST_PARTS = (
    ("security",),
    ("api", "auth"),
    ("api", "routes", "agent"),
    ("api", "routes", "api_keys"),
    ("api", "routes", "billing"),
    ("core", "llm"),
    ("core", "orchestration"),
    ("core", "security"),
    ("core", "queue"),
    ("core", "microvm_sandbox"),
    ("services", "usage"),
    ("services", "memory"),
    ("tools", "checkpoint_manager"),
    ("tools", "parallel_agent_executor"),
)

_IMPORTANT_TEST_PARTS = (
    ("services",),
    ("tools",),
    ("api", "routes"),
)


def _matches_test_parts(
    test_file: Path, patterns: tuple[tuple[str, ...], ...]
) -> bool:
    relative = test_file.resolve().relative_to(_TEST_ROOT).parts
    return any(
        len(relative) >= len(pattern)
        and all(
            segment == pattern_segment
            or (
                pattern_segment.endswith("*")
                and segment.startswith(pattern_segment[:-1])
            )
            for segment, pattern_segment in zip(relative, pattern)
        )
        for pattern in patterns
    )


def pytest_configure(config):
    """Register explicit CI tier markers for strict-marker mode."""
    config.addinivalue_line(
        "markers", "critical: fast, merge-blocking tests for core production paths"
    )
    config.addinivalue_line(
        "markers",
        "important: important backend regression tests for normal PR validation",
    )
    config.addinivalue_line(
        "markers", "overall: full backend test-suite classification marker"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-classify collected tests into Critical/Important/Overall tiers."""
    import pytest
    for item in items:
        test_file = Path(str(item.fspath))
        if _matches_test_parts(test_file, _CRITICAL_TEST_PARTS):
            item.add_marker(pytest.mark.critical)
        elif _matches_test_parts(test_file, _IMPORTANT_TEST_PARTS):
            item.add_marker(pytest.mark.important)
        else:
            item.add_marker(pytest.mark.overall)


class CustomAssertions:'''

replace_in_file(r'backend/tests/conftest.py', conftest_hook_old, conftest_hook_new)
