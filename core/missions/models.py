"""Mission Orchestration models (Task 7-c).

Two tables back the generic Mission Orchestration core
(``docs/plans/design/mission_orchestration_plan.md`` semantics):

- ``missions``: a Mission links a GOAL (``goal_text`` — the plan's
  "Requirement") to a STRATEGY (``strategy`` — the plan's "Exploitation
  Technique") and tracks ordered PHASES (``phases`` JSON) through the strict
  state machine in :mod:`missions.state_machine`.
- ``mission_trace_events``: immutable, per-mission sequenced audit trail (the
  plan's "Mission Trace" — step-by-step agent logic + audit linkage).

DEVIATION from the plan document: the plan says "Store in Firestore:
active_missions/", but this codebase persists via SQLAlchemy models on
Supabase PostgreSQL — hence SQLAlchemy here. The models intentionally
subclass ``models.base.Base`` (NOT ``core.db.Base``): that is the canonical
DeclarativeBase shared by ~25 existing models, wired into
``alembic_migrations/env.py`` (``target_metadata``) and the test conftest's
``create_all``.

JSON columns use ``JSON().with_variant(JSONB, "postgresql")`` (same pattern as
``models/system_config.py`` / ``models/meta_ai.py``) so the schema stays
sqlite-testable while using JSONB in production PostgreSQL.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin

# JSON that compiles to ``json`` on SQLite (tests) and ``jsonb`` on PostgreSQL
# (production) — repo-wide pattern, see models/system_config.py.
JSON_VARIANT = JSON().with_variant(JSONB, "postgresql")


def _utcnow() -> datetime:
    """Client-side UTC timestamp factory.

    Client-side defaults (vs the mixin's server_default/onupdate) keep the
    attributes loaded in Python during flush, so pydantic can serialize the
    ORM object BEFORE commit without triggering an async lazy refresh
    (MissingGreenlet) in the API layer.
    """
    return datetime.now(UTC)


class Mission(Base, TimestampMixin):
    """A mission linking a goal (requirement) to a strategy (technique)."""

    # Override TimestampMixin's server-generated timestamps with client-side
    # defaults — see _utcnow docstring (MissingGreenlet in API serialization).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __tablename__ = "missions"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Mission identity
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # The GOAL — the plan's "Requirement" (what must be achieved).
    goal_text: Mapped[str] = mapped_column(Text, nullable=False)
    # The STRATEGY — the plan's "Exploitation Technique" (how it is achieved).
    strategy: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Candidate strategies for the failure-repair loop to rotate through.
    strategy_options: Mapped[list[str]] = mapped_column(
        JSON_VARIANT,
        nullable=False,
        default=list,
        server_default="[]",
    )
    # Ordered phases: [{"name": str, "status": str, "note": str}, ...]
    # status ∈ {"pending", "in_progress", "completed"}.
    phases: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_VARIANT,
        nullable=False,
        default=list,
        server_default="[]",
    )
    # 0-based index of the phase currently being executed.
    current_phase: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Strict state machine state — see missions.state_machine.STATES.
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="planned", index=True)

    # Scheduling metadata
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    # Authenticated principal that owns the mission (from the JWT ``sub``).
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Assigned agent label ("auto-agent-v1" for the default stub assigner).
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Last failure reason (set by ``fail`` / exhausted repair loop).
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # How many repair rotations have been performed (bounded by MAX_REPAIRS).
    repair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<Mission(id={self.id!s}, state={self.state}, strategy={self.strategy!r})>"


class MissionTraceEvent(Base):
    """Immutable, per-mission sequenced trace event (audit trail).

    Event kinds: ``state_transition`` | ``agent_assigned`` | ``phase_started``
    | ``phase_completed`` | ``repair_triggered`` | ``cancelled``.
    ``detail`` carries structured context (including the acting principal when
    provided) for the plan's audit-linkage requirement.
    """

    __tablename__ = "mission_trace_events"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Owning mission — cascade delete with the mission (trace is 1:1 lifetime).
    mission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("missions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Monotonically increasing per-mission sequence number.
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    # Phase index the mission was in when the event fired.
    phase: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Event kind (see class docstring).
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    # Structured context: {"from": ..., "to": ..., "actor": ..., ...}.
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON_VARIANT, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("mission_id", "seq", name="uq_mission_trace_mission_seq"),)

    def __repr__(self) -> str:
        return (
            f"<MissionTraceEvent(mission_id={self.mission_id!s}, seq={self.seq}, "
            f"event={self.event!r})>"
        )
