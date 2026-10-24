from __future__ import annotations

import logging

"""
Query Timing Middleware — Track API Response Times
v4.0: Log slow requests, track percentiles, alert on degradation
"""


import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

# RESTORE-AND-WIRE (2026-09-14): `from typing import ASGI` never existed in the
# stdlib (module failed to import on Python 3.12) — replaced with the correct
# ASGI application callable type.
from core.logging_config import logger

# Configuration
SLOW_REQUEST_MS = float(__import__("os").getenv("SLOW_REQUEST_MS", "2000"))
HISTORY_SIZE = int(__import__("os").getenv("QUERY_TIMING_HISTORY", "1000"))

# Thread-safe request history (for percentile calculation)
_request_history: deque[dict] = deque(maxlen=HISTORY_SIZE)


class QueryTimingMiddleware:
    """
    ASGI middleware that tracks API response times.

    Features:
      - Logs all requests with timing
      - Alerts on slow requests (> SLOW_REQUEST_MS)
      - Maintains rolling history for percentile calculation
      - Exposes /metrics endpoint data
    """

    def __init__(self, app: Callable[[Any, Any, Any], Awaitable[Any]]) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_code = None

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        # Process request
        await self.app(scope, receive, send_wrapper)

        # Calculate metrics
        duration_ms = (time.monotonic() - start) * 1000
        method = scope.get("method", "")
        path = scope.get("path", "")

        # Log request
        log_level = logging.WARNING if duration_ms > SLOW_REQUEST_MS else logging.INFO
        logger.log(
            log_level,
            f"{method} {path} → {status_code} ({duration_ms:.0f}ms)"
            + (" 🐌 SLOW" if duration_ms > SLOW_REQUEST_MS else ""),
        )

        # Store in history
        _request_history.append(
            {
                "method": method,
                "path": path,
                "status": status_code,
                "duration_ms": round(duration_ms, 2),
                "timestamp": time.time(),
            }
        )


def get_timing_stats() -> dict:
    """Get aggregated timing statistics from history."""
    if not _request_history:
        return {"total_requests": 0}

    durations = [r["duration_ms"] for r in _request_history]
    sorted_durations = sorted(durations)
    n = len(sorted_durations)

    return {
        "total_requests": n,
        "avg_ms": round(sum(durations) / n, 2),
        "p50_ms": sorted_durations[n // 2],
        "p95_ms": sorted_durations[int(n * 0.95)] if n > 20 else None,
        "p99_ms": sorted_durations[int(n * 0.99)] if n > 100 else None,
        "max_ms": max(durations),
        "min_ms": min(durations),
        "slow_count": sum(1 for d in durations if d > SLOW_REQUEST_MS),
        "slow_pct": round(sum(1 for d in durations if d > SLOW_REQUEST_MS) / n * 100, 1),
    }
