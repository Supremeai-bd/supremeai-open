from __future__ import annotations

import logging

# backend/core/llm/telemetry.py
"""LLM Call Telemetry — structured logging + durable learning event for every gateway call.

Two sinks per call:
1. JSON-log line (historical behavior, unchanged): timestamp, session_id,
   provider, model, task_type, latency_ms, tokens, cost, success.
2. Durable learning event (Sprint 3 of the Self-Evolution Zero-Cost plan):
   the same record is enqueued on the process-wide LearningStore
   (``core.learning.store``), which flushes to Supabase Postgres
   (``learning_events``) via PostgREST. The durable sink is
   best-effort + never-raising: telemetry failures must NEVER replace the
   outcome of the actual LLM call.

This is the data source for the self-evolving routing policies.
"""


import contextlib
import json
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

try:
    from core.logging_config import logger
except ImportError:
    from core.logging_config import logger

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def classify_llm_error(exc: BaseException | None) -> str:
    """Map an exception to a coarse, privacy-safe error class.

    Classes match the ``error_class`` vocabulary used by LearningStore
    aggregation (``rate_limit`` is counted into ``provider_metrics.rate_limited``).
    """
    if exc is None:
        return ""
    text = str(exc).lower()
    status = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    if status == 429 or "rate limit" in text or "429" in text or "quota" in text:
        return "rate_limit"
    if status in (401, 403) or "unauthorized" in text or "forbidden" in text or "api key" in text:
        return "auth"
    if status is not None:
        try:
            if int(status) >= 500:
                return "server_error"
        except (TypeError, ValueError) as status_err:
            logger.debug(f"Failed to parse HTTP status {status!r}: {status_err}")
    if re.search(r"\b5\d{2}\b", text):
        return "server_error"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "connection" in text or "network" in text or "unreachable" in text or "dns" in text:
        return "network"
    if "cancel" in text:
        return "cancelled"
    return "unknown"


def _error_fingerprint(exc: BaseException | None) -> str:
    """Best-effort normalized error fingerprint (never raises)."""
    if exc is None:
        return ""
    try:
        from core.failure_fingerprint import make_fingerprint

        return make_fingerprint(exc)
    except Exception:
        return ""


@dataclass
class LLMCallRecord:
    """Immutable record of a single LLM gateway call."""

    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    session_id: str = ""
    provider: str = ""
    model: str = ""
    task_type: str = "general"
    latency_ms: float = 0.0
    tokens_prompt: int | None = None
    tokens_completion: int | None = None
    cost_usd: float = 0.0
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # ── Sprint 3 learning-loop fields (durable learning_events columns) ──
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    cache_hit: bool = False
    # attempts consumed before this call within the same request (0 = first)
    fallback_count: int = 0
    # 429 backoff retries that succeeded for this same model
    retry_count: int = 0
    rate_limited: bool = False
    # estimated tokens from the pre-call estimator (calibration baseline)
    estimated_tokens: int | None = None
    error_class: str | None = None
    error_hash: str | None = None

    def to_log_line(self) -> str:
        # বাংলা মন্তব্য: default=str — provider থেকে আসা কোনো field (যেমন usage.prompt_tokens)
        # যদি plain int/str/float না হয়ে কোনো non-JSON-native object হয়, json.dumps যেন
        # crash না করে বরং str() রূপান্তর করে log করে। টেলিমেট্রি সিরিয়ালাইজেশন কখনো
        # আসল LLM কলের ফলাফলকে mask/replace করবে না — এটা শুধু একটা log line, critical path না।
        return json.dumps(asdict(self), default=str)

    def to_learning_event_fields(self) -> dict[str, Any]:
        """Project the record onto the privacy-safe learning_events schema.

        NEVER includes raw prompt/response content — only identifiers,
        categories and metrics. ``record`` is only called for REAL provider
        calls (cache hits bypass the gateway loop and record separately).
        """
        return {
            "provider": self.provider,
            "model": self.model,
            "task_type": self.task_type,
            "success": self.success,
            "latency_ms": int(self.latency_ms) if self.latency_ms else None,
            "input_tokens": self.tokens_prompt,
            "output_tokens": self.tokens_completion,
            "actual_cost": self.cost_usd or None,
            "error_class": self.error_class,
            "error_hash": self.error_hash,
            "cache_hit": self.cache_hit,
            "request_id": self.request_id,
            "session_id": self.session_id or None,
            "metadata": {
                "fallback_count": self.fallback_count,
                "retry_count": self.retry_count,
                "rate_limited": self.rate_limited,
                "estimated_tokens": self.estimated_tokens,
                "estimated_cost": None,  # filled by calibration-aware callers
            },
        }


