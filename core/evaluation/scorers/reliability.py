"""Reliability scorer — uptime %, error rate from service_topology (#4047).

বাংলা: reliability score = uptime % + error rate (from service_topology health check)।
"""

from __future__ import annotations

from ..models import DimensionScore, ScoreDimension


def score_reliability(
    uptime_pct: float,
    error_rate_pct: float = 0.0,
    health_status: str = "healthy",
    benchmark_run_id: str = "",
) -> DimensionScore:
    """Score reliability from uptime + error rate + health status.

    Args:
        uptime_pct: 0.0-100.0 (percentage of time provider was reachable)
        error_rate_pct: 0.0-100.0 (percentage of calls that errored)
        health_status: "healthy" / "degraded" / "unhealthy" / "skipped" (from service_topology)
        benchmark_run_id: for evidence trail

    Returns:
        DimensionScore with normalized score (higher uptime = higher score)
    """
    if not 0.0 <= uptime_pct <= 100.0:
        raise ValueError(f"uptime_pct must be 0.0-100.0, got {uptime_pct}")
    if not 0.0 <= error_rate_pct <= 100.0:
        raise ValueError(f"error_rate_pct must be 0.0-100.0, got {error_rate_pct}")

    # Base score from uptime (99.9% → 1.0, 90% → 0.5, 0% → 0.0)
    uptime_score = min(1.0, uptime_pct / 99.9)

    # Penalty for error rate (10% errors → -0.2, 50% errors → -1.0)
    error_penalty = min(1.0, error_rate_pct / 50.0) * 0.2

    # Health status adjustment
    status_mult = {
        "healthy": 1.0,
        "degraded": 0.7,
        "unhealthy": 0.0,
        "skipped": 0.5,  # not configured ≠ broken
        "unknown": 0.5,
        "maintenance": 0.3,
    }.get(health_status.lower(), 0.5)

    score = max(0.0, (uptime_score - error_penalty) * status_mult)

    return DimensionScore(
        dimension=ScoreDimension.RELIABILITY,
        score=score,
        raw_value=uptime_pct,
        unit="%",
        evidence={
            "uptime_pct": uptime_pct,
            "error_rate_pct": error_rate_pct,
            "health_status": health_status,
            "benchmark_run_id": benchmark_run_id,
        },
    )
