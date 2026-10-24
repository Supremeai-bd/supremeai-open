from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from route_graph_query import RouteGraph


def build_impact_report(graph: RouteGraph, node_ids: list[str], *, max_depth: int = 2, max_nodes: int = 100) -> dict[str, Any]:
    if not node_ids:
        raise ValueError("at least one node id is required")
    impacted: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for node_id in sorted(set(node_ids)):
        if graph.get_node(node_id) is None:
            missing.append(node_id)
            continue
        for node in graph.traverse(node_id, direction="outgoing", max_depth=max_depth, max_nodes=max_nodes):
            current = impacted.get(node["id"])
            if current is None or node["depth"] < current["depth"]:
                impacted[node["id"]] = node
    nodes = sorted(impacted.values(), key=lambda node: (node["depth"], node["kind"], node["id"]))
    return {
        "schema_version": "1.0",
        "roots": sorted(set(node_ids)),
        "missing_roots": missing,
        "limits": {"max_depth": max_depth, "max_nodes_per_root": max_nodes},
        "impact_count": len(nodes),
        "impacted_nodes": nodes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a bounded route graph impact report")
    parser.add_argument("--graph", default="docs/generated/route_knowledge_graph.json")
    parser.add_argument("--node", action="append", required=True, dest="nodes")
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-nodes", type=int, default=100)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = build_impact_report(RouteGraph.from_path(args.graph), args.nodes, max_depth=args.max_depth, max_nodes=args.max_nodes)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
