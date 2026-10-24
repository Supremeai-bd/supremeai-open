"""Governance — delegates to canonical adaptive_engine.governance.

Preserves backward-compatibility while eliminating code duplication.
"""

from __future__ import annotations

from adaptive_engine.governance import (
    ActionRisk,
    BudgetKind,
    Budgets,
    GovernanceEngine,
    RiskDecision,
    get_governance_engine,
)

__all__ = [
    "ActionRisk",
    "BudgetKind",
    "Budgets",
    "RiskDecision",
    "GovernanceEngine",
    "get_governance_engine",
]
