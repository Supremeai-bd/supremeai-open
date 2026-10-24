from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class CircleName(StrEnum):
    GATEWAY = "gateway"
    LLM = "llm"
    MEMORY = "memory"
    TASK = "task"
    BROWSER = "browser"
    MCP = "mcp"
    ADMIN = "admin"
    REALTIME = "realtime"
    ARTIFACT = "artifact"
    EVOLUTION = "evolution"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutionStatus(StrEnum):
    ACCEPTED = "accepted"
    APPROVAL_REQUIRED = "approval_required"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"


class ExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str = Field(default_factory=lambda: f"exec_{uuid4().hex}")
    correlation_id: str = Field(default_factory=lambda: f"corr_{uuid4().hex}")
    actor_id: str
    tenant_id: str
    workspace_id: str | None = None
    project_id: str | None = None
    conversation_id: str | None = None
    deadline_ms: int = Field(default=30_000, ge=1, le=300_000)
    idempotency_key: str | None = None
    trace_id: str | None = None


class CapabilityRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    owner_circle: CircleName
    risk_level: RiskLevel = RiskLevel.LOW
    approval_required: bool = False
    tenant_activation_required: bool = True
    timeout_ms: int = Field(default=30_000, ge=1, le=300_000)
    version: str = "1"


class CapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: CapabilityRef
    context: ExecutionContext
    source: str = Field(default="api", min_length=1, max_length=40)
    payload: Mapping[str, Any] = Field(default_factory=dict)


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    approval_required: bool = False
    reason: str | None = None
    policy_version: str = "1"


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verified: bool
    method: str
    details: Mapping[str, Any] = Field(default_factory=dict)


class AuditContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    policy_version: str = "1"
    approval_id: str | None = None


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str
    status: ExecutionStatus
    data: Any = None
    error_code: str | None = None
    error_message: str | None = None
    circle: CircleName
    capability: str
    verification: VerificationResult | None = None
    audit: AuditContext | None = None
    started_at: datetime | None = None
    finished_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex}")
    event_type: str
    schema_version: str = "1"
    execution_id: str
    correlation_id: str
    actor_id: str
    tenant_id: str
    circle: CircleName
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: Mapping[str, Any] = Field(default_factory=dict)


class CircleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CircleName
    display_name: str
    owner: str
    capabilities: tuple[CapabilityRef, ...] = ()
    health: str = "unknown"
    version: str = "1"
