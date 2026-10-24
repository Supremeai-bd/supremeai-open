from __future__ import annotations

from core.capability_activation import capability_activation_store
from core.capability_gateway import register_core_capabilities
from core.circles.contracts import CapabilityRef
from core.circles.registry import circle_registry


def discover_capability(capability: str, tenant_id: str) -> dict[str, object] | None:
    """Return one canonical, tenant-aware capability description."""
    register_core_capabilities()
    reference: CapabilityRef | None = circle_registry.describe(capability)
    if reference is None:
        return None
    return {
        "name": reference.name,
        "circle": reference.owner_circle.value,
        "risk": reference.risk_level.value,
        "approval_required": reference.approval_required,
        "enabled": capability_activation_store.is_enabled(
            tenant_id,
            reference.name,
            core=not reference.tenant_activation_required,
        ),
        "version": reference.version,
    }


def discover_capabilities(tenant_id: str) -> tuple[dict[str, object], ...]:
    # Issue #472 (xdist parallel-safety): ensure core capabilities are
    # registered BEFORE iterating the registry. `discover_capability` does
    # this per-item, but the aggregated path evaluated
    # `circle_registry.capabilities()` first — so in a fresh process (new
    # xdist worker, or any cold start) it returned an empty set and the
    # per-item registration never ran. Registration is idempotent and
    # guarded, making this order-independent.
    register_core_capabilities()
    return tuple(
        description
        for capability in circle_registry.capabilities()
        if (description := discover_capability(capability, tenant_id)) is not None
    )
