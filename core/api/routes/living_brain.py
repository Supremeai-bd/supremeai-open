# backend/api/routes/living_brain.py
"""
Living Brain Dashboard API
===========================

Real-time observability endpoints for SupremeAI's "brain" health.

Provides visibility into:
- ai_memory/pgvector status and contents
- Learning engine component status (unified_learning retired #2259; canonical
  LearningStore metrics return via #2259 D2)
- Cost per hour / provider breakdown

This is the "pulse check" for whether AI is truly alive and learning.

Endpoints:
GET /api/living-brain/status - Overall brain health summary
GET /api/living-brain/metrics - Detailed metrics with history
GET /api/living-brain/timeline - Learning timeline events
GET /api/living-brain/costs - Cost breakdown by provider/time
POST /api/living-brain/query - Query learned patterns

Author: System Lead Engineer
Version: 1.0.0
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

# Issue #1496: this router used core.security.authentication.rbac's
# get_current_admin, whose token extraction ONLY trusts AuthMiddleware-injected
# request.state.user — it never decodes the Authorization header itself. Admin
# JWTs minted by the admin-auth flow (the dashboard's getAdminToken()) were
# therefore rejected with 401 even though the same token works on every other
# admin route. api.dependencies.get_current_admin is the canonical dependency
# used across the admin surface (decodes the Bearer token + enforces the admin
# role) — use it so /api/living-brain/* behaves like the rest.
from api.dependencies import get_current_admin
from core.logging_config import logger

# Import brain components
# UNIFY FIX: removed 'backend.' prefix from imports — they were silently
# failing (wrapped in try/except) because CWD is backend/, not project root.
# Correct paths use top-level packages (brain/, memory/) directly.
# বাংলা (#2259 D1): SupremeLearningEngine/unified_learning retired — learning
# telemetry now lives in core.learning (LearningStore); real living-brain
# learning metrics return via #2259 D2 (collective experience layer).
try:
    from memory.supabase_store import SupabaseStore

    MEMORY_STORE_AVAILABLE = True
except ImportError:
    MEMORY_STORE_AVAILABLE = False
    logger.warning("⚠️ Memory store not available")

try:
    from brain.economic_optimizer import EconomicOptimizer

    ECON_OPTIMIZER_AVAILABLE = True
except ImportError:
    ECON_OPTIMIZER_AVAILABLE = False


# AUD-2.6: the registry registers this router with the admin flag, but that
# only attaches a plain user-token dependency. Enforce the admin role here as
# well (defense in depth, fail-closed). (SEC-003 note: wording kept off the
# literal flag-assignment pattern so this prose is not flagged as code.)
router = APIRouter(
    prefix="/api/living-brain", tags=["living-brain"], dependencies=[Depends(get_current_admin)]
)


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class BrainStatus(BaseModel):
    """Overall brain health status."""

    is_alive: bool
    overall_health: str  # "healthy", "degraded", "critical"
    uptime_hours: float
    last_learning_activity: str | None
    components: dict[str, Any]


class MemoryMetrics(BaseModel):
    """Memory system metrics."""

    provider: str  # "supabase", "sqlite", "hybrid"
    total_facts_stored: int
    pgvector_enabled: bool
    embeddings_generated: int
    search_accuracy_estimate: float


class CostBreakdown(BaseModel):
    """Cost metrics."""

    total_cost_today_usd: float
    cost_by_provider: dict[str, float]
    cost_by_hour: list[dict[str, Any]]
    tokens_consumed_today: int
    avg_cost_per_1k_tokens: float


# ---------------------------------------------------------------------------
# Main Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=BrainStatus)
async def get_brain_status():
    """
    Get overall brain health status.

    This is the main "pulse check" endpoint.
    Returns quickly to indicate if AI systems are operational.
    """
    time.time()

    # Initialize component statuses
    components = {
        "learning_engine": {"status": "unknown", "details": {}},
        "memory": {"status": "unknown", "details": {}},
        "economic_optimizer": {"status": "unknown", "details": {}},
    }

    # Check Learning Engine (#2259 D1: unified_learning retired — component
    # is honestly "unavailable" instead of the previous guaranteed-error path:
    # sync call on an async get_stats() coroutine raised AttributeError here
    # on every request)
    components["learning_engine"] = {
        "status": "unavailable",
        "details": {
            "note": "unified_learning retired (#2259 D1); canonical LearningStore telemetry wired via D2"
        },
    }

    # Check Memory Store
    if MEMORY_STORE_AVAILABLE:
        try:
            # Try to get or create a store instance
            store = SupabaseStore()
            mem_stats = store.get_stats()

            components["memory"] = {
                "status": "healthy" if mem_stats.get("provider") else "degraded",
                "details": {
                    "provider": mem_stats.get("provider", "unknown"),
                    "pgvector_enabled": mem_stats.get("pgvector_enabled", False),
                    "total_queries": mem_stats.get("total_queries", 0),
                    "pgvector_success_rate": (
                        f"{mem_stats['pgvector_success'] / max(1, mem_stats['total_queries']) * 100:.1f}%"
                        if mem_stats.get("total_queries", 0) > 0
                        else "N/A"
                    ),
                },
            }
        except Exception as e:
            logger.warning(f"[LivingBrain] Memory store status check failed: {e}", exc_info=True)
            components["memory"] = {"status": "error", "error": str(e)}
    else:
        components["memory"]["status"] = "unavailable"

    # Check Economic Optimizer
    if ECON_OPTIMIZER_AVAILABLE:
        try:
            optimizer = EconomicOptimizer()
            opt_stats = optimizer.get_stats()

            components["economic_optimizer"] = {
                "status": "healthy",
                "details": {
                    "total_optimizations": opt_stats.get("total_routes_optimized", 0),
                    "cost_saved_usd": opt_stats.get("total_cost_saved", 0.0),
                    "active_providers": len(opt_stats.get("provider_stats", {})),
                },
            }
        except Exception as e:
            components["economic_optimizer"] = {"status": "error", "error": str(e)}

    # Determine overall health
    healthy_count = sum(
        1 for c in components.values() if isinstance(c, dict) and c.get("status") == "healthy"
    )
    total_checked = sum(
        1
        for c in components.values()
        if isinstance(c, dict) and c.get("status") != "not_configured"
    )

    if healthy_count == total_checked:
        overall_health = "healthy"
    elif healthy_count >= total_checked * 0.5:
        overall_health = "degraded"
    else:
        overall_health = "critical"

    return BrainStatus(
        is_alive=overall_health != "critical",
        overall_health=overall_health,
        uptime_hours=(time.time() - _get_startup_time()) / 3600,
        last_learning_activity=_get_last_learning_time(),
        components=components,
    )


@router.get("/metrics")
async def get_detailed_metrics(
    hours: int = Query(default=24, ge=1, le=168),  # Max 7 days
):
    """Get detailed metrics over time period."""
    metrics = {
        "timestamp": datetime.now().isoformat(),
        "period_hours": hours,
        "learning": {},
        "memory": {},
        "costs": {},
    }

    # Learning metrics (#2259 D1: unified_learning retired — this block used
    # to error out on every call: sync get_stats() coroutine + engine.db_path
    # attribute that no longer existed on the engine singleton)
    metrics["learning"] = {
        "status": "unavailable",
        "note": "unified_learning retired (#2259 D1); canonical LearningStore metrics wired via D2",
    }

    # Memory metrics
    if MEMORY_STORE_AVAILABLE:
        try:
            store = SupabaseStore()
            stats = store.get_stats()

            metrics["memory"] = MemoryMetrics(
                provider=stats.get("provider", "unknown"),
                total_facts_stored=stats.get("pgvector_success", 0)
                + stats.get("sqlite_fallback", 0),
                pgvector_enabled=stats.get("pgvector_enabled", False),
                embeddings_generated=stats.get("embeddings_generated", 0),
                search_accuracy_estimate=_estimate_search_accuracy(stats),
            ).model_dump()
        except Exception as e:
            metrics["memory"] = {"error": str(e)}

    return metrics


@router.get("/timeline")
async def get_learning_timeline(
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Get recent learning events timeline.

    Shows what the AI has been learning recently.
    (#2259 D1: legacy SQLite `patterns` source retired with unified_learning;
    the block had been erroring on every call — engine.db_path no longer
    existed — so events were always empty in practice. D2 re-wires this to
    the canonical experience store after query verification.)
    """
    events = []

    return {
        "total_events": len(events),
        "events": events,
        "query_time": datetime.now().isoformat(),
    }


