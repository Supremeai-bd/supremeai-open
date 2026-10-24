# backend/learning/pattern_detector.py
"""Structured Pattern Detector with Canonical Taxonomy for Continuous Learning."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from learning.experience import ExperienceStore, get_experience_store


@dataclass
class EvidenceReference:
    """Detailed causal evidence reference."""

    task_id: str
    experience_id: str
    failure_reason: str | None = None
    latency_ms: float = 0.0
    cost_usd: float = 0.0


@dataclass
class DetectedPattern:
    """Recurring pattern identified from past execution experiences with evidence metrics."""

    pattern_type: str  # "SYNTAX", "TIMEOUT", "BUDGET", "ROUTING", "TOOL", "SUCCESS"
    category: str  # "FAILURE", "SUCCESS", "OPPORTUNITY"
    support_count: int
    population_size: int
    occurrence_rate: float
    confidence: float
    description: str
    evidence: list[EvidenceReference] = field(default_factory=list)
    suggested_action: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def evidence_task_ids(self) -> list[str]:
        return [e.task_id for e in self.evidence]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_type": self.pattern_type,
            "category": self.category,
            "support_count": self.support_count,
            "population_size": self.population_size,
            "occurrence_rate": self.occurrence_rate,
            "confidence": self.confidence,
            "description": self.description,
            "evidence_task_ids": self.evidence_task_ids,
            "suggested_action": self.suggested_action,
            "timestamp": self.timestamp,
        }


class PatternDetector:
    """Scans experience ledger to identify systematic failures and optimization opportunities."""

    def __init__(self, store: ExperienceStore | None = None) -> None:
        self.store = store or get_experience_store()

    def analyze_patterns(self, min_support: int = 2) -> list[DetectedPattern]:
        records = self.store.get_recent(limit=100)
        if not records:
            return []

        population = len(records)
        patterns: list[DetectedPattern] = []

        syntax_evidence: list[EvidenceReference] = []
        budget_evidence: list[EvidenceReference] = []
        timeout_evidence: list[EvidenceReference] = []
        success_evidence: list[EvidenceReference] = []

        for rec in records:
            if rec.verified:
                success_evidence.append(
                    EvidenceReference(
                        task_id=rec.task_id,
                        experience_id=rec.experience_id,
                        latency_ms=rec.latency_ms,
                        cost_usd=rec.cost_usd,
                    )
                )

            for failure in rec.failures:
                failure_lower = failure.lower()
                ref = EvidenceReference(
                    task_id=rec.task_id,
                    experience_id=rec.experience_id,
                    failure_reason=failure,
                    latency_ms=rec.latency_ms,
                    cost_usd=rec.cost_usd,
                )
                if any(k in failure_lower for k in ["syntax", "ast", "parse", "invalid syntax"]):
                    syntax_evidence.append(ref)
                elif any(k in failure_lower for k in ["budget", "cost", "token", "limit exceeded"]):
                    budget_evidence.append(ref)
                elif any(k in failure_lower for k in ["timeout", "timed out", "latency"]):
                    timeout_evidence.append(ref)

        # 1. Syntax Error Pattern
        if len(syntax_evidence) >= min_support:
            rate = round(len(syntax_evidence) / population, 4)
            patterns.append(
                DetectedPattern(
                    pattern_type="SYNTAX",
                    category="FAILURE",
                    support_count=len(syntax_evidence),
                    population_size=population,
                    occurrence_rate=rate,
                    confidence=round(min(0.98, 0.70 + (rate * 0.5)), 2),
                    description=f"Syntax parsing errors detected in {len(syntax_evidence)} tasks ({rate * 100:.1f}%).",
                    evidence=syntax_evidence,
                    suggested_action="Optimize code generation prompt to enforce strict AST compliance and markdown stripping.",
                )
            )

        # 2. Budget Exhaustion Pattern
        if len(budget_evidence) >= min_support:
            rate = round(len(budget_evidence) / population, 4)
            patterns.append(
                DetectedPattern(
                    pattern_type="BUDGET",
                    category="FAILURE",
                    support_count=len(budget_evidence),
                    population_size=population,
                    occurrence_rate=rate,
                    confidence=round(min(0.95, 0.75 + (rate * 0.4)), 2),
                    description=f"Budget or token exhaustion occurred in {len(budget_evidence)} tasks ({rate * 100:.1f}%).",
                    evidence=budget_evidence,
                    suggested_action="Scale initial token budget allocation or optimize step graph decomposition.",
                )
            )

        # 3. Timeout Pattern (Fixed Bug)
        if len(timeout_evidence) >= min_support:
            rate = round(len(timeout_evidence) / population, 4)
            patterns.append(
                DetectedPattern(
                    pattern_type="TIMEOUT",
                    category="FAILURE",
                    support_count=len(timeout_evidence),
                    population_size=population,
                    occurrence_rate=rate,
                    confidence=round(min(0.95, 0.70 + (rate * 0.4)), 2),
                    description=f"Execution timeouts detected in {len(timeout_evidence)} tasks ({rate * 100:.1f}%).",
                    evidence=timeout_evidence,
                    suggested_action="Decompose complex multi-step reasoning into asynchronous subtasks.",
                )
            )

        # 4. Success Routing Pattern
        if len(success_evidence) >= min_support and (len(success_evidence) / population) >= 0.80:
            rate = round(len(success_evidence) / population, 4)
            patterns.append(
                DetectedPattern(
                    pattern_type="SUCCESS",
                    category="OPPORTUNITY",
                    support_count=len(success_evidence),
                    population_size=population,
                    occurrence_rate=rate,
                    confidence=0.95,
                    description=f"High verification success rate ({rate * 100:.1f}%) observed across {len(success_evidence)} tasks.",
                    evidence=success_evidence,
                    suggested_action="Reinforce current routing and planner decomposition policy.",
                )
            )

        return patterns


# Global Singleton
_detector: PatternDetector | None = None


def get_pattern_detector() -> PatternDetector:
    global _detector
    if _detector is None:
        _detector = PatternDetector()
    return _detector
