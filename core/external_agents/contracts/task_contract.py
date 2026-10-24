"""
backend/external_agents/contracts/task_contract.py
==================================================
ISSUE-1572 (Part 3): the canonical ``TaskContract`` — the unit of work a
human/operator delegates to external coding agents (ZCode, ChatGPT, Gemini,
Lovable, Bolt), plus the provider and task-state vocabularies shared by the
whole external-agents pipeline.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "AgentProvider",
    "TaskContract",
    "TaskState",
    "new_task_id",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def new_task_id() -> str:
    return f"task-{uuid.uuid4().hex[:12]}"


class AgentProvider(StrEnum):
    """External agent providers recognised by the capability registry (#1573)."""

    ZCODE = "zcode"
    CHATGPT = "chatgpt"
    GEMINI = "gemini"
    LOVABLE = "lovable"
    BOLT = "bolt"


class TaskState(StrEnum):
    """Durable lifecycle states (#1572) — extended by #1573+ stages."""

    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    CHECKPOINT = "CHECKPOINT"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    WAITING_FOR_CHANNEL = "WAITING_FOR_CHANNEL"


class TaskContract(BaseModel):
    """The binding work order handed to an external agent."""

    task_id: str = Field(default_factory=new_task_id)
    issue_number: int | None = Field(
        default=None, description="GitHub issue this task implements, when applicable"
    )
    goal: str = Field(min_length=1, description="What the agent must accomplish")
    constraints: dict[str, Any] = Field(
        default_factory=dict,
        description="Hard boundaries: file scope, forbidden paths, budget, deadline…",
    )
    allowed_providers: list[AgentProvider] = Field(
        default_factory=lambda: list(AgentProvider),
        description="Providers permitted to claim this task",
    )
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def with_constraints(self, **extra: Any) -> TaskContract:
        merged = {**self.constraints, **extra}
        return self.model_copy(update={"constraints": merged})
