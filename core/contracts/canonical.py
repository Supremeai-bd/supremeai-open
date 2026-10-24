"""Canonical, provider-neutral control-plane contracts.

These contracts are intentionally serializable and contain no persistence or provider code.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import StrEnum
from typing import Any


class ExecutionStatus(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


def utc_now() -> datetime:
    return datetime.now(UTC)


def _required(value: str, name: str) -> str:
    if not value or len(value) > 256:
        raise ValueError(f"invalid {name}")
    return value


@dataclass(frozen=True)
class ExecutionContext:
    execution_id: str = field(default_factory=lambda: f"exec_{uuid.uuid4().hex}")
    tenant_id: str = ""
    actor_id: str = ""
    workspace_id: str = ""
    correlation_id: str = ""
    idempotency_key: str = ""
    capability: str = ""
    risk_level: str = "medium"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "execution_id",
            "tenant_id",
            "actor_id",
            "workspace_id",
            "correlation_id",
            "idempotency_key",
            "capability",
        ):
            _required(getattr(self, name), name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "workspace_id": self.workspace_id,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "capability": self.capability,
            "risk_level": self.risk_level,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ExecutionResult:
    status: ExecutionStatus
    output: Any = None
    error_code: str | None = None
    error_message: str | None = None
    evidence: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "output": self.output,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class CapabilityContract:
    """Provider-neutral description of an executable capability."""

    capability_id: str
    version: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permissions: tuple[str, ...] = ()
    resource_requirements: dict[str, Any] = field(default_factory=dict)
    tenant_id: str | None = None

    def __post_init__(self) -> None:
        _required(self.capability_id, "capability_id")
        _required(self.version, "version")


@dataclass(frozen=True)
class ResourceContract:
    """A selectable execution resource without provider-specific behavior."""

    resource_id: str
    provider: str
    kind: str
    state: str = "available"
    capabilities: tuple[str, ...] = ()
    tenant_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required(self.resource_id, "resource_id")
        _required(self.provider, "provider")
        _required(self.kind, "kind")


@dataclass(frozen=True)
class ArtifactReference:
    """Small control-plane pointer to a potentially large immutable artifact."""

    artifact_id: str
    uri: str
    media_type: str
    sha256: str
    size_bytes: int
    tenant_id: str
    run_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("artifact_id", "uri", "media_type", "sha256", "tenant_id", "run_id"):
            _required(getattr(self, name), name)
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")


@dataclass(frozen=True)
class PolicyEvaluation:
    decision: PolicyDecision
    capability_id: str
    actor_id: str
    tenant_id: str
    reason: str = ""
    approval_id: str | None = None


@dataclass(frozen=True)
class EventEnvelope:
    event_type: str
    context: ExecutionContext
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex}")
    occurred_at: datetime = field(default_factory=utc_now)
    sequence: int | None = None

    @property
    def fingerprint(self) -> str:
        raw = json.dumps(
            {
                "event_type": self.event_type,
                "execution_id": self.context.execution_id,
                "payload": self.payload,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "context": self.context.to_dict(),
            "payload": self.payload,
            "occurred_at": self.occurred_at.isoformat(),
            "sequence": self.sequence,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str
    context: ExecutionContext
    action: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    reason: str = ""
    expires_at: datetime | None = None

    def consume(self) -> ApprovalRequest:
        if self.status is not ApprovalStatus.APPROVED:
            raise ValueError("approval must be approved before consumption")
        if self.expires_at and self.expires_at <= utc_now():
            raise ValueError("approval expired")
        return ApprovalRequest(
            self.approval_id,
            self.context,
            self.action,
            ApprovalStatus.CONSUMED,
            self.reason,
            self.expires_at,
        )


__all__ = [
    "ApprovalRequest",
    "ApprovalStatus",
    "ArtifactReference",
    "CapabilityContract",
    "EventEnvelope",
    "ExecutionContext",
    "ExecutionResult",
    "ExecutionStatus",
    "PolicyDecision",
    "PolicyEvaluation",
    "ResourceContract",
]
