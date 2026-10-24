"""Source Governance — delegates to canonical adaptive_engine.source_governance.

Preserves backward-compatibility while eliminating code duplication.
"""

from __future__ import annotations

from adaptive_engine.source_governance import (
    LearnedItem,
    SourceCategory,
    SourceGovernance,
    SourcePolicy,
    SourceState,
    SourceStateError,
    get_source_governance,
)

__all__ = [
    "SourceState",
    "SourceCategory",
    "SourcePolicy",
    "LearnedItem",
    "SourceGovernance",
    "get_source_governance",
    "SourceStateError",
]
