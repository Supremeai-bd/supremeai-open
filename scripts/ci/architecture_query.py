#!/usr/bin/env python3
"""Bounded, read-only architecture inspection CLI.

Examples:
  python scripts/ci/architecture_query.py --flow browser_task
  python scripts/ci/architecture_query.py --kind route --label '/health'
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from route_graph_query import RouteGraph

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "docs/generated/route_knowledge_graph.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flow", help="Exact graph label to inspect")
    parser.add_argument("--kind", choices=("contract", "route", "capability", "control"))
    parser.add_argument("--label", help="Exact node label")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--max-nodes", type=int, default=100)
    args = parser.parse_args()
    if args.depth < 0 or args.depth > 10 or args.max_nodes < 1 or args.max_nodes > 1000:
        parser.error("depth must be 0..10 and max-nodes must be 1..1000")

    graph = RouteGraph.from_path(GRAPH)
    label = args.flow or args.label
    matches = graph.find(kind=args.kind, label=label)
    if not label and not args.kind:
        result = {"schema_version": graph.graph.get("schema_version"), "nodes": len(graph.nodes)}
    else:
        result = {"matches": []}
        for node in matches:
            result["matches"].append({
                "node": node,
                "neighbors": graph.traverse(node["id"], max_depth=args.depth, max_nodes=args.max_nodes),
            })
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

__all__ = ["main"]
