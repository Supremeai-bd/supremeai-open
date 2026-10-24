import inspect
from collections.abc import Callable
from typing import Any

from core.logging_config import logger


class InProcessCapabilityDispatcher:
    """In-process handler and capability dispatcher registry."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable] = {}
        self._signatures: dict[str, Any] = {}

    def register(self, capability: str, handler: Callable) -> None:
        self._handlers[capability] = handler
        try:
            self._signatures[capability] = inspect.signature(handler)
        except (ValueError, TypeError):
            self._signatures[capability] = None

    def capabilities(self) -> dict[str, Any | None]:
        return dict(self._signatures)

    def supports(self, capability: str) -> bool:
        return capability in self._handlers

    def dispatch(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
        handler = self._handlers.get(capability)
        if not handler:
            raise KeyError(f"No handler registered for capability '{capability}'")
        try:
            return handler(payload)
        except Exception as exc:
            logger.exception("Dispatch failed for capability=%s", capability)
            return {"success": False, "error": str(exc), "capability": capability}


# Backward compatibility alias
ApiRouter = InProcessCapabilityDispatcher
