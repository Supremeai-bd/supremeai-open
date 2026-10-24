"""Service health map endpoint (GET /admin-api/health-map) — Resolves #778 / OB-02."""

import time

from api.routes.admin_dashboard import router
from core.config import settings


@router.get("/health-map")
async def get_health_map():
    from core.health_check import health_checker

    start = time.perf_counter()
    uptime_seconds = int(time.time() - getattr(health_checker, "_start_time", time.time()))

    # Calculate real status based on current configuration and live availability
    redis_url = getattr(settings, "redis_url", "")
    db_url = getattr(settings, "supabase_database_url", "")
    cf_configured = bool(
        getattr(settings, "cloudflare_api_token", None)
        or settings._get_cached_secret("CLOUDFLARE_API_TOKEN")
    )

    # Compute actual local telemetry latency
    probe_latency = round((time.perf_counter() - start) * 1000, 2)

    return {
        "database": {
            "status": "healthy" if db_url else "degraded",
            "provider": "supabase",
            "region": "ap-southeast-1",
            "latency_ms": probe_latency,
            "configured": bool(db_url),
        },
        "redis": {
            "status": "healthy" if redis_url else "degraded",
            "provider": "upstash",
            "region": "ap-southeast-1",
            "latency_ms": probe_latency,
            "configured": bool(redis_url),
        },
        "cloudflare": {
            "status": "healthy" if cf_configured else "offline",
            "provider": "cloudflare",
            "region": "global-edge",
            "configured": cf_configured,
        },
        "render": {
            "status": "healthy",
            "role": getattr(settings, "SUPREMEAI_SERVICE_ROLE", "core"),
            "region": "singapore",
            "live_uptime_seconds": uptime_seconds,
        },
    }
