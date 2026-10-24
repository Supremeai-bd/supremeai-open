"""backend/core/kernel/interface.py — SupremeKernel Unified Interface Contracts.

Mandatory Rule #1 & Pure Cloud Production Parity:
- Fully typed, tenant-aware, zero-local dependency interface.
- Central single-door entry for all capabilities across the 4 SupremeAI Circles.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ExecutionMode(StrEnum):
    SYNC = "sync"
    ASYNC = "async"
    STREAM = "stream"
    DEBATE = "debate"


class CircleScope(StrEnum):
    GOVERNANCE = "governance"
    EXECUTION = "execution"
    EVOLUTION = "evolution"
    INFRASTRUCTURE = "infrastructure"


class KernelRequest(BaseModel):
    """Universal inbound request contract for SupremeKernel."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default_factory=lambda: f"req_{uuid4().hex}")
    correlation_id: str = Field(default_factory=lambda: f"corr_{uuid4().hex}")
    trace_id: str | None = None
    target_circle: CircleScope
    capability: str = Field(min_length=1, max_length=160)
    mode: ExecutionMode = ExecutionMode.SYNC
    actor_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    workspace_id: str | None = None
    idempotency_key: str | None = None
    deadline_ms: int = Field(default=30_000, ge=1, le=300_000)
    payload: Mapping[str, Any] = Field(default_factory=dict)
    metadata: Mapping[str, Any] = Field(default_factory=dict)


class KernelResponse(BaseModel):
    """Universal outbound response contract from SupremeKernel."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    correlation_id: str
    trace_id: str | None = None
    target_circle: CircleScope
    capability: str
    status: str = Field(default="succeeded")  # accepted | running | succeeded | failed | rejected
    data: Any = None
    error_code: str | None = None
    error_message: str | None = None
    execution_time_ms: float = 0.0
    verified: bool = True
    audit_id: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
