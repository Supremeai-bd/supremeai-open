"""Latency scorer — p50/p95/p99 response time (#4047).

বাংলা: latency score = inverse of response time (lower latency = higher score)।
"""

from __future__ import annotations

from typing import Any

from ..models import DimensionScore, ScoreDimension

# Latency thresholds (ms) for score normalization.
# বাংলা: latency thresholds — p95 < 500ms = 1.0, p95 > 5000ms = 0.0
LATENCY_P95_BEST_MS = 500.0  # 0.5s → score 1.0
LATENCY_P95_WORST_MS = 5000.0  # 5s → score 0.0


def score_latency(
    p50_ms: float,
    p95_ms: float,
    p99_ms: float | None = None,
    benchmark_run_id: str = "",
) -> DimensionScore:
    """Score latency from response time percentiles.

    Uses p95 as the primary signal (p50 too optimistic, p99 too pessimistic).

    Args:
        p50_ms: median response time
        p95_ms: 95th percentile response time
        p99_ms: 99th percentile (optional, for evidence)
        benchmark_run_id: for evidence trail

    Returns:
        DimensionScore with normalized score (lower latency = higher score)
    """
    if p95_ms < 0:
        raise ValueError(f"p95_ms must be >= 0, got {p95_ms}")

    # Linear normalization: 500ms → 1.0, 5000ms → 0.0
    if p95_ms <= LATENCY_P95_BEST_MS:
        score = 1.0
    elif p95_ms >= LATENCY_P95_WORST_MS:
        score = 0.0
    else:
        score = 1.0 - (p95_ms - LATENCY_P95_BEST_MS) / (LATENCY_P95_WORST_MS - LATENCY_P95_BEST_MS)

    return DimensionScore(
        dimension=ScoreDimension.LATENCY,
        score=score,
        raw_value=p95_ms,
        unit="ms",
        evidence={
            "p50_ms": p50_ms,
            "p95_ms": p95_ms,
            "p99_ms": p99_ms,
            "threshold_best_ms": LATENCY_P95_BEST_MS,
            "threshold_worst_ms": LATENCY_P95_WORST_MS,
            "benchmark_run_id": benchmark_run_id,
        },
    )
