"""gateway/circuit_breaker.py — Circuit breaker for degraded upstream LLM APIs (#2228).

Stdlib-only. Tracks per-provider state (closed/open/half-open) based on
consecutive failures. When a provider trips the threshold it is skipped for
a cooldown window, then probed once (half-open) before re-closing.

States:
  CLOSED    — normal operation; failures increment counter.
  OPEN      — provider skipped; after cooldown transitions to HALF_OPEN.
  HALF_OPEN — one probe allowed; success -> CLOSED, failure -> OPEN.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class _ProviderState:
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure: float = 0.0
    opened_at: float = 0.0


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_s: float = 30.0,
        half_open_max: int = 1,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self.half_open_max = half_open_max
        self._states: dict[str, _ProviderState] = {}
        self._half_open_in_flight: dict[str, int] = {}
        self._lock = Lock()

    def _get(self, provider: str) -> _ProviderState:
        if provider not in self._states:
            self._states[provider] = _ProviderState()
        return self._states[provider]

    def allow(self, provider: str) -> bool:
        """Return True if a request to this provider should be attempted."""
        with self._lock:
            st = self._get(provider)
            now = time.monotonic()
            if st.state == CircuitState.CLOSED:
                return True
            if st.state == CircuitState.OPEN:
                if now - st.opened_at >= self.cooldown_s:
                    st.state = CircuitState.HALF_OPEN
                    self._half_open_in_flight[provider] = 0
                    # fall through
                else:
                    return False
            if st.state == CircuitState.HALF_OPEN:
                if self._half_open_in_flight.get(provider, 0) < self.half_open_max:
                    self._half_open_in_flight[provider] = self._half_open_in_flight.get(provider, 0) + 1
                    return True
                return False
            return True

    def record_success(self, provider: str) -> None:
        with self._lock:
            st = self._get(provider)
            st.state = CircuitState.CLOSED
            st.failure_count = 0
            self._half_open_in_flight.pop(provider, None)

    def record_failure(self, provider: str) -> None:
        with self._lock:
            st = self._get(provider)
            st.failure_count += 1
            st.last_failure = time.monotonic()
            if st.state == CircuitState.HALF_OPEN:
                st.state = CircuitState.OPEN
                st.opened_at = time.monotonic()
                self._half_open_in_flight.pop(provider, None)
            elif st.failure_count >= self.failure_threshold:
                st.state = CircuitState.OPEN
                st.opened_at = time.monotonic()

    def state_of(self, provider: str) -> CircuitState:
        with self._lock:
            return self._get(provider).state

    def reset(self, provider: str | None = None) -> None:
        with self._lock:
            if provider is None:
                self._states.clear()
                self._half_open_in_flight.clear()
            else:
                self._states.pop(provider, None)
                self._half_open_in_flight.pop(provider, None)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {k: {"state": v.state.value, "failures": v.failure_count} for k, v in self._states.items()}


# Module-level singleton (configurable via env at import not needed; callers may
# instantiate their own).
default_breaker = CircuitBreaker()


def allow(provider: str) -> bool:
    return default_breaker.allow(provider)


def record_success(provider: str) -> None:
    default_breaker.record_success(provider)


def record_failure(provider: str) -> None:
    default_breaker.record_failure(provider)
