# backend/learning/outcome_analyzer.py
"""Outcome Analyzer for Continual Learning and Hypothesis Generation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from learning.experience import ExperienceRecord


class OutcomeClassification(StrEnum):
    SUCCESS = "success"
    SYNTAX_ERROR = "syntax_error"
    CRITERION_FAILURE = "criterion_failure"
    BUDGET_EXHAUSTED = "budget_exhausted"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    GENERAL_FAILURE = "general_failure"


@dataclass
class LearningInsight:
    """Actionable insight extracted from task execution patterns."""

    insight_type: str  # "routing" | "prompt" | "tool_policy" | "budget"
    observation: str
    confidence: float
    evidence_task_ids: list[str] = field(default_factory=list)
    recommended_action: str = ""
    insight_id: str = field(default_factory=lambda: f"ins_{uuid.uuid4().hex[:8]}")
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "insight_type": self.insight_type,
            "observation": self.observation,
            "confidence": self.confidence,
            "evidence_task_ids": self.evidence_task_ids,
            "recommended_action": self.recommended_action,
            "created_at": self.created_at.isoformat(),
        }


class OutcomeAnalyzer:
    """Analyzes execution logs, extracts failure reasons, and synthesizes lessons."""

    def __init__(self) -> None:
        self.insights: list[LearningInsight] = []

    def classify_outcome(self, record: ExperienceRecord) -> OutcomeClassification:
        if record.verified and record.verification_score >= 0.8:
            return OutcomeClassification.SUCCESS

        for failure in record.failures:
            f_lower = failure.lower()
            if "syntax" in f_lower or "ast" in f_lower:
                return OutcomeClassification.SYNTAX_ERROR
            if "budget" in f_lower:
                return OutcomeClassification.BUDGET_EXHAUSTED
            if "rate limit" in f_lower:
                return OutcomeClassification.RATE_LIMITED
            if "timeout" in f_lower:
                return OutcomeClassification.TIMEOUT

        return (
            OutcomeClassification.CRITERION_FAILURE
            if record.failures
            else OutcomeClassification.GENERAL_FAILURE
        )

    def analyze_and_extract_lessons(self, record: ExperienceRecord) -> list[str]:
        classification = self.classify_outcome(record)
        lessons: list[str] = []

        if classification == OutcomeClassification.SUCCESS:
            lessons.append(
                f"Optimal provider execution achieved via {record.providers_used or ['default']}."
            )
        elif classification == OutcomeClassification.SYNTAX_ERROR:
            lessons.append(
                "AST verification failed: Ensure strict code formatting and markdown strip."
            )
        elif classification == OutcomeClassification.BUDGET_EXHAUSTED:
            lessons.append(
                "Compute budget exceeded: Allocate higher token allowance or prune context."
            )
        elif classification == OutcomeClassification.CRITERION_FAILURE:
            lessons.append("Target criterion not satisfied: Re-prompt with explicit output schema.")

        record.lessons_extracted = lessons
        return lessons


# Global Singleton
_outcome_analyzer: OutcomeAnalyzer | None = None


def get_outcome_analyzer() -> OutcomeAnalyzer:
    global _outcome_analyzer
    if _outcome_analyzer is None:
        _outcome_analyzer = OutcomeAnalyzer()
    return _outcome_analyzer
