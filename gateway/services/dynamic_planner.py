# backend/services/dynamic_planner.py
"""SupremeAI Dynamic Planning Engine (Phase 6.2 - North Star Pillar 2).

Hierarchical task decomposition & DAG execution planner:
- Converts unstructured IntentAnalysis into actionable, atomic TaskNodes in a Directed Acyclic Graph.
- Enforces strict cycle detection via Kahn's / Topological sorting.
- Automatically inserts Epistemic Probing, AST Analysis, Execution, Formal Verification, and Memory Consolidation nodes.
"""

from __future__ import annotations

import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.llm.advanced_model_router import ExpertType
from core.logging_config import logger
from services.intent_deciphering import IntentAnalysis


@dataclass
class TaskNode:
    id: str
    name: str
    capability: str
    description: str = ""
    input_params: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    expected_output_type: str = "json"
    status: str = "pending"
    output: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "capability": self.capability,
            "description": self.description,
            "input_params": self.input_params,
            "dependencies": self.dependencies,
            "expected_output_type": self.expected_output_type,
            "status": self.status,
            "output": self.output,
            "error": self.error,
        }


@dataclass
class TaskDAG:
    dag_id: str
    intent: IntentAnalysis
    nodes: dict[str, TaskNode] = field(default_factory=dict)

    def add_node(self, node: TaskNode) -> None:
        self.nodes[node.id] = node

    def add_dependency(self, child_id: str, parent_id: str) -> None:
        if child_id not in self.nodes:
            raise KeyError(f"Child node '{child_id}' not in DAG")
        if parent_id not in self.nodes:
            raise KeyError(f"Parent node '{parent_id}' not in DAG")
        if parent_id not in self.nodes[child_id].dependencies:
            self.nodes[child_id].dependencies.append(parent_id)

    def topological_sort(self) -> list[TaskNode]:
        """Returns nodes in valid dependency execution order. Raises ValueError on cycles."""
        in_degree: dict[str, int] = {node_id: 0 for node_id in self.nodes}
        graph: dict[str, list[str]] = defaultdict(list)

        for node_id, node in self.nodes.items():
            for dep_id in node.dependencies:
                if dep_id not in self.nodes:
                    raise ValueError(f"Node '{node_id}' depends on non-existent node '{dep_id}'")
                graph[dep_id].append(node_id)
                in_degree[node_id] += 1

        queue = deque([node_id for node_id, deg in in_degree.items() if deg == 0])
        ordered_ids: list[str] = []

        while queue:
            current = queue.popleft()
            ordered_ids.append(current)
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered_ids) != len(self.nodes):
            unresolved = [n for n, deg in in_degree.items() if deg > 0]
            raise ValueError(
                f"Cyclic dependency detected in TaskDAG. Unresolved nodes: {unresolved}"
            )

        return [self.nodes[nid] for nid in ordered_ids]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dag_id": self.dag_id,
            "intent": self.intent.to_dict(),
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
            "execution_order": [n.id for n in self.topological_sort()],
        }


