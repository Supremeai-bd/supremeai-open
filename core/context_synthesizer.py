"""
Hierarchical Context Budgeter & Progressive Disclosure Engine — Core Decision Moat.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar


class ContextStage(str, Enum):
    STAGE1_DISCOVERY = "STAGE1_DISCOVERY"  # Metadata only (< 1,000 tokens)
    STAGE2_ACTIVATION = "STAGE2_ACTIVATION"  # Contract + Instructions (< 4,000 tokens)
    STAGE3_EXECUTION = (
        "STAGE3_EXECUTION"  # Full Source + Verification (< 16,000 tokens)
    )


@dataclass(frozen=True)
class BudgetLimits:
    max_tokens: int
    allow_source_code: bool
    allow_full_diff: bool


class ContextSynthesizer:
    """
    Enforces the token diet contract across task lifecycles to prevent prompt bloat.
    """

    STAGE_BUDGETS: ClassVar[dict[ContextStage, BudgetLimits]] = {
        ContextStage.STAGE1_DISCOVERY: BudgetLimits(
            max_tokens=1000, allow_source_code=False, allow_full_diff=False
        ),
        ContextStage.STAGE2_ACTIVATION: BudgetLimits(
            max_tokens=4000, allow_source_code=False, allow_full_diff=False
        ),
        ContextStage.STAGE3_EXECUTION: BudgetLimits(
            max_tokens=16000, allow_source_code=True, allow_full_diff=True
        ),
    }

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """Lightweight heuristic: 1 token ≈ 4 characters."""
        return max(1, len(text) // 4)

    @classmethod
    def fit_context(cls, stage: ContextStage, text: str) -> str:
        """
        Truncates or slices content strictly inside the stage's token budget ceiling.
        """
        budget = cls.STAGE_BUDGETS[stage]
        char_limit = budget.max_tokens * 4

        if len(text) <= char_limit:
            return text

        return text[:char_limit] + f"\n... [TRUNCATED per {stage.value} token budget]"
