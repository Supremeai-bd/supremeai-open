from collections import defaultdict, deque
from typing import Any

from core.logging_config import logger


class ForgeCompiler:
    @staticmethod
    def compile_and_sort(
        nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Parses React Flow nodes and edges, validates DAG properties,
        and returns the linear execution sequence.
        """
        adj_list = defaultdict(list)
        in_degree = {node["id"]: 0 for node in nodes}
        node_map = {node["id"]: node for node in nodes}

        # Build adjacency list and calculate in-degrees
        for edge in edges:
            src = edge["source"]
            tgt = edge["target"]
            adj_list[src].append(tgt)
            if tgt in in_degree:
                in_degree[tgt] += 1

        # Queue for nodes with 0 in-degrees (Starting Triggers / TaskNodes)
        queue = deque([node_id for node_id, degree in in_degree.items() if degree == 0])
        execution_order = []

        while queue:
            curr = queue.popleft()
            execution_order.append(node_map[curr])

            for neighbor in adj_list[curr]:
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        if len(execution_order) != len(nodes):
            logger.critical("FATAL: Circular dependency detected in Visual Swarm Flow!")
            raise ValueError(
                "Circular dependency detected! Flow must be a strict Directed Acyclic Graph (DAG)."
            )

        return execution_order
