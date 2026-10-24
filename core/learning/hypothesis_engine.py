# backend/learning/hypothesis_engine.py
"""Improvement Hypothesis Engine and Governed Proposal Bridge."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.logging_config import logger
from evolution.change_proposal import (
    ChangeProposal,
    ChangeProposalManager,
    ChangeType,
    get_change_manager,
)
from learning.evidence_analyzer import (
    EvidenceAnalyzer,
    PatternEvidenceMetrics,
    get_evidence_analyzer,
)
from learning.pattern_detector import PatternDetector, get_pattern_detector


@dataclass
class ImprovementHypothesis:
    """Rigorous evidence-backed hypothesis for autonomous system enhancement."""

    category: str
    observation: str
    root_cause: str
    proposed_change: dict[str, Any]
    target_module: str
    evidence_metrics: PatternEvidenceMetrics | None = None
    expected_delta: float = 0.05
    risk_level: str = "LOW"  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    validation_plan: str = "Automated AST Security Scan + Comparative Benchmark + Canary Gate"
    confidence: float = 0.85
    hypothesis_id: str = field(default_factory=lambda: f"hyp_{uuid.uuid4().hex[:10]}")
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def evidence_ids(self) -> list[str]:
        if self.evidence_metrics and self.evidence_metrics.evidence_references:
            return [ref.task_id for ref in self.evidence_metrics.evidence_references]
        return []

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "category": self.category,
            "observation": self.observation,
            "root_cause": self.root_cause,
            "proposed_change": self.proposed_change,
            "target_module": self.target_module,
            "evidence_metrics": self.evidence_metrics.to_dict() if self.evidence_metrics else None,
            "expected_delta": self.expected_delta,
            "risk_level": self.risk_level,
            "validation_plan": self.validation_plan,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
        }


class HypothesisEngine:
    """Transforms discovered execution patterns into formal improvement hypotheses and governed ChangeProposals."""

    def __init__(
        self,
        detector: PatternDetector | None = None,
        analyzer: EvidenceAnalyzer | None = None,
        proposal_manager: ChangeProposalManager | None = None,
    ) -> None:
        self.detector = detector or get_pattern_detector()
        self.analyzer = analyzer or get_evidence_analyzer()
        self.proposal_manager = proposal_manager or get_change_manager()

    def generate_hypotheses(self) -> list[ImprovementHypothesis]:
        patterns = self.detector.analyze_patterns()
        hypotheses: list[ImprovementHypothesis] = []

        for pat in patterns:
            metrics = self.analyzer.analyze_pattern_evidence(pat)
            if not metrics.is_statistically_significant:
                continue

            if pat.pattern_type == "SYNTAX":
                hypotheses.append(
                    ImprovementHypothesis(
                        category="PROMPT_OPTIMIZATION",
                        observation=f"Syntax parsing errors in {pat.support_count}/{pat.population_size} tasks ({pat.occurrence_rate * 100:.1f}%).",
                        root_cause="Markdown code block fences and natural language chatter contaminating raw AST output.",
                        proposed_change={
                            "system_prompt_addition": "CRITICAL: Return purely valid, parseable syntax. Strip all markdown code fences.",
                            "strip_markdown_enabled": True,
                        },
                        target_module="backend/brain/code_generation_prompt.py",
                        evidence_metrics=metrics,
                        expected_delta=0.15,
                        risk_level="LOW",
                        confidence=pat.confidence,
                    )
                )
            elif pat.pattern_type == "BUDGET":
                hypotheses.append(
                    ImprovementHypothesis(
                        category="PARAMETER_TUNING",
                        observation=f"Budget constraints exceeded in {pat.support_count}/{pat.population_size} tasks.",
                        root_cause="Multi-step reasoning plans underestimating initial token envelope requirements.",
                        proposed_change={"default_token_multiplier": 1.25},
                        target_module="adapters/budget_parameters.py",
                        evidence_metrics=metrics,
                        expected_delta=0.10,
                        risk_level="LOW",
                        confidence=pat.confidence,
                    )
                )
            elif pat.pattern_type == "TIMEOUT":
                hypotheses.append(
                    ImprovementHypothesis(
                        category="ARCHITECTURE_REFACTOR",
                        observation=f"Execution timeouts detected in {pat.support_count}/{pat.population_size} tasks.",
                        root_cause="Synchronous tool call chains blocking the main event loop under high latency.",
                        proposed_change={"enable_async_step_parallelism": True},
                        target_module="adapters/step_parallelism.py",
                        evidence_metrics=metrics,
                        expected_delta=0.20,
                        risk_level="MEDIUM",
                        confidence=pat.confidence,
                    )
                )

        return hypotheses

    def convert_hypothesis_to_proposal(
        self, hypothesis: ImprovementHypothesis
    ) -> ChangeProposal | None:
        """Convert a validated hypothesis with statistical evidence into a formal ChangeProposal."""
        if hypothesis.confidence < 0.70:
            logger.info(
                f"⏳ Hypothesis [{hypothesis.hypothesis_id}] confidence too low ({hypothesis.confidence}); skipping proposal."
            )
            return None

        if hypothesis.category == "PROMPT_OPTIMIZATION":
            change_type = ChangeType.PROMPT_OPTIMIZATION
        elif hypothesis.category == "PARAMETER_TUNING":
            change_type = ChangeType.PARAMETER_TUNING
        else:
            change_type = ChangeType.CODE_REFACTOR

        proposal = self.proposal_manager.create_proposal(
            title=f"Self-Improvement: {hypothesis.category} ({hypothesis.hypothesis_id})",
            description=f"{hypothesis.observation} Root cause: {hypothesis.root_cause}",
            change_type=change_type,
            diff_content=hypothesis.proposed_change,
            target_module=hypothesis.target_module,
            current_fitness=0.80,
        )

        logger.info(
            f"✨ Created Governed ChangeProposal [{proposal.proposal_id}] from Hypothesis [{hypothesis.hypothesis_id}]"
        )
        return proposal


# Global Singleton
_hypothesis_engine: HypothesisEngine | None = None


def get_hypothesis_engine() -> HypothesisEngine:
    global _hypothesis_engine
    if _hypothesis_engine is None:
        _hypothesis_engine = HypothesisEngine()
    return _hypothesis_engine
