"""Capability-to-resource runtime placement (Phase 3/6).

বাংলা: planner বা MCP gateway সরাসরি provider বেছে নেবে না। এই selector
প্রথমে capability registry থেকে active capability খুঁজে, তারপর tenant-safe
resource registry থেকে health/capability অনুযায়ী resource নির্বাচন করে।
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from adaptive_engine.capability_registry import (
    Capability,
    CapabilityLifecycleState,
    CapabilityRegistry,
)
from adaptive_engine.resource_registry import ResourceRecord, ResourceRegistry, ResourceState


@dataclass(frozen=True)
class Placement:
    capability: Capability
    resource: ResourceRecord
    score: float


class PlacementError(RuntimeError):
    """Raised when no safe runtime placement can be selected."""


def select_placement(
    capability_registry: CapabilityRegistry,
    resource_registry: ResourceRegistry,
    *,
    capability_signature: str,
    tenant_id: str | None = None,
    required_provider: str | None = None,
) -> Placement:
    """Select the best registered resource for an active capability.

    Selection is deterministic: healthy resources first, then capability
    declaration match, then stable resource id ordering. Tenant filtering is
    delegated to the registry's deny-by-default shared-resource query.
    """
    capability = capability_registry.find_by_signature(capability_signature)
    if capability is None:
        raise PlacementError(f"capability_not_found:{capability_signature}")
    if capability.lifecycle_state is not CapabilityLifecycleState.ACTIVE:
        raise PlacementError(f"capability_not_active:{capability.capability_id}")

    resources = resource_registry.list(tenant_id=tenant_id, limit=500)
    candidates: list[tuple[float, ResourceRecord]] = []
    for resource in resources:
        if resource.state not in {ResourceState.HEALTHY, ResourceState.REGISTERED}:
            continue
        if required_provider and resource.provider.value != required_provider:
            continue
        if (
            capability.capability_id not in resource.capabilities
            and capability.signature not in resource.capabilities
        ):
            continue
        score = 2.0 if resource.state is ResourceState.HEALTHY else 1.0
        if resource.tenant_id == tenant_id and tenant_id is not None:
            score += 0.5
        candidates.append((score, resource))

    if not candidates:
        raise PlacementError(f"resource_unavailable:{capability_signature}")
    score, resource = sorted(candidates, key=lambda item: (-item[0], item[1].resource_id))[0]
    return Placement(capability=capability, resource=resource, score=score)


__all__ = ["Placement", "PlacementError", "select_placement"]
