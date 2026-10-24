#!/usr/bin/env python3
"""Generate an evidence report for runtime configuration registry migration.

This tool intentionally does not mutate the canonical registry. It extracts the
runtime aliases that the existing contract checker understands and reports which
ones are already canonical/aliased. Classification is left for evidence-based
review instead of guessing from variable names.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLASSIFICATION = ROOT / "backend" / "core" / "config_classification.py"


def load_registry():
    spec = importlib.util.spec_from_file_location("supremeai_config_classification", CLASSIFICATION)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {CLASSIFICATION}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module.BY_NAME, module.ALIAS_TO_CANONICAL


def runtime_aliases() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
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
                if kw.arg != "validation_alias" or not isinstance(kw.value, ast.Constant):
                    continue
                if not isinstance(kw.value.value, str):
                    continue
                key = kw.value.value
                found.setdefault(key, []).append(str(path.relative_to(ROOT)))
    return found


def build_report() -> dict[str, object]:
    by_name, aliases = load_registry()
    runtime = runtime_aliases()
    keys = []
    for key in sorted(runtime):
        canonical = aliases.get(key, key)
        spec = by_name.get(canonical)
        keys.append({
            "key": key,
            "canonical": canonical if spec else None,
            "status": "classified" if spec else "unclassified",
            "evidence": sorted(set(runtime[key])),
            "review_required": spec is None,
        })
    return {
        "schema_version": 1,
        "source": "backend/core/config*.py Field(validation_alias=...)",
        "total_runtime_keys": len(keys),
        "classified": sum(x["status"] == "classified" for x in keys),
        "unclassified": sum(x["status"] == "unclassified" for x in keys),
        "keys": keys,
    }


def main() -> int:
    report = build_report()
    if len(sys.argv) == 2:
        output = Path(sys.argv[1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {output}")
    else:
        print(json.dumps(report, indent=2))
    print(
        f"runtime={report['total_runtime_keys']} "
        f"classified={report['classified']} "
        f"unclassified={report['unclassified']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
