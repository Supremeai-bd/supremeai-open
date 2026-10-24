"""Correlation IDs — distributed tracing across the ecosystem (ROADMAP §44).

বাংলা: প্রতিটি user request → task → capability → resource → deployment → audit
চেইন একটি CorrelationContext-এর মাধ্যমে trace করা যায়। এটি distributed debugging
সহজ করে এবং "which commit caused which incident" প্রশ্নের উত্তর দেয়।
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from adaptive_engine._store import get_conn, jdump, jload

# বাংলা: ContextVar দিয়া same async task-এর ভেতরে correlation স্বয়ংক্রিয়ভাবে প্রবাহিত।
_current: ContextVar[CorrelationContext | None] = ContextVar(
    "adaptive_engine_correlation", default=None
)


@dataclass
class CorrelationContext:
    """Carry request_id / task_id / job_id / deployment_id / capability_id / audit_id."""

    request_id: str = field(default_factory=lambda: f"req-{uuid.uuid4().hex[:16]}")
    task_id: str | None = None
    job_id: str | None = None
    deployment_id: str | None = None
    resource_id: str | None = None
    capability_id: str | None = None
    audit_id: str | None = None
    user_id: str | None = None
    tenant_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_headers(self) -> dict[str, str]:
        """Headers to forward across service boundaries (HTTP / queue / WS)."""
        h = {
            "x-correlation-request-id": self.request_id,
            "x-correlation-audit-id": self.audit_id or "",
        }
        if self.task_id:
            h["x-correlation-task-id"] = self.task_id
        if self.job_id:
            h["x-correlation-job-id"] = self.job_id
        if self.deployment_id:
            h["x-correlation-deployment-id"] = self.deployment_id
        if self.resource_id:
            h["x-correlation-resource-id"] = self.resource_id
        if self.capability_id:
            h["x-correlation-capability-id"] = self.capability_id
        if self.tenant_id:
            h["x-correlation-tenant-id"] = self.tenant_id
        return h

    def child(self, **overrides: Any) -> CorrelationContext:
        """Spawn a child correlation inheriting the parent IDs (ROADMAP §44)."""
        base = {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "job_id": self.job_id,
            "deployment_id": self.deployment_id,
            "resource_id": self.resource_id,
            "capability_id": self.capability_id,
            "audit_id": self.audit_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "extra": dict(self.extra),
        }
        base.update(overrides)
        return CorrelationContext(**base)


def new_correlation_context(**kwargs: Any) -> CorrelationContext:
    """Create a fresh correlation context and bind it to the current async task."""
    ctx = CorrelationContext(**kwargs)
    _current.set(ctx)
    return ctx


def current_correlation() -> CorrelationContext:
    """Return the active correlation, creating an ephemeral one if none bound."""
    ctx = _current.get()
    if ctx is None:
        ctx = CorrelationContext()
        _current.set(ctx)
    return ctx


def bind_correlation(ctx: CorrelationContext) -> None:
    _current.set(ctx)


__all__ = [
    "CorrelationContext",
    "new_correlation_context",
    "current_correlation",
    "bind_correlation",
]
