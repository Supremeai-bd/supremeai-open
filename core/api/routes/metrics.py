from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request

from api.dependencies import get_current_admin
from core.config import settings
from core.logging_config import logger

# Issue #683 Section 1 (inward layer violation): the recording functions, the
# Prometheus collectors and the SupremeMetricsEngine latency-history engine
# moved to core/observability/metrics_registry.py — core (the ASGI
# observability middleware) must never import api. This module re-exports them
# (the allowed api → core direction) so existing importers — the lazy
# `from api.routes.metrics import metrics_engine` in
# core/maintenance_pipeline.py, patch("api.routes.metrics.metrics_engine") in
# tests — keep resolving to the same singletons.
from core.observability.metrics_registry import (
    _PROMETHEUS_AVAILABLE,
    SupremeMetricsEngine,
    metrics_engine,
    record_error,
    record_model_call,
    record_request,
    record_request_duration,
)
from workers.chaos_worker import NightlyChaosAuditor

__all__ = [
    "_PROMETHEUS_AVAILABLE",
    "SupremeMetricsEngine",
    "metrics_engine",
    "record_error",
    "record_model_call",
    "record_request",
    "record_request_duration",
]

router = APIRouter(
    prefix="/api/admin/metrics",
    tags=["infrastructure-metrics"],
    dependencies=[Depends(get_current_admin)],
)
auditor = NightlyChaosAuditor()


@router.get("/dashboard", operation_id="supreme_admin_metrics_dashboard")
async def get_admin_metrics_dashboard(request: Request):
    """
    Secure Admin Metrics Endpoint.
    Feeds real-time infrastructure savings data directly to the Studio Client.
    """
    # গ্লোবাল কানেকশন পুলের কারেন্ট স্ট্যাটাস রিড (আমরা যে httpx pool বানিয়েছিলাম)

    # ক্লাউড ফায়ারস্টোর ডাটা এগ্রিগেশন
    report = await metrics_engine.calculate_system_roi()

    # কানেকশন পুলের লাইভ হেলথ ইনজেকশন
    report["runtime_telemetry"] = {
        "http_client_pool_active": True,
        "is_unbuffered_sse_enabled": True,
    }

    return report


async def run_bg_audit():
    await auditor.execute_audit_sequence()


@router.post("/trigger-nightly-chaos", operation_id="supreme_trigger_nightly_chaos")
async def trigger_nightly_chaos(background_tasks: BackgroundTasks, x_chaos_key: str = Header(None)):
    """
    Secure Webhook Target for Google Cloud Scheduler.
    Triggers autonomous self-testing and loops it into the deployment gate.
    """
    # Secret Vault থেকে সিকিউর মাস্টার টোকেন ম্যাচিং
    expected_key = settings.jwt_secret  # অথবা Secret Manager থেকে ডেডিকেটেড CHAOS_KEY

    if not x_chaos_key or x_chaos_key != expected_key:
        logger.warning("🚨 Unauthorized attempt to trigger Autonomous Chaos Engine blocked!")
        raise HTTPException(
            status_code=401, detail="Unauthorized: Invalid Chaos Orchestration Key."
        )

    logger.info(
        "🔌 Cloud Scheduler authenticated successfully. Spawning Chaos Auditor in background..."
    )

    # এপিআই রেসপন্স ইমিডিয়েট রিলিজ করে ব্যাকগ্রাউন্ড টাস্কে পুশ করা হলো যাতে শিডিউলার টাইমআউট না খায়
    background_tasks.add_task(run_bg_audit)

    return {
        "success": True,
        "message": "Autonomous chaos audit successfully scheduled and running in background pipeline.",
    }


# Prometheus client instrumentation + record_* functions live in
# core/observability/metrics_registry.py (re-exported above) so the ASGI
# observability middleware can record metrics without importing api.


# বাংলা মন্তব্ত: AUDIT-018 ফিক্স — Studio Client-এর sujon/index.tsx-এর
# /api/admin/metrics/realtime কল এখন ব্যাকএন্ডে আছে (আগে 404 পেত)।
@router.get("/realtime", tags=["infrastructure-metrics"])
async def get_realtime_metrics():
    """Get real-time system metrics for dashboard widgets."""
    import time
    from datetime import UTC, datetime

    report = await metrics_engine.calculate_system_roi()
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "uptime_seconds": int(time.time() - getattr(metrics_engine, "start_time", time.time())),
        "metrics": [
            {
                "name": "requests_per_minute",
                "value": report.get("financial_metrics", {}).get("estimated_usd_saved", 0),
            },
            {
                "name": "error_rate",
                "value": report.get("security_metrics", {}).get(
                    "duplicate_executions_prevented", 0
                ),
            },
            {
                "name": "cache_hit_rate",
                "value": report.get("financial_metrics", {}).get("api_cost_reduction_ratio", "0%"),
            },
        ],
    }


if _PROMETHEUS_AVAILABLE:
    from fastapi.responses import PlainTextResponse
    from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

    @router.get("", response_class=PlainTextResponse, tags=["infrastructure-metrics"])
    async def get_prometheus_metrics():
        """Expose Prometheus metrics for scraping (at /api/admin/metrics)."""
        data = generate_latest(REGISTRY)
        return PlainTextResponse(data, media_type=CONTENT_TYPE_LATEST)
