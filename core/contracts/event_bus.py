"""Typed, idempotent event publishing over the canonical EventEnvelope."""

from __future__ import annotations

from core.contracts.canonical import EventEnvelope
from core.contracts.fake_store import FakeExecutionStore


class EventBus:
    """Small provider-neutral event boundary; persistence is injectable later."""

    def __init__(self, store: FakeExecutionStore | None = None) -> None:
        self.store = store or FakeExecutionStore()

    def publish(self, event: EventEnvelope) -> EventEnvelope:
        if not event.event_type or "." not in event.event_type:
            raise ValueError("event_type must be namespaced, e.g. run.completed")
        return self.store.append_event(event)

    def tenant_events(self, tenant_id: str) -> list[EventEnvelope]:
        return self.store.events_for_tenant(tenant_id)


__all__ = ["EventBus"]
