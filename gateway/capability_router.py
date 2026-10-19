"""Capability router: logical capability -> healthy provider/account selection.

Implements the proposal's "one logical capability per provider, with hidden
account selection, health, quota, cooldown, and failover" contract. Agents
request a capability (e.g. "cache", "chat", "edge"); the router picks an
eligible configured account and records the outcome so subsequent calls can
avoid unhealthy or quota-exhausted accounts.

Stdlib only. No secrets are stored here: accounts carry an alias and a
provider/model pair; credentials live in the secrets manager and are
resolved by the execution layer.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass


@dataclass
class Account:
    alias: str
    provider: str
    model: str
    healthy: bool = True
    cooldown_until: float = 0.0
    quota_remaining: int | None = None
    latency_ms: float = 0.0
    consecutive_failures: int = 0


@dataclass
class Selection:
    capability: str
    account: Account | None
    reason: str


class CapabilityRouter:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._accounts: dict[str, list[Account]] = {}

    def register(self, capability: str, accounts: Iterable[Account]) -> None:
        if not capability:
            raise ValueError("capability name required")
        accs = list(accounts)
        if not accs:
            raise ValueError(f"no accounts for capability {capability!r}")
        self._accounts[capability] = accs

    def capabilities(self) -> list[str]:
        return sorted(self._accounts)

    def accounts(self, capability: str) -> list[Account]:
        return list(self._accounts.get(capability, []))

    def select(self, capability: str) -> Selection:
        now = self._clock()
        candidates = self._accounts.get(capability)
        if not candidates:
            return Selection(capability, None, "unknown capability")
        eligible = [
            a
            for a in candidates
            if a.healthy and a.cooldown_until <= now
            and (a.quota_remaining is None or a.quota_remaining > 0)
        ]
        if not eligible:
            return Selection(capability, None, "no eligible account")
        # Prefer lowest latency, then fewest failures, then first registered.
        chosen = min(
            eligible,
            key=lambda a: (a.latency_ms, a.consecutive_failures, candidates.index(a)),
        )
        return Selection(capability, chosen, "ok")

    def record_success(self, capability: str, alias: str, latency_ms: float = 0.0, quota_used: int = 1) -> None:
        acc = self._find(capability, alias)
        if acc is None:
            return
        acc.healthy = True
        acc.consecutive_failures = 0
        acc.latency_ms = latency_ms if latency_ms > 0 else acc.latency_ms
        if acc.quota_remaining is not None:
            acc.quota_remaining = max(0, acc.quota_remaining - quota_used)

    def record_failure(self, capability: str, alias: str, cooldown_s: float = 30.0) -> None:
        acc = self._find(capability, alias)
        if acc is None:
            return
        acc.consecutive_failures += 1
        if acc.consecutive_failures >= 3:
            acc.healthy = False
        acc.cooldown_until = self._clock() + cooldown_s

    def reset_health(self, capability: str, alias: str) -> None:
        acc = self._find(capability, alias)
        if acc is None:
            return
        acc.healthy = True
        acc.consecutive_failures = 0
        acc.cooldown_until = 0.0

    def _find(self, capability: str, alias: str) -> Account | None:
        for acc in self._accounts.get(capability, []):
            if acc.alias == alias:
                return acc
        return None
