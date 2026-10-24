"""Capability Evaluator — main orchestrator (#4047).

বাংলা: এটি main entry point। একটি provider × task-type pair-এর জন্য সব ৭টি
dimension score তৈরি করে + weighted aggregate compute করে → ProviderScore।

Usage:
    from evaluation.capability_evaluator import evaluate_provider

    score = evaluate_provider(
        provider="groq",
        task_type="ci_fix",
        measurements={
            "test_pass_rate": 0.95,
            "llm_judge_score": 0.88,
            "p50_ms": 200,
            "p95_ms": 450,
            "cost_per_call_usd": 0.0005,
            "uptime_pct": 99.9,
            "error_rate_pct": 0.5,
            "health_status": "healthy",
            "data_exposure_risk": 0.1,
            "pii_redaction_enabled": True,
            "sandbox_isolation": True,
            "egress_restricted": False,
            "tool_calls_total": 10,
            "tool_calls_succeeded": 9,
            "previous_weighted_score": 0.82,
        },
        benchmark_run_id="run-2026-10-06-001",
    )
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

from .models import (
    DimensionScore,
    ProviderScore,
    compute_weighted_aggregate,
    get_weights,
)
from .scorers import (
    score_correctness,
    score_cost,
    score_latency,
    score_regression,
    score_reliability,
    score_security,
    score_tool_use,
)


def evaluate_provider(
    provider: str,
    task_type: str,
    measurements: dict[str, Any],
    benchmark_run_id: str | None = None,
    previous_run_id: str = "",
) -> ProviderScore:
    """Evaluate a provider for a task-type across all 7 dimensions.

    Args:
        provider: provider name (e.g., "groq", "openai", "cerebras")
        task_type: task type (e.g., "ci_fix", "code_review", "research")
        measurements: dict of measurement values for each scorer
        benchmark_run_id: unique run ID (auto-generated if None)
        previous_run_id: previous benchmark run ID (for regression)

    Returns:
        ProviderScore with 7 dimensions + weighted aggregate
    """
    run_id = (
        benchmark_run_id
        or f"run-{_dt.datetime.utcnow().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    )
    evaluated_at = _dt.datetime.utcnow().isoformat() + "Z"

    # Build each dimension score
    dimensions: list[DimensionScore] = []

    # 1. Correctness
    dimensions.append(
        score_correctness(
            test_pass_rate=measurements.get("test_pass_rate", 0.0),
            llm_judge_score=measurements.get("llm_judge_score"),
            benchmark_run_id=run_id,
        )
    )

    # 2. Latency
    dimensions.append(
        score_latency(
            p50_ms=measurements.get("p50_ms", 0.0),
            p95_ms=measurements.get("p95_ms", 0.0),
            p99_ms=measurements.get("p99_ms"),
            benchmark_run_id=run_id,
        )
    )

    # 3. Cost
    dimensions.append(
        score_cost(
            cost_per_call_usd=measurements.get("cost_per_call_usd", 0.0),
            cost_per_task_usd=measurements.get("cost_per_task_usd"),
            benchmark_run_id=run_id,
        )
    )

    # 4. Reliability
    dimensions.append(
        score_reliability(
            uptime_pct=measurements.get("uptime_pct", 0.0),
            error_rate_pct=measurements.get("error_rate_pct", 0.0),
            health_status=measurements.get("health_status", "unknown"),
            benchmark_run_id=run_id,
        )
    )

    # 5. Security
    dimensions.append(
        score_security(
            data_exposure_risk=measurements.get("data_exposure_risk", 0.5),
            pii_redaction_enabled=measurements.get("pii_redaction_enabled", True),
            sandbox_isolation=measurements.get("sandbox_isolation", True),
            egress_restricted=measurements.get("egress_restricted", False),
            benchmark_run_id=run_id,
        )
    )

    # 6. Tool-use
    dimensions.append(
        score_tool_use(
            tool_calls_total=measurements.get("tool_calls_total", 0),
            tool_calls_succeeded=measurements.get("tool_calls_succeeded", 0),
            benchmark_run_id=run_id,
        )
    )

    # Compute weighted aggregate (before regression, since regression needs it)
    weights = get_weights(task_type)
    current_aggregate = compute_weighted_aggregate(tuple(dimensions), weights)

    # 7. Regression (uses current aggregate vs previous)
    previous_score = measurements.get("previous_weighted_score", current_aggregate)
    dimensions.append(
        score_regression(
            current_score=current_aggregate,
            previous_score=previous_score,
            benchmark_run_id=run_id,
            previous_run_id=previous_run_id,
        )
    )

    # Recompute aggregate with regression dimension included
    final_aggregate = compute_weighted_aggregate(tuple(dimensions), weights)

    return ProviderScore(
        provider=provider,
        task_type=task_type,
        dimensions=tuple(dimensions),
        weighted_aggregate=final_aggregate,
        weights=weights,
        benchmark_run_id=run_id,
        evaluated_at=evaluated_at,
    )
