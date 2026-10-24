from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from adaptive_engine.capability_node import CapabilityNodeBridge, NodeContext, NodeResult

EventSink = Callable[[str, dict[str, Any]], None | Awaitable[None]]


@dataclass
class GovernedCapabilityExecutor:
    bridge: CapabilityNodeBridge
    event_sink: EventSink | None = None

    async def execute(
        self, signature: str, context: NodeContext, payload: dict[str, Any]
    ) -> NodeResult:
        await self._emit(
            "execution.started", {"capability": signature, "correlation_id": context.correlation_id}
        )
        result = await self.bridge.dispatch(signature, context, payload)
        await self._emit(
            "execution.succeeded" if result.ok else "execution.failed",
            {
                "capability": signature,
                "correlation_id": context.correlation_id,
                "error_code": result.error_code,
            },
        )
        return result

    async def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.event_sink is None:
            return
        result = self.event_sink(event_type, payload)
        if hasattr(result, "__await__"):
            await result


__all__ = ["GovernedCapabilityExecutor"]
