"""Correctness scorer — does output solve the task? (#4047).

বাংলা: correctness = LLM-judge + test-suite pass rate। 0.0-1.0 normalized।
"""

from __future__ import annotations

from typing import Any

from ..models import DimensionScore, ScoreDimension


def score_correctness(
    test_pass_rate: float,
    llm_judge_score: float | None = None,
    benchmark_run_id: str = "",
) -> DimensionScore:
    """Score correctness from test-suite pass rate + optional LLM-judge.

    Args:
        test_pass_rate: 0.0-1.0 (fraction of tests passed)
        llm_judge_score: 0.0-1.0 (optional LLM-judge semantic correctness)
        benchmark_run_id: for evidence trail

    Returns:
        DimensionScore with normalized score (higher = better)
    """
    if not 0.0 <= test_pass_rate <= 1.0:
        raise ValueError(f"test_pass_rate must be 0.0-1.0, got {test_pass_rate}")

    # Weighted: test-suite 0.7, LLM-judge 0.3 (if provided)
    if llm_judge_score is not None:
        if not 0.0 <= llm_judge_score <= 1.0:
            raise ValueError(f"llm_judge_score must be 0.0-1.0, got {llm_judge_score}")
        score = 0.7 * test_pass_rate + 0.3 * llm_judge_score
    else:
        score = test_pass_rate

    return DimensionScore(
        dimension=ScoreDimension.CORRECTNESS,
        score=score,
        raw_value=test_pass_rate,
        unit="ratio",
        evidence={
            "test_pass_rate": test_pass_rate,
            "llm_judge_score": llm_judge_score,
            "benchmark_run_id": benchmark_run_id,
        },
    )
