"""
SupremeAI Health Check System — Production-Ready Monitoring
🔬 Evolution v3.0: Comprehensive /health, /ready, /live endpoints

Endpoints:
  GET /health       — Full health status (all checks)
  GET /health/ready — Readiness probe (is service accepting traffic?)
  GET /health/live  — Liveness probe (is process alive?)

Usage:
  from core.health import router as health_router
  app.include_router(health_router, prefix="/health")
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, Response
from loguru import logger

router = APIRouter(tags=["health"])


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheck:
    """Individual health check registration."""

    name: str
    check_fn: Callable[[], bool] | Callable[[], Awaitable[bool]]
    critical: bool = True
    timeout_ms: int = 5000


@dataclass
class HealthResult:
    """Result of a single health check."""

    name: str
    status: HealthStatus
    latency_ms: float
    error: str | None = None
    critical: bool = True


@dataclass
class OverallHealth:
    """Aggregate health status."""

    status: HealthStatus
    timestamp: str
    uptime_seconds: float
    version: str
    environment: str
    platform: str
    checks: list[HealthResult] = field(default_factory=list)


# Global state
_start_time = time.time()
_checks: list[HealthCheck] = []
_liveness_status: bool = True

# ─────────────────────────────────────────────────────────────────────────────
# Issue #468 (item 3 — honest health-result TTL cache):
#
# Every /health request previously re-ran ALL registered checks — the
# database probe (SELECT 1 incl. pool checkout) costs ~100-180ms, which
# made the primary node's health response ~190-250ms server-side and put
# a redundant query load on Supabase every time any monitor poller,
# dashboard, or synthetic probe looked at the node.
#
# Cache semantics (deliberately conservative — this is a HEALTH gate, so
# freshness is a safety property, not just a performance one):
#   - ONLY fully-HEALTHY (HTTP 200) results are cached. Any degraded or
#     unhealthy outcome bypasses the cache entirely, so incident detection
#     and recovery are never delayed by the cache (failure → next request
#     re-runs the real checks).
#   - TTL is short (10s) — bounded staleness, far below typical monitor
#     intervals; also advertised via Cache-Control so shared caches behave
#     the same way.
#   - Hits are HONEST: ``cache_hit: true`` + ``cache_age_seconds`` tell the
#     consumer the data is served from the TTL window (never a fake
#     fresh-looking payload).
#   - In-process (per node), NOT Redis: a Redis-backed cache would add a
#     network hop on miss and burn federation quota to avoid a DB query —
#     health is single-node state by definition.
# ─────────────────────────────────────────────────────────────────────────────
# Issue #468: 15s TTL matches the fleet-monitor probe cadence — every probe
# is served from cache instead of each paying the DB SELECT + pool checkout
# (~100-180ms documented cost). Trade-off: a DB outage takes ≤15s to reflect
# here (still well within Render's health-check policy).
_HEALTH_CACHE_TTL_SECONDS = 15.0
_health_cache_payload: dict[str, Any] | None = None
_health_cache_monotonic: float = 0.0
_health_cache_status_code: int = 200


def reset_health_cache() -> None:
    """Clear the health TTL cache (test isolation + manual invalidation)."""
    global _health_cache_payload, _health_cache_monotonic, _health_cache_status_code
    _health_cache_payload = None
    _health_cache_monotonic = 0.0
    _health_cache_status_code = 200


def register_check(
    name: str,
    check_fn: Callable[[], bool] | Callable[[], Awaitable[bool]],
    critical: bool = True,
    timeout_ms: int = 5000,
) -> None:
    """Register a new health check. Call during app startup."""
    _checks.append(
        HealthCheck(
            name=name,
            check_fn=check_fn,
            critical=critical,
            timeout_ms=timeout_ms,
        )
    )


def set_liveness(alive: bool) -> None:
    """Update liveness status. Set to False to trigger pod restart."""
    global _liveness_status
    _liveness_status = alive


async def _run_check(check: HealthCheck) -> HealthResult:
    """Execute a single health check with timeout."""
    start = time.monotonic()
    try:
        if asyncio.iscoroutinefunction(check.check_fn):
            result = await asyncio.wait_for(check.check_fn(), timeout=check.timeout_ms / 1000)
        else:
            result = await asyncio.to_thread(check.check_fn)

        latency = (time.monotonic() - start) * 1000
        return HealthResult(
            name=check.name,
            status=HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY,
            latency_ms=round(latency, 2),
            critical=check.critical,
        )
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return HealthResult(
            name=check.name,
            status=HealthStatus.UNHEALTHY,
            latency_ms=round(latency, 2),
            error=str(e)[:200],
            critical=check.critical,
        )


def _compute_overall(results: list[HealthResult]) -> HealthStatus:
    """Compute overall health from individual results."""
    if all(r.status == HealthStatus.HEALTHY for r in results):
        return HealthStatus.HEALTHY

    # Critical failures = unhealthy, non-critical = degraded
    critical_failures = [r for r in results if r.status == HealthStatus.UNHEALTHY and r.critical]
    if critical_failures:
        return HealthStatus.UNHEALTHY

    return HealthStatus.DEGRADED


@router.get("")
@router.get("/full")
async def get_full_health(response: Response) -> dict[str, Any]:
    """Full health check — runs ALL registered checks.

    Served from a 10s TTL cache when the previous outcome was fully HEALTHY
    (#468): check failures bypass the cache so incident detection is never
    delayed. Cache hits are labeled honestly (``cache_hit`` /
    ``cache_age_seconds``).
    """
    global _health_cache_payload, _health_cache_monotonic, _health_cache_status_code

    import os

    now_monotonic = time.monotonic()
    if (
        _health_cache_payload is not None
        and (now_monotonic - _health_cache_monotonic) < _HEALTH_CACHE_TTL_SECONDS
    ):
        response.status_code = _health_cache_status_code
        response.headers["Cache-Control"] = (
            f"public, max-age={int(_HEALTH_CACHE_TTL_SECONDS)}, "
            f"stale-while-revalidate={int(_HEALTH_CACHE_TTL_SECONDS * 2)}"
        )
        payload = dict(_health_cache_payload)
        payload["cache_hit"] = True
        payload["cache_age_seconds"] = round(now_monotonic - _health_cache_monotonic, 2)
        return payload

    results = [_run_check(check) for check in _checks]
    results = await asyncio.gather(*results)
    overall = _compute_overall(results)

    payload = {
        "status": overall.value,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "uptime_seconds": round(time.time() - _start_time, 2),
        "version": os.getenv("APP_VERSION", "unknown"),
        "environment": os.getenv("ENV", "development"),
        "platform": os.getenv("PLATFORM", "unknown"),
        "total_checks": len(results),
        "passed_checks": sum(1 for r in results if r.status == HealthStatus.HEALTHY),
        "checks": [
            {
                "name": r.name,
                "status": r.status.value,
                "latency_ms": r.latency_ms,
                "error": r.error,
                "critical": r.critical,
            }
            for r in results
        ],
    }

    status_code = 200 if overall == HealthStatus.HEALTHY else 503
    response.status_code = status_code
    response.headers["Cache-Control"] = (
        f"public, max-age={int(_HEALTH_CACHE_TTL_SECONDS)}, "
        f"stale-while-revalidate={int(_HEALTH_CACHE_TTL_SECONDS * 2)}"
    )

    # Only cache healthy outcomes (see cache-semantics note above).
    if status_code == 200:
        _health_cache_payload = dict(payload)
        _health_cache_monotonic = now_monotonic
        _health_cache_status_code = status_code
    else:
        _health_cache_payload = None

    payload["cache_hit"] = False
    payload["cache_age_seconds"] = 0.0
    return payload


@router.get("/ready")
async def readiness_probe(response: Response) -> dict[str, Any]:
    """Readiness probe — is the service ready to accept traffic?

    Decision semantics follow the P1 DB degradation policy
    (``core/health_policy.py``): only CRITICAL checks gate readiness. For
    role=worker/scraper/mcp the database check registers non-critical
    (``app_builder.register_check`` + ``is_critical_db_check``), so a DB
    failure leaves the service ready — role-specific degradation allowed.
    Unhealthy non-critical checks are reported in the ``degraded`` list so a
    ready-but-degraded state stays observable instead of silently green
    (this implements the contract's documented ``200 ready/degraded`` shape).
    """
    import os

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    role = (os.getenv("SUPREMEAI_SERVICE_ROLE", "core") or "core").strip().lower() or "core"

    critical_checks = [c for c in _checks if c.critical]
    non_critical_checks = [c for c in _checks if not c.critical]

    # Degraded visibility: non-critical check failures never block traffic
    # (role-specific degradation), but the fact must be observable here —
    # an orchestrator polling /health/ready should see WHAT is degraded.
    degraded: list[str] = []
    if non_critical_checks:
        nc_results = await asyncio.gather(*[_run_check(c) for c in non_critical_checks])
        degraded = [r.name for r in nc_results if r.status != HealthStatus.HEALTHY]

    # Issue #478: schema gate — production fail-closed when a required table
    # is missing; schema state always observable in the probe payload.
    # Read-only REST probe (settings SSoT), cached 60s, never crashes the probe.
    from core.db_schema_gate import check_schema_status, production_schema_incompatible

    schema_reason: str | None = None
    schema_status: dict[str, Any] = {
        "checked": False,
        "reason": "probe error",
        "missing": [],
        "present": [],
    }
    try:
        schema_reason = await asyncio.to_thread(production_schema_incompatible)
        schema_status = await asyncio.to_thread(check_schema_status)
    except Exception as exc:  # noqa: BLE001 — probe must never crash readiness
        logger.warning(f"schema gate probe error (treated as unknown): {exc}")
    schema_block = {k: schema_status.get(k) for k in ("checked", "missing", "present", "unknown")}
    if schema_reason and role == "core":
        logger.critical(f"Readiness schema gate: {schema_reason} (env={os.getenv('ENV', '')})")
        response.status_code = 503
        return {
            "status": "not_ready",
            "timestamp": now,
            "role": role,
            "degraded": degraded,
            "schema": schema_block,
            "detail": f"Schema incompatible — not ready ({schema_reason})",
        }

    if not critical_checks:
        # No critical checks registered: the service is ready by definition,
        # but non-critical failures still surface as degraded visibility.
        response.status_code = 200
        return {
            "status": "degraded" if degraded else "ready",
            "timestamp": now,
            "role": role,
            "degraded": degraded,
            "schema": schema_block,
        }

    results = await asyncio.gather(*[_run_check(c) for c in critical_checks])
    all_healthy = all(r.status == HealthStatus.HEALTHY for r in results)

    response.status_code = 200 if all_healthy else 503
    status = "not_ready" if not all_healthy else ("degraded" if degraded else "ready")
    return {
        "status": status,
        "timestamp": now,
        "role": role,
        "degraded": degraded,
        "schema": schema_block,
    }


@router.get("/live")
async def liveness_probe(response: Response) -> dict[str, Any]:
    """Liveness probe — is the process alive? Kubernetes uses this for restarts."""
    response.status_code = 200 if _liveness_status else 503
    return {
        "status": "alive" if _liveness_status else "dead",
        "alive": _liveness_status,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
