# backend/core/evolution/performance_oracle.py
"""
Layer 6: Self-Evolution — PerformanceOracle.

Tracks agent performance metrics, identifies weakest links, and suggests:
- Retrain / Replace / Deprecate / Optimize / Breed new

Uses configurable weights for composite scoring. All thresholds from settings.

বাংলা মন্তব্য: Agent-দের response time, accuracy, cost track করে weakest link identify করে retrain/replace suggest করে।
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.logging_config import logger
from models.meta_ai import (
    MetricType,
    PerformanceMetric,
    SuggestionAction,
    WeakestLinkReport,
)

# ────────────────────────────────
# Configuration
# ────────────────────────────────


@dataclass(frozen=True)
class OracleConfig:
    """Runtime configuration sourced from environment/settings."""

    # Weight configuration (must sum to 1.0 ideally)
    weight_response_time: float
    weight_accuracy: float
    weight_cost: float
    weight_error_rate: float

    # Thresholds
    weak_link_threshold: float
    retrain_threshold: float
    replace_threshold: float
    deprecate_threshold: float

    # Lookback window (hours)
    lookback_hours: int

    # Minimum samples for reliable statistics
    min_sample_size: int

    @classmethod
    def from_settings(cls) -> OracleConfig:
        return cls(
            weight_response_time=getattr(settings, "oracle_weight_response_time", 0.25),
            weight_accuracy=getattr(settings, "oracle_weight_accuracy", 0.35),
            weight_cost=getattr(settings, "oracle_weight_cost", 0.20),
            weight_error_rate=getattr(settings, "oracle_weight_error_rate", 0.20),
            weak_link_threshold=getattr(settings, "oracle_weak_link_threshold", 0.40),
            retrain_threshold=getattr(settings, "oracle_retrain_threshold", 0.50),
            replace_threshold=getattr(settings, "oracle_replace_threshold", 0.30),
            deprecate_threshold=getattr(settings, "oracle_deprecate_threshold", 0.15),
            lookback_hours=getattr(settings, "oracle_lookback_hours", 24),
            min_sample_size=getattr(settings, "oracle_min_sample_size", 10),
        )


# ────────────────────────────────
# Core Engine
# ────────────────────────────────


class PerformanceOracle:
    """
    Monitors agent performance, computes percentile ranks, identifies weakest links.

    Key Components:
    - record_metric(): Ingest a single metric event.
    - get_agent_stats(): Aggregated stats per agent over lookback window.
    - identify_weakest_links(): Find underperformers and suggest actions.
    - generate_report(): Persist WeakestLinkReport to DB.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        config: OracleConfig | None = None,
    ) -> None:
        self._db = db_session
        self._config = config or OracleConfig.from_settings()

    # ── Metric ingestion ──

    async def record_metric(
        self,
        agent_name: str,
        metric_type: MetricType,
        value: float,
        unit: str,
        context: dict[str, Any] | None = None,
    ) -> PerformanceMetric:
        """
        Record a single performance metric event.
        """
        metric = PerformanceMetric(
            id=uuid.uuid4(),
            agent_name=agent_name,
            metric_type=metric_type,
            value=value,
            unit=unit,
            context=context or {},
            recorded_at=datetime.now(UTC),
        )
        self._db.add(metric)
        await self._db.commit()
        logger.debug(f"Recorded {metric_type.value}={value}{unit} for {agent_name}")
        return metric

    # ── Aggregation ──

    async def get_agent_stats(
        self,
        agent_name: str,
        lookback_hours: int | None = None,
    ) -> dict[str, Any]:
        """
        Compute aggregated statistics for an agent over the lookback window.
        """
        hours = lookback_hours or self._config.lookback_hours
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        query = select(PerformanceMetric).where(
            and_(
                PerformanceMetric.agent_name == agent_name,
                PerformanceMetric.recorded_at >= cutoff,
            )
        )
        result = await self._db.execute(query)
        metrics = list(result.scalars().all())

        if len(metrics) < self._config.min_sample_size:
            return {
                "agent_name": agent_name,
                "sample_count": len(metrics),
                "reliable": False,
                "message": f"Insufficient samples: {len(metrics)} < {self._config.min_sample_size}",
            }

        # Group by metric type
        by_type: dict[str, list[float]] = {}
        for m in metrics:
            by_type.setdefault(m.metric_type.value, []).append(m.value)

        stats = {
            "agent_name": agent_name,
            "sample_count": len(metrics),
            "lookback_hours": hours,
            "reliable": True,
        }

        for mtype, values in by_type.items():
            stats[mtype] = {
                "mean": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "p50": self._percentile(values, 50),
                "p95": self._percentile(values, 95),
                "p99": self._percentile(values, 99),
                "count": len(values),
            }

        return stats

    @staticmethod
    def _percentile(values: list[float], p: int) -> float:
        """Compute percentile using nearest-rank method."""
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        k = (len(sorted_vals) - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_vals) else f
        if f == c:
            return sorted_vals[f]
        return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])

    # ── Weakest link identification ──

    async def identify_weakest_links(
        self,
        agent_names: list[str] | None = None,
    ) -> list[WeakestLinkReport]:
        """
        Identify underperforming agents and suggest remediation actions.
        """
        # If no agents specified, get all agents with recent metrics
        if not agent_names:
            cutoff = datetime.now(UTC) - timedelta(hours=self._config.lookback_hours)
            distinct_query = (
                select(PerformanceMetric.agent_name)
                .where(PerformanceMetric.recorded_at >= cutoff)
                .distinct()
            )
            result = await self._db.execute(distinct_query)
            agent_names = [r[0] for r in result.all()]

        if not agent_names:
            logger.warning("No agents with recent metrics found")
            return []

        # Gather stats for all agents
        all_stats: dict[str, dict[str, Any]] = {}
        for name in agent_names:
            stats = await self.get_agent_stats(name)
            if stats.get("reliable"):
                all_stats[name] = stats

        if len(all_stats) < 2:
            logger.warning("Need >= 2 agents with reliable stats for comparison")
            return []

        # Compute percentile ranks per dimension
        reports: list[WeakestLinkReport] = []

        for agent_name, stats in all_stats.items():
            # Extract dimension scores (lower is better for response_time, cost, error_rate)
            # For accuracy, higher is better — invert
            rt_mean = stats.get(MetricType.RESPONSE_TIME_MS.value, {}).get("mean", 0)
            acc_mean = stats.get(MetricType.ACCURACY_SCORE.value, {}).get("mean", 1)
            cost_mean = stats.get(MetricType.COST_PER_REQUEST.value, {}).get("mean", 0)
            err_mean = stats.get(MetricType.ERROR_RATE.value, {}).get("mean", 0)

            # Compute percentile ranks across all agents
            rt_pct = self._rank_percentile(
                rt_mean,
                [
                    s.get(MetricType.RESPONSE_TIME_MS.value, {}).get("mean", 0)
                    for s in all_stats.values()
                ],
                lower_is_better=True,
            )
            acc_pct = self._rank_percentile(
                acc_mean,
                [
                    s.get(MetricType.ACCURACY_SCORE.value, {}).get("mean", 1)
                    for s in all_stats.values()
                ],
                lower_is_better=False,
            )
            cost_pct = self._rank_percentile(
                cost_mean,
                [
                    s.get(MetricType.COST_PER_REQUEST.value, {}).get("mean", 0)
                    for s in all_stats.values()
                ],
                lower_is_better=True,
            )
            err_pct = self._rank_percentile(
                err_mean,
                [s.get(MetricType.ERROR_RATE.value, {}).get("mean", 0) for s in all_stats.values()],
                lower_is_better=True,
            )

            # Weighted composite (0-1, lower = worse)
            composite = (
                self._config.weight_response_time * rt_pct
                + self._config.weight_accuracy * acc_pct
                + self._config.weight_cost * cost_pct
                + self._config.weight_error_rate * err_pct
            )

            # Determine suggestion
            suggestion, reasoning = self._suggest_action(
                composite, rt_pct, acc_pct, cost_pct, err_pct
            )

            report = WeakestLinkReport(
                id=uuid.uuid4(),
                agent_name=agent_name,
                composite_score=composite,
                response_time_percentile=rt_pct,
                accuracy_percentile=acc_pct,
                cost_percentile=cost_pct,
                error_rate_percentile=err_pct,
                suggestion=suggestion,
                reasoning=reasoning,
                is_acknowledged=False,
            )

            self._db.add(report)
            reports.append(report)

        await self._db.commit()

        # Sort by composite score ascending (worst first)
        reports.sort(key=lambda r: r.composite_score)

        logger.info(f"Generated {len(reports)} weakest-link reports")
        return reports

    @staticmethod
    def _rank_percentile(
        value: float,
        all_values: list[float],
        lower_is_better: bool,
    ) -> float:
        """
        Compute percentile rank (0-1) of value within all_values.
        """
        if not all_values:
            return 0.5

        sorted_vals = sorted(all_values)
        n = len(sorted_vals)

        # Find rank
        rank = sum(1 for v in sorted_vals if v <= value)
        if lower_is_better:
            # Lower value = higher rank (better)
            percentile = rank / n
        else:
            # Higher value = higher rank (better)
            percentile = (n - rank + 1) / n

        return max(0.0, min(1.0, percentile))

    def _suggest_action(
        self,
        composite: float,
        rt_pct: float,
        acc_pct: float,
        cost_pct: float,
        err_pct: float,
    ) -> tuple[SuggestionAction, str]:
        """
        Determine remediation action based on composite and dimension scores.
        """
        if composite >= self._config.weak_link_threshold:
            return (
                SuggestionAction.NO_ACTION,
                f"Composite score {composite:.2f} is acceptable. "
                f"All dimensions within normal range.",
            )

        if composite <= self._config.deprecate_threshold:
            return (
                SuggestionAction.DEPRECATE,
                f"CRITICAL: Composite {composite:.2f}. "
                f"Multiple failures across all dimensions. "
                f"Recommend immediate deprecation and replacement.",
            )

        if composite <= self._config.replace_threshold:
            return (
                SuggestionAction.REPLACE,
                f"SEVERE: Composite {composite:.2f}. "
                f"Accuracy={acc_pct:.0%}, ErrorRate={err_pct:.0%}. "
                f"Agent consistently underperforms. Replace with evolved version.",
            )

        if composite <= self._config.retrain_threshold:
            # Determine specific weakness
            weakest = min(
                [
                    ("response_time", rt_pct),
                    ("accuracy", acc_pct),
                    ("cost", cost_pct),
                    ("error_rate", err_pct),
                ],
                key=lambda x: x[1],
            )
            return (
                SuggestionAction.RETRAIN,
                f"MODERATE: Composite {composite:.2f}. "
                f"Weakest dimension: {weakest[0]} ({weakest[1]:.0%} percentile). "
                f"Targeted retraining recommended.",
            )

        # Between retrain and weak_link thresholds: optimize
        return (
            SuggestionAction.OPTIMIZE,
            f"LOW: Composite {composite:.2f}. "
            f"Marginal underperformance. Light optimization (prompt tuning, model swap) suggested.",
        )

    # ── Batch operations ──

    async def get_top_performers(
        self,
        limit: int = 5,
        lookback_hours: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return top-N agents by composite score.
        """
        hours = lookback_hours or self._config.lookback_hours
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        # Subquery: average composite per agent
        subquery = (
            select(
                WeakestLinkReport.agent_name,
                func.avg(WeakestLinkReport.composite_score).label("avg_score"),
            )
            .where(WeakestLinkReport.created_at >= cutoff)
            .group_by(WeakestLinkReport.agent_name)
            .order_by(desc("avg_score"))
            .limit(limit)
        )

        result = await self._db.execute(subquery)
        rows = result.all()

        return [{"agent_name": r.agent_name, "avg_composite_score": r.avg_score} for r in rows]

    async def acknowledge_report(self, report_id: uuid.UUID) -> bool:
        """Mark a weakest-link report as acknowledged."""
        query = select(WeakestLinkReport).where(WeakestLinkReport.id == report_id)
        result = await self._db.execute(query)
        report = result.scalar_one_or_none()

        if not report:
            return False

        report.is_acknowledged = True
        await self._db.commit()
        logger.info(f"Report {report_id} acknowledged for {report.agent_name}")
        return True
