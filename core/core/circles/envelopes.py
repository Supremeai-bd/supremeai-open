"""Canonical center-to-center envelopes — FCC Architecture.

SupremeAI Federated Capability Circle Architecture (FCC):

    Module A → own circle center → shared control protocol (envelope)
    Circle center → GovernanceCore → other circle center

Direct module-to-module dependency is forbidden; the ONLY permitted wire
format for cross-circle calls is the envelope pair below. The JSON shape
matches the FCC contract 1:1:

    request  → {"execution_id", "circle", "capability", "tenant_id",
                "actor_id", "correlation_id", "payload", "policy",
                "deadline_ms"}
    result   → {"execution_id", "status", "circle", "data", "events",
                "error"}

The envelopes bridge to the legacy in-process contracts
(``CapabilityRequest`` / ``ExecutionResult``) so the federation and the
pre-FCC ``circle_registry`` stay interoperable during migration.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .contracts import (
    CapabilityRef,
    CapabilityRequest,
    CircleName,
    EventEnvelope,
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
)


class ExecutionError(BaseModel):
    """Structured error inside a :class:`ResultEnvelope`."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str | None = None


class ExecutionEnvelope(BaseModel):
    """The single permitted cross-circle request format (FCC contract)."""

    model_config = ConfigDict(extra="forbid")

    execution_id: str = Field(default_factory=lambda: f"exec_{uuid4().hex}")
    circle: CircleName
    capability: str = Field(min_length=1, max_length=160)
    tenant_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    correlation_id: str = Field(default_factory=lambda: f"corr_{uuid4().hex}")
    payload: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)
    deadline_ms: int = Field(default=30_000, ge=1, le=300_000)

    def to_capability_request(self, ref: CapabilityRef | None = None) -> CapabilityRequest:
        """Bridge into the legacy in-process request contract."""
        capability_ref = ref or CapabilityRef(name=self.capability, owner_circle=self.circle)
        return CapabilityRequest(
            capability=capability_ref,
            context=ExecutionContext(
                execution_id=self.execution_id,
                correlation_id=self.correlation_id,
                actor_id=self.actor_id,
                tenant_id=self.tenant_id,
                deadline_ms=self.deadline_ms,
            ),
            source="federation",
            payload=self.payload,
        )

    @classmethod
    def from_capability_request(cls, request: CapabilityRequest) -> ExecutionEnvelope:
        """Bridge a legacy request into the federation envelope."""
        return cls(
            execution_id=request.context.execution_id,
            circle=request.capability.owner_circle,
            capability=request.capability.name,
            tenant_id=request.context.tenant_id,
            actor_id=request.context.actor_id,
            correlation_id=request.context.correlation_id,
            payload=dict(request.payload),
            deadline_ms=min(request.context.deadline_ms, request.capability.timeout_ms),
        )


class ResultEnvelope(BaseModel):
    """The single permitted cross-circle result format (FCC contract)."""

    model_config = ConfigDict(extra="forbid")

    execution_id: str
    status: ExecutionStatus
    circle: CircleName
    data: Any = None
    events: tuple[EventEnvelope, ...] = ()
    error: ExecutionError | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe projection matching the FCC result contract."""
        return {
            "execution_id": self.execution_id,
            "status": self.status.value,
            "circle": self.circle.value,
            "data": self.data,
            "events": [event.model_dump(mode="json") for event in self.events],
            "error": self.error.model_dump() if self.error else None,
        }


def result_envelope_from_execution(
    result: ExecutionResult, events: tuple[EventEnvelope, ...] = ()
) -> ResultEnvelope:
    """Bridge a legacy :class:`ExecutionResult` into a :class:`ResultEnvelope`."""
    error = None
    if result.error_code or result.error_message:
        error = ExecutionError(
            code=result.error_code or "circle_handler_failed",
            message=result.error_message,
        )
    return ResultEnvelope(
        execution_id=result.execution_id,
        status=result.status,
        circle=result.circle,
        data=result.data,
        events=events,
        error=error,
    )


__all__ = [
    "ExecutionEnvelope",
    "ExecutionError",
    "ResultEnvelope",
    "result_envelope_from_execution",
]
