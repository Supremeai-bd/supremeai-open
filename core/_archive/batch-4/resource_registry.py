"""Resource Registry — delegates to canonical adaptive_engine.resource_registry.

Preserves backward-compatibility while eliminating code duplication.
"""

from __future__ import annotations

from adaptive_engine.resource_registry import (
    AdapterNotRegisteredError,
    BaseProviderAdapter,
    ProviderKind,
    ResourceExistsError,
    ResourceNotFoundError,
    ResourceRecord,
    ResourceRegistry,
    ResourceState,
    get_resource_registry,
)

__all__ = [
    "ProviderKind",
    "ResourceState",
    "ResourceRecord",
    "BaseProviderAdapter",
    "ResourceRegistry",
    "get_resource_registry",
    "ResourceExistsError",
    "ResourceNotFoundError",
    "AdapterNotRegisteredError",
]
