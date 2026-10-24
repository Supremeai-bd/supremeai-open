"""Capability Registry — delegates to canonical adaptive_engine.capability_registry.

Preserves backward-compatibility while eliminating code duplication.
"""

from __future__ import annotations

from adaptive_engine.capability_registry import (
    Capability,
    CapabilityExistsError,
    CapabilityLifecycleState,
    CapabilityRegistry,
    CapabilityRuntimeTier,
    CapabilityStateError,
    get_capability_registry,
)

__all__ = [
    "Capability",
    "CapabilityLifecycleState",
    "CapabilityRuntimeTier",
    "CapabilityStateError",
    "CapabilityExistsError",
    "CapabilityRegistry",
    "get_capability_registry",
]
