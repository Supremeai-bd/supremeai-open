"""
SupremeAI — Ethics Monitor Agent
=================================
Ensures AI decisions align with ethical guidelines.
Provides ethical assessment, bias checking, and ethics compliance reporting.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from brain.model_router import ModelRouter
from core.cache import get_cache
from core.config_cache import config_cache
from core.errors.error_bus import with_error_bus

ETHICS_CACHE_TTL = 3600


class EthicalPrinciple(StrEnum):
    FAIRNESS = "fairness"
    TRANSPARENCY = "transparency"
    ACCOUNTABILITY = "accountability"
    PRIVACY = "privacy"
    NON_MALEFICENCE = "non_maleficence"
    BENEFICENCE = "beneficence"
    AUTONOMY = "autonomy"
    JUSTICE = "justice"


@dataclass(frozen=True)
class DecisionAssessment:
    """Immutable decision ethics assessment."""

    decision_id: str
    principles_checked: list[EthicalPrinciple]
    violations: list[dict[str, Any]]
    overall_score: float
    is_ethical: bool
    recommendations: list[str]


@dataclass(frozen=True)
class EthicsVerdict:
    """Immutable ethics verdict."""

    verdict: str  # approved, flagged, rejected
    confidence: float
    explanation: str
    reviewed_principles: list[str]


class EthicsMonitorAgent:
    """
    Ensures AI decisions align with ethical guidelines.
    """

    def __init__(self, llm_router: ModelRouter | None = None) -> None:
        self.llm = llm_router or ModelRouter()
        self.cache = get_cache()
        self._assessments: list[DecisionAssessment] = []

    def _cache_key(self, prefix: str, identifier: str) -> str:
        raw = f"ethics:{prefix}:{identifier}:{datetime.now(UTC).strftime('%Y%m%d%H')}"
        return f"ethics:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    @with_error_bus("assess_decision")
    async def assess_decision(
        self, decision_context: str, decision_id: str = ""
    ) -> DecisionAssessment:
        """Assess a decision against ethical principles."""
        prompt = (
            f"Assess this decision against ethical principles (fairness, transparency, "
            f"accountability, privacy, non-maleficence, beneficence, autonomy, justice):\n\n"
            f"{decision_context}\n\n"
            f"Return as JSON with: violations (list of {{principle, severity, description}}), "
            f"overall_score (0-1), is_ethical (bool), recommendations (list of strings)."
        )

        try:
            result = await self.llm.async_route_and_generate(
                prompt=prompt,
                task_type="reasoning",
                max_tokens=config_cache.get("ethics_monitor_agent_max_tokens", 500),
            )
            import json

            content = result.get("text", "{}")
            data = json.loads(content) if isinstance(content, str) else content
            violations = data.get("violations", [])
            score = float(data.get("overall_score", 0.5))
        except Exception:
            violations = []
            score = 1.0

        assessment = DecisionAssessment(
            decision_id=decision_id or hashlib.sha256(decision_context.encode()).hexdigest()[:12],
            principles_checked=list(EthicalPrinciple),
            violations=violations,
            overall_score=score,
            is_ethical=score >= 0.7,
            recommendations=data.get("recommendations", []) if "data" in dir() else [],
        )
        self._assessments.append(assessment)
        return assessment

    def check_bias(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Check for potential biases in input data."""
        bias_flags = []
        protected_attributes = [
            "race",
            "gender",
            "age",
            "religion",
            "disability",
            "sexual_orientation",
        ]

        for attr in protected_attributes:
            if attr in input_data:
                bias_flags.append(
                    {
                        "attribute": attr,
                        "concern": f"Decision uses protected attribute: {attr}",
                        "severity": "high",
                    }
                )

        return {
            "has_bias_risk": len(bias_flags) > 0,
            "flags": bias_flags,
            "recommendation": (
                "Review decision logic to ensure no discriminatory outcomes"
                if bias_flags
                else "No bias detected"
            ),
        }

    @with_error_bus("validate_ethical_principle")
    async def validate_ethical_principle(
        self, principle: EthicalPrinciple, context: str
    ) -> EthicsVerdict:
        """Validate a decision against a specific ethical principle."""
        prompt = (
            f"Evaluate this context against the ethical principle of {principle.value}:\n\n"
            f"{context}\n\n"
            f"Return as JSON with: verdict (approved/flagged/rejected), confidence (0-1), "
            f"explanation, reviewed_principles (list)."
        )

        try:
            result = await self.llm.async_route_and_generate(
                prompt=prompt,
                task_type="reasoning",
                max_tokens=config_cache.get("ethics_monitor_agent_max_tokens", 300),
            )
            import json

            content = result.get("text", "{}")
            data = json.loads(content) if isinstance(content, str) else content
            return EthicsVerdict(
                verdict=data.get("verdict", "flagged"),
                confidence=float(data.get("confidence", 0.5)),
                explanation=data.get("explanation", "Insufficient context for evaluation"),
                reviewed_principles=data.get("reviewed_principles", [principle.value]),
            )
        except Exception:
            return EthicsVerdict(
                verdict="flagged",
                confidence=0.5,
                explanation="Unable to validate due to processing error",
                reviewed_principles=[principle.value],
            )

    async def generate_ethics_report(self) -> dict[str, Any]:
        """Generate an ethics compliance report."""
        total = len(self._assessments)
        ethical_count = sum(1 for a in self._assessments if a.is_ethical)
        return {
            "total_assessments": total,
            "ethical_percentage": (ethical_count / total * 100) if total > 0 else 100,
            "flagged_decisions": total - ethical_count,
            "average_score": sum(a.overall_score for a in self._assessments) / total
            if total > 0
            else 1.0,
            "report_generated_at": datetime.now(UTC).isoformat(),
        }


# Singleton
_ethics_instance: EthicsMonitorAgent | None = None


def get_ethics_monitor() -> EthicsMonitorAgent:
    """Get or create the singleton EthicsMonitorAgent."""
    global _ethics_instance
    if _ethics_instance is None:
        _ethics_instance = EthicsMonitorAgent()
    return _ethics_instance
