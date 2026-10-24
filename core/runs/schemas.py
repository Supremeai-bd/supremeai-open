"""Pydantic schemas for the canonical Run API (M1-C).

Mirrors ``missions/schemas.py`` conventions: request payloads validate
input, response payloads serialize ORM rows (``from_attributes``) without
triggering async lazy loads (all serialized columns are client-side loaded
per the models' ``_utcnow`` defaults).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from runs.models import RunType
from runs.state_machine import STATES


class RunCreate(BaseModel):
    """Creation request — the async boundary returns a ``run_id`` ack."""

    run_type: str = Field(..., description=f"One of: {sorted(rt.value for rt in RunType)}")
    title: str | None = Field(None, max_length=200)
    workspace_id: str | None = Field(None, max_length=255)
    chat_id: str | None = Field(None, max_length=255)
    mission_id: uuid.UUID | None = None
    parent_run_id: uuid.UUID | None = None
    source_type: str | None = Field(None, max_length=32)
    source_ref: str | None = Field(None, max_length=255)
    idempotency_key: str | None = Field(None, max_length=100)
    trace_id: str | None = Field(None, max_length=100)
    correlation_id: str | None = Field(None, max_length=100)
    max_wall_clock_ms: int | None = Field(None, ge=0)
    max_tokens: int | None = Field(None, ge=0)
    max_tool_calls: int | None = Field(None, ge=0)
    max_retries: int | None = Field(None, ge=0)


class RunOut(BaseModel):
    """Canonical run view — the M1 verdict field list, serialized."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    run_type: str
    status: str
    title: str | None
    user_id: str
    workspace_id: str | None
    chat_id: str | None
    mission_id: uuid.UUID | None
    parent_run_id: uuid.UUID | None
    source_type: str | None
    source_ref: str | None
    trace_id: str | None
    correlation_id: str | None
    max_wall_clock_ms: int | None
    max_tokens: int | None
    max_tool_calls: int | None
    max_retries: int | None
    tokens_used: int
    tool_calls_used: int
    retries_used: int
    retry_class: str | None
    error: str | None
    artifacts: list[dict[str, Any]]
    requested_at: datetime
    started_at: datetime | None
    terminal_at: datetime | None
    finalized_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RunTransitionRequest(BaseModel):
    """Lifecycle transition request — ``to`` must be a legal next state."""

    to: str = Field(..., description=f"Target state; one of: {list(STATES)}")
    actor: str | None = Field(None, max_length=255)
    detail: dict[str, Any] | None = None


class RunUsageRequest(BaseModel):
    """Usage report — admission-controlled against the run's budgets."""

    tokens: int = Field(0, ge=0)
    tool_calls: int = Field(0, ge=0)
    actor: str | None = Field(None, max_length=255)


class RunClassifyRequest(BaseModel):
    """Failure classification — the fixed 8-class retry taxonomy."""

    retry_class: str = Field(..., max_length=32)
    error: str | None = None
    actor: str | None = Field(None, max_length=255)


class RunRetryRequest(BaseModel):
    """Retry scheduling — RUNNING -> RETRYING under budget + guard."""

    retry_class: str | None = Field(None, max_length=32)
    actor: str | None = Field(None, max_length=255)


class RunCancelRequest(BaseModel):
    actor: str | None = Field(None, max_length=255)
    reason: str | None = Field(None, max_length=1024)


class RunEventOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    run_id: uuid.UUID
    seq: int
    event: str
    detail: dict[str, Any] | None
    created_at: datetime


class RunAck(BaseModel):
    """The async boundary contract: long ops receive this immediately."""

    run_id: uuid.UUID
    status: str
    poll: str = Field(..., description="GET path to observe the run")
