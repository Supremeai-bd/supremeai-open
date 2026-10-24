"""Correlation Context — delegates to canonical adaptive_engine.correlation.

Preserves backward-compatibility while eliminating code duplication.
"""

from __future__ import annotations

from adaptive_engine.correlation import (
    CorrelationContext,
    current_correlation,
    new_correlation_context,
)

__all__ = [
    "CorrelationContext",
    "current_correlation",
    "new_correlation_context",
]
