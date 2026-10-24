# backend/learning/evolution_bridge.py
"""Learning to Evolution Bridge (Hypothesis Synthesis and Proposal Generation).

Converts recurring LearningInsights into validated ChangeProposals.
"""

from __future__ import annotations

from core.logging_config import logger
from evolution.change_proposal import (
    ChangeProposal,
    ChangeProposalManager,
    ChangeType,
    get_change_manager,
)
from learning.experience import ExperienceRecord
from learning.outcome_analyzer import (
    OutcomeAnalyzer,
    OutcomeClassification,
    get_outcome_analyzer,
)


class EvolutionBridge:
    """Evaluates learning insights and automatically generates change proposals for self-evolution."""

    def __init__(
        self,
        analyzer: OutcomeAnalyzer | None = None,
        proposal_manager: ChangeProposalManager | None = None,
    ) -> None:
        self.analyzer = analyzer or get_outcome_analyzer()
        self.proposal_manager = proposal_manager or get_change_manager()

    def process_experience_and_propose(
        self,
        record: ExperienceRecord,
        min_evidence_threshold: int = 1,
    ) -> ChangeProposal | None:
        """Analyze task experience, synthesize insight, and propose system optimization."""
        classification = self.analyzer.classify_outcome(record)

        if classification == OutcomeClassification.SYNTAX_ERROR:
            # Propose stricter markdown stripping & AST prompt template optimization
            proposal = self.proposal_manager.create_proposal(
                title=f"Prompt Optimization for Code Generation ({record.task_id})",
                description="Inject explicit AST syntax compliance instruction and clean markdown fences",
                change_type=ChangeType.PROMPT_OPTIMIZATION,
                diff_content={
                    "prompt_modifier": "Output ONLY clean syntax-compliant code without explanatory text.",
                    "strip_markdown": True,
                },
                target_module="backend/brain/code_generation_prompt.py",
                current_fitness=record.verification_score,
            )
            logger.info(
                f"✨ Synthesized ChangeProposal [{proposal.proposal_id}] from AST Syntax Error"
            )
            return proposal

        elif classification == OutcomeClassification.BUDGET_EXHAUSTED:
            # Propose token allowance auto-tuning
            proposal = self.proposal_manager.create_proposal(
                title="Dynamic Token Budget Escalation",
                description="Increase initial token allocation for complex multi-step reasoning",
                change_type=ChangeType.PARAMETER_TUNING,
                diff_content={"token_multiplier": 1.25},
                target_module="backend/runtime/budget_guard.py",
                current_fitness=0.70,
            )
            logger.info(
                f"✨ Synthesized ChangeProposal [{proposal.proposal_id}] from Budget Exhaustion"
            )
            return proposal

        return None


# Global Singleton
_evolution_bridge: EvolutionBridge | None = None


def get_evolution_bridge() -> EvolutionBridge:
    global _evolution_bridge
    if _evolution_bridge is None:
        _evolution_bridge = EvolutionBridge()
    return _evolution_bridge
