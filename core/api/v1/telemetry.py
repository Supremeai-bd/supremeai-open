"""
Performance and Telemetry API for SupremeAI 2.0

This module provides endpoints for monitoring system performance,
collecting metrics, and exposing health information.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.cache.multi_layer_cache import multi_layer_cache
from core.config import settings
from monitoring.metrics_collector import metrics_collector

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/health")
async def get_system_health():
    """Get comprehensive system health metrics."""
    health_data = await metrics_collector.get_overall_health()
    return JSONResponse(content=health_data)


@router.get("/metrics/cache")
async def get_cache_metrics():
    """Get detailed cache performance metrics."""
    cache_stats = await multi_layer_cache.get_cache_statistics()
    return JSONResponse(content=cache_stats)


@router.get("/metrics/db")
async def get_db_metrics():
    """Get database performance metrics."""
    db_metrics = await metrics_collector.get_db_performance()
    return JSONResponse(content=db_metrics)


@router.get("/metrics/ai")
async def get_ai_metrics():
    """Get AI model usage and cost metrics."""
    ai_metrics = await metrics_collector.get_ai_cost_metrics()
    return JSONResponse(content=ai_metrics)


@router.get("/metrics/security")
async def get_security_metrics():
    """Get security event metrics."""
    security_metrics = await metrics_collector.get_security_metrics()
    return JSONResponse(content=security_metrics)


@router.get("/performance/overview")
async def get_performance_overview():
    """Get a comprehensive overview of system performance."""
    health_data = await metrics_collector.get_overall_health()
    cache_stats = await multi_layer_cache.get_cache_statistics()

    overview = {
        "timestamp": health_data["timestamp"],
        "system_health": {
            "active_connections": health_data["active_connections"],
            "total_requests": health_data["total_requests"],
            "total_errors": health_data["total_errors"],
            "uptime_minutes": health_data["uptime_minutes"],
        },
        "cache_performance": {
            "hit_rate_percentage": cache_stats["hit_rate_percentage"],
            "total_accesses": cache_stats["total_accesses"],
            "breakdown": {
                "exact_hits": cache_stats["exact_hits"],
                "semantic_hits": cache_stats["semantic_hits"],
                "prefix_hits": cache_stats["prefix_hits"],
                "session_hits": cache_stats["session_hits"],
                "misses": cache_stats["misses"],
            },
        },
        "database_performance": health_data["database_performance"],
        "ai_costs": health_data["ai_costs"],
        "security_events": health_data["security_events"],
    }

    return JSONResponse(content=overview)


@router.get("/status")
async def get_detailed_status():
    """Get detailed system status including subsystem health."""
    health_data = await metrics_collector.get_overall_health()

    status = {
        "status": "operational",
        "timestamp": health_data["timestamp"],
        "version": settings.app_name,
        "environment": settings.env,
        "subsystems": {
            "database": "operational"
            if health_data["database_performance"]["avg_query_time"] < 1.0
            else "degraded",
            "cache": "operational"
            if health_data["cache_performance"]["hit_rate_percentage"] > 50
            else "degraded",
            "api": (
                "operational"
                if health_data["total_errors"] / max(1, health_data["total_requests"]) < 0.05
                else "degraded"
            ),
        },
        "metrics": {
            "request_rate_per_minute": health_data["total_requests"]
            / max(1, health_data["uptime_minutes"]),
            "error_rate_percentage": (
                (health_data["total_errors"] / max(1, health_data["total_requests"])) * 100
                if health_data["total_requests"] > 0
                else 0
            ),
            "cache_hit_rate_percentage": health_data["cache_performance"]["hit_rate_percentage"],
            "avg_db_query_time_seconds": health_data["database_performance"]["avg_query_time"],
        },
    }

    return JSONResponse(content=status)


from pydantic import BaseModel, Field


class FrontendErrorReport(BaseModel):
    message: str = Field(..., max_length=2000)
    stack: str | None = Field(None, max_length=4000)
    url: str | None = Field(None, max_length=500)
    user_agent: str | None = Field(None, max_length=500)


# বাংলা মন্তব্য: AUDIT-018 ফিক্স — Studio Client-এর GlobalErrorBoundary.tsx-এর
# /api/telemetry/frontend-error কল এখন ব্যাকএন্ডে আছে
@router.post("/frontend-error", tags=["telemetry"])
async def report_frontend_error(payload: FrontendErrorReport):
    """Receive and log frontend error reports safely from the Studio Client."""
    from core.logging_config import logger

    logger.error(f"Frontend error report: message={payload.message[:200]} url={payload.url}")
    return {"status": "logged", "message": "Frontend error report received"}
