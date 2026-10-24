#!/usr/bin/env python3
"""Validate the declarative API router registry against importable routers."""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def module_file(module_path: str) -> Path:
    relative = Path(*module_path.split("."))
    package_file = BACKEND / relative / "__init__.py"
    module_file = BACKEND / relative.with_suffix(".py")
    return module_file if module_file.exists() else package_file


def registry_entries() -> list[dict[str, object]]:
    source = (BACKEND / "api" / "routers.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "ALL_ROUTERS" for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                return value
    raise RuntimeError("ALL_ROUTERS must be a literal list of dictionaries")


def has_router_definition(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    normalized = ast.unparse(tree)
    return bool(
        re.search(r"\brouter\s*=|\brouter\s*:\s*|\brouter\s*,|,\s*router\b", normalized)
    )


def main() -> int:
    registry = registry_entries()
    modules = [entry["path"] for entry in registry]
    errors: list[str] = []

    for index, entry in enumerate(registry):
        if set(entry) != {"path", "prefix", "is_admin", "is_critical"}:
            errors.append(f"entry {index} has an invalid schema: {entry}")
            continue
        path = module_file(str(entry["path"]))
        if not path.exists():
            errors.append(f"{entry['path']} is registered but missing: {path.relative_to(ROOT)}")
        else:
            try:
                if not has_router_definition(path):
                    errors.append(f"{entry['path']} has no router definition")
            except SyntaxError as exc:
                errors.append(f"{entry['path']} has invalid Python syntax: {exc}")

    duplicates = [path for path, count in Counter(modules).items() if count > 1]
    errors.extend(f"duplicate router registration: {path}" for path in duplicates)

    if errors:
        print("ROUTE REGISTRY: FAIL")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(f"ROUTE REGISTRY: OK ({len(registry)} unique importable routers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
