# backend/api/server.py
"""SupremeAI REST API Server - FastAPI Implementation (Phase 4 Production Ready).

Production-ready HTTP interface for SupremeAI:
- Full Request Lifecycle (`/api/v1/process`)
- Health and Telemetry Dashboard (`/api/v1/health`, `/api/v1/status`, `/api/v1/dashboard`)
- Real-time Evolution Control (`/api/v1/evolution/status`, `/api/v1/evolution/trigger`)
- Smart Memory Management (`/api/v1/memory/stats`, `/api/v1/memory/consolidate`)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timezone
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.deps import get_current_user_token
from api.middleware import CSRFMiddleware, GlobalRateLimiterMiddleware
from core.factory import SupremeAIFactory, get_factory
from core.integration_layer import SupremeAIIntegrator
from core.logging_config import logger
from core.neon_repository import close_neon_pool
from core.startup.services import initialize_independent_services

ai_integrator: SupremeAIIntegrator | None = None
factory: SupremeAIFactory | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan management - initialize factory on startup, cleanup on shutdown."""
    global ai_integrator, factory
    app.state.started_at = time.monotonic()
    app.state.subsystem_status = {"db": "up", "redis": "up", "config": "up"}
    try:
        await initialize_independent_services(app)
    except Exception as exc:
        logger.error(f"Independent service initialization failed: {exc}")
        app.state.subsystem_status["db"] = "down"

    factory = get_factory()
    ai_integrator = await factory.create_production_instance()
    yield

    # Cleanup on shutdown
    if factory:
        await factory.graceful_shutdown()
    try:
        from database.session import dispose_engine

        await dispose_engine()
    except Exception as e:
        logger.debug(f"Engine disposal error: {e}")
    try:
        await close_neon_pool()
    except Exception as e:
        logger.debug(f"Neon pool disposal error: {e}")


app = FastAPI(
    title="SupremeAI API",
    description="Living, Self-Evolving Intelligence System (Phase 4 Production Ready)",
    version="4.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Hardened CORS middleware (Audit P1-5)
# SECURE FIX: production origins must come from env vars (zero hardcoded value).
# Dev localhost entries are kept as convenience defaults.
# Set ALLOWED_ORIGINS env var in production, e.g.:
#   ALLOWED_ORIGINS=https://supremeai.app,https://admin.supremeai.app
#
# Phase 1 (specs/001 close-out) — CORS unification: raw env parsing এখন
# middleware/cors_policy.py-র resolver দিয়ে যায় — single source of truth:
#   * wildcard '*' সবসময় বাদ (credentialed CORS-এ অবৈধ ও অনিরাপদ);
#   * ADMIN_CORS_ORIGINS-এ ঘোষিত admin console origin সবসময় উপস্থিত;
#   * একই resolver app_builder.py ও /config/validation-report-ও ব্যবহার করে।
import os as _os

from core.config_parsers import parse_origin_list
from middleware.cors_policy import (
    resolve_admin_cors_origins as _resolve_admin_cors_origins,
)
from middleware.cors_policy import (
    resolve_user_cors_origins as _resolve_user_cors_origins,
)

_dev_origins = [
    "http://localhost:3000",  # is_local()
    "http://localhost:5173",  # is_local()
    "http://127.0.0.1:3000",  # is_local()
    "http://127.0.0.1:5173",  # is_local()
    "tauri://localhost",  # is_local()
]
# Accept the canonical portal-specific variables and retain ALLOWED_ORIGINS as
# a compatibility fallback for deployments that have not migrated yet.
_prod_origins_env = (
    _os.getenv("USER_CORS_ORIGINS")
    or _os.getenv("CORS_ORIGINS")
    or _os.getenv("ALLOWED_ORIGINS", "")
)
_prod_origins = parse_origin_list(
    _prod_origins_env
)  # roadmap 1.4 (#1173): JSON-array ও comma — দুটোই কাজ করে
_configured_origins = _dev_origins + _prod_origins
_admin_raw = parse_origin_list(_os.getenv("ADMIN_CORS_ORIGINS", ""))
_allowed_origins = sorted(
    set(_resolve_user_cors_origins(_configured_origins))
    | set(_resolve_admin_cors_origins(_admin_raw))
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",  # is_local()
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
        "X-CSRF-Token",
        "X-JIT-OTP",
        "X-Device-Fingerprint",
        "X-Request-ID",
        "X-Correlation-ID",
        "apikey",
        # ERR-S02 hygiene (2026-09-16): keep in sync with app_builder.py and
        # apiClient.ts — the backend IdempotencyMiddleware requires this
        # header on some mutating paths, and a CORS allow-list without it
        # makes every such browser preflight fail with 400.
        "Idempotency-Key",
    ],
    # Issue #685 (Domain 15): keep in sync with app_builder.py — expose the
    # tracing headers so the browser JS can read the correlation id.
    expose_headers=[
        "Content-Length",
        "X-Pagination-Total",
        "X-Request-ID",
        "X-Correlation-ID",
    ],
)

