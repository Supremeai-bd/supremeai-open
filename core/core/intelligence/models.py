from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IntelligenceTier(StrEnum):
    FAST = "fast"
    VERIFIED = "verified"
    SWARM = "swarm"
    LAB = "lab"


class TaskClassification(StrEnum):
    GENERAL = "general"
    RESEARCH = "research"
    CODING = "coding"
    SENSITIVE = "sensitive"
    IRREVERSIBLE = "irreversible"


class ExecutionBudget(BaseModel):
    max_agents: int = Field(default=1, ge=1, le=12)
    max_refinements: int = Field(default=0, ge=0, le=3)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    requires_approval: bool = False
    sandbox_only: bool = True


class RoutingDecision(BaseModel):
    model_config = ConfigDict(frozen=True)
    tier: IntelligenceTier
    classification: TaskClassification
    budget: ExecutionBudget
    reason: str
    override_requested: str | None = None
    override_applied: bool = False
    audit_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class VerificationResult(BaseModel):
    status: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    degraded: bool = False


class ManualTask(BaseModel):
    id: str
    category: str
    title: str
    owner: str
    steps: list[str]
    evidence_required: list[str]
    status: str = "open"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    secret_free: bool = True
