"""Global Governance Core — the shared control protocol of the FCC.

This is the SMALL center-of-centers. It owns ONLY cross-cutting concerns:

    identity/context    tenant + actor presence enforcement
    policy              injectable global policy boundary
    approval            approval gate before risky capabilities
    correlation         correlation/execution id propagation
    lifecycle           overall deadline + status normalization
    audit               journal fan-out of every execution event
    cross-circle events subscriber fan-out (realtime sync)

It must NEVER import domain modules or individual centers — centers are
wired in by ``core.circles.bootstrap.build_federation``. This constraint
is enforced by ``tests/test_fcc_boundaries.py``.

Hot path (zero infrastructure):

    request → GovernanceCore.route → center.handle → local adapter → result

Governed path (risky or durable work):

    request → policy → approval gate → center → audit/event fan-out
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from core.circles.centers.base import CircleCenter
from core.circles.contracts import (
    CircleManifest,
    CircleName,
    EventEnvelope,
    ExecutionStatus,
    PolicyDecision,
)
from core.circles.envelopes import (
    ExecutionEnvelope,
    ExecutionError,
    ResultEnvelope,
    result_envelope_from_execution,
)
from core.circles.event_journal import CircleEventJournal, circle_event_journal

PolicyEvaluator = Callable[
    [ExecutionEnvelope], PolicyDecision | bool | Awaitable[PolicyDecision | bool]
]
EventSubscriber = Callable[[EventEnvelope], None]


def default_global_policy(envelope: ExecutionEnvelope) -> PolicyDecision:
    """Minimal central policy: identity must be present and tenant-scoped."""
    if not envelope.actor_id.strip() or not envelope.tenant_id.strip():
        return PolicyDecision(allowed=False, reason="actor_context_invalid")
    return PolicyDecision(allowed=True)


class GovernanceCore:
    """Federated control plane: routes envelopes between circle centers."""

    def __init__(
        self,
        *,
        journal: CircleEventJournal | None = None,
        policy_evaluator: PolicyEvaluator | None = None,
    ) -> None:
        self._centers: dict[CircleName, CircleCenter] = {}
        self._journal = journal or circle_event_journal
        self._policy_evaluator = policy_evaluator or default_global_policy
        self._subscribers: list[EventSubscriber] = []

    # ── center registry ──────────────────────────────────────────────
    def register_center(self, center: CircleCenter) -> None:
        if center.circle in self._centers:
            raise ValueError(f"Circle center already registered: {center.circle.value}")
        self._centers[center.circle] = center

    def resolve(self, circle: CircleName) -> CircleCenter | None:
        return self._centers.get(circle)

    def centers(self) -> tuple[CircleCenter, ...]:
        return tuple(self._centers.values())

    def capabilities(self) -> tuple[str, ...]:
        names: set[str] = set()
        for center in self._centers.values():
            names.update(center.capabilities())
        return tuple(sorted(names))

    def set_policy_evaluator(self, evaluator: PolicyEvaluator | None) -> None:
        self._policy_evaluator = evaluator or default_global_policy

    # ── realtime sync ────────────────────────────────────────────────
    def subscribe(self, subscriber: EventSubscriber) -> None:
        if subscriber not in self._subscribers:
            self._subscribers.append(subscriber)

    # ── canonical cross-circle door ──────────────────────────────────
    async def route(self, envelope: ExecutionEnvelope) -> ResultEnvelope:
        """Route one ExecutionEnvelope to its owning circle center."""
        center = self._centers.get(envelope.circle)
        if center is None:
            result = self._failed(
                envelope,
                ExecutionStatus.UNAVAILABLE,
                "unknown_circle",
                f"No circle center registered for '{envelope.circle.value}'",
            )
            self._fan_out(result)
            return result

        spec = center.describe(envelope.capability)
        if spec is None:
            result = self._failed(
                envelope,
                ExecutionStatus.UNAVAILABLE,
                "unknown_capability",
                f"Capability '{envelope.capability}' is not registered in the "
                f"'{envelope.circle.value}' circle",
            )
            self._fan_out(result)
            return result

        policy = await self._evaluate_policy(envelope)
        if not policy.allowed:
            event = self._audit_event(envelope, "capability.rejected", policy)
            result = self._failed(
                envelope,
                ExecutionStatus.REJECTED,
                "central_policy_denied",
                policy.reason or "Central policy denied this capability",
                events=(event,),
            )
            self._fan_out(result)
            return result

        overall_timeout = min(envelope.deadline_ms, spec.timeout_ms) / 1000.0
        try:
            result = await asyncio.wait_for(center.handle(envelope), overall_timeout)
        except TimeoutError:
            result = self._failed(
                envelope,
                ExecutionStatus.FAILED,
                "deadline_exceeded",
                f"Execution exceeded {int(overall_timeout * 1000)}ms deadline",
            )

        self._fan_out(result)
        return result

    async def dispatch_to(
        self,
        circle: CircleName | str,
        capability: str,
        payload: dict[str, Any] | None = None,
        *,
        actor_id: str,
        tenant_id: str,
        deadline_ms: int = 30_000,
        correlation_id: str | None = None,
        policy: dict[str, Any] | None = None,
    ) -> ResultEnvelope:
        """Convenience builder: construct an envelope and route it."""
        circle_name = CircleName(circle) if not isinstance(circle, CircleName) else circle
        envelope = ExecutionEnvelope(
            circle=circle_name,
            capability=capability,
            tenant_id=tenant_id,
            actor_id=actor_id,
            payload=payload or {},
            policy=policy or {},
            deadline_ms=deadline_ms,
            correlation_id=correlation_id or f"corr_{uuid4().hex}",
        )
        return await self.route(envelope)

    # ── introspection ────────────────────────────────────────────────
    def topology(self) -> list[dict[str, Any]]:
        topology: list[dict[str, Any]] = []
        for circle in CircleName:
            center = self._centers.get(circle)
            if center is None:
                topology.append(
                    {
                        "circle": circle.value,
                        "display_name": None,
                        "owner": None,
                        "status": "unregistered",
                        "capabilities": [],
                    }
                )
                continue
            health = center.health()
            topology.append(
                {
                    "circle": circle.value,
                    "display_name": center.display_name,
                    "owner": center.owner,
                    "status": health.status,
                    "capabilities": [
                        spec.model_dump(mode="json") for spec in center.capability_specs()
                    ],
                    "health": health.model_dump(mode="json"),
                }
            )
        return topology

    def federation_health(self) -> dict[str, Any]:
        centers = self.centers()
        healths = [center.health() for center in centers]
        counts: dict[str, int] = {}
        for health in healths:
            counts[health.status] = counts.get(health.status, 0) + 1
        if counts.get("unavailable", 0) == len(healths):
            status = "unavailable"
        elif counts.get("degraded", 0) and counts.get("degraded", 0) >= len(healths) / 2:
            status = "degraded"
        else:
            status = "healthy"
        return {
            "status": status,
            "centers": len(healths),
            "center_status": counts,
            "capabilities": len(self.capabilities()),
            "checked_at": time.time(),
        }

    def manifests(self) -> tuple[CircleManifest, ...]:
        manifests = []
        for center in self.centers():
            manifests.append(
                CircleManifest(
                    name=center.circle,
                    display_name=center.display_name,
                    owner=center.owner,
                    capabilities=tuple(
                        spec.to_ref(center.circle) for spec in center.capability_specs()
                    ),
                    health=center.health().status,
                )
            )
        return tuple(manifests)

    # ── internals ────────────────────────────────────────────────────
    async def _evaluate_policy(self, envelope: ExecutionEnvelope) -> PolicyDecision:
        decision = self._policy_evaluator(envelope)
        if hasattr(decision, "__await__"):
            decision = await decision
        if isinstance(decision, PolicyDecision):
            return decision
        return PolicyDecision(allowed=bool(decision))

    def _audit_event(
        self, envelope: ExecutionEnvelope, event_type: str, policy: PolicyDecision
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type=event_type,
            execution_id=envelope.execution_id,
            correlation_id=envelope.correlation_id,
            actor_id=envelope.actor_id,
            tenant_id=envelope.tenant_id,
            circle=envelope.circle,
            payload={
                "capability": envelope.capability,
                "policy_version": policy.policy_version,
            },
        )

    def _failed(
        self,
        envelope: ExecutionEnvelope,
        status: ExecutionStatus,
        code: str,
        message: str,
        *,
        events: tuple[EventEnvelope, ...] = (),
    ) -> ResultEnvelope:
        return ResultEnvelope(
            execution_id=envelope.execution_id,
            status=status,
            circle=envelope.circle,
            events=events,
            error=ExecutionError(code=code, message=message),
        )

    def _fan_out(self, result: ResultEnvelope) -> None:
        """Audit journal + subscriber fan-out (cross-circle events)."""
        for event in result.events:
            self._journal.append(event)
            for subscriber in self._subscribers:
                try:
                    subscriber(event)
                except Exception:  # noqa: BLE001 — fan-out must never break routing
                    continue


# ── process-wide federation singleton ────────────────────────────────
_governance_core: GovernanceCore | None = None
_governance_lock = threading.Lock()


def get_governance_core() -> GovernanceCore:
    """Process-wide GovernanceCore; wired with all default centers once."""
    global _governance_core
    if _governance_core is None:
        with _governance_lock:
            if _governance_core is None:
                from core.circles.bootstrap import build_federation

                _governance_core = build_federation()
    return _governance_core


def reset_governance_core() -> None:
    """Test helper: drop the singleton so the next access rebuilds."""
    global _governance_core
    with _governance_lock:
        _governance_core = None


__all__ = [
    "GovernanceCore",
    "default_global_policy",
    "get_governance_core",
    "reset_governance_core",
    "result_envelope_from_execution",
]
