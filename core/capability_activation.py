from __future__ import annotations

from collections import defaultdict
from threading import RLock

CORE_CAPABILITIES = frozenset({"system.health.read"})


class CapabilityActivationStore:
    """Central tenant capability boundary.

    Persistence is intentionally behind this small interface so the policy
    gateway does not depend on a particular database implementation.
    """

    def __init__(self) -> None:
        self._overrides: dict[str, set[str]] = defaultdict(set)
        self._lock = RLock()

    def is_enabled(self, tenant_id: str, capability: str, *, core: bool = False) -> bool:
        if core or capability in CORE_CAPABILITIES:
            return True
        with self._lock:
            return capability in self._overrides.get(tenant_id, set())

    def enable(self, tenant_id: str, capability: str) -> None:
        with self._lock:
            self._overrides[tenant_id].add(capability)

    def disable(self, tenant_id: str, capability: str) -> None:
        with self._lock:
            self._overrides[tenant_id].discard(capability)

    def list_enabled(self, tenant_id: str) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(CORE_CAPABILITIES | self._overrides.get(tenant_id, set())))


capability_activation_store = CapabilityActivationStore()