app.add_middleware(GlobalRateLimiterMiddleware, limit=100, window=60)
app.add_middleware(CSRFMiddleware)


# Request/Response Models
class ProcessRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000, description="User input/query")
    context: dict[str, Any] | None = Field(default=None, description="Additional context")
    priority: str | None = Field(default="normal", description="Priority level")
    timeout_seconds: int | None = Field(default=60, ge=1, le=300)


class ProcessResponse(BaseModel):
    success: bool
    answer: Any
    confidence: float
    processing_time_ms: float
    request_id: str
    timestamp: str
    components_used: list[str]
    metadata: dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float
    version: str
    components: dict[str, str]
    metrics: dict[str, Any]


class EvolutionStatusResponse(BaseModel):
    is_running: bool
    total_cycles: int
    successful_cycles: int
    recent_cycles: list[dict[str, Any]]


class MemoryStatsResponse(BaseModel):
    total_entries: int
    working_memory: int
    episodic_memory: int
    semantic_nodes: int
    estimated_size_mb: float


# ==================== ENDPOINTS ====================


@app.get("/", tags=["Root"])
async def root() -> dict[str, Any]:
    """Root endpoint - API information."""
    return {
        "name": "SupremeAI API",
        "version": "4.0.0",
        "description": "Living, Self-Evolving Intelligence System",
        "status": "operational" if ai_integrator else "initializing",
        "endpoints": {
            "process": "/api/v1/process",
            "health": "/api/v1/health",
            "status": "/api/v1/status",
            "evolution": "/api/v1/evolution/status",
            "memory": "/api/v1/memory/stats",
            "docs": "/docs",
        },
    }


@app.post("/api/v1/process", response_model=ProcessResponse, tags=["Processing"])
async def process_query(
    request: ProcessRequest,
    background_tasks: BackgroundTasks,
    x_client_id: str = Query(default="anonymous"),
    _token: dict = Depends(get_current_user_token),
) -> ProcessResponse:
    """Main processing endpoint accepting user queries and returning AI solutions."""
    global factory, ai_integrator
    if not factory or not ai_integrator:
        factory = get_factory()
        ai_integrator = await factory.create_production_instance()

    request_id = str(uuid.uuid4())
    start_time = time.perf_counter()

    try:
        safe_res = await asyncio.wait_for(
            factory.safe_process(request.query, request.context),
            timeout=float(request.timeout_seconds or 60),
        )

        processing_time = round((time.perf_counter() - start_time) * 1000.0, 2)

        if not safe_res.get("success"):
            raise HTTPException(
                status_code=429 if safe_res.get("rate_limited") else 503,
                detail=safe_res.get("error", "AI service busy"),
            )

        return ProcessResponse(
            success=safe_res.get("success", True),
            answer=safe_res.get("answer", ""),
            confidence=safe_res.get("confidence", 0.95),
            processing_time_ms=processing_time,
            request_id=request_id,
            timestamp=datetime.now().isoformat(),
            components_used=safe_res.get("components_used", ["reasoning_engine", "rate_limiter"]),
            metadata={
                "provider_used": safe_res.get("provider_used", "Gemini"),
                "rate_limited": safe_res.get("rate_limited", False),
            },
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Processing timeout exceeded")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Processing error: {exc!s}") from exc


