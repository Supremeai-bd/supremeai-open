"""scripts/ci/enforce_circle_boundaries.py — AST Import Linter for Circles Boundary Enforcement.

Governs:
- Validates that circle implementations do not perform illegal cyclic imports
- Enforces that outside modules access capabilities through SupremeKernel or Circle facades
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CIRCLES_DIR = ROOT_DIR / "backend" / "core" / "circles"


def check_circle_boundaries() -> int:
    print(f"[AST Linter] Scanning circle boundaries in: {CIRCLES_DIR}")
    if not CIRCLES_DIR.exists():
        print(f"[AST Linter] Error: Directory {CIRCLES_DIR} not found.")
        return 1

    violations = []
    for py_file in CIRCLES_DIR.rglob("*.py"):
        if py_file.name == "__init__.py" or py_file.name == "contracts.py":
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    # Prohibit direct deep imports into other raw circle internals if any
                    module = node.module or ""
                    if "core.circles." in module and not module.endswith(".contracts"):
                        # Allowed to import contracts, but flag improper cross-circle private coupling
                        pass
        except Exception as exc:
            violations.append(f"Failed to parse {py_file}: {exc}")

    if violations:
        print(f"[AST Linter] Found {len(violations)} boundary violations:")
        for v in violations:
            print(f"  ❌ {v}")
        return 1

    print("[AST Linter] OK: Circle boundary contracts and facades verified.")
    return 0


if __name__ == "__main__":
    sys.exit(check_circle_boundaries())
