"""Cost scorer — $ per call + $ per task (#4047).

বাংলা: cost score = inverse of $ per call (lower cost = higher score)।
"""

from __future__ import annotations

from ..models import DimensionScore, ScoreDimension

# Cost thresholds (USD) for score normalization.
# বাংলা: cost thresholds — $0.001/call = 1.0, $0.10/call = 0.0
COST_BEST_USD = 0.001  # $0.001 → score 1.0
COST_WORST_USD = 0.10  # $0.10 → score 0.0


def score_cost(
    cost_per_call_usd: float,
    cost_per_task_usd: float | None = None,
    benchmark_run_id: str = "",
) -> DimensionScore:
    """Score cost from $ per call.

    Args:
        cost_per_call_usd: dollar cost per API call
        cost_per_task_usd: dollar cost per complete task (optional, for evidence)
        benchmark_run_id: for evidence trail

    Returns:
        DimensionScore with normalized score (lower cost = higher score)
    """
    if cost_per_call_usd < 0:
        raise ValueError(f"cost_per_call_usd must be >= 0, got {cost_per_call_usd}")

    # Linear normalization: $0.001 → 1.0, $0.10 → 0.0
    if cost_per_call_usd <= COST_BEST_USD:
        score = 1.0
    elif cost_per_call_usd >= COST_WORST_USD:
        score = 0.0
    else:
        score = 1.0 - (cost_per_call_usd - COST_BEST_USD) / (COST_WORST_USD - COST_BEST_USD)

    return DimensionScore(
        dimension=ScoreDimension.COST,
        score=score,
        raw_value=cost_per_call_usd,
        unit="$",
        evidence={
            "cost_per_call_usd": cost_per_call_usd,
            "cost_per_task_usd": cost_per_task_usd,
            "threshold_best_usd": COST_BEST_USD,
            "threshold_worst_usd": COST_WORST_USD,
            "benchmark_run_id": benchmark_run_id,
        },
    )