@app.get("/api/v1/health", response_model=HealthResponse, tags=["Monitoring"])
async def health_check() -> HealthResponse:
    """Comprehensive health check endpoint."""
    if not ai_integrator:
        return HealthResponse(
            status="initializing",
            uptime_seconds=0.0,
            version="4.0.0",
            components={},
            metrics={},
        )

    status_data = ai_integrator.get_system_status()
    return HealthResponse(
        status="healthy" if status_data.get("initialized") else "degraded",
        uptime_seconds=max(
            0.0, time.monotonic() - getattr(app.state, "started_at", time.monotonic())
        ),
        version="4.0.0",
        components={"integrator": "healthy", "auto_evolution": "healthy"},
        metrics=status_data.get("session_stats", {}),
    )


@app.get("/api/v1/status", tags=["Monitoring"])
async def system_status(_token: dict = Depends(get_current_user_token)) -> dict[str, Any]:
    """Detailed system status including all subsystems."""
    if not ai_integrator:
        raise HTTPException(status_code=503, detail="System not initialized")
    return ai_integrator.get_system_status()


@app.get("/api/v1/evolution/status", response_model=EvolutionStatusResponse, tags=["Evolution"])
async def evolution_status(
    _token: dict = Depends(get_current_user_token),
) -> EvolutionStatusResponse:
    """Get current evolution status and history."""
    if not ai_integrator or not ai_integrator.auto_evolution:
        raise HTTPException(status_code=503, detail="Evolution system not available")

    stats = ai_integrator.auto_evolution.get_statistics()
    return EvolutionStatusResponse(
        is_running=stats.get("is_running", True),
        total_cycles=stats.get("total_cycles", 0),
        successful_cycles=stats.get("successful_cycles", 0),
        recent_cycles=stats.get("recent_cycles", []),
    )


@app.post("/api/v1/evolution/trigger", tags=["Evolution"])
async def trigger_evolution(_token: dict = Depends(get_current_user_token)) -> dict[str, Any]:
    """Manually trigger an evolution cycle."""
    if not ai_integrator or not ai_integrator.auto_evolution:
        raise HTTPException(status_code=503, detail="Evolution system not available")

    cycle = await ai_integrator.auto_evolution.run_evolution_cycle()
    return {
        "message": "Evolution cycle triggered",
        "cycle_id": cycle.cycle_id,
        "status": cycle.state.value if hasattr(cycle.state, "value") else str(cycle.state),
        "improvements_measured": cycle.improvements_measured,
        "duration_seconds": cycle.duration_seconds,
    }


@app.get("/api/v1/memory/stats", response_model=MemoryStatsResponse, tags=["Memory"])
async def memory_statistics(_token: dict = Depends(get_current_user_token)) -> MemoryStatsResponse:
    """Get memory system statistics."""
    if not ai_integrator or not ai_integrator.memory_consolidator:
        raise HTTPException(status_code=503, detail="Memory system not available")

    stats = ai_integrator.memory_consolidator.get_memory_stats()
    return MemoryStatsResponse(
        total_entries=stats.get("total_blocks", 0),
        working_memory=stats.get("tiers", {}).get("working", 0),
        episodic_memory=stats.get("tiers", {}).get("episodic", 0),
        semantic_nodes=stats.get("tiers", {}).get("semantic", 0),
        estimated_size_mb=stats.get("estimated_size_mb", 0.0),
    )


@app.post("/api/v1/memory/consolidate", tags=["Memory"])
async def trigger_consolidation(_token: dict = Depends(get_current_user_token)) -> dict[str, Any]:
    """Trigger memory consolidation cycle."""
    if not ai_integrator or not ai_integrator.memory_consolidator:
        raise HTTPException(status_code=503, detail="Consolidation system not available")

    result = await ai_integrator.memory_consolidator.consolidate()
    return {
        "message": "Consolidation completed",
        "success": result.success,
        "action_taken": result.action_taken.value
        if hasattr(result.action_taken, "value")
        else str(result.action_taken),
        "blocks_affected": result.blocks_affected,
        "memory_freed_bytes": result.memory_freed_bytes,
        "time_ms": result.time_ms,
    }


@app.get("/api/v1/dashboard", tags=["Monitoring"])
async def dashboard_data(_token: dict = Depends(get_current_user_token)) -> dict[str, Any]:
    """Get comprehensive dashboard data for monitoring UI."""
    if not ai_integrator:
        raise HTTPException(status_code=503, detail="System not initialized")

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "system": ai_integrator.get_system_status(),
    }
