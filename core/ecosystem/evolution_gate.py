"""Evidence gate for governed self-evolution and remediation promotion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class PromotionDecision(StrEnum):
    REJECT = "reject"
    STAGE = "stage"
    PROMOTE = "promote"


@dataclass(frozen=True)
class EvidenceReport:
    tests_passed: bool
    security_passed: bool
    benchmark_passed: bool
    rollback_ready: bool
    canary_passed: bool = False


@dataclass(frozen=True)
class PromotionResult:
    decision: PromotionDecision
    reasons: tuple[str, ...]


def evaluate_promotion(
    evidence: EvidenceReport,
    *,
    impact_score: float,
    requires_approval: bool = False,
) -> PromotionResult:
    """Apply deterministic gates; no evidence means no promotion."""
    reasons: list[str] = []
    if not evidence.tests_passed:
        reasons.append("tests_failed")
    if not evidence.security_passed:
        reasons.append("security_failed")
    if not evidence.rollback_ready:
        reasons.append("rollback_not_ready")
    if reasons:
        return PromotionResult(PromotionDecision.REJECT, tuple(reasons))
    if impact_score < 0 or impact_score > 1:
        return PromotionResult(PromotionDecision.REJECT, ("invalid_impact_score",))
    if requires_approval or impact_score >= 0.4:
        if not evidence.canary_passed:
            return PromotionResult(PromotionDecision.STAGE, ("approval_or_canary_required",))
    if not evidence.benchmark_passed:
        return PromotionResult(PromotionDecision.STAGE, ("benchmark_missing",))
    if not evidence.canary_passed:
        return PromotionResult(PromotionDecision.STAGE, ("canary_missing",))
    return PromotionResult(PromotionDecision.PROMOTE, ())


__all__ = ["EvidenceReport", "PromotionDecision", "PromotionResult", "evaluate_promotion"]
