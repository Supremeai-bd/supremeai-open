"""Persistent Learning Store — Sprint 2 of the Self-Evolution Zero-Cost plan.

Buffered, privacy-by-default telemetry pipeline that moves learning/telemetry
state out of RAM/SQLite and into the existing Supabase Postgres through the
proven PostgREST repository pattern (``database.supabase_client.SupabaseDB``).

Design invariants:
  * PRIVACY BY DEFAULT — no raw prompt/response content is ever recorded.
    Only hashes (``error_hash``), coarse categories (``error_class``,
    ``task_type``, ``feedback``) and numeric metrics leave the process.
    ``metadata`` dicts are recursively scrubbed of keys that look like raw
    content (prompt/response/content) before serialization.
  * BOUNDED MEMORY — the primary buffer is a ``deque(maxlen=1000)`` with
    drop-oldest semantics (overflow counted + DEBUG-logged), and writer
    failures park events in a bounded ``deque(maxlen=5000)`` fallback.
  * NEVER BLOCKS THE CALLER — ``record_event`` only enqueues (no network,
    no awaits); the network write happens on a single background flush task
    (every 5s or when the buffer holds >= 50 events).
  * DEGRADED MODE SAFE — the writer (PostgREST ``service_client``) is
    resolved lazily inside ``flush``; this module imports cleanly with no
    network. When the writer is unavailable, events stay buffered,
    ``get_stats()["db_ok"]`` flips False and a CRITICAL is logged once per
    minute. PostgREST is used — never SQLAlchemy.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
import uuid
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

try:  # house logger; fall back to stdlib so this module has zero heavy deps
    from core.logging_config import logger  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - only when logging_config is broken
    logger = logging.getLogger("core.learning.store")

__all__ = [
    "ALLOWED_FEEDBACK_TYPES",
    "LEARNING_EVENT_FIELDS",
    "LearningEvent",
    "LearningStore",
    "aggregate_provider_metrics",
    "get_learning_store",
    "record_feedback",
    "record_llm_event",
    "sanitize_metadata",
]

# Categorical feedback tags (mirrors feedback_events CHECK constraint in DDL).
ALLOWED_FEEDBACK_TYPES = frozenset(
    {"thumbs_up", "thumbs_down", "retry", "regenerate", "follow_up", "correction"}
)

# Fixed serialization whitelist for LearningEvent. Any new field MUST be
# added here AND to the learning_events DDL — and must NOT be raw content.
LEARNING_EVENT_FIELDS: tuple[str, ...] = (
    "event_id",
    "ts",
    "tenant_id",
    "session_id",
    "request_id",
    "task_type",
    "skill_id",
    "provider",
    "model",
    "success",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "estimated_cost",
    "actual_cost",
    "error_class",
    "error_hash",
    "cache_hit",
    "feedback",
)

# Privacy: metadata is an explicit allowlist. Unknown fields are discarded before
# serialization so raw user content cannot reach Postgres under an unexpected key.
_ALLOWED_METADATA_KEYS = frozenset(
    {
        "route",
        "provider",
        "model",
        "region",
        "cache_status",
        "error_class",
        "latency_bucket",
        "task_category",
        "feature_flag",
        "feedback_type",
        "weight",
    }
)

_MAX_METADATA_LIST_ITEMS = 20
_MAX_COERCED_STR = 200
_MAX_METADATA_DEPTH = 3
_FORBIDDEN_METADATA_MARKERS = ("prompt", "response", "content")


def sanitize_metadata(metadata: Mapping[str, Any] | None, _depth: int = 0) -> dict[str, Any]:
    """Return a privacy-safe, bounded copy of ``metadata``.

    Drops any key whose name contains 'prompt', 'response' or 'content'
    (case-insensitive) at any nesting depth, bounds list sizes and coerces
    exotic values to short strings. Never mutates the input.
    """
    if not isinstance(metadata, Mapping):
        return {}
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        key_str = str(key)
        key_lower = key_str.lower()
        if any(marker in key_lower for marker in _FORBIDDEN_METADATA_MARKERS):
            continue  # privacy: never serialize prompt, response or content
        if isinstance(value, Mapping):
            if _depth < _MAX_METADATA_DEPTH:
                clean[key_str] = sanitize_metadata(value, _depth + 1)
            continue
        if (
            _depth == 0
            and not isinstance(value, (list, tuple))
            and key_lower not in _ALLOWED_METADATA_KEYS
        ):
            continue  # only known operational metadata or structured items allowed at top level
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[key_str] = value
        elif isinstance(value, (list, tuple)):
            clean[key_str] = [
                sanitize_metadata(v, _depth + 1) if isinstance(v, Mapping) else v
                for v in list(value)[:_MAX_METADATA_LIST_ITEMS]
            ]
        else:
            clean[key_str] = str(value)[:_MAX_COERCED_STR]
    return clean


@dataclass
class LearningEvent:
    """One privacy-safe learning/telemetry observation.

    ``event_id`` (uuid4) and ``ts`` (UTC ISO-8601) are auto-generated. This
    dataclass intentionally has NO fields for raw prompt/response text.
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    tenant_id: str | None = None
    session_id: str | None = None
    request_id: str | None = None
    task_type: str | None = None
    skill_id: str | None = None
    provider: str | None = None
    model: str | None = None
    success: bool | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None
    actual_cost: float | None = None
    error_class: str | None = None
    error_hash: str | None = None
    cache_hit: bool = False
    # Categorical feedback tag (thumbs_up / thumbs_down / ...), NEVER user text.
    feedback: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a PostgREST row — whitelisted keys + scrubbed metadata."""
        row: dict[str, Any] = {}
        for name in LEARNING_EVENT_FIELDS:
            value = getattr(self, name)
            if value is None:
                continue
            row[name] = value
        row["metadata"] = sanitize_metadata(self.metadata)
        return row


def _percentile(sorted_values: list[int], pct: float) -> int | None:
    """Linear-interpolated percentile over an ascending list (None if empty)."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return int(sorted_values[lo])
    frac = rank - lo
    return int(round(sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac))


