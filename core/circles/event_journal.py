from __future__ import annotations

from collections import deque
from threading import Lock

from .contracts import EventEnvelope


class CircleEventJournal:
    """Bounded in-process replay buffer; durable stores can subscribe later."""

    def __init__(self, max_events: int = 2048) -> None:
        self._events: deque[EventEnvelope] = deque(maxlen=max_events)
        self._lock = Lock()

    def append(self, event: EventEnvelope) -> EventEnvelope:
        with self._lock:
            self._events.append(event)
        return event

    def replay(
        self, *, tenant_id: str, after_event_id: str | None = None
    ) -> tuple[EventEnvelope, ...]:
        with self._lock:
            events = tuple(self._events)
        if after_event_id is None:
            return tuple(event for event in events if event.tenant_id == tenant_id)
        found = False
        replayed: list[EventEnvelope] = []
        for event in events:
            if found and event.tenant_id == tenant_id:
                replayed.append(event)
            elif event.event_id == after_event_id:
                found = True
        return tuple(replayed)


circle_event_journal = CircleEventJournal()
