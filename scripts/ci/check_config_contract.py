#!/usr/bin/env python3
"""Enforce that runtime configuration aliases are covered by the canonical registry."""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLASSIFICATION = ROOT / "backend" / "core" / "config_classification.py"


def load_registry():
    spec = importlib.util.spec_from_file_location("supremeai_config_classification", CLASSIFICATION)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {CLASSIFICATION}")
    module = importlib.util.module_from_spec(spec)
    # বাংলা: exec_module()-এর আগে sys.modules-এ register করা must — নাহলে
    # config_classification.py-এর `@dataclass(frozen=True)` ক্লাসগুলোতে ব্যবহৃত
    # `frozenset[ConfigClass]` টাইপ হিন্ট রিজলভ করার সময় dataclasses.py-এর
    # অভ্যন্তরীণ `_is_type()` হেল্পার `sys.modules[cls.__module__]` লুকআপ করে,
    # module registered না থাকলে None পায় এবং
    # "AttributeError: 'NoneType' object has no attribute '__dict__'" দিয়ে crash করে।
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return module.BY_NAME, module.ALIAS_TO_CANONICAL


def runtime_aliases() -> set[str]:
    result: set[str] = set()
    for path in (ROOT / "backend" / "core").glob("config*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "Field":
                continue
            for kw in node.keywords:
                if kw.arg == "validation_alias" and isinstance(kw.value, ast.Constant):
                    if isinstance(kw.value.value, str):
                        result.add(kw.value.value)
    return result


def main() -> int:
    by_name, aliases = load_registry()
    known = set(by_name) | set(aliases)
    used = runtime_aliases()
    unknown = sorted(used - known)
    for name in unknown:
        print(f"::error::runtime configuration alias is not classified: {name}")
    print(f"runtime validation aliases: {len(used)}")
    print(f"unclassified runtime aliases: {len(unknown)}")
    if unknown:
        print("FAIL: runtime configuration and canonical registry have drifted")
        return 1
    print("PASS: runtime configuration aliases are classified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
