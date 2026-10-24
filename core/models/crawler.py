"""SQLAlchemy ORM models for Crawler Policies, Domain Rules, and Crawl History."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from models.base import Base, TimestampMixin

# Use JSON compatible with both PostgreSQL JSONB and SQLite JSON
JSONType = JSON().with_variant(JSONB, "postgresql")


class CrawlPolicyModel(Base, TimestampMixin):
    """Database model for tenant crawl governance policies."""

    __tablename__ = "crawler_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="Default Policy")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_depth: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    max_results: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    default_rate_limit_per_min: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    request_timeout_seconds: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    cache_ttl_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    allowed_domains: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    blocked_domains: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)

    domain_rules: Mapped[list[DomainRuleModel]] = relationship(
        "DomainRuleModel", back_populates="policy", cascade="all, delete-orphan", lazy="selectin"
    )


class DomainRuleModel(Base):
    """Database model for domain-specific crawl constraints."""

    __tablename__ = "crawler_domain_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("crawler_policies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    domain: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    trust_level: Mapped[str] = mapped_column(String(20), default="standard", nullable=False)
    rate_limit_per_min: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    render_js: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allowed_paths: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    disallowed_paths: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)

    policy: Mapped[CrawlPolicyModel] = relationship(
        "CrawlPolicyModel", back_populates="domain_rules"
    )


class CrawlHistoryModel(Base):
    """Database model for audit and telemetry of crawl executions."""

    __tablename__ = "crawler_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    sources_crawled: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    total_pages_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_pages_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_content_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    extractive_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    token_reduction_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
