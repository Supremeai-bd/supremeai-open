"""Realtime Circle Center — realtime synchronization.

Owns (per FCC plan): realtime event synchronization. The center keeps a
local ring buffer of published events and a subscriber list. The Global
Governance Core registers itself as a subscriber so every cross-circle
execution event is mirrored here — that is the zero-infrastructure
realtime bus (no external queue required).
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from typing import Any

from core.circles.centers.base import CircleCenter, LocalCapability
from core.circles.contracts import CircleName, EventEnvelope, RiskLevel

Subscriber = Callable[[EventEnvelope], None]


class RealtimeCenter(CircleCenter):
    circle = CircleName.REALTIME
    display_name = "Realtime events"
    owner = "backend/api/routes/stream_hitl_sse.py"

    _RING_MAX = 512

    def __init__(self) -> None:
        super().__init__()
        self._ring: deque[dict[str, Any]] = deque(maxlen=self._RING_MAX)
        self._subscribers: list[Subscriber] = []
        self.register(
            LocalCapability(
                name="realtime.publish",
                description="Publish a realtime event to federation subscribers",
                risk_level=RiskLevel.LOW,
                timeout_ms=5_000,
            ),
            self._publish,
        )

    # ── realtime sync surface ────────────────────────────────────────
    def subscribe(self, subscriber: Subscriber) -> None:
        if subscriber not in self._subscribers:
            self._subscribers.append(subscriber)

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return list(self._ring)[-limit:]

    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def receive(self, event: EventEnvelope) -> None:
        """Entry point used by the GovernanceCore fan-out (mirror event)."""
        self._ring.append(
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "circle": event.circle.value,
                "execution_id": event.execution_id,
                "correlation_id": event.correlation_id,
                "occurred_at": event.occurred_at.isoformat(),
                "payload": dict(event.payload),
            }
        )

    # ── capability handlers ──────────────────────────────────────────
    async def _publish(self, request) -> dict:
        payload = dict(request.payload.get("event", {}))
        self._ring.append(
            {
                "event_id": f"evt_{request.context.execution_id}",
                "event_type": str(payload.get("event_type", "custom.published")),
                "circle": self.circle.value,
                "execution_id": request.context.execution_id,
                "correlation_id": request.context.correlation_id,
                "occurred_at": time.time(),
                "payload": payload,
            }
        )
        return {"published": True, "subscriber_count": self.subscriber_count()}


__all__ = ["RealtimeCenter"]