def aggregate_provider_metrics(
    events: Iterable[dict[str, Any]] | None, window_start: str
) -> list[dict[str, Any]]:
    """Pure function: aggregate learning_events dicts into provider_metrics rows.

    Groups by (provider, model) and computes requests/successes/failures,
    rate_limited (from ``error_class == "rate_limit"``), latency p50/p95 and
    summed estimated/actual cost — matching the provider_metrics DDL.
    """
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events or []:
        if not isinstance(event, dict):
            continue
        provider = event.get("provider")
        model = event.get("model")
        if not provider or not model:
            continue
        key = (str(provider), str(model))
        group = groups.setdefault(
            key,
            {
                "requests": 0,
                "successes": 0,
                "failures": 0,
                "rate_limited": 0,
                "latencies": [],
                "estimated_cost": 0.0,
                "actual_cost": 0.0,
            },
        )
        group["requests"] += 1
        success = event.get("success")
        if success is True:
            group["successes"] += 1
        elif success is False:
            group["failures"] += 1
            error_class = str(event.get("error_class") or "").strip().lower()
            if error_class == "rate_limit":
                group["rate_limited"] += 1
        latency = event.get("latency_ms")
        if isinstance(latency, (int, float)) and latency >= 0:
            group["latencies"].append(int(latency))
        estimated = event.get("estimated_cost")
        if isinstance(estimated, (int, float)):
            group["estimated_cost"] += float(estimated)
        actual = event.get("actual_cost")
        if isinstance(actual, (int, float)):
            group["actual_cost"] += float(actual)

    rows: list[dict[str, Any]] = []
    for (provider, model), group in sorted(groups.items()):
        latencies = sorted(group["latencies"])
        rows.append(
            {
                "window_start": window_start,
                "provider": provider,
                "model": model,
                "requests": group["requests"],
                "successes": group["successes"],
                "failures": group["failures"],
                "rate_limited": group["rate_limited"],
                "latency_p50_ms": _percentile(latencies, 50),
                "latency_p95_ms": _percentile(latencies, 95),
                "estimated_cost": round(group["estimated_cost"], 6),
                "actual_cost": round(group["actual_cost"], 6),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
    return rows


def _get_db() -> Any | None:
    """Lazily resolve the PostgREST writer (``SupabaseDB`` singleton).

    The import happens HERE, not at module import, so this module loads with
    zero network/config side effects. Returns None when unavailable; failures
    are cached-free (retried on the next flush).
    """
    try:
        from database.supabase_client import db as supabase_db

        return supabase_db
    except Exception as exc:  # pragma: no cover - import failure path
        logger.debug(f"learning store writer unavailable: {exc}")
        return None


class LearningStore:
    """Bounded in-process buffer -> background flush -> PostgREST writer."""

    def __init__(
        self,
        *,
        max_buffer: int = 1000,
        flush_interval: float = 5.0,
        flush_threshold: int = 50,
        fallback_max: int = 5000,
        max_batch: int = 500,
        drop_log_every: int = 100,
    ) -> None:
        self._buffer: deque[dict[str, Any]] = deque(maxlen=max(1, int(max_buffer)))
        self._fallback: deque[dict[str, Any]] = deque(maxlen=max(1, int(fallback_max)))
        self._flush_interval = float(flush_interval)
        self._flush_threshold = max(1, int(flush_threshold))
        self._max_batch = max(1, int(max_batch))
        self._drop_log_every = max(1, int(drop_log_every))
        self._lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._stopped = False
        self._dropped = 0
        self._flushed = 0
        self._last_flush_at: str | None = None
        self._db_ok = True
        self._last_writer_failure_log = 0.0
        self._last_critical_log = 0.0
        # Event-loop the async primitives are currently bound to. asyncio.Lock/
        # Event objects are loop-bound: if the singleton outlives its loop
        # (pytest per-test loops, app reloads), they must be RECREATED on the
        # new loop or every operation raises "bound to a different event loop".
        self._loop: asyncio.AbstractEventLoop | None = None

    def _ensure_loop_primitives(self) -> None:
        """Recreate loop-bound primitives when the running loop has changed."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no running loop — sync context; keep current primitives
        if self._loop is not loop:
            self._loop = loop
            self._lock = asyncio.Lock()
            self._wake = asyncio.Event()

    # ------------------------------------------------------------------ API

    def record_event(self, event: LearningEvent | dict[str, Any]) -> bool:
        """Fast, never-raising enqueue. No network, no awaits."""
        try:
            if isinstance(event, LearningEvent):
                payload = event.to_dict()
            elif isinstance(event, dict):
                payload = {
                    k: v for k, v in event.items() if k in LEARNING_EVENT_FIELDS or k == "metadata"
                }
                payload["metadata"] = sanitize_metadata(payload.get("metadata"))
            else:
                return False
            if len(self._buffer) == self._buffer.maxlen:
                # deque append is about to silently evict the oldest event.
                self._dropped += 1
                if self._dropped % self._drop_log_every == 1:
                    logger.debug(
                        f"LearningStore buffer full; drop-oldest engaged "
                        f"(dropped={self._dropped}, queued={len(self._buffer)})"
                    )
            self._buffer.append(payload)
            if len(self._buffer) >= self._flush_threshold:
                try:
                    self._wake.set()
                except Exception as wake_exc:  # pragma: no cover - cross-thread edge
                    logger.debug(f"LearningStore wake signal failed: {wake_exc}")
            return True
        except Exception as exc:  # record_event NEVER raises
            logger.debug(f"record_event failed: {exc}")
            return False

    def record_llm_event(
        self,
        provider: str | None,
        model: str | None,
        task_type: str | None = None,
        success: bool = True,
        latency_ms: int | None = None,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        estimated_cost: float | None = None,
        actual_cost: float | None = None,
        error_class: str | None = None,
        error_hash: str | None = None,
        cache_hit: bool = False,
        request_id: str | None = None,
        session_id: str | None = None,
        tenant_id: str | None = None,
        skill_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Convenience shim for LLM telemetry (matches track_llm_call fields)."""
        return self.record_event(
            LearningEvent(
                provider=provider,
                model=model,
                task_type=task_type,
                success=success,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost=estimated_cost,
                actual_cost=actual_cost,
                error_class=error_class,
                error_hash=error_hash,
                cache_hit=cache_hit,
                request_id=request_id,
                session_id=session_id,
                tenant_id=tenant_id,
                skill_id=skill_id,
                metadata=dict(metadata or {}),
            )
        )

    def record_feedback(
        self,
        feedback_type: str,
        *,
        task_type: str | None = None,
        skill_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        session_id: str | None = None,
        request_id: str | None = None,
        tenant_id: str | None = None,
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Record a categorical feedback event; rejects unknown types."""
        if feedback_type not in ALLOWED_FEEDBACK_TYPES:
            logger.warning(
                f"record_feedback rejected invalid feedback_type: {feedback_type!r} "
                f"(allowed: {sorted(ALLOWED_FEEDBACK_TYPES)})"
            )
            return False
        enriched = dict(metadata or {})
        enriched.setdefault("feedback_type", feedback_type)
        try:
            enriched.setdefault("weight", float(weight))
        except (TypeError, ValueError) as weight_err:
            logger.debug(f"Invalid feedback weight {weight!r}: {weight_err}")
        return self.record_event(
            LearningEvent(
                feedback=feedback_type,
                task_type=task_type,
                skill_id=skill_id,
                provider=provider,
                model=model,
                session_id=session_id,
                request_id=request_id,
                tenant_id=tenant_id,
                metadata=enriched,
            )
        )

    async def flush(self) -> int:
        """Drain buffer (+replay fallback) into the writer. Returns rows flushed."""
        self._ensure_loop_primitives()
        async with self._lock:
            batch: list[dict[str, Any]] = []
            while self._fallback and len(batch) < self._max_batch:
                batch.append(self._fallback.popleft())
            while self._buffer and len(batch) < self._max_batch:
                batch.append(self._buffer.popleft())
            if not batch:
                return 0

            db = _get_db()
            if db is None:
                self._stash_failed_batch(batch, unavailable=True)
                return 0
            try:
                result = db.append_learning_events(batch)
            except Exception as exc:
                logger.debug(f"learning writer raised: {exc}")
                self._stash_failed_batch(batch, unavailable=False)
                return 0
            if result is None or result is False:
                # PostgREST retry decorator exhausted → graceful None/False.
                self._stash_failed_batch(batch, unavailable=False)
                return 0
            try:
                inserted = len(batch) if isinstance(result, bool) else int(result)
            except (TypeError, ValueError):
                inserted = 0
            if inserted <= 0:
                self._stash_failed_batch(batch, unavailable=False)
                return 0
            self._flushed += inserted
            self._db_ok = True
            self._last_flush_at = datetime.now(UTC).isoformat()
            if inserted < len(batch):
                # Preserve the unwritten tail for a later retry. The repository
                # returns the number of rows accepted in input order.
                remainder = batch[inserted:]
                for item in reversed(remainder):
                    if len(self._fallback) == self._fallback.maxlen:
                        self._dropped += 1
                    self._fallback.appendleft(item)
                logger.warning(
                    f"LearningStore partial flush: {inserted}/{len(batch)} rows "
                    f"written; {len(remainder)} rows requeued for retry"
                )
            return inserted

    def get_stats(self) -> dict[str, Any]:
        return {
            "queued": len(self._buffer),
            "dropped": self._dropped,
            "flushed": self._flushed,
            "last_flush_at": self._last_flush_at,
            "db_ok": self._db_ok,
            "fallback": len(self._fallback),
        }

    # ------------------------------------------------------- lifecycle

    def start(self) -> None:
        """Start the background flush task (no-op without a running loop)."""
        self._ensure_loop_primitives()
        if self._task is not None and not self._task.done():
            # Abandon a task still pending on a DIFFERENT (likely closed) loop —
            # it can never wake again; recreate on the current loop instead.
            try:
                if self._task.get_loop() is not asyncio.get_running_loop():
                    self._task = None
                else:
                    return
            except RuntimeError:  # no running loop
                return
        self._stopped = False
        try:
            self._task = asyncio.get_running_loop().create_task(self._flush_loop())
        except RuntimeError:
            logger.debug("LearningStore.start() without running event loop; flush stays manual")
            self._task = None

    async def stop(self) -> None:
        """Stop the background task and flush remaining events best-effort."""
        self._stopped = True
        self._ensure_loop_primitives()
        try:
            self._wake.set()
        except Exception as wake_err:
            logger.debug(f"LearningStore wake signal during stop failed: {wake_err}")
        task = self._task
        self._task = None
        for _ in range(10):  # bounded: 10 * max_batch covers fallback capacity
            if not self._buffer and not self._fallback:
                break
            try:
                await self.flush()
            except Exception:
                break
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.debug("LearningStore task cancelled successfully during stop")
            except Exception as task_err:  # pragma: no cover
                logger.debug(f"LearningStore task stop encountered error: {task_err}")

    # ------------------------------------------------------- internals

    async def _flush_loop(self) -> None:
        """Flush every ``flush_interval`` seconds or when threshold is hit."""
        try:
            while not self._stopped:
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=self._flush_interval)
                except TimeoutError:
                    logger.debug(
                        "LearningStore flush loop wait timeout (proceeding with scheduled flush)"
                    )
                self._wake.clear()
                if self._stopped:
                    break
                try:
                    await self.flush()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # keep the loop alive no matter what
                    logger.debug(f"learning flush cycle error: {exc}")
        except asyncio.CancelledError:
            raise

    def _stash_failed_batch(self, batch: list[dict[str, Any]], *, unavailable: bool) -> None:
        """Park events in the bounded fallback deque; rate-limit the log noise."""
        for item in batch:
            if len(self._fallback) == self._fallback.maxlen:
                self._dropped += 1
            self._fallback.append(item)
        self._db_ok = False
        now = time.monotonic()
        if unavailable:
            if now - self._last_critical_log >= 60.0:
                logger.critical(
                    "LearningStore: PostgREST writer unavailable — events buffered "
                    f"in fallback ({len(self._fallback)} parked, "
                    f"{self._dropped} dropped total). Will retry on next flush."
                )
                self._last_critical_log = now
        elif now - self._last_writer_failure_log >= 60.0:
            logger.warning(
                "LearningStore: writer flush failed — events kept in fallback "
                f"({len(self._fallback)} parked). Will retry on next flush."
            )
            self._last_writer_failure_log = now


_learning_store: LearningStore | None = None


def get_learning_store() -> LearningStore:
    """Process-wide LearningStore singleton (created lazily, never started)."""
    global _learning_store
    if _learning_store is None:
        _learning_store = LearningStore()
    return _learning_store


def record_llm_event(
    provider: str | None,
    model: str | None,
    task_type: str | None = None,
    success: bool = True,
    latency_ms: int | None = None,
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    estimated_cost: float | None = None,
    actual_cost: float | None = None,
    error_class: str | None = None,
    error_hash: str | None = None,
    cache_hit: bool = False,
    request_id: str | None = None,
    session_id: str | None = None,
    tenant_id: str | None = None,
    skill_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Module-level convenience: record an LLM call event on the singleton.

    NEVER raises and NEVER touches the network (fast enqueue only) — safe to
    call from any request path. Gateway wiring itself belongs to a later sprint.
    """
    return get_learning_store().record_llm_event(
        provider,
        model,
        task_type,
        success,
        latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=estimated_cost,
        actual_cost=actual_cost,
        error_class=error_class,
        error_hash=error_hash,
        cache_hit=cache_hit,
        request_id=request_id,
        session_id=session_id,
        tenant_id=tenant_id,
        skill_id=skill_id,
        metadata=metadata,
    )


def record_feedback(
    feedback_type: str,
    *,
    task_type: str | None = None,
    skill_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    tenant_id: str | None = None,
    weight: float = 1.0,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Module-level convenience: validate + record a categorical feedback event.

    Returns False (never raises) for feedback types outside ALLOWED_FEEDBACK_TYPES.
    """
    return get_learning_store().record_feedback(
        feedback_type,
        task_type=task_type,
        skill_id=skill_id,
        provider=provider,
        model=model,
        session_id=session_id,
        request_id=request_id,
        tenant_id=tenant_id,
        weight=weight,
        metadata=metadata,
    )
