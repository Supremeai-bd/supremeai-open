"""Render Account State and Preflight Event SQLAlchemy Models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text, func

from models.base import Base


class RenderAccountState(Base):
    """Stores the latest known state, plan, usage, and cooldown for a Render account/role."""

    __tablename__ = "render_account_states"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_key = Column(String(120), nullable=False, unique=True, index=True)
    role = Column(String(80), nullable=False, index=True)
    plan = Column(String(40), nullable=False, default="unknown")
    status = Column(
        String(32), nullable=False, default="unknown"
    )  # ready, cooldown, blocked, unknown, error, etc.
    reason = Column(String(120), nullable=True)
    usage_minutes = Column(Float, nullable=True)
    usage_period_start = Column(DateTime(timezone=True), nullable=True)
    recheck_at = Column(DateTime(timezone=True), nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    extra_metadata = Column("metadata", JSON, nullable=True, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "account_key": self.account_key,
            "role": self.role,
            "plan": self.plan,
            "status": self.status,
            "reason": self.reason,
            "usage_minutes": self.usage_minutes,
            "usage_period_start": self.usage_period_start.isoformat()
            if self.usage_period_start
            else None,
            "recheck_at": self.recheck_at.isoformat() if self.recheck_at else None,
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
            "last_error": self.last_error,
            "retry_count": self.retry_count,
            "metadata": self.extra_metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RenderPreflightEvent(Base):
    """Audit log of all preflight checks, status transitions, cooldowns, and overrides."""

    __tablename__ = "render_preflight_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_key = Column(String(120), nullable=False, index=True)
    status = Column(String(32), nullable=False)
    reason = Column(String(120), nullable=True)
    usage_minutes = Column(Float, nullable=True)
    observed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        index=True,
    )
    extra_metadata = Column("metadata", JSON, nullable=True, default=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "account_key": self.account_key,
            "status": self.status,
            "reason": self.reason,
            "usage_minutes": self.usage_minutes,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "metadata": self.extra_metadata or {},
        }
