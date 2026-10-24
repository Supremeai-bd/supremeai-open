# backend/models/meta_ai.py
"""
Layer 6: Self-Evolution (Meta-AI) — Data Models.

Provides:
- AgentGenome: Genetic representation of an agent for breeding.
- AgentOffspring: Result of crossover/mutation breeding.
- PerformanceMetric: Time-series performance data per agent.
- WeakestLinkReport: Identified underperforming agents with suggestions.
- BreedingPool: Active pool of agents eligible for breeding.

বাংলা মন্তব্য: জেনেটিক অ্যালগরিদম এবং পারফরম্যান্স ট্র্যাকিং-এর জন্য ডাটা মডেল।
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class AgentStatus(enum.StrEnum):
    """Agent lifecycle status."""

    ACTIVE = "active"
    BREEDING = "breeding"
    RETIRED = "retired"
    FAILED = "failed"
    UNDER_REVIEW = "under_review"


class MetricType(enum.StrEnum):
    """Types of performance metrics tracked."""

    RESPONSE_TIME_MS = "response_time_ms"
    LATENCY = "latency"
    ACCURACY_SCORE = "accuracy_score"
    COST_PER_REQUEST = "cost_per_request"
    ERROR_RATE = "error_rate"
    THROUGHPUT_RPS = "throughput_rps"
    USER_SATISFACTION = "user_satisfaction"


class SuggestionAction(enum.StrEnum):
    """Possible actions suggested by PerformanceOracle."""

    RETRAIN = "retrain"
    REPLACE = "replace"
    DEPRECATE = "deprecate"
    OPTIMIZE = "optimize"
    BREED_NEW = "breed_new"
    NO_ACTION = "no_action"


# ────────────────────────────────
# SQLAlchemy Models (PostgreSQL)
# ────────────────────────────────


class AgentGenome(Base):
    """Genetic blueprint of an agent — stored as JSONB chromosome."""

    __tablename__ = "agent_genomes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    chromosome: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    """Genetic traits: prompt_template, model_name, temperature, tools, etc."""

    fitness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parent_a_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_genomes.id"), nullable=True
    )
    parent_b_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_genomes.id"), nullable=True
    )
    status: Mapped[AgentStatus] = mapped_column(
        String(50), default=AgentStatus.ACTIVE, nullable=False
    )
    lineage: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    """Ordered list of ancestor agent names for traceability."""

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __mapper_args__ = {"version_id_col": version}


class AgentOffspring(Base):
    """Result of a breeding operation — candidate agent awaiting evaluation."""

    __tablename__ = "agent_offspring"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    offspring_name: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    parent_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_genomes.id"), nullable=False
    )
    parent_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_genomes.id"), nullable=False
    )
    chromosome: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    crossover_method: Mapped[str] = mapped_column(String(50), nullable=False)
    mutation_rate: Mapped[float] = mapped_column(Float, default=0.05, nullable=False)
    evaluation_status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    fitness_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __mapper_args__ = {"version_id_col": version}


class PerformanceMetric(Base):
    """Time-series performance data for every agent invocation."""

    __tablename__ = "performance_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    metric_type: Mapped[MetricType] = mapped_column(String(50), index=True, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    """Extra context: request_id, user_id, model_used, etc."""

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    __mapper_args__ = {"version_id_col": version}


class WeakestLinkReport(Base):
    """Auto-generated report identifying underperforming agents."""

    __tablename__ = "weakest_link_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    """Weighted composite (0-1). Lower = worse."""

    response_time_percentile: Mapped[float] = mapped_column(Float, nullable=False)
    accuracy_percentile: Mapped[float] = mapped_column(Float, nullable=False)
    cost_percentile: Mapped[float] = mapped_column(Float, nullable=False)
    error_rate_percentile: Mapped[float] = mapped_column(Float, nullable=False)
    suggestion: Mapped[SuggestionAction] = mapped_column(String(50), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __mapper_args__ = {"version_id_col": version}


class BreedingPool(Base):
    """Active pool of agents eligible for genetic breeding."""

    __tablename__ = "breeding_pools"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pool_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    agent_names: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    min_fitness_threshold: Mapped[float] = mapped_column(Float, default=0.6, nullable=False)
    max_pool_size: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __mapper_args__ = {"version_id_col": version}
