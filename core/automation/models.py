from datetime import UTC, datetime, timezone
from enum import StrEnum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class AutomationStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"  # When automation is disabled


class IntegrationHealth(BaseModel):
    """Health check response for any third-party integration."""

    status: str = Field(..., description="healthy, degraded, or unhealthy")
    provider: str
    message: str
    latency_ms: float | None = None
    details: dict | None = None


class AutomationEvent(BaseModel):
    """
    Vendor-neutral envelope for background events.

    বাংলা: Plan Section 6 অনুযায়ী durable distributed automation-এর জন্য
    প্রয়োজনীয় সব field যোগ করা হয়েছে — event_id, idempotency_key, trace_id,
    schema_version, timestamp, source, tenant_id, actor_type, actor_id।

    Backward-compat: সব নতুন field optional (default সহ), যাতে existing
    `AutomationEvent(workflow_key=..., payload=...)` call গুলো কাজ করে।
    event_id ও idempotency_key auto-generate হয় যদি না দেওয়া হয়।
    """

    model_config = ConfigDict(extra="forbid")

    # ── Identity & idempotency (Section 8) ─────────────────────────────────
    event_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique event identifier (UUID). Auto-generated if not provided.",
    )
    idempotency_key: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Idempotency key — একই key দিয়ে dispatch করলে duplicate execution এড়ানো যায়।",
    )
    schema_version: str = Field(
        default="1",
        description="Event schema version — future migration-এর জন্য।",
    )

    # ── Routing & tracing (Section 6) ──────────────────────────────────────
    workflow_key: str = Field(
        ...,
        description="The unique registry key identifying the target workflow (e.g., 'USER_REGISTERED').",
    )
    trace_id: str | None = Field(
        default=None,
        description="OpenTelemetry/observability trace ID for distributed tracing.",
    )

    # ── Timing & provenance ─────────────────────────────────────────────────
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="ISO-8601 timestamp of event creation (UTC).",
    )
    source: str = Field(
        default="supremeai",
        description="Event source identifier (e.g., 'supremeai', 'agent-xyz').",
    )

    # ── Multi-tenancy & actor (Section 6) ───────────────────────────────────
    tenant_id: str | None = Field(
        default=None,
        description="Tenant identifier for multi-tenant isolation.",
    )
    actor_type: str | None = Field(
        default=None,
        description="Actor type (e.g., 'agent', 'user', 'system').",
    )
    actor_id: str | None = Field(
        default=None,
        description="Actor identifier (e.g., agent ID or user ID).",
    )

    # ── Payload (backward-compat preserved) ─────────────────────────────────
    payload: dict[str, Any] = Field(
        default_factory=dict, description="The data to be processed by the workflow."
    )
    metadata: dict[str, Any] | None = Field(
        default=None, description="Optional tracking metadata (e.g., user_id, trace_id)."
    )


class ExecutionEnvelope(BaseModel):
    """Canonical governance envelope shared by chat, tools, browser, and agents."""

    model_config = ConfigDict(extra="forbid")

    execution_id: str = Field(default_factory=lambda: str(uuid4()))
    actor_id: str
    tenant_id: str
    intent: str
    policy_decision: str = "pending"
    model_route: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)
    status: str = "queued"
    trace_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AutomationResult(BaseModel):
    """
    Standardized response from the automation dispatcher.
    """

    status: AutomationStatus
    provider: str
    message: str
    execution_id: str | None = None
    # Plan Section 7: link event → execution
    event_id: str | None = Field(
        default=None,
        description="The event_id that triggered this result (for event→execution linkage).",
    )
    attempt: int = Field(
        default=1,
        description="Which attempt this result represents (1-based, for retry tracking).",
    )