def _record_durable(record: LLMCallRecord) -> None:
    """Best-effort durable sink: enqueue the record on the LearningStore.

    NEVER raises — the durable pipeline must not be able to affect the
    request path (same contract as the log-line sink above).
    """
    try:
        from core.learning import record_llm_event as _record_llm_event

        fields = record.to_learning_event_fields()
        metadata = fields.pop("metadata", {})
        _record_llm_event(
            provider=fields.get("provider") or None,
            model=fields.get("model") or None,
            task_type=fields.get("task_type"),
            success=bool(fields.get("success", False)),
            latency_ms=fields.get("latency_ms"),
            input_tokens=fields.get("input_tokens"),
            output_tokens=fields.get("output_tokens"),
            actual_cost=fields.get("actual_cost"),
            error_class=fields.get("error_class") or None,
            error_hash=fields.get("error_hash") or None,
            cache_hit=bool(fields.get("cache_hit", False)),
            request_id=fields.get("request_id"),
            session_id=fields.get("session_id"),
            metadata=metadata,
        )
        # Token calibration (Sprint 5, bounded EMA): actual-vs-estimated signal
        if record.tokens_prompt and record.estimated_tokens:
            with contextlib.suppress(Exception):
                from core.learning.calibration import update_ratio

                update_ratio(
                    record.provider,
                    record.model,
                    estimated=record.estimated_tokens,
                    actual=int(record.tokens_prompt) + int(record.tokens_completion or 0),
                )
    except Exception as exc:  # pragma: no cover - durability must never raise
        logger.debug(f"[llm_telemetry] durable sink skipped: {exc}")


def _ensure_store_started() -> None:
    """Start the LearningStore flush task once, from inside a running loop."""
    try:
        from core.learning import get_learning_store

        store = get_learning_store()
        if store._task is None or store._task.done():
            store.start()
    except Exception as exc:  # best-effort store start — telemetry never blocks LLM call
        import logging

        logging.getLogger(__name__).warning(
            "[telemetry] LearningStore start failed (best-effort): %s", exc
        )


@asynccontextmanager
async def track_llm_call(
    *,
    session_id: str = "",
    provider: str = "",
    model: str = "",
    task_type: str = "general",
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[LLMCallRecord]:
    """Context manager that times an LLM call and emits a structured log + durable event."""
    record = LLMCallRecord(
        session_id=session_id,
        provider=provider,
        model=model,
        task_type=task_type,
        metadata=metadata or {},
    )
    # Merge caller-supplied loop context (fallback_count, retry_count, …)
    if metadata:
        for key in ("fallback_count", "retry_count", "estimated_tokens", "request_id"):
            value = metadata.get(key)
            if value is not None and hasattr(record, key):
                try:
                    setattr(record, key, value)
                except Exception as set_err:
                    logger.debug(f"Failed to set telemetry record attribute {key!r}: {set_err}")
    _ensure_store_started()
    t0 = time.perf_counter()
    try:
        yield record
        record.success = True
    except Exception as exc:
        record.success = False
        record.error = str(exc)[:500]
        record.error_class = classify_llm_error(exc)
        record.error_hash = _error_fingerprint(exc)
        raise
    finally:
        record.latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        # বাংলা মন্তব্য: telemetry logging সম্পূর্ণ best-effort — এই ব্লকের কোনো ব্যর্থতা
        # (log_line সিরিয়ালাইজেশন, logger backend সমস্যা, ইত্যাদি) কখনোই context manager-এর
        # বাইরে propagate করবে না, কারণ সেটা করলে আসল yield-এর ফলাফল/exception-কে replace
        # করে ফেলবে (আগের বাগ: except ব্লক একই ব্যর্থ to_log_line() আবার কল করত, যা আবার
        # raise করে সফল LLM completion-কে "ALL_MODELS_FAILED"-এর মতো দেখাত)।
        try:
            log_line = record.to_log_line()
        except Exception as log_exc:
            logger.warning(f"[llm_telemetry] failed to serialize call record: {log_exc}")
        else:
            with contextlib.suppress(Exception):
                logger.bind(llm_telemetry=log_line).info("llm_call")
        # Sprint 3: durable learning event — same best-effort contract: even a
        # broken sink (or a patched-out sink in tests) can never replace the
        # outcome of the actual LLM call (see historical bug above).
        try:
            _record_durable(record)
        except Exception as sink_exc:
            logger.debug(f"[llm_telemetry] durable sink raised: {sink_exc}")
