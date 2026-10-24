"""Backward compatibility shim for brain.api_router.

Canonical domain module: core.in_process_dispatcher
"""

from core.in_process_dispatcher import ApiRouter, InProcessCapabilityDispatcher

__all__ = ["ApiRouter", "InProcessCapabilityDispatcher"]