class DynamicPlanningEngine:
    """Decomposes structured IntentAnalysis into an optimal Directed Acyclic Graph of execution steps."""

    def __init__(self) -> None:
        pass

    async def plan_task(self, intent: IntentAnalysis) -> TaskDAG:
        """Main entrypoint: Generates a complete execution DAG for the given intent."""
        dag_id = f"dag_{uuid.uuid4().hex[:8]}"
        dag = TaskDAG(dag_id=dag_id, intent=intent)

        # 1. Epistemic Probing Node (Inspect environment & state before mutation)
        # PLAN-003: CODER-domain probes get a real, budget-bounded repo map —
        # non-CODER intents are byte-for-byte unchanged (explicit absence, not
        # a fake map; indexer failure degrades honestly to today's behavior).
        repo_map_text: str | None = None
        if intent.domain == ExpertType.CODER.value:
            try:
                from core.code_indexer import CodeIndexer

                repo_map_text = CodeIndexer.get_instance(
                    root_dir=str(Path(__file__).resolve().parents[2])
                ).render_repo_map(budget_chars=4000, goal=intent.ultimate_goal)
            except Exception as exc:
                logger.warning(
                    f"[DynamicPlanner] repo map unavailable ({exc}); probe continues without it — honest degradation"
                )

        probe_params: dict[str, Any] = {"goal": intent.ultimate_goal, "domain": intent.domain}
        if repo_map_text:
            probe_params["repo_map"] = repo_map_text
        probe_node = TaskNode(
            id=f"{dag_id}_step1_probe",
            name="Epistemic State Probe",
            capability="probe_system_state",
            description=f"Inspect system state, relevant files, and contracts for: {intent.ultimate_goal}",
            input_params=probe_params,
        )
        dag.add_node(probe_node)

        # 2. Domain-Specific Execution Node(s)
        action_nodes = self._build_action_nodes(dag_id, intent, parent_id=probe_node.id)
        for node in action_nodes:
            dag.add_node(node)

        # 3. Formal Invariance Verification Node
        last_action_id = action_nodes[-1].id if action_nodes else probe_node.id
        verify_node = TaskNode(
            id=f"{dag_id}_step_verify",
            name="Dual-Loop Invariant Verifier",
            capability="verify_invariants",
            description="Run unit tests, check SLA metrics, and assert zero regression",
            input_params={
                "invariants": intent.invariants,
                "latent_constraints": intent.latent_constraints,
            },
            dependencies=[last_action_id],
        )
        dag.add_node(verify_node)

        # 4. Eternal Brain Memory Consolidation Node
        consolidate_node = TaskNode(
            id=f"{dag_id}_step_consolidate",
            name="Eternal Brain Memory Consolidation",
            capability="consolidate_ai_memory",
            description="Embed successful execution path and persist to ai_memory (pgvector)",
            input_params={
                "goal": intent.ultimate_goal,
                "methodology": intent.suggested_methodology,
            },
            dependencies=[verify_node.id],
        )
        dag.add_node(consolidate_node)

        # Ensure DAG validity
        dag.topological_sort()
        logger.info(
            f"DynamicPlanningEngine: Generated DAG '{dag_id}' with {len(dag.nodes)} nodes for goal '{intent.ultimate_goal[:50]}'"
        )
        return dag

    def _build_action_nodes(
        self, dag_id: str, intent: IntentAnalysis, parent_id: str
    ) -> list[TaskNode]:
        """Synthesizes intermediate execution nodes based on intent methodology."""
        methodology = intent.suggested_methodology

        if methodology == "reproduce_localize_ast_patch_and_verify":
            # Bugfix Pipeline
            n1 = TaskNode(
                id=f"{dag_id}_step2_localize",
                name="Defect Localization & AST Parse",
                capability="ast_localize_defect",
                description="Locate offending functions and parse syntax tree",
                dependencies=[parent_id],
            )
            n2 = TaskNode(
                id=f"{dag_id}_step3_patch",
                name="Synthesize AST Safe Patch",
                capability="apply_safe_code_patch",
                description="Generate and apply drop-in code fix without breaking invariants",
                dependencies=[n1.id],
            )
            return [n1, n2]

        elif methodology == "profile_bottlenecks_and_apply_caching":
            # Performance Pipeline
            n1 = TaskNode(
                id=f"{dag_id}_step2_profile",
                name="Performance Bottleneck Profiler",
                capability="profile_latency_and_throughput",
                description="Measure p99 latency, cache hit ratios, and db query times",
                dependencies=[parent_id],
            )
            n2 = TaskNode(
                id=f"{dag_id}_step3_optimize",
                name="Multi-Layer Cache & Index Tuning",
                capability="optimize_cache_layers",
                description="Apply Redis/in-memory LRU caching and query optimizations",
                dependencies=[n1.id],
            )
            return [n1, n2]

        elif methodology == "inject_explicit_rbac_guards":
            # Security Pipeline
            n1 = TaskNode(
                id=f"{dag_id}_step2_audit_routes",
                name="Route Security & Auth Audit",
                capability="audit_route_dependencies",
                description="Scan router endpoints for missing role dependencies",
                dependencies=[parent_id],
            )
            n2 = TaskNode(
                id=f"{dag_id}_step3_apply_rbac",
                name="Inject Role-Based Dependencies",
                capability="inject_rbac_guards",
                description="Inject Depends(get_current_admin) or Depends(get_current_user_token)",
                dependencies=[n1.id],
            )
            return [n1, n2]

        else:
            # General / Dynamic Task Pipeline
            n1 = TaskNode(
                id=f"{dag_id}_step2_execute",
                name="Dynamic Task Execution",
                capability="execute_dynamic_action",
                description=f"Execute task steps for: {intent.ultimate_goal}",
                dependencies=[parent_id],
            )
            return [n1]
