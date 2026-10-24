"""Backward compatibility shim for core.messaging.events.

Canonical domain module: core.firebase_auth
"""

from core.firebase_auth import auth, get_firebase_auth  # noqa: F401

__all__ = ["auth", "get_firebase_auth"]
