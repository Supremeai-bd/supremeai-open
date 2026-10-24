"""CI smoke tests for the supremeai-browser satellite.

The satellite ci.yml gate 2 runs ``pytest -v``. Until now the repo shipped
zero test files, so pytest exited 5 (no tests collected) and the job failed
even when linting passed. These tests are intentionally dependency-free:
CI installs only ruff/pytest/pytest-asyncio/pydantic, while the runtime
needs playwright, httpx, bs4, lxml and cryptography -- so nothing here
imports runtime modules. Everything is checked at syntax/config level.
"""

import compileall
import pathlib
import re
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_all_python_files_compile() -> None:
    """Every .py file in the repo must be syntactically valid.

    compileall parses (and byte-compiles) without executing imports, so no
    runtime dependency is required and no side effect can leak.
    """
    ok = compileall.compile_dir(str(REPO_ROOT), quiet=2, force=True)
    assert ok, "compileall found syntax errors"


@pytest.mark.skipif(
    sys.version_info < (3, 11), reason="tomllib requires Python 3.11+ (CI runs 3.12)"
)
def test_pyproject_pins_ruff_rule_set() -> None:
    """Guard against ruff default-drift regressions.

    ruff 0.17 expanded its *default* select (BLE001, S110, TRY004, EXE002,
    RUF012, PYI034, PIE810 now fire with zero config), which turned this
    previously-green satellite red with no code change. The pinned classic
    stable rule set in pyproject.toml is the root-cause fix; this test pins
    the pin.
    """
    import tomllib

    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    ruff_cfg = data.get("tool", {}).get("ruff", {})
    # tolerate both layouts: [tool.ruff] select / [tool.ruff.lint] select
    lint_cfg = ruff_cfg.get("lint", ruff_cfg)
    select = lint_cfg.get("select", [])
    assert set(select) >= {"E4", "E7", "E9", "F"}, (
        f"ruff rule-set pin missing or weakened: {select!r}"
    )


def test_ci_gate_surface_files_exist() -> None:
    """Files the three CI gates depend on must remain present at their paths."""
    required = (
        "browser_agent.py",
        "ghost_tower/__init__.py",
        "pyproject.toml",
        ".github/workflows/ci.yml",
    )
    for rel in required:
        assert (REPO_ROOT / rel).is_file(), f"missing CI-gate surface file: {rel}"


def test_ruff_select_comment_documents_root_cause() -> None:
    """The ruff pin must keep its why-comment (anti-accidental-removal)."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"(?is)\[tool\.ruff(?:\.lint)?\](.*?)select\s*=", text)
    assert match, "[tool.ruff] lint select missing from pyproject.toml"
    assert "default" in match.group(1), (
        "the ruff default-drift rationale comment was removed from pyproject.toml"
    )
