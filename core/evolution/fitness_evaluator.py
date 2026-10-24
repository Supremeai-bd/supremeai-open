# backend/evolution/fitness_evaluator.py
"""Multi-factor Evidence-Backed Fitness Evaluator for Self-Evolution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FitnessBreakdown:
    correctness_score: float = 1.0
    validation_score: float = 1.0
    security_score: float = 1.0
    reliability_score: float = 1.0
    latency_score: float = 1.0
    cost_score: float = 1.0
    regression_penalty: float = 0.0

    @property
    def composite_fitness(self) -> float:
        """Calculate weighted multi-dimensional fitness score between 0.0 and 1.0."""
        # Weights sum to 1.0
        weights = {
            "correctness": 0.35,
            "validation": 0.25,
            "security": 0.20,
            "reliability": 0.10,
            "latency": 0.05,
            "cost": 0.05,
        }
        raw_score = (
            self.correctness_score * weights["correctness"]
            + self.validation_score * weights["validation"]
            + self.security_score * weights["security"]
            + self.reliability_score * weights["reliability"]
            + self.latency_score * weights["latency"]
            + self.cost_score * weights["cost"]
        ) - self.regression_penalty

        return max(0.0, min(1.0, round(raw_score, 4)))


class FitnessEvaluator:
    """Computes evidence-backed, multi-dimensional fitness reports."""

    def evaluate_skill_execution(
        self,
        passed_tests: int,
        total_tests: int,
        ast_security_passed: bool,
        latency_ms: float,
        cost_usd: float = 0.0,
        baseline_latency_ms: float = 1000.0,
        errors: list[str] | None = None,
    ) -> FitnessBreakdown:
        validation_ratio = (passed_tests / total_tests) if total_tests > 0 else 0.0
        correctness = (
            1.0
            if (errors is None or len(errors) == 0) and validation_ratio == 1.0
            else validation_ratio
        )
        security = 1.0 if ast_security_passed else 0.0
        reliability = 1.0 if not errors else max(0.0, 1.0 - (len(errors) * 0.25))

        # Latency score: 1.0 at baseline, scaling down gracefully if slower
        latency_score = max(0.2, min(1.0, baseline_latency_ms / max(100.0, latency_ms)))
        cost_score = max(0.5, 1.0 - (cost_usd / 0.10))  # penalize high token cost

        return FitnessBreakdown(
            correctness_score=correctness,
            validation_score=validation_ratio,
            security_score=security,
            reliability_score=reliability,
            latency_score=latency_score,
            cost_score=cost_score,
            regression_penalty=0.0,
        )


# Global Singleton
_evaluator: FitnessEvaluator | None = None


def get_fitness_evaluator() -> FitnessEvaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = FitnessEvaluator()
    return _evaluator
