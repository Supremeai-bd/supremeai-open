"""circle_architecture_gate.py — cross-circle import boundary gate (M11 Phase-1 refactored).

বাংলা: নিয়মগুলো এখন ``architecture-rules.yml`` (repo root) থেকে লোড হয় —
M11-এর zero-hardcode গ্রহণ-শর্ত; আগে FORBIDDEN_CROSS_CIRCLE_IMPORTS dict
ইন-কোডে ছিল। rules-ফাইল অনুপস্থিত/বিকৃত হলে লাউড ব্যর্থতা — কোনো নীরব
ডিফল্ট-নিয়ম নেই (fail-closed)।
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "architecture-rules.yml"


def load_forbidden_rules() -> dict[str, set[str]]:
    """নিয়ম ডেটা-ফাইল থেকে (backend/root → নিষিদ্ধ target-set)।"""
    import yaml

    if not RULES_PATH.exists():
        raise RuntimeError(
            f"architecture-rules.yml not found at {RULES_PATH} — boundary rules are "
            "load-bearing data; refusing to run without them (fail-closed)"
        )
    data = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")) or {}
    rules = data.get("forbidden_cross_circle_imports")
    if not isinstance(rules, dict) or not rules:
        raise RuntimeError(
            "architecture-rules.yml: 'forbidden_cross_circle_imports' must be a non-empty map"
        )
    return {str(src): {str(t) for t in targets} for src, targets in rules.items()}


def module_name(path: Path) -> str:
    return str(path).replace("\\", "/")


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.add(node.module)
    return values


def violations(root: Path, rules: dict[str, set[str]] | None = None) -> list[str]:
    """সব নিষিদ্ধ cross-circle আমদানি রিটার্ন (rules=None → data file থেকে)।"""
    forbidden = rules if rules is not None else load_forbidden_rules()
    found: list[str] = []
    for source_root, blocked in sorted(forbidden.items()):
        source_dir = root / source_root
        if not source_dir.exists():
            continue
        for path in sorted(source_dir.rglob("*.py")):
            imported = " ".join(sorted(imports(path)))
            for target in sorted(blocked):
                target_module = target.removesuffix(".py").replace("/", ".")
                if target_module in imported or target.replace("/", ".") in imported:
                    found.append(
                        f"{module_name(path)} imports forbidden cross-circle dependency {target}"
                    )
    return found


def main() -> int:
    errors = violations(ROOT)
    if errors:
        print("\n".join(errors))
        return 1
    print("circle architecture gate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
