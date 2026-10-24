"""Health Model — delegates to canonical adaptive_engine.health_model.

Preserves backward-compatibility while eliminating code duplication.
"""

from __future__ import annotations

from adaptive_engine.health_model import (
    HealthAggregator,
    HealthStatus,
    MemoryInfo,
    UnifiedHealth,
    get_health_aggregator,
)

__all__ = [
    "HealthStatus",
    "MemoryInfo",
    "UnifiedHealth",
    "HealthAggregator",
    "get_health_aggregator",
]
