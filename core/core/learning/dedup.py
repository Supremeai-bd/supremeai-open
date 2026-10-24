"""Single-flight request deduplication — Sprint 5 (plan §13.3).

For identical in-flight LLM requests:

    Request A -> LLM
    Request B -> waits for A
    Request C -> waits for A

Safety contract (plan §13.3: "bounded timeouts and cancellation handling"):
  * bounded map (maxsize) — overflow just executes normally
  * followers wait at most ``timeout`` seconds; on timeout they execute
    normally themselves (never fail because of coalescing)
  * if the leader's task is cancelled, followers execute normally
  * responses are returned as shallow copies so followers mutating the dict
    cannot corrupt the leader's result
  * pure asyncio primitives; every failure mode degrades to "execute
    normally" — dedup can never reduce availability.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import time
from collections import OrderedDict
from typing import Any

__all__ = [
    "DedupResult",
    "RequestCoalescer",
    "dedup_key",
    "get_request_coalescer",
    "request_dedup_enabled",
]

DEFAULT_FOLLOWER_TIMEOUT = 60.0
DEFAULT_MAX_INFLIGHT = 100


def request_dedup_enabled() -> bool:
    return (os.getenv("ENABLE_REQUEST_DEDUP", "") or "").strip().lower() == "true"


def dedup_key(model: str, task_type: str, messages_payload: Any) -> str:
    """Stable key over (model, task_type, normalized messages). No content stored."""
    try:
        blob = json.dumps(messages_payload, sort_keys=True, default=str)
    except Exception:
        blob = str(messages_payload)
    digest = hashlib.sha256(f"{model}|{task_type}|{blob}".encode()).hexdigest()
    return digest  # hash only — never persists raw content


class DedupResult:
    __slots__ = ("created_at", "event", "future", "response")

    def __init__(self) -> None:
        self.event = asyncio.Event()
        self.response: dict[str, Any] | None = None
        self.future: asyncio.Future | None = None
        self.created_at = time.monotonic()


class RequestCoalescer:
    """Bounded in-flight dedup: one leader executes, identical followers wait."""

    def __init__(
        self,
        *,
        max_inflight: int = DEFAULT_MAX_INFLIGHT,
        follower_timeout: float = DEFAULT_FOLLOWER_TIMEOUT,
    ):
        self._inflight: OrderedDict[str, DedupResult] = OrderedDict()
        self._max_inflight = max(1, int(max_inflight))
        self._follower_timeout = float(follower_timeout)

    # ------------------------------------------------------------- leader path
    def try_claim(self, key: str) -> DedupResult | None:
        """Return the existing flight to WAIT on, or None if this call leads.

        The caller that gets None must execute the request itself and finish
        with :meth:`publish_success` / :meth:`publish_failure`.
        """
        entry = self._inflight.get(key)
        if entry is not None:
            if time.monotonic() - entry.created_at > self._follower_timeout:
                self._inflight.pop(key, None)  # stale leader; become the leader
            else:
                self._inflight.move_to_end(key)
                return entry
        entry = DedupResult()
        self._inflight[key] = entry
        while len(self._inflight) > self._max_inflight:
            self._inflight.popitem(last=False)  # evict oldest (bounded map)
        return None

    def publish_success(self, key: str, response: dict[str, Any]) -> None:
        entry = self._inflight.pop(key, None)
        if entry is None:
            return
        entry.response = response
        entry.event.set()

    def publish_failure(self, key: str, exc: BaseException) -> None:
        entry = self._inflight.pop(key, None)
        if entry is None:
            return
        entry.future = asyncio.get_running_loop().create_future()
        if not entry.future.done():
            entry.future.set_exception(exc)
        entry.event.set()

    # ------------------------------------------------------------ follower path
    async def wait_for_leader(self, entry: DedupResult) -> dict[str, Any] | None:
        """Wait for the leader, bounded. None → follower must execute itself."""
        try:
            await asyncio.wait_for(entry.event.wait(), timeout=self._follower_timeout)
        except TimeoutError:
            return None  # bounded wait: execute normally
        except asyncio.CancelledError:
            raise
        if (
            entry.future is not None
            and entry.future.done()
            and entry.future.exception() is not None
        ):
            return None  # leader failed → follower executes normally
        if entry.response is None:
            return None
        try:
            return copy.copy(entry.response)  # shallow copy: isolate followers
        except Exception:
            return dict(entry.response)

    # ------------------------------------------------------------- observability
    def get_stats(self) -> dict[str, Any]:
        return {
            "in_flight": len(self._inflight),
            "max_inflight": self._max_inflight,
            "follower_timeout_s": self._follower_timeout,
        }


_coalescer: RequestCoalescer | None = None


def get_request_coalescer() -> RequestCoalescer:
    global _coalescer
    if _coalescer is None:
        _coalescer = RequestCoalescer()
    return _coalescer
