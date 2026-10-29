"""Canonical domain module for events.

Firebase Auth has been removed (Zero-Firebase Native Auth); `auth` is None.
"""

auth = None
get_firebase_auth = lambda: None

__all__ = ["auth", "get_firebase_auth"]
