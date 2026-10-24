"""Pydantic request/response schemas for the Mission Orchestration API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PhaseSpec(BaseModel):
    """A user-supplied phase definition (created in ``pending`` status)."""

    name: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=2000)


class PhaseState(BaseModel):
    """A phase as stored on the mission (name/status/note)."""

    name: str
    status: str = "pending"
    note: str = ""


class MissionCreate(BaseModel):
    """POST /api/v1/missions request body.

    ``owner_id`` is NOT accepted here — identity is ALWAYS derived from the
    authenticated principal (JWT ``sub``), never from the request body.
    """

    title: str = Field(min_length=1, max_length=200)
    goal_text: str = Field(min_length=1, max_length=20000)
    strategy: str | None = Field(default=None, max_length=200)
    strategy_options: list[str] = Field(default_factory=list, max_length=20)
    phases: list[PhaseSpec] | None = Field(default=None, max_length=50)
    priority: int = Field(default=5, ge=0, le=9)
    agent_id: str | None = Field(default=None, max_length=255)


class MissionOut(BaseModel):
    """Mission response payload."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    goal_text: str
    strategy: str | None = None
    strategy_options: list[str] = Field(default_factory=list)
    phases: list[PhaseState] = Field(default_factory=list)
    current_phase: int = 0
    state: str
    priority: int = 5
    owner_id: str
    agent_id: str | None = None
    failure_reason: str | None = None
    repair_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TraceEventOut(BaseModel):
    """Mission trace event response payload (audit trail)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mission_id: uuid.UUID
    seq: int
    phase: int
    event: str
    detail: dict[str, Any] | None = None
    created_at: datetime | None = None


class TransitionRequest(BaseModel):
    """Optional body for transition endpoints (fail / cancel / approve...).

    ``actor`` is service-level metadata for non-HTTP callers; the HTTP routes
    always derive the acting principal from the JWT instead.
    """

    reason: str | None = Field(default=None, max_length=2000)
    actor: str | None = Field(default=None, max_length=255)