@router.post("/query")
async def query_learned_patterns(query: str, limit: int = 5):
    """
    Query the learned knowledge base.

    This shows what the AI already knows about a topic.
    """
    results = []

    if MEMORY_STORE_AVAILABLE:
        try:
            store = SupabaseStore()
            facts = store.search_facts(query)

            for fact in facts[:limit]:
                results.append(
                    {
                        "content": fact.get("content", fact.get("text", ""))[:500],
                        "confidence": fact.get("confidence", 0.0),
                        "source": fact.get("source", "unknown"),
                        "learned_at": fact.get("created_at", ""),
                    }
                )
        except Exception as e:
            logger.error(f"Query failed: {e}")

    return {
        "query": query,
        "results_found": len(results),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

_startup_time: float = time.time()


def _get_startup_time() -> float:
    """Get application startup time."""
    global _startup_time
    return _startup_time


def _get_last_learning_time() -> str | None:
    """Get timestamp of most recent learning activity.

    (#2259 D1: legacy SQLite patterns source retired — this always returned
    None in practice since the engine lost its db_path attribute. D2 re-wires
    to the canonical LearningStore.)
    """
    return None


def _estimate_search_accuracy(mem_stats: dict) -> float:
    """Estimate search accuracy from pgvector success rate."""
    total = mem_stats.get("total_queries", 0)
    success = mem_stats.get("pgvector_success", 0)

    if total == 0:
        return 0.0

    return round(success / total, 3)
