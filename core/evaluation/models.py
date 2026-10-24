"""ProviderScore data models for Capability Evaluation Engine (#4047).

বাংলা: ProviderScore হলো একটি provider-এর জন্য ৭-dimension evaluation result।
weights হলো task-type অনুযায়ী dimension weights (admin-configurable)।
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ScoreDimension(StrEnum):
    """৭টি evaluation dimension (Roadmap v2 §5.1)।"""

    CORRECTNESS = "correctness"
    LATENCY = "latency"
    COST = "cost"
    RELIABILITY = "reliability"
    SECURITY = "security"
    TOOL_USE = "tool_use"
    REGRESSION = "regression"


@dataclass(frozen=True)
class DimensionScore:
    """Single dimension score (0.0-1.0 normalized, higher = better)."""

    dimension: ScoreDimension
    score: float  # 0.0-1.0 normalized (higher = better)
    raw_value: float  # original measurement (ms, $, %, etc.)
    unit: str  # "ms", "$", "%", "ratio", "delta"
    evidence: dict[str, Any] = field(default_factory=dict)  # benchmark_run_id, samples, etc.

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be 0.0-1.0, got {self.score} for {self.dimension}")


@dataclass(frozen=True)
class ProviderScore:
    """Complete evaluation score for a provider × task-type pair."""

    provider: str
    task_type: str  # "ci_fix", "code_review", "research", "browser_automation", etc.
    dimensions: tuple[DimensionScore, ...]
    weighted_aggregate: float  # 0.0-1.0 (weighted by task-type weights)
    weights: dict[str, float]  # dimension → weight (for audit trail)
    benchmark_run_id: str
    evaluated_at: str  # ISO timestamp

    def __post_init__(self) -> None:
        if not 0.0 <= self.weighted_aggregate <= 1.0:
            raise ValueError(f"weighted_aggregate must be 0.0-1.0, got {self.weighted_aggregate}")
        if len(self.dimensions) != 7:
            raise ValueError(f"expected 7 dimensions, got {len(self.dimensions)}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "task_type": self.task_type,
            "weighted_aggregate": round(self.weighted_aggregate, 4),
            "weights": self.weights,
            "benchmark_run_id": self.benchmark_run_id,
            "evaluated_at": self.evaluated_at,
            "dimensions": [
                {
                    "dimension": d.dimension.value,
                    "score": round(d.score, 4),
                    "raw_value": d.raw_value,
                    "unit": d.unit,
                    "evidence": d.evidence,
                }
                for d in self.dimensions
            ],
        }


# Default weights per task-type (admin-configurable via future Policy Engine).
# বাংলা: প্রতিটি task-type-এর জন্য dimension weights। উদাহরণ:
#   ci_fix → correctness সবচেয়ে গুরুত্বপূর্ণ (weight 0.3)
#   research → latency কম গুরুত্বপূর্ণ (weight 0.1)
DEFAULT_TASK_WEIGHTS: dict[str, dict[str, float]] = {
    "ci_fix": {
        "correctness": 0.30,
        "latency": 0.15,
        "cost": 0.10,
        "reliability": 0.20,
        "security": 0.10,
        "tool_use": 0.05,
        "regression": 0.10,
    },
    "code_review": {
        "correctness": 0.35,
        "latency": 0.10,
        "cost": 0.10,
        "reliability": 0.15,
        "security": 0.15,
        "tool_use": 0.05,
        "regression": 0.10,
    },
    "research": {
        "correctness": 0.30,
        "latency": 0.10,
        "cost": 0.15,
        "reliability": 0.15,
        "security": 0.10,
        "tool_use": 0.10,
        "regression": 0.10,
    },
    "browser_automation": {
        "correctness": 0.25,
        "latency": 0.20,
        "cost": 0.10,
        "reliability": 0.20,
        "security": 0.10,
        "tool_use": 0.10,
        "regression": 0.05,
    },
    "default": {
        "correctness": 0.25,
        "latency": 0.15,
        "cost": 0.15,
        "reliability": 0.20,
        "security": 0.10,
        "tool_use": 0.10,
        "regression": 0.05,
    },
}


def get_weights(task_type: str) -> dict[str, float]:
    """Get dimension weights for a task-type (falls back to 'default')."""
    return DEFAULT_TASK_WEIGHTS.get(task_type, DEFAULT_TASK_WEIGHTS["default"]).copy()


def compute_weighted_aggregate(
    dimensions: tuple[DimensionScore, ...],
    weights: dict[str, float],
) -> float:
    """Compute weighted aggregate score (0.0-1.0)."""
    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0
    weighted_sum = 0.0
    for d in dimensions:
        w = weights.get(d.dimension.value, 0.0)
        weighted_sum += d.score * w
    return min(1.0, max(0.0, weighted_sum / total_weight))
