"""
permission_cache.py - Tiered Permission Cache for Pillar 0
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_L1_TTL_SECONDS: int = 30
_L2_TTL_SECONDS: int = 300
_DEFAULT_FALLBACK_STATE: str = "not_allowed"
_REDIS_KEY_PREFIX: str = "supremeai:perms:"


@dataclass(frozen=True)
class PermissionResult:
    action_name: str
    state: str
    expires_at: datetime | None = None
    is_temp_grant_active: bool = False

    def __bool__(self) -> bool:
        if self.state == "never_allowed":
            return False
        if self.state == "not_allowed":
            return False
        if self.state in ("always_allowed", "allowed_for_now"):
            if self.state == "allowed_for_now" and self.expires_at:
                if datetime.now(UTC) > self.expires_at:
                    return False
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_name": self.action_name,
            "state": self.state,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_temp_grant_active": self.is_temp_grant_active,
        }


class PermissionCache:
    """Tiered (L1->L2->L3) permission cache with fail-closed semantics."""

    def __init__(self, l1_ttl: int = _L1_TTL_SECONDS, l2_ttl: int = _L2_TTL_SECONDS):
        self._l1_cache: dict[str, PermissionResult] = {}
        self._l1_timestamps: dict[str, float] = {}
        self._l1_ttl = l1_ttl
        self._l2_ttl = l2_ttl
        self._lock = threading.Lock()

    def _check_l1(self, action_name: str) -> PermissionResult | None:
        with self._lock:
            cached = self._l1_cache.get(action_name)
            if cached is None:
                return None
            ts = self._l1_timestamps.get(action_name, 0)
            if (time.time() - ts) > self._l1_ttl:
                self._l1_cache.pop(action_name, None)
                self._l1_timestamps.pop(action_name, None)
                return None
            return cached

    def _set_l1(self, result: PermissionResult) -> None:
        with self._lock:
            now = time.time()
            self._l1_cache[result.action_name] = result
            self._l1_timestamps[result.action_name] = now

    def check(self, action_name: str) -> str:
        """Sync L1 check. For high-frequency sync checks."""
        cached = self._check_l1(action_name)
        if cached is not None:
            return cached.state
        return _DEFAULT_FALLBACK_STATE

    def invalidate(self, action_name: str | None = None) -> None:
        with self._lock:
            if action_name:
                self._l1_cache.pop(action_name, None)
                self._l1_timestamps.pop(action_name, None)
            else:
                self._l1_cache.clear()
                self._l1_timestamps.clear()

    def health_check(self) -> dict[str, Any]:
        with self._lock:
            return {
                "l1_cache_size": len(self._l1_cache),
                "l1_keys": list(self._l1_cache.keys()),
                "l1_ttl_seconds": self._l1_ttl,
                "l2_ttl_seconds": self._l2_ttl,
            }
