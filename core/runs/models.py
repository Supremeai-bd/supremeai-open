"""Canonical Run + RunEvent models (M1 — ecosystem Ph1).

Two tables back the canonical Run fabric:

- ``runs``: the execution boundary row. Every Mission / Agent / Tool / MCP /
  Browser / Code execution observable as a Run carries identity
  (``user_id`` / ``workspace_id`` / ``chat_id``), lifecycle ``status``
  (strict machine in :mod:`runs.state_machine`), budgets (wall-clock, token,
  tool-call, retry — plain DB columns, colibrì-free), consumed counters,
  ``retry_class``, ``error`` and an ``artifacts`` reference list (M7 will
  formalize ``ref://`` semantics on top).
- ``run_events``: immutable, per-run sequenced audit stream (lifecycle
  transitions, budget verdicts, retry classifications, cancellations) —
  the same pattern as ``mission_trace_events``.

Extend-not-replace anchoring:

- ``Run.mission_id`` FK keeps canonical runs anchored to the existing
  Mission core (``missions/models.py``) — a mission's executions ARE runs,
  not a second run system.
- ``Run.source_type`` / ``Run.source_ref`` point at the originating evidence
  row (``automation_executions.id``, tool-call id, MCP invocation id, ...)
  without duplicating those subsystems; bridge mapping lands in M1-C.
- ``Run.parent_run_id`` self-reference lets M2's Context Engine anchor
  RUN/STEP scopes later (STEP = child run).

DEVIATION notes (same rationale as ``missions/models.py``): persistence is
SQLAlchemy on the canonical ``models.base.Base`` (NOT ``core.db.Base``) so
the tables join ``alembic_migrations/env.py`` metadata and the conftest
``create_all`` world. JSON columns use ``JSON().with_variant(JSONB,
"postgresql")`` so the schema stays sqlite-testable on production
PostgreSQL. Client-side ``_utcnow`` defaults keep attributes loaded in
Python during flush so pydantic can serialize BEFORE commit without an
async lazy refresh (MissingGreenlet) in the API layer.

Enum columns are plain ``String(32)`` validated at the service layer
against the ``StrEnum``/state-machine constants — same choice as the
missions ``state`` column; it avoids PG enum-type churn in migrations and
keeps sqlite tests honest.
"""

from __future__ import annotations

import enum
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
    """Client-side UTC timestamp factory (see module docstring)."""
    return datetime.now(UTC)


class RunType(enum.StrEnum):
    """Which subsystem's execution this run observes."""

    mission = "mission"
    agent = "agent"
    tool = "tool"
    mcp = "mcp"
    browser = "browser"
    code = "code"
    automation = "automation"
    pipeline = "pipeline"


class Run(Base, TimestampMixin):
    """A canonical execution run — the one execution contract (M1)."""

    # Override TimestampMixin's server-generated timestamps with client-side
    # defaults — see _utcnow docstring (MissingGreenlet in API serialization).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __tablename__ = "runs"

    # Primary key — this IS the run_id every subsystem observes.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # --- identity ---------------------------------------------------------
    # Which subsystem executes (RunType values; validated at service layer).
    run_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # Strict lifecycle state — see runs.state_machine.STATES.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="requested", index=True)
    # Human-readable label (e.g. "Deploy site via MCP", mission title, ...).
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Scope anchors (user verdict field list): user / workspace / chat.
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    chat_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # --- extend-not-replace anchoring -------------------------------------
    # Canonical anchor into the existing Mission core (SET NULL: the run's
    # audit trail must survive a mission cleanup).
    mission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("missions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # STEP anchoring for M2's Context Engine (STEP = child run); deleting a
    # parent must NOT delete the child's audit trail.
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Originating evidence row (e.g. "automation_execution:<uuid>",
    # "mcp_invocation:<id>", "tool_call:<id>") — bridges without duplication.
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Idempotency for run creation (same key must not double-create a run).
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    # Distributed tracing hand-off (matches automation_executions.trace_id).
    trace_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # --- budgets (roadmap M1: wall-clock / token / tool-call / retry) ------
    max_wall_clock_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_tool_calls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_retries: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- consumed counters --------------------------------------------------
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_calls_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retries_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- failure + artifacts ------------------------------------------------
    # RetryClass value of the last classified failure (runs.retry).
    retry_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Last error surface (user verdict field: error).
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Artifact reference list (M7 formalizes ref://run/{id}/artifact/{aid};
    # entries: {"artifact_id": ..., "kind": ..., "ref": ...}).
    artifacts: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_VARIANT,
        nullable=False,
        default=list,
        server_default="[]",
    )

    # --- lifecycle timestamps ------------------------------------------------
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Run(id={self.id!s}, run_type={self.run_type!r}, status={self.status!r})>"


class RunEvent(Base):
    """Immutable, per-run sequenced audit event (the run's event stream).

    Event kinds (open set, service-layer emits): ``run_created`` |
    ``status_transition`` | ``budget_exceeded`` | ``retry_classified`` |
    ``approval_requested`` | ``approval_resolved`` | ``cancelled`` |
    ``finalized`` | ... ``detail`` carries structured context (from/to,
    actor, budget snapshot, classification).
    """

    __tablename__ = "run_events"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Owning run — cascade delete with the run (event stream is 1:1 lifetime).
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Monotonically increasing per-run sequence number.
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    # Event kind (see class docstring).
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    # Structured context: {"from": ..., "to": ..., "actor": ..., ...}.
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON_VARIANT, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_run_events_run_seq"),)

    def __repr__(self) -> str:
        return f"<RunEvent(run_id={self.run_id!s}, seq={self.seq}, event={self.event!r})>"
