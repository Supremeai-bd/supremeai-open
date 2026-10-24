"""Regression scorer — quality delta vs last benchmark run (#4047).

বাংলা: regression score = quality delta vs previous benchmark। degradation > threshold
triggers alert। higher score = less regression / more improvement।
"""

from __future__ import annotations

from ..models import DimensionScore, ScoreDimension

# Regression threshold: > 10% degradation = alert
REGRESSION_ALERT_THRESHOLD = 0.10


def score_regression(
    current_score: float,
    previous_score: float,
    benchmark_run_id: str = "",
    previous_run_id: str = "",
) -> DimensionScore:
    """Score regression from delta vs previous benchmark.

    Args:
        current_score: current weighted_aggregate (0.0-1.0)
        previous_score: previous weighted_aggregate (0.0-1.0)
        benchmark_run_id: current run ID
        previous_run_id: previous run ID (for evidence)

    Returns:
        DimensionScore:
        - Improvement (delta > 0) → score 1.0
        - No change → score 0.8
        - Small degradation (< threshold) → score 0.5
        - Large degradation (> threshold) → score 0.0 + alert flag
    """
    if not 0.0 <= current_score <= 1.0:
        raise ValueError(f"current_score must be 0.0-1.0, got {current_score}")
    if not 0.0 <= previous_score <= 1.0:
        raise ValueError(f"previous_score must be 0.0-1.0, got {previous_score}")

    delta = current_score - previous_score  # positive = improvement, negative = regression

    if delta > 0.05:
        score = 1.0  # significant improvement
    elif delta > 0:
        score = 0.9  # small improvement
    elif delta == 0:
        score = 0.8  # no change
    elif delta > -REGRESSION_ALERT_THRESHOLD:
        score = 0.5  # small degradation (< 10%)
    else:
        score = 0.0  # large degradation (> threshold) → alert

    return DimensionScore(
        dimension=ScoreDimension.REGRESSION,
        score=score,
        raw_value=delta,
        unit="delta",
        evidence={
            "current_score": current_score,
            "previous_score": previous_score,
            "delta": delta,
            "regression_threshold": REGRESSION_ALERT_THRESHOLD,
            "alert": delta < -REGRESSION_ALERT_THRESHOLD,
            "benchmark_run_id": benchmark_run_id,
            "previous_run_id": previous_run_id,
        },
    )
