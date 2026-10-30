"""Guard: modules imported as top-level by satellite tests must be layout-agnostic.

Incident #3441: core/decision_engine.py used
`from core.monitoring.logging_config import logger`, which only resolves in the
open-repo layout. In the satellite core repo the module is imported as a
top-level module, so the import failed and blocked pytest collection.

This guard parses core/tests/*.py for top-level module imports, then ensures
those modules do not hard-import layout-fragile `core.*` paths at module
top level without a try/except fallback.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = REPO_ROOT / "core"
CORE_TESTS = CORE_DIR / "tests"

FRAGILE = {("monitoring", "logging_config")}


def _top_level_imports_in_tests():
    modules = set()
    if not CORE_TESTS.exists():
        return modules
    for py in CORE_TESTS.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module and not node.module.startswith("."):
                    modules.add(node.module.split(".")[0])
    return modules


def _hard_fragile_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("core.")
            and getattr(node, "col_offset", 1) == 0
        ):
            parts = node.module.split(".")[1:]
            if tuple(parts[:2]) in FRAGILE or tuple(parts) in FRAGILE:
                yield node.lineno, node.module


def test_satellite_top_level_modules_are_layout_agnostic():
    modules = _top_level_imports_in_tests()
    offenders = []
    for name in sorted(modules):
        path = CORE_DIR / f"{name}.py"
        if not path.exists():
            continue
        for lineno, mod in _hard_fragile_imports(path):
            offenders.append(f"core/{name}.py:{lineno}: {mod}")
    assert not offenders, "Hardcoded layout-fragile core.* imports in satellite-top-level modules:\n" + "\n".join(offenders)
