from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


class RouteGraph:
    """Read-only, bounded query interface for the generated route graph."""

    def __init__(self, graph: dict[str, Any]):
        self.graph = graph
        self.nodes = {node["id"]: node for node in graph.get("nodes", [])}
        self.outgoing: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.incoming: dict[str, list[dict[str, str]]] = defaultdict(list)
        for edge in graph.get("edges", []):
            self.outgoing[edge["source"]].append(edge)
            self.incoming[edge["target"]].append(edge)
        for edges in (self.outgoing, self.incoming):
            for node_edges in edges.values():
                node_edges.sort(key=lambda edge: (edge["relation"], edge["target"], edge["source"]))

    @classmethod
    def from_path(cls, path: str | Path) -> "RouteGraph":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self.nodes.get(node_id)

    def find(self, *, kind: str | None = None, label: str | None = None) -> list[dict[str, Any]]:
        matches = self.nodes.values()
        if kind is not None:
            matches = (node for node in matches if node.get("kind") == kind)
        if label is not None:
            matches = (node for node in matches if node.get("label") == label)
        return sorted(matches, key=lambda node: node["id"])

    def neighbors(self, node_id: str, *, direction: str = "outgoing", relation: str | None = None) -> list[dict[str, Any]]:
        if direction not in {"outgoing", "incoming"}:
            raise ValueError("direction must be 'outgoing' or 'incoming'")
        edges = self.outgoing.get(node_id, []) if direction == "outgoing" else self.incoming.get(node_id, [])
        target_key = "target" if direction == "outgoing" else "source"
        return [self.nodes[edge[target_key]] for edge in edges if relation is None or edge["relation"] == relation]

    def traverse(self, start_id: str, *, direction: str = "outgoing", max_depth: int = 2, max_nodes: int = 100) -> list[dict[str, Any]]:
        if max_depth < 0 or max_nodes < 1:
            raise ValueError("max_depth must be non-negative and max_nodes must be positive")
        if start_id not in self.nodes:
            return []
        result: list[dict[str, Any]] = []
        queue = deque([(start_id, 0)])
        seen = {start_id}
        while queue and len(result) < max_nodes:
            node_id, depth = queue.popleft()
            result.append({**self.nodes[node_id], "depth": depth})
            if depth >= max_depth:
                continue
            for node in self.neighbors(node_id, direction=direction):
                if node["id"] not in seen:
                    seen.add(node["id"])
                    queue.append((node["id"], depth + 1))
        return result
