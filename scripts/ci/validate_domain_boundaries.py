#!/usr/bin/env python3
"""Validate generated domain evidence and the Knowledge pilot contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "docs/generated/domain_dependency_graph.json"
CONTRACT = ROOT / "docs/architecture/module_contract.schema.yaml"


def main() -> int:
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    domains = {item["id"] for item in graph.get("domains", [])}
    errors: list[str] = []
    for edge in graph.get("edges", []):
        if edge["source"] not in domains or edge["target"] not in domains:
            errors.append(f"unknown domain edge: {edge}")
    for violation in graph.get("boundary_violations", []):
        errors.append(f"private cross-domain import: {violation['source']} -> {violation['target']}")
    if not CONTRACT.exists():
        errors.append("module contract schema is missing")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Domain boundary evidence valid: {len(domains)} domains, {len(graph.get('edges', []))} edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
