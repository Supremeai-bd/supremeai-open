"""Provider-neutral execution planning for offload and failover paths.

The planner only emits an execution contract. Actual adapters must enforce their
own authentication and ownership checks; no credentials are rotated here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from core.execution_policy import (
    ExecutionMode,
    ProviderBudget,
    TaskClass,
    choose_execution,
)


class AdapterKind(StrEnum):
    """Execution adapter types."""

    SERVER = "server"
    CLIENT = "client"
    BYOC = "byoc"
    RESEARCH = "research"


@dataclass(frozen=True)
class ExecutionRequest:
    """Request to plan execution for a task."""

    task_id: str
    tenant_id: str
    task_class: TaskClass
    payload: dict[str, Any]
    cache_hit: bool = False
    client_capabilities: tuple[str, ...] = ()
    byoc_capabilities: tuple[str, ...] = ()
    urgent: bool = False

    def __post_init__(self) -> None:
        if not self.task_id or not self.tenant_id:
            raise ValueError("task_id and tenant_id are required")


@dataclass(frozen=True)
class ExecutionPlan:
    """Deterministic execution plan with ownership context."""

    task_id: str
    tenant_id: str
    mode: ExecutionMode
    adapter: AdapterKind | None
    provider: str | None
    reason: str
    degraded: bool
    capability: str | None = None


def build_execution_plan(
    request: ExecutionRequest,
    *,
    providers: tuple[ProviderBudget, ...] = (),
) -> ExecutionPlan:
    """Build a safe plan with deterministic client/BYOC failover semantics.

    Order: cache → client/BYOC (if authorized) → healthy provider → queued → unavailable.
    No credential rotation or notebook keep-alive.
    """
    capability = request.task_class.value
    client_available = capability in request.client_capabilities
    byoc_available = capability in request.byoc_capabilities

    decision = choose_execution(
        request.task_class,
        cache_hit=request.cache_hit,
        providers=providers,
        client_available=client_available,
        byoc_available=byoc_available,
        urgent=request.urgent,
    )

    adapter_map = {
        ExecutionMode.SERVER: AdapterKind.SERVER,
        ExecutionMode.QUEUED: AdapterKind.SERVER,
        ExecutionMode.CLIENT: AdapterKind.CLIENT,
        ExecutionMode.BYOC: AdapterKind.BYOC,
        ExecutionMode.RESEARCH: AdapterKind.RESEARCH,
        ExecutionMode.CACHE: None,
        ExecutionMode.UNAVAILABLE: None,
    }

    adapter = adapter_map.get(decision.mode)

    return ExecutionPlan(
        task_id=request.task_id,
        tenant_id=request.tenant_id,
        mode=decision.mode,
        adapter=adapter,
        provider=decision.provider,
        reason=decision.reason,
        degraded=decision.degraded,
        capability=capability if adapter in (AdapterKind.CLIENT, AdapterKind.BYOC) else None,
    )


def fallback_plan(
    request: ExecutionRequest,
    failed_provider: str,
    *,
    providers: tuple[ProviderBudget, ...] = (),
) -> ExecutionPlan:
    """Re-plan after provider failure without retrying the failed provider."""
    remaining = tuple(p for p in providers if p.name != failed_provider)
    return build_execution_plan(request, providers=remaining)


__all__ = [
    "AdapterKind",
    "ExecutionPlan",
    "ExecutionRequest",
    "build_execution_plan",
    "fallback_plan",
]
