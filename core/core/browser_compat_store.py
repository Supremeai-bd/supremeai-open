from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any
from uuid import uuid4


class BrowserCompatibilityStore:
    """Process-local compatibility state isolated by authenticated owner.

    Canonical browser automation uses BrowserSessionManager; this store only
    preserves legacy UI endpoints until they are migrated to durable storage.
    """

    def __init__(self) -> None:
        self._state: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "status": {"browsing": False, "currentUrl": "about:blank"},
                "activities": [],
                "paused": {"paused": False},
                "credentials": {},
                "permissions": [],
                "requests": [],
                "learning": {"enabled": True},
                "tasks": {},
                "findings": [],
                "sessions": {},
            }
        )

    def owner(self, owner_id: str) -> dict[str, Any]:
        return self._state[owner_id]

    def new_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"

    def snapshot(self, owner_id: str, key: str) -> Any:
        return deepcopy(self.owner(owner_id)[key])


browser_compat_store = BrowserCompatibilityStore()

__all__ = ["BrowserCompatibilityStore", "browser_compat_store"]
