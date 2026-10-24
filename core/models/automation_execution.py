import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from models.base import Base


class AutomationExecution(Base):
    __tablename__ = "automation_executions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String(36), index=True, nullable=False)
    idempotency_key = Column(String(100), index=True, nullable=True)
    workflow_key = Column(String(100), index=True, nullable=False)
    provider = Column(String(50), nullable=False)
    status = Column(String(50), default="PENDING", index=True)
    attempt = Column(Integer, default=1)

    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    http_status = Column(Integer, nullable=True)
    external_execution_id = Column(String(100), nullable=True)
    trace_id = Column(String(100), index=True, nullable=True)

    error_code = Column(String(100), nullable=True)
    error_message = Column(String(1024), nullable=True)

    # Orchestrator ExecutionRecord bridge (Plan Section 7 / Board TODO:
    # "Persist ExecutionRecord durably with policy, budget, tool-call, and
    # timestamp history"). These columns let the canonical orchestration truth
    # record (core.orchestration.conversation_orchestrator.ExecutionRecord)
    # land in the same durable table as automation dispatches.
    correlation_id = Column(String(100), index=True, nullable=True)
    tenant_id = Column(String(100), index=True, nullable=True)
    project_id = Column(String(100), nullable=True)
    conversation_id = Column(String(100), nullable=True)
    capability = Column(String(100), nullable=True)
    evidence = Column(JSON, nullable=True)
    policy = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint(
            "workflow_key", "idempotency_key", name="uq_automation_workflow_idempotency"
        ),
    )


class AutomationExecutionAttempt(Base):
    __tablename__ = "automation_execution_attempts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    execution_id = Column(
        String(36),
        ForeignKey("automation_executions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    attempt = Column(Integer, default=1, nullable=False)
    status = Column(String(50), default="PENDING")

    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    http_status = Column(Integer, nullable=True)
    error_code = Column(String(100), nullable=True)
    error_message = Column(String(1024), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
