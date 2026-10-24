#!/usr/bin/env python3
"""Generate a secret-free Mermaid topology from the committed route graph."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "docs/generated/route_knowledge_graph.json"
OUTPUT = ROOT / "docs/generated/route_topology.mmd"


def mermaid_id(node_id: str) -> str:
    return "n_" + node_id.replace(":", "_")


def main() -> int:
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    lines = ["flowchart LR", "  %% Generated from route_knowledge_graph.json; no secrets or tenant data."]
    for node in graph.get("nodes", []):
        label = str(node.get("label", node["id"])).replace('"', "'")
        lines.append(f'  {mermaid_id(node["id"])}["{label}"]')
    for edge in graph.get("edges", []):
        relation = str(edge.get("relation", "links")).replace("|", "/")
        lines.append(f"  {mermaid_id(edge['source'])} -->|{relation}| {mermaid_id(edge['target'])}")
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"generated {len(lines) - 2} topology lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

__all__ = ["main", "mermaid_id"]
