"""Learning Loop — delegates to canonical adaptive_engine.learning_loop.

Preserves backward-compatibility while eliminating code duplication.
"""

from __future__ import annotations

from adaptive_engine.learning_loop import (
    EvolutionSignal,
    LearningLoop,
    LearningOpportunity,
    LearningStage,
    LearningStageError,
    get_learning_loop,
)

__all__ = [
    "LearningStage",
    "EvolutionSignal",
    "LearningOpportunity",
    "LearningLoop",
    "get_learning_loop",
    "LearningStageError",
]
