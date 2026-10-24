"""Backward-compatible import shim for the renamed refactor proposer.

Use ``core.tier8.codebase_refactor_proposer`` for new integrations.
"""

from core.tier8.codebase_refactor_proposer import (
    CodebaseRefactorProposer,
    ImprovementProposal,
    SelfImprovementAgent,
    get_codebase_refactor_proposer,
    get_self_improvement_agent,
)

__all__ = [
    "CodebaseRefactorProposer",
    "ImprovementProposal",
    "SelfImprovementAgent",
    "get_codebase_refactor_proposer",
    "get_self_improvement_agent",
]
