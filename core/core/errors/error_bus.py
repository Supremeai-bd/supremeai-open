# backend/core/error_bus.py
"""Observable Error Pipeline & Decorator Integration.

বাংলা মন্তব্য: ErrorEventBus-এর সাথে সমন্বয় রেখে ফেইলুর ট্র্যাকিং করার জন্য Decorator।
কোডের কোনো স্থানে unhandled failure হলে এটি ErrorEventBus-এ emit করে re-raise করবে।
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from typing import Any

from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus


def with_error_bus(component_name: str = "GenericComponent") -> Callable:
    """Decorator to automatically log and report exceptions via ErrorEventBus."""

    def decorator(fn: Callable) -> Callable:
        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    context = ErrorContext(module=component_name)
                    event = ErrorEvent(
                        module=component_name,
                        error_type=exc.__class__.__name__,
                        message=str(exc),
                        severity="ERROR",
                        structured_context=context,
                    )
                    error_event_bus.emit(event)
                    raise

            return async_wrapper

        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    context = ErrorContext(module=component_name)
                    event = ErrorEvent(
                        module=component_name,
                        error_type=exc.__class__.__name__,
                        message=str(exc),
                        severity="ERROR",
                        structured_context=context,
                    )
                    error_event_bus.emit(event)
                    raise

            return sync_wrapper

    return decorator


__all__ = ["with_error_bus"]
