"""Deterministic in-memory store used by local contract tests.

The same interface can be implemented by Supabase/Postgres after manual setup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .canonical import EventEnvelope, ExecutionContext, ExecutionResult


@dataclass
class FakeExecutionStore:
    executions: dict[str, dict[str, Any]] = field(default_factory=dict)
    events: list[EventEnvelope] = field(default_factory=list)
    idempotency: dict[tuple[str, str], str] = field(default_factory=dict)

    def start(self, context: ExecutionContext) -> bool:
        key = (context.tenant_id, context.idempotency_key)
        existing = self.idempotency.get(key)
        if existing and existing != context.execution_id:
            return False
        self.idempotency[key] = context.execution_id
        self.executions.setdefault(
            context.execution_id, {"context": context.to_dict(), "result": None}
        )
        return True

    def finish(self, execution_id: str, result: ExecutionResult) -> None:
        if execution_id not in self.executions:
            raise KeyError(execution_id)
        self.executions[execution_id]["result"] = result.to_dict()

    def append_event(self, event: EventEnvelope) -> EventEnvelope:
        if any(item.fingerprint == event.fingerprint for item in self.events):
            return next(item for item in self.events if item.fingerprint == event.fingerprint)
        event = EventEnvelope(
            event.event_type,
            event.context,
            event.payload,
            event.event_id,
            event.occurred_at,
            len(self.events) + 1,
        )
        self.events.append(event)
        return event

    def events_for_tenant(self, tenant_id: str) -> list[EventEnvelope]:
        return [event for event in self.events if event.context.tenant_id == tenant_id]
