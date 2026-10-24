#!/usr/bin/env python3
"""Export a deterministic knowledge graph from the committed route inventory."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs/generated/route_inventory.json"
OUTPUT = ROOT / "docs/generated/route_knowledge_graph.json"


def stable_id(kind: str, value: str) -> str:
    digest = hashlib.sha256(f"{kind}:{value}".encode()).hexdigest()[:20]
    return f"{kind}:{digest}"


def build_graph(inventory: dict) -> dict:
    nodes: dict[str, dict] = {}
    edges: set[tuple[str, str, str]] = set()

    source_id = stable_id("contract", inventory["source"])
    nodes[source_id] = {"id": source_id, "kind": "contract", "label": inventory["source"]}

    for route in inventory.get("routes", []):
        route_key = f"{route['method']} {route['path']}"
        route_id = stable_id("route", route_key)
        nodes[route_id] = {
            "id": route_id,
            "kind": "route",
            "label": route_key,
            "metadata": {
                "operation_id": route.get("operation_id"),
                "auth_required": route.get("auth", {}).get("required", False),
                "owner": route.get("owner", "unassigned"),
            },
        }
        edges.add((source_id, "defines", route_id))
        for tag in sorted(route.get("tags", [])):
            tag_id = stable_id("capability", tag)
            nodes[tag_id] = {"id": tag_id, "kind": "capability", "label": tag}
            edges.add((route_id, "exposes", tag_id))
        if route.get("auth", {}).get("required"):
            auth_id = stable_id("control", "authenticated-access")
            nodes[auth_id] = {"id": auth_id, "kind": "control", "label": "authenticated-access"}
            edges.add((route_id, "requires", auth_id))

    serialized_edges = [
        {"source": source, "relation": relation, "target": target}
        for source, relation, target in sorted(edges)
    ]
    return {
        "schema_version": "1.0",
        "source": inventory["source"],
        "source_sha256": inventory["source_sha256"],
        "node_count": len(nodes),
        "edge_count": len(serialized_edges),
        "nodes": [nodes[node_id] for node_id in sorted(nodes)],
        "edges": serialized_edges,
    }


def main() -> int:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    graph = build_graph(inventory)
    OUTPUT.write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"generated {graph['node_count']} nodes and {graph['edge_count']} edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
