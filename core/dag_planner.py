"""
Task Dependency Graph Solver & Topological Planner — Core Decision Moat.
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple


class CycleDetectedError(ValueError):
    """Raised when a circular dependency is detected in the task DAG."""
    pass


@dataclass
class TaskNode:
    task_id: str
    title: str
    target_repo: str
    dependencies: Set[str] = field(default_factory=set)
    estimated_cost: int = 1


class DAGPlanner:
    """
    Topological Task Dependency Graph Resolver.
    Decomposes multi-task objectives and orders execution into parallel stages.
    """

    def __init__(self):
        self._nodes: Dict[str, TaskNode] = {}

    def add_task(self, task: TaskNode) -> None:
        self._nodes[task.task_id] = task

    def get_task(self, task_id: str) -> TaskNode | None:
        return self._nodes.get(task_id)

    def topological_sort(self) -> List[str]:
        """
        Kahn's Algorithm: computes execution order or raises CycleDetectedError.
        """
        # Validate dependencies exist
        in_degree: Dict[str, int] = {t_id: 0 for t_id in self._nodes}
        adj: Dict[str, Set[str]] = {t_id: set() for t_id in self._nodes}

        for task_id, task in self._nodes.items():
            for dep in task.dependencies:
                if dep not in self._nodes:
                    raise KeyError(f"Task '{task_id}' depends on undefined task '{dep}'")
                adj[dep].add(task_id)
                in_degree[task_id] += 1

        queue = deque([t_id for t_id, deg in in_degree.items() if deg == 0])
        ordered: List[str] = []

        while queue:
            current = queue.popleft()
            ordered.append(current)

            for neighbor in adj[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered) != len(self._nodes):
            unresolved = [t_id for t_id, deg in in_degree.items() if deg > 0]
            raise CycleDetectedError(f"Circular dependency detected involving tasks: {unresolved}")

        return ordered

    def compute_execution_tiers(self) -> List[List[str]]:
        """
        Groups tasks into execution tiers where each tier can be executed in parallel.
        """
        self.topological_sort()  # Assert acyclic first

        tiers: List[List[str]] = []
        completed: Set[str] = set()
        remaining = set(self._nodes.keys())

        while remaining:
            current_tier = [
                t_id for t_id in remaining
                if self._nodes[t_id].dependencies.issubset(completed)
            ]
            if not current_tier:
                break
            tiers.append(sorted(current_tier))
            completed.update(current_tier)
            remaining.difference_update(current_tier)

        return tiers
