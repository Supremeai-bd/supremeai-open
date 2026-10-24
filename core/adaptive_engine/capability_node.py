from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from adaptive_engine.capability_registry import Capability, CapabilityRegistry

Handler = Callable[[dict[str, Any]], Any | Awaitable[Any]]


@dataclass(frozen=True)
class NodeContext:
    tenant_id: str
    actor_id: str
    correlation_id: str
    capability: str
    idempotency_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NodeResult:
    ok: bool
    output: Any = None
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: float = 0.0


class CapabilityNodeBridge:
    """Typed in-process dispatch bridge backed by the canonical registry."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry
        self._handlers: dict[str, Handler] = {}

    def register(self, capability: Capability, handler: Handler) -> None:
        if capability.signature in self._handlers:
            raise ValueError(f"handler already registered: {capability.signature}")
        self._handlers[capability.signature] = handler
        if self.registry.find_by_signature(capability.signature) is None:
            self.registry.register(capability)

    async def dispatch(
        self, signature: str, context: NodeContext, payload: dict[str, Any]
    ) -> NodeResult:
        started = time.perf_counter()
        if context.capability != signature:
            return self._failure(
                "capability_context_mismatch", "context capability does not match request", started
            )
        capability = self.registry.find_by_signature(signature)
        handler = self._handlers.get(signature)
        if capability is None or handler is None:
            return self._failure(
                "capability_unavailable", f"capability is not active: {signature}", started
            )
        if capability.tenant_id not in (None, context.tenant_id):
            return self._failure(
                "tenant_denied", "capability is not available to this tenant", started
            )
        try:
            result = handler({"payload": dict(payload), "context": context})
            if inspect.isawaitable(result):
                result = await result
            self.registry.record_usage(capability.capability_id, success=True)
            return NodeResult(True, result, duration_ms=self._duration(started))
        except Exception as exc:
            self.registry.record_usage(capability.capability_id, success=False)
            return self._failure("handler_failed", str(exc), started)

    def dispatch_sync(
        self, signature: str, context: NodeContext, payload: dict[str, Any]
    ) -> NodeResult:
        return asyncio.run(self.dispatch(signature, context, payload))

    @staticmethod
    def _duration(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 3)

    def _failure(self, code: str, message: str, started: float) -> NodeResult:
        return NodeResult(
            False, error_code=code, error_message=message, duration_ms=self._duration(started)
        )


__all__ = ["CapabilityNodeBridge", "NodeContext", "NodeResult"]
