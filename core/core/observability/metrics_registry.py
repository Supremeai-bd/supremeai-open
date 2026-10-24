"""Neutral metrics registry — shared request/latency/error instrumentation.

Issue #683 Section 1 (inward layer violation): ``core/observability/
observability_middleware.py`` imported ``record_request`` /
``record_error`` / ``record_request_duration`` from ``api.routes.metrics``
— a forbidden core → api import. The recording functions (plus the
Prometheus collectors and the latency-history engine they feed) are pure
instrumentation with no routing concerns, so they live here in
``core/observability/``; the api layer (``api/routes/metrics.py``) imports
them from this module — the allowed api → core direction — and re-exports
them for backwards compatibility.

Single-source guarantee: this module owns the one ``metrics_engine``
singleton and the one set of Prometheus collectors. ``api.routes.metrics``
re-exports (it does not copy) so ``patch("api.routes.metrics.metrics_engine")``
in tests and the lazy ``from api.routes.metrics import metrics_engine`` in
core/maintenance_pipeline.py keep resolving to the same objects.
"""

from __future__ import annotations

import threading
import time as _time
from collections import deque
from typing import Any

from core.config import settings
from core.logging_config import logger

# শেয়ার্ড ইউটিলিটি — Firestore ইনিশিয়ালাইজেশন কেন্দ্রীভূত
from utils.firestore_helpers import get_firestore_db


class SupremeMetricsEngine:
    def __init__(self):
        # রিফ্যাক্টর: সরাসরি firestore.Client() এর বদলে শেয়ার্ড হেল্পার ব্যবহার
        self.db = get_firestore_db()
        # বাংলা মন্তব্য: P95 ল্যাটেন্সি রিয়াল-টাইম ট্র্যাকিং করার জন্য একটি সার্কুলার বাফারের মতো লিস্ট।
        # এটি মেমোরিতে শেষ ১০০০টি রিকোয়েস্টের ল্যাটেন্সি ট্র্যাক করে।
        self.latency_history: list[float] = []

    async def calculate_system_roi(self) -> dict[str, Any]:
        """সিস্টেমের সেভ করা কস্ট এবং ব্লক করা অ্যাটাকের রিয়াল-টাইম ম্যাট্রিক্স ক্যালকুলেটর"""
        try:
            # ১. সিমান্টিক ক্যাশ হিট কাউন্ট (Gemini/OpenRouter Token Saved)
            cache_ref = self.db.collection("supreme_semantic_cache")
            cache_docs = cache_ref.stream()

            total_saved_requests = 0
            # এভারেজ এন্টারপ্রাইজ এলএলএম কল কস্ট (ধরে নিলাম $0.015 প্রতি ১০০০ টোকেন ও রিকোয়েস্ট)
            ESTIMATED_COST_PER_REQUEST = 0.015

            for _ in cache_docs:
                total_saved_requests += 1

            total_billing_saved = total_saved_requests * ESTIMATED_COST_PER_REQUEST

            # ২. আইডেমপোটেন্সি ইঞ্জিন দ্বারা ব্লক করা ডাবল-সাবমিশন এবং ক্র্যাশ কাউন্ট
            lock_ref = self.db.collection("idempotency_locks")
            # শুধুমাত্র সকসেসফুলি ব্লক হওয়া ডুপ্লিকেট রিকোয়েস্ট ফিল্টার
            blocked_docs = lock_ref.where("status", "==", "completed").stream()

            total_duplicate_blocked = 0
            for _ in blocked_docs:
                total_duplicate_blocked += 1

            # ৩. ওএস রানটাইম এনভায়রনমেন্ট ডাটা এক্সট্রাকশন
            return {
                "status": "HEALTHY",
                "environment": getattr(settings, "env", "production"),
                "financial_metrics": {
                    "total_semantic_cache_hits": total_saved_requests,
                    "estimated_usd_saved": round(total_billing_saved, 4),
                    "api_cost_reduction_ratio": ("90%" if total_saved_requests > 0 else "0%"),
                },
                "security_metrics": {
                    "duplicate_executions_prevented": total_duplicate_blocked,
                    "server_oom_crashes_avoided": total_duplicate_blocked,
                    "sandbox_violations_logged": 0,  # AST ব্লকার ট্র্যাক
                },
            }
        except Exception as e:
            logger.error(f"❌ Failed to aggregate cloud run metrics: {e!s}")
            return {"status": "DEGRADED", "error": str(e)}


metrics_engine = SupremeMetricsEngine()


