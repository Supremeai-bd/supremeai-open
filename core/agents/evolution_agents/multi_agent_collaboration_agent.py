"""
SupremeAI — Multi-Agent Collaboration Agent
============================================
Coordinates complex interactions between multiple agents.
- Agent capability registration and discovery
- Task decomposition and planning
- Collaborative execution and result aggregation
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from brain.model_router import ModelRouter
from core.cache import get_cache
from core.config_cache import config_cache
from core.logging_config import logger

COLLAB_CACHE_TTL = 300


@dataclass(frozen=True)
class AgentCapability:
    """Immutable agent capability record."""

    agent_id: str
    agent_name: str
    capabilities: list[str]
    specialties: list[str]
    max_concurrent_tasks: int
    current_load: float


@dataclass(frozen=True)
class TaskDecomposition:
    """Immutable task decomposition result."""

    original_task: str
    subtasks: list[dict[str, Any]]
    dependencies: list[tuple[str, str]]
    estimated_complexity: str
    recommended_agents: list[str]


@dataclass(frozen=True)
class CollaborationTask:
    """Immutable collaborative task."""

    task_id: str
    description: str
    assigned_agents: list[str]
    subtasks: list[dict[str, Any]]
    status: str
    created_at: datetime
    result: dict[str, Any] | None


class MultiAgentCollaborationAgent:
    """
    Coordinates complex interactions between multiple agents.
    """

    def __init__(self, llm_router: ModelRouter | None = None) -> None:
        self.llm = llm_router or ModelRouter()
        self.cache = get_cache()
        self._agents: dict[str, AgentCapability] = {}
        self._tasks: dict[str, CollaborationTask] = {}

    def _cache_key(self, prefix: str, identifier: str) -> str:
        raw = f"collab:{prefix}:{identifier}:{datetime.now(UTC).strftime('%Y%m%d%H')}"
        return f"collab:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    def register_agent_capability(self, capability: AgentCapability) -> None:
        """Register an agent's capabilities for collaboration."""
        self._agents[capability.agent_id] = capability
        logger.info(
            "Registered agent %s with capabilities: %s",
            capability.agent_name,
            capability.capabilities,
        )

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from the collaboration pool."""
        self._agents.pop(agent_id, None)

    async def decompose_task(self, task_description: str) -> TaskDecomposition:
        """Decompose a complex task into subtasks suitable for multi-agent execution."""
        cache_key = self._cache_key(
            "decompose", hashlib.sha256(task_description.encode()).hexdigest()[:12]
        )
        cached = await self.cache.get(cache_key)
        if cached:
            return TaskDecomposition(**cached)

        prompt = (
            f"Decompose this task into subtasks suitable for multi-agent execution:\n\n"
            f"{task_description}\n\n"
            f"Available agents with capabilities:\n"
            + "\n".join(
                f"- {a.agent_name}: {', '.join(a.capabilities)}" for a in self._agents.values()
            )
            + "\n\nReturn as JSON with: subtasks (list of {{id, description, required_capability, estimated_effort}}), "
            "dependencies (list of [subtask_id, depends_on_id]), estimated_complexity (simple/medium/complex), "
            "recommended_agents (list of agent names)"
        )

        try:
            result = await self.llm.async_route_and_generate(
                prompt=prompt,
                task_type="reasoning",
                max_tokens=config_cache.get("multi_agent_collaboration_agent_max_tokens", 1000),
            )
            import json

            content = result.get("text", "{}")
            data = json.loads(content) if isinstance(content, str) else content
            decomposition = TaskDecomposition(
                original_task=task_description,
                subtasks=data.get("subtasks", []),
                dependencies=[tuple(d) for d in data.get("dependencies", [])],
                estimated_complexity=data.get("estimated_complexity", "simple"),
                recommended_agents=data.get("recommended_agents", []),
            )
        except Exception as e:
            logger.error("Failed to decompose task: %s", e)
            decomposition = TaskDecomposition(
                original_task=task_description,
                subtasks=[
                    {
                        "id": "subtask-1",
                        "description": task_description,
                        "required_capability": "general",
                        "estimated_effort": "medium",
                    }
                ],
                dependencies=[],
                estimated_complexity="simple",
                recommended_agents=list(self._agents.keys())[:1] if self._agents else [],
            )

        await self.cache.set(
            cache_key,
            {
                "original_task": decomposition.original_task,
                "subtasks": decomposition.subtasks,
                "dependencies": decomposition.dependencies,
                "estimated_complexity": decomposition.estimated_complexity,
                "recommended_agents": decomposition.recommended_agents,
            },
            ttl=COLLAB_CACHE_TTL,
        )

        return decomposition

    def find_collaborators(
        self, required_capability: str, min_load: float = 0.0
    ) -> list[AgentCapability]:
        """Find agents with a specific capability and available capacity."""
        candidates = []
        for agent in self._agents.values():
            if (
                required_capability in agent.capabilities
                or required_capability in agent.specialties
            ):
                if agent.current_load < agent.max_concurrent_tasks:
                    candidates.append(agent)
        return sorted(candidates, key=lambda a: a.current_load)

    async def execute_collaborative_task(self, task_description: str) -> CollaborationTask:
        """Execute a collaborative task by decomposing and delegating to agents."""
        decomposition = await self.decompose_task(task_description)

        task_id = hashlib.sha256(
            f"{task_description}:{datetime.now(UTC).isoformat()}".encode()
        ).hexdigest()[:12]
        assigned_agents = []

        for subtask in decomposition.subtasks:
            req_cap = subtask.get("required_capability", "general")
            collaborators = self.find_collaborators(req_cap)
            if collaborators:
                assigned_agents.append(collaborators[0].agent_name)

        task = CollaborationTask(
            task_id=task_id,
            description=task_description,
            assigned_agents=assigned_agents,
            subtasks=decomposition.subtasks,
            status="decomposed",
            created_at=datetime.now(UTC),
            result=None,
        )
        self._tasks[task_id] = task
        return task

    def get_available_agents_summary(self) -> list[dict[str, Any]]:
        """Get summary of all registered agents and their capabilities."""
        return [
            {
                "agent_id": a.agent_id,
                "name": a.agent_name,
                "capabilities": a.capabilities,
                "load": f"{a.current_load}/{a.max_concurrent_tasks}",
            }
            for a in self._agents.values()
        ]


# Singleton
_collab_instance: MultiAgentCollaborationAgent | None = None


def get_multi_agent_collaboration() -> MultiAgentCollaborationAgent:
    """Get or create the singleton MultiAgentCollaborationAgent."""
    global _collab_instance
    if _collab_instance is None:
        _collab_instance = MultiAgentCollaborationAgent()
    return _collab_instance
