# backend/evolution/skill_graph.py
"""Semantic Skill Graph module for SupremeAI 2.0.

Provides dynamic, directed graph representation of skills using networkx,
including input-output type compatibility verification, dynamic weights,
and fallback routing.
"""

from __future__ import annotations

try:
    import networkx as nx
except ImportError:
    nx = None
from typing import Any

from core.logging_config import logger


class EvolutionSkillGraph:
    """Directed graph representing semantic connections between dynamic skills.

    Nodes represent skill names.
    Edges represent compatible data transitions (Skill A output -> Skill B input).
    """

    def __init__(self) -> None:
        if nx is not None:
            self.graph = nx.DiGraph()
        else:
            self.graph = None
        # Fallback dictionary mapping skill_id to fallback_skill_id
        self.fallbacks: dict[str, str] = {}

    def is_type_compatible(self, output_type: str, input_type: str) -> bool:
        """Determines if the output type of a skill can fit into the input type of another."""
        out_clean = output_type.strip().lower()
        in_clean = input_type.strip().lower()

        if out_clean == in_clean:
            return True

        # Common conversions
        compatibility_matrix = {
            "list": ["json", "array"],
            "dict": ["json", "object"],
            "json": ["dict", "list"],
            "int": ["float"],
            "float": [],
            "str": [],
        }

        allowed_inputs = compatibility_matrix.get(out_clean, [])
        return in_clean in allowed_inputs

    def add_skill(self, skill_id: str, metadata: dict[str, Any]) -> None:
        """Registers a skill node and scans for connections to other nodes in the graph."""
        if self.graph is None:
            return

        self.graph.add_node(skill_id, metadata=metadata)

        # Register fallback if defined
        fallback = metadata.get("fallback_skill")
        if fallback:
            self.fallbacks[skill_id] = fallback

        # Re-evaluate edges incrementally
        inputs = metadata.get("inputs", [])
        outputs = metadata.get("outputs", [])

        # Check existing nodes to see if this new skill can consume their outputs
        for existing_id, node_data in self.graph.nodes(data=True):
            if existing_id == skill_id or not node_data:
                continue

            # Can existing_id feed into skill_id?
            existing_outputs = node_data.get("metadata", {}).get("outputs", [])
            for e_out in existing_outputs:
                e_out_type = e_out.get("type", "str")
                for s_in in inputs:
                    s_in_type = s_in.get("type", "str")
                    if self.is_type_compatible(e_out_type, s_in_type):
                        self.graph.add_edge(existing_id, skill_id, weight=1.0, type=s_in_type)

            # Can skill_id feed into existing_id?
            existing_inputs = node_data.get("metadata", {}).get("inputs", [])
            for s_out in outputs:
                s_out_type = s_out.get("type", "str")
                for e_in in existing_inputs:
                    e_in_type = e_in.get("type", "str")
                    if self.is_type_compatible(s_out_type, e_in_type):
                        self.graph.add_edge(skill_id, existing_id, weight=1.0, type=e_in_type)

    def remove_skill(self, skill_id: str) -> None:
        """Gracefully removes a skill and its associated edges and fallbacks."""
        if self.graph is not None and self.graph.has_node(skill_id):
            self.graph.remove_node(skill_id)
        if skill_id in self.fallbacks:
            del self.fallbacks[skill_id]

    def update_edge_weight(self, source: str, target: str, success: bool) -> None:
        """Feedback-driven Weighting. Enhances or penalizes the edge weight based on usage."""
        if self.graph is not None and self.graph.has_edge(source, target):
            current_weight = self.graph[source][target]["weight"]
            if success:
                # Stronger connection (lower cost for shortest path algorithm)
                self.graph[source][target]["weight"] = max(0.1, current_weight - 0.1)
            else:
                # Penalize connection
                self.graph[source][target]["weight"] = current_weight + 0.5

    def find_execution_path(self, start_skill: str, end_skill: str) -> list[str]:
        """Finds the optimal path (lowest weight sum) from start to end skill."""
        if self.graph is None or nx is None:
            return []
        try:
            path = nx.shortest_path(
                self.graph, source=start_skill, target=end_skill, weight="weight"
            )
            return path

        except (nx.NetworkXNoPath, nx.NodeNotFound) as e:
            logger.warning(f"No semantic path found between {start_skill} and {end_skill}: {e}")
            return []

    def get_fallback(self, skill_id: str) -> str | None:
        return self.fallbacks.get(skill_id)
