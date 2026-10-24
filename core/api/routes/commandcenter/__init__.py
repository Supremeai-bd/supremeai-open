"""Command Center API — admin observability endpoints.

Provides aggregated metrics for the admin Command Center UI:
- /health — basic liveness check
- /metrics — aggregated system metrics (background services, cache, errors)
- /events — recent error events from the error_event_bus

OBSERVE phase: implements the previously-stub /metrics endpoint with real
aggregated data, so admin can observe the entire system from one place.
"""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import APIRouter, Depends

from api.dependencies import get_current_admin
from core.logging_config import logger

router = APIRouter(
    prefix="/admin-api/commandcenter",
    tags=["Command Center"],
    dependencies=[Depends(get_current_admin)],
)

# Issue #1495 (HIGH): the 7 Command Center sub-modules below each define their
# own APIRouter with an empty prefix, but they were never included anywhere —
# every /admin-api/commandcenter/{build,money,observe,operate,overview,secure,
# system}/* route answered 404 and the modules were dead code. Mount them on
# the package router so ALL_ROUTERS (which registers this package's `router`
# only) picks them all up under the same admin-auth dependency.
from api.routes.commandcenter.build import router as _build_router  # noqa: E402
from api.routes.commandcenter.money import router as _money_router  # noqa: E402
from api.routes.commandcenter.observe import router as _observe_router  # noqa: E402
from api.routes.commandcenter.operate import router as _operate_router  # noqa: E402
from api.routes.commandcenter.overview import router as _overview_router  # noqa: E402
from api.routes.commandcenter.secure import router as _secure_router  # noqa: E402
from api.routes.commandcenter.system import router as _system_router  # noqa: E402

router.include_router(_build_router)
router.include_router(_money_router)
router.include_router(_observe_router)
router.include_router(_operate_router)
router.include_router(_overview_router)
router.include_router(_secure_router)
router.include_router(_system_router)

# Track app start time for uptime calculation
_app_start_time = time.time()


@router.get("/health")
async def command_health():
    """Basic liveness check for Command Center."""
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - _app_start_time),
    }


@router.get("/metrics")
async def command_metrics():
    """Aggregated system metrics for admin Command Center.

    Returns background service status, system resources, cache stats,
    and error counts — all in one call.
    """
    metrics: dict[str, Any] = {
        "timestamp": int(time.time()),
        "uptime_seconds": int(time.time() - _app_start_time),
    }

    # 1. System resources (CPU/memory) — best-effort, no crash if psutil missing
    try:
        import psutil

        metrics["system"] = {
            "cpu_percent": float(psutil.cpu_percent(interval=None) or 0),
            "memory_percent": float(psutil.virtual_memory().percent or 0),
            "disk_percent": float(psutil.disk_usage("/").percent or 0),
        }
    except ImportError:
        metrics["system"] = {"error": "psutil not installed"}
    except Exception as exc:
        metrics["system"] = {"error": str(exc)[:100]}

    # 2. Background service status — env-driven (default off, so we show what's enabled)
    metrics["services"] = {
        "auto_healer_enabled": os.getenv("ENABLE_AUTO_HEALER", "false").lower() == "true",
        "evolution_enabled": os.getenv("ENABLE_EVOLUTION", "false").lower() == "true",
        "daily_learner_enabled": os.getenv("ENABLE_DAILY_LEARNER", "false").lower() == "true",
        "tier8_enabled": os.getenv("ENABLE_TIER8", "false").lower() == "true",
        "evolution_learning_enabled": os.getenv("ENABLE_EVOLUTION_LEARNING", "false").lower()
        == "true",
        "token_juice_enabled": os.getenv("TOKEN_JUICE_ENABLED", "true").lower() == "true",
    }

    # 3. WebSocket connection metric — REMOVED (#1832): the websocket_agent
    # manager is unmounted (replaced by the SSE transports); its counts were
    # structurally always zero, a fake metric on the admin dashboard.

    # 4. Maintenance pipeline health — best-effort
    try:
        from core.maintenance_pipeline import maintenance_pipeline

        metrics["maintenance"] = {
            "health_score": getattr(maintenance_pipeline, "health_score", None),
            "monitoring_active": getattr(maintenance_pipeline, "_monitoring", False),
        }
    except Exception as exc:
        metrics["maintenance"] = {"error": f"pipeline unavailable: {type(exc).__name__}"}

    # 5. Error event bus stats — best-effort
    # NOTE: error_event_bus.stats is a @property (not a method), so we access
    # it without parentheses.
    try:
        from core.messaging.event_bus import error_event_bus

        stats = error_event_bus.stats  # property access, not method call
        metrics["errors"] = stats if isinstance(stats, dict) else {"stats": str(stats)}
    except Exception as exc:
        metrics["errors"] = {"error": f"event_bus unavailable: {type(exc).__name__}"}

    # 6. App state — check if app has been created yet (best-effort)
    try:
        from core.app import app

        metrics["app"] = {
            "title": getattr(app, "title", "unknown"),
            "version": getattr(app, "version", "unknown"),
            "route_count": len(getattr(app, "routes", [])),
        }
    except Exception:
        # App not yet created (e.g., during testing)
        metrics["app"] = {"status": "not_yet_created"}

    logger.debug(f"[commandcenter] metrics gathered: {list(metrics.keys())}")
    return metrics


@router.get("/events")
async def command_events(limit: int = 50):
    """Recent error events from the error_event_bus.

    Returns the last N error events so admin can see what's failing.
    """
    try:
        from core.messaging.event_bus import error_event_bus

        # event_bus may have a dead_letter_queue or recent_events list
        # Try common attribute names
        events: list[Any] = []
        for attr in ("recent_events", "_recent_events", "events", "_events"):
            val = getattr(error_event_bus, attr, None)
            if isinstance(val, list):
                events = val[-limit:]
                break
        # Also check dead_letter_queue
        if not events:
            dlq = getattr(error_event_bus, "_dead_letter_queue", None) or []
            events = list(dlq)[-limit:]
        return {
            "count": len(events),
            "events": events,
        }
    except Exception as exc:
        logger.warning(f"[commandcenter] events fetch failed: {exc}")
        return {"count": 0, "events": [], "error": str(exc)[:100]}


# FIX (CI red 36219425476): the sub-router inclusion block that used to sit
# here duplicated the mounts at the top of this file (#1499, issue #1495).
# include_router on the same router twice registers every /admin-api/
# commandcenter/{build,money,observe,operate,overview,secure,system}/* route
# ×2 — test_router_mount_hygiene::test_no_route_registered_more_than_once
# caught 41 duplicated triples. The top-of-file block (with its issue #1495
# rationale) is the single mount point now; nothing else changed.
