# backend/evolution/benchmark_runner.py
"""Baseline vs. Candidate Comparative Benchmark Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evolution.change_proposal import ChangeProposal
from evolution.fitness_evaluator import FitnessBreakdown, get_fitness_evaluator


@dataclass
class PromotionDecision:
    """Formal, evidence-backed decision report for proposal promotion."""

    eligible: bool
    baseline_fitness: float
    candidate_fitness: float
    fitness_delta: float
    confidence: float
    safety_status: str
    regression_status: str
    reason: str
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "baseline_fitness": self.baseline_fitness,
            "candidate_fitness": self.candidate_fitness,
            "fitness_delta": self.fitness_delta,
            "confidence": self.confidence,
            "safety_status": self.safety_status,
            "regression_status": self.regression_status,
            "reason": self.reason,
            "evidence_ids": self.evidence_ids,
        }


class BenchmarkRunner:
    """Runs rigorous empirical benchmarks comparing candidates against current baselines."""

    def __init__(self) -> None:
        self.evaluator = get_fitness_evaluator()

    def compare_and_decide(
        self,
        proposal: ChangeProposal,
        candidate_eval: FitnessBreakdown,
        baseline_fitness: float = 0.75,
        min_gain_threshold: float = 0.0,
    ) -> PromotionDecision:
        # 🛡️ Governance Kernel Check (Defense-in-depth)
        from core.security.governance_policy import get_governance_policy

        is_allowed, reason = get_governance_policy().validate_evolution_target(
            proposal.target_module
        )
        if not is_allowed:
            return PromotionDecision(
                eligible=False,
                baseline_fitness=baseline_fitness,
                candidate_fitness=candidate_eval.composite_fitness,
                fitness_delta=0.0,
                confidence=1.0,
                safety_status="GOVERNANCE_BLOCKED",
                regression_status="POLICY_VIOLATION",
                reason=f"Governance policy blocked target: {reason}",
                evidence_ids=[proposal.proposal_id],
            )

        candidate_fitness = candidate_eval.composite_fitness
        delta = round(candidate_fitness - baseline_fitness, 4)

        safety_status = "PASS" if candidate_eval.security_score >= 1.0 else "FAIL"
        regression_status = "NONE" if candidate_eval.regression_penalty == 0.0 else "DETECTED"

        if safety_status == "FAIL":
            return PromotionDecision(
                eligible=False,
                baseline_fitness=baseline_fitness,
                candidate_fitness=candidate_fitness,
                fitness_delta=delta,
                confidence=0.99,
                safety_status=safety_status,
                regression_status=regression_status,
                reason="Security AST Layout Violation detected during benchmark.",
            )

        if candidate_fitness < baseline_fitness + min_gain_threshold:
            return PromotionDecision(
                eligible=False,
                baseline_fitness=baseline_fitness,
                candidate_fitness=candidate_fitness,
                fitness_delta=delta,
                confidence=0.90,
                safety_status=safety_status,
                regression_status="REGRESSION" if delta < 0 else "NO_IMPROVEMENT",
                reason=f"Candidate fitness ({candidate_fitness}) failed to outperform baseline ({baseline_fitness}).",
            )

        return PromotionDecision(
            eligible=True,
            baseline_fitness=baseline_fitness,
            candidate_fitness=candidate_fitness,
            fitness_delta=delta,
            confidence=0.95,
            safety_status=safety_status,
            regression_status=regression_status,
            reason=f"Empirical fitness gain (+{delta:.4f}) meets promotion criteria.",
            evidence_ids=[proposal.proposal_id],
        )


# Global Singleton
_runner: BenchmarkRunner | None = None


def get_benchmark_runner() -> BenchmarkRunner:
    global _runner
    if _runner is None:
        _runner = BenchmarkRunner()
    return _runner