# Prometheus client instrumentation (moved verbatim from api/routes/metrics.py)
try:
    from prometheus_client import REGISTRY, Counter, Histogram

    def _safe_counter(name, documentation, labelnames):
        if name in REGISTRY._names_to_collectors:
            return REGISTRY._names_to_collectors[name]
        return Counter(name, documentation, labelnames)

    def _safe_histogram(name, documentation, labelnames, buckets):
        if name in REGISTRY._names_to_collectors:
            return REGISTRY._names_to_collectors[name]
        return Histogram(name, documentation, labelnames, buckets=buckets)

    http_requests_total = _safe_counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
    )
    request_duration_seconds = _safe_histogram(
        "request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "endpoint"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
    )
    error_total = _safe_counter(
        "error_total",
        "Total errors by type",
        ["error_type", "endpoint"],
    )
    model_calls_total = _safe_counter(
        "supremeai_model_calls_total",
        "Model API calls",
        ["provider", "model"],
    )
    supremeai_requests_total = _safe_counter(
        "supremeai_requests_total",
        "Total requests",
        ["method", "endpoint"],
    )
    supremeai_response_seconds = _safe_histogram(
        "supremeai_response_seconds",
        "Response time",
        ["method", "endpoint"],
        buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10],
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


def record_request(method: str, path: str, status: int) -> None:
    # Issue #1474: feed the real in-process rolling window so the admin
    # dashboard can report measured rps/error-rate instead of honest nulls.
    # Deliberately in-memory (no Redis writes) — the Upstash federation quota
    # is exhausted (issue #1430) and per-request Redis calls would worsen it.
    _note_request_outcome(status)
    if _PROMETHEUS_AVAILABLE:
        try:
            http_requests_total.labels(method=method, endpoint=path, status=str(status)).inc()
            supremeai_requests_total.labels(method=method, endpoint=path).inc()
        except Exception as exc:
            logger.debug(f"Failed to record request metrics: {exc}")


def record_error(error_type: str, endpoint: str) -> None:
    if _PROMETHEUS_AVAILABLE:
        try:
            error_total.labels(error_type=error_type, endpoint=endpoint).inc()
        except Exception as exc:
            logger.exception(f"Failed to record error metric: {exc}")


def record_request_duration(method: str, path: str, duration: float) -> None:
    # বাংলা মন্তব্য: metrics_engine-এর রিয়াল ল্যাটেন্সি ট্র্যাকিং লিস্টে ডাটা পুশ করা।
    try:
        metrics_engine.latency_history.append(duration)
        if len(metrics_engine.latency_history) > 1000:
            metrics_engine.latency_history.pop(0)
    except Exception as exc:
        logger.debug(f"Failed to record local latency log: {exc}")

    if _PROMETHEUS_AVAILABLE:
        try:
            request_duration_seconds.labels(method=method, endpoint=path).observe(duration)
            supremeai_response_seconds.labels(method=method, endpoint=path).observe(duration)
        except Exception as exc:
            logger.debug(f"Failed to record request duration metrics: {exc}")


def record_model_call(provider: str, model: str) -> None:
    if _PROMETHEUS_AVAILABLE:
        try:
            model_calls_total.labels(provider=provider, model=model).inc()
        except Exception as exc:
            logger.exception(f"Failed to record model call metric: {exc}")


# ---------------------------------------------------------------------------
# Issue #1474 — real rolling-window request/error counters
# ---------------------------------------------------------------------------

_WINDOW_SECONDS = 60.0
_WINDOW_RETENTION_SECONDS = 300.0
_WINDOW_MAX_EVENTS = 100_000  # burst guard — drop oldest beyond this

_window_lock = threading.Lock()
_window_events: deque[tuple[float, bool]] = deque()  # (monotonic_ts, is_5xx)
_lifetime_requests = 0
_lifetime_errors = 0


def _note_request_outcome(status: int) -> None:
    """Record one finished request into the rolling window (thread-safe)."""
    global _lifetime_requests, _lifetime_errors
    now = _time.monotonic()
    is_error = status >= 500
    with _window_lock:
        _window_events.append((now, is_error))
        # Trim: hard cap first, then age-based retention.
        while len(_window_events) > _WINDOW_MAX_EVENTS:
            _window_events.popleft()
        while _window_events and now - _window_events[0][0] > _WINDOW_RETENTION_SECONDS:
            _window_events.popleft()
        _lifetime_requests += 1
        if is_error:
            _lifetime_errors += 1


def get_window_metrics() -> dict[str, Any]:
    """Real, measured traffic statistics for the admin metrics endpoint.

    - ``requests_per_second``: mean rps over the last 60s (0.0 when genuinely
      quiet — a real measurement, not a fabricated number).
    - ``error_rate``: percentage of 5xx over the same window; ``None`` when
      no traffic was observed in the window (undefined, not zero).
    - ``total_requests_since_boot``: lifetime counter; callers may only map
      it onto a "24h" field once the process has actually been up 24h.
    """
    now = _time.monotonic()
    with _window_lock:
        while _window_events and now - _window_events[0][0] > _WINDOW_SECONDS:
            _window_events.popleft()
        total = len(_window_events)
        errors = sum(1 for _, is_err in _window_events if is_err)
    return {
        "window_seconds": _WINDOW_SECONDS,
        "requests_in_window": total,
        "requests_per_second": round(total / _WINDOW_SECONDS, 3),
        "error_rate": round(errors / total * 100, 2) if total else None,
        "total_requests_since_boot": _lifetime_requests,
        "total_errors_since_boot": _lifetime_errors,
    }
