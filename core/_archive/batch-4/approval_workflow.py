"""Approval Workflow — delegates to canonical adaptive_engine.approval_workflow.

Preserves backward-compatibility while eliminating code duplication.
"""

from __future__ import annotations

from adaptive_engine.approval_workflow import (
    ApprovalDecision,
    ApprovalProposal,
    ApprovalWorkflow,
    ProposalCooldownError,
    ProposalKind,
    ProposalPriority,
    ProposalState,
    ProposalStateError,
    get_approval_workflow,
)

__all__ = [
    "ProposalKind",
    "ProposalPriority",
    "ProposalState",
    "ApprovalProposal",
    "ApprovalDecision",
    "ApprovalWorkflow",
    "get_approval_workflow",
    "ProposalStateError",
    "ProposalCooldownError",
]
