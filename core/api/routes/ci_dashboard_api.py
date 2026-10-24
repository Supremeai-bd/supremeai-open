"""
================================================================================
SuperAI CI Dashboard API - Backend Integration
================================================================================
🔌 REST + WebSocket endpoints for CI/CD dashboard data
📊 Serves enhanced CI summaries to admin dashboard
⚡ Real-time updates via WebSocket push
💾 Stores historical CI data for trend analysis

ENDPOINTS:
─────────────────────────────────────────
REST:
  GET  /api/ci/summary/{run_id}     - Get specific run summary
  GET  /api/ci/latest-summary       - Get most recent summary (for dashboard)
  GET  /api/ci/history             - Get historical runs (paginated)
  GET  /api/ci/trends              - Get trend analysis data
  POST /api/ci/webhook             - Receive CI reports from GitHub Actions

WebSocket:
  WS   /ws/dashboard               - Real-time CI status updates
        ?channels=ci.summary,jobs.status,metrics.update

DATABASE MODELS (if using):
  - CISummary: Enhanced run summaries (JSON)
  - CIJob: Individual job results
  - CITrend: Historical metrics for trends

INTEGRATION:
─────────────────────────────────────────
1. Add to your FastAPI app:
   from ci_dashboard_api import router as ci_router
   app.include_router(ci_router)

2. Configure environment:
   CI_WEBHOOK_SECRET=your-secret-here
   CI_DATA_RETENTION_DAYS=30

3. Update GitHub Actions to call webhook on completion

Author: SuperAI Toolkit v2.0
Version: 2.0.0

CPU Impact: <2% when active, idle ~0%
================================================================================
"""

import asyncio
import hmac
import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket
from pydantic import BaseModel, Field

from core.config import settings
from core.logging_config import logger
from core.security.ws_auth import authenticate_websocket

# Set up logging

# Create router
router = APIRouter(
    prefix="/api/ci",
    tags=["CI Dashboard"],
    responses={404: {"description": "Not found"}, 500: {"description": "Internal error"}},
)


# ════════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ══════════════════════════════════════════════════════════════════════════════


class JobResultModel(BaseModel):
    """Individual job result model"""

    name: str
    status: str  # success, failure, cancelled, skipped, in_progress
    conclusion: str | None = None
    duration_seconds: float = 0.0
    url: str | None = None
    runner_name: str | None = None
    error_count: int = 0
    warning_count: int = 0
    is_flaky: bool = False
    performance_score: int = 100


class CIMetricsModel(BaseModel):
    """CI run metrics"""

    total_jobs: int = 0
    passed: int = 0
    failed: int = 0
    cancelled: int = 0
    skipped: int = 0
    success_rate: float = 0.0
    score: int = 0
    grade: str = "F"
    badges: list[str] = Field(default_factory=list)


class CIErrorModel(BaseModel):
    """Error entry model"""

    severity: str  # P0, P1, P2, P3
    severity_icon: str
    category: str
    message: str
    job: str
    line_number: int | None = None


class CIInsightModel(BaseModel):
    """Insight entry model"""

    icon: str
    title: str
    description: str
    category: str  # performance, quality, security, reliability
    severity: str
    action_item: str
    confidence: float  # 0.0 to 1.0


class CISummaryModel(BaseModel):
    """Complete CI Summary model (matches v2 output format)"""

    version: str = "2.0"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    repository: str = ""

    # Run info
    run_id: int = 0
    run_number: int = 0
    event_type: str = "push"
    branch: str = "main"
    commit_sha: str = ""
    commit_message: str = ""
    triggered_by: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float = 0.0

    # Metrics
    metrics: CIMetricsModel = Field(default_factory=CIMetricsModel)

    # Jobs
    jobs: list[JobResultModel] = Field(default_factory=list)

    # Errors & Warnings
    errors_total: int = 0
    errors_by_severity: dict[str, int] = Field(default_factory=dict)
    errors_by_category: dict[str, int] = Field(default_factory=dict)
    error_items: list[CIErrorModel] = Field(default_factory=list)
    warnings_total: int = 0
    warning_samples: list[str] = Field(default_factory=list)

    # Insights & Recommendations
    insights: list[CIInsightModel] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    # Trends (optional)
    trends_available: bool = False
    recent_success_rate: float | None = None
    overall_success_rate: float | None = None
    trend_direction: str | None = None  # improving, declining, stable
    prediction: dict[str, Any] | None = None


class WebhookPayload(BaseModel):
    """Incoming webhook payload from GitHub Actions"""

    secret: str  # For verification
    summary: CISummaryModel


# ══════════════════════════════════════════════════════════════════════════════
# IN-MEMORY STORAGE (Replace with DB in production)
# ══════════════════════════════════════════════════════════════════════════════

# In-memory storage for demo purposes
# In production, use PostgreSQL/MongoDB/Redis
_ci_summaries_store: dict[int, CISummaryModel] = {}  # run_id -> summary
# Audit B-11 fix (2026-09-17): bounded like _ci_history — prune oldest run_ids.
_MAX_SUMMARY_ITEMS = 200
_ci_history: list[dict[str, Any]] = []  # Ordered by timestamp (newest first)
_max_history_items = 50

# WebSocket connection managers
_ws_connections: list[WebSocket] = []


def _store_summary(summary: CISummaryModel):
    """Store a CI summary (in memory or DB)"""
    global _ci_summaries_store, _ci_history

    # Store by run_id
    _ci_summaries_store[summary.run_id] = summary

    # Audit B-11: keep the store bounded — evict oldest runs by timestamp.
    if len(_ci_summaries_store) > _MAX_SUMMARY_ITEMS:
        oldest_ids = sorted(
            _ci_summaries_store,
            key=lambda rid: getattr(_ci_summaries_store[rid], "timestamp", None) or 0,
        )
        for rid in oldest_ids[: len(_ci_summaries_store) - _MAX_SUMMARY_ITEMS]:
            _ci_summaries_store.pop(rid, None)

    # Add to history
    history_entry = {
        "run_id": summary.run_id,
        "run_number": summary.run_number,
        "timestamp": summary.timestamp.isoformat(),
        "branch": summary.branch,
        "event": summary.event_type,
        "commit_sha": summary.commit_sha[:8],
        "success_rate": summary.metrics.success_rate,
        "score": summary.metrics.score,
        "grade": summary.metrics.grade,
        "duration": summary.duration_seconds,
        "total_jobs": summary.metrics.total_jobs,
        "passed": summary.metrics.passed,
        "failed": summary.metrics.failed,
        "repository": summary.repository,
    }

    # Insert at beginning (newest first)
    _ci_history.insert(0, history_entry)

    # Trim to max size
    if len(_ci_history) > _max_history_items:
        _ci_history = _ci_history[:_max_history_items]

    logger.info(f"Stored CI summary for run #{summary.run_number} ({summary.repository})")


async def _broadcast_to_websockets(event_type: str, data: dict[str, Any]):
    """Broadcast data to all connected WebSocket clients"""
    if not _ws_connections:
        return

    message = json.dumps(
        {
            "channel": f"ci.{event_type}",
            "type": f"ci_{event_type}",
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
    )

    # Send to all connections (with error handling)
    disconnected = []
    for ws in _ws_connections:
        try:
            await ws.send_text(message)
        except Exception as e:
            logger.warning(f"WebSocket send failed: {e}")
            disconnected.append(ws)

    # Remove disconnected
    for ws in disconnected:
        _ws_connections.remove(ws)


# ══════════════════════════════════════════════════════════════════════════════
# WEBHOOK ENDPOINT (Receives data from GitHub Actions)
# ══════════════════════════════════════════════════════════════════════════════


@router.post("/webhook")
async def receive_ci_webhook(payload: WebhookPayload):
    """
    Receive CI summary from GitHub Actions workflow.

    Called by ci_summary_v2.py after generating summary.
    Expects X-CI-Webhook-Secret header for verification.
    """
    # বাংলা মন্তব্য (Wave-1 security fix): তিনটি দুর্বলতা ঠিক করা হলো —
    # (১) আগে secret unset থাকলে fail-open হতো (যেকোনো কলার CI ডেটা ঢোকাতে পারত),
    # এখন n8n/cdc-র মতো কঠোর fail-closed: secret না থাকলে উঁচু লগ + 401;
    # (২) আগে raw os.environ.get() ব্যবহার হতো যা Settings-এর Single Source of
    # Truth bypass করত — এখন settings.ci_webhook_secret (config_secrets.py);
    # (৩) আগে plain != তুলনা ছিল — timing attack এড়াতে constant-time compare।
    expected_secret = settings.ci_webhook_secret
    if not expected_secret:
        logger.error(
            "CI_WEBHOOK_SECRET is not configured! "
            "Rejecting all CI hook submissions under fail-closed policy."
        )
        raise HTTPException(status_code=401, detail="CI webhook secret not configured")

    provided_secret = str(payload.secret or "")
    if not hmac.compare_digest(provided_secret.encode("utf-8"), expected_secret.encode("utf-8")):
        logger.warning("CI hook submission rejected: invalid secret")
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # Store the summary
    summary = payload.summary
    _store_summary(summary)

    # Broadcast to WebSocket clients
    await _broadcast_to_websockets("summary_updated", summary.dict())

    return {
        "status": "received",
        "run_id": summary.run_id,
        "run_number": summary.run_number,
        "grade": summary.metrics.grade,
        "score": summary.metrics.score,
        "stored_at": datetime.utcnow().isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# REST API ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════


@router.get("/latest-summary", response_model=CISummaryModel)
async def get_latest_summary():
    """
    Get the most recent CI summary for dashboard display.

    This is the primary endpoint called by the React CIDashboard component
    on initial load and during refresh.
    """
    if not _ci_history:
        raise HTTPException(status_code=404, detail="No CI data available yet")

    latest = _ci_history[0]
    run_id = latest.get("run_id")

    if run_id and run_id in _ci_summaries_store:
        summary = _ci_summaries_store[run_id]
        return summary

    # Return basic info from history if full summary not available
    return CISummaryModel(
        version="2.0",
        repository=latest.get("repository", "Unknown"),
        run_id=run_id or 0,
        run_number=latest.get("run_number", 0),
        event_type=latest.get("event", "unknown"),
        branch=latest.get("branch", "main"),
        commit_sha=latest.get("commit_sha", ""),
        triggered_by=latest.get("triggered_by", "system"),
        duration_seconds=latest.get("duration", 0),
        metrics=CIMetricsModel(
            total_jobs=latest.get("total_jobs", 0),
            passed=latest.get("passed", 0),
            failed=latest.get("failed", 0),
            success_rate=latest.get("success_rate", 0),
            score=latest.get("score", 0),
            grade=latest.get("grade", "N/A"),
        ),
        trends_available=len(_ci_history) >= 5,
    )


@router.get("/summary/{run_id}", response_model=CISummaryModel)
async def get_summary_by_run_id(run_id: int):
    """
    Get CI summary for a specific workflow run.

    Used for viewing historical build details.
    """
    if run_id in _ci_summaries_store:
        return _ci_summaries_store[run_id]

    raise HTTPException(status_code=404, detail=f"Summary not found for run ID {run_id}")


@router.get("/history")
async def get_ci_history(
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    branch: str | None = Query(None, description="Filter by branch"),
    event_type: str | None = Query(None, description="Filter by event type (push, schedule, etc.)"),
    min_score: int | None = Query(None, ge=0, le=100, description="Minimum score filter"),
):
    """
    Get paginated CI history with optional filters.

    Used for building trend charts and historical views.
    """
    history = _ci_history.copy()

    # Apply filters
    if branch:
        history = [h for h in history if h.get("branch") == branch]

    if event_type:
        history = [h for h in history if h.get("event") == event_type]

    if min_score is not None:
        history = [h for h in history if h.get("score", 0) >= min_score]

    # Paginate
    total = len(history)
    paginated = history[offset : offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": paginated,
        "filters_applied": {
            "branch": branch,
            "event_type": event_type,
            "min_score": min_score,
        },
    }


@router.get("/trends")
async def get_trend_analysis(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    branch: str | None = Query(None, description="Filter by branch"),
):
    """
    Get trend analysis data including success rates over time.

    Calculates:
    - Overall success rate
    - Recent success rate (last N days)
    - Trend direction (improving/declining/stable)
    - Prediction for next build
    - Top failing categories
    """
    if len(_ci_history) < 3:
        return {"available": False, "reason": "Need at least 3 completed builds for trend analysis"}

    # Filter by date range
    cutoff = datetime.utcnow() - timedelta(days=days)
    recent = [
        h
        for h in _ci_history
        if datetime.fromisoformat(h["timestamp"]) >= cutoff
        and (not branch or h.get("branch") == branch)
    ]

    if len(recent) < 3:
        return {
            "available": False,
            "reason": f"Not enough data points in last {days} days (found {len(recent)})",
        }

    # Calculate metrics
    success_rates = [h["success_rate"] for h in recent]
    scores = [h["score"] for h in recent]
    durations = [h["duration"] for h in recent]

    overall_rate = sum(success_rates) / len(success_rates)
    recent_rate = sum(success_rates[-5:]) / min(5, len(success_rates))

    # Simple linear regression for trend direction
    n = len(success_rates)
    x_mean = (n - 1) / 2
    y_mean = sum(success_rates) / n

    numerator = sum((i - x_mean) * (success_rates[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    slope = numerator / denominator if denominator != 0 else 0

    if slope > 0.02:
        trend = "improving"
        strength = min(abs(slope) * 100, 1.0)
    elif slope < -0.02:
        trend = "declining"
        strength = min(abs(slope) * 100, 1.0)
    else:
        trend = "stable"
        strength = 0

    # Prediction
    weighted_recent = success_rates[-5:] if len(success_rates) >= 5 else success_rates
    weights = [0.1, 0.15, 0.2, 0.25, 0.3][-len(weighted_recent) :]
    prediction_prob = (
        sum(w * s for w, s in zip(weights, weighted_recent, strict=True))
        if weighted_recent
        else overall_rate
    )

    prediction_confidence = min(len(_ci_history) / 20, 0.95)

    if prediction_prob > 0.75:
        verdict = "likely_pass"
    elif prediction_prob > 0.45:
        verdict = "uncertain"
    else:
        verdict = "risk_of_failure"

    # Error category analysis (would need detailed data)
    error_categories = {}
    for entry in recent:
        if entry.get("failed", 0) > 0:
            # In real implementation, pull from stored error breakdowns
            error_categories["Build Failure"] = error_categories.get(
                "Build Failure", 0
            ) + entry.get("failed", 0)

    # Generate recommendations
    recommendations = []

    if trend == "declining":
        recommendations.append("📉 Success rate declining - investigate recent changes")

    if recent_rate < 80:
        recommendations.append("⚠️ Recent success rate below 80% - review failures")

    if any(d > 1800 for d in durations[-5:]):
        avg_duration = sum(durations[-5:]) / min(5, len(durations))
        recommendations.append(f"⚡ Build times increasing (avg: {avg_duration / 60:.1f}min)")

    if not recommendations:
        recommendations.append("✅ Pipeline performing well - maintain current practices")

    return {
        "available": True,
        "analysis_period_days": days,
        "total_analyzed": len(recent),
        "overall_success_rate": round(overall_rate, 2),
        "recent_success_rate": round(recent_rate, 2),
        "trend_direction": trend,
        "trend_strength": round(strength, 2),
        "prediction": {
            "success_probability": round(prediction_prob * 100, 1),
            "confidence": round(prediction_confidence * 100, 1),
            "verdict": verdict,
        },
        "averages": {
            "score": round(sum(scores) / len(scores), 1) if scores else 0,
            "duration_seconds": round(sum(durations) / len(durations), 1) if durations else 0,
            "jobs_per_run": round(sum(h.get("total_jobs", 0) for h in recent) / len(recent), 1),
        },
        "error_breakdown": error_categories,
        "recommendations": recommendations,
        "chart_data": [
            {
                "date": h["timestamp"][:10],
                "success_rate": h["success_rate"],
                "score": h["score"],
                "duration": h.get("duration", 0),
                "label": f"#{h.get('run_number', '?')}",
            }
            for h in recent[-14:]  # Last 14 entries
        ],
    }


@router.get("/stats/overview")
async def get_stats_overview():
    """
    Get quick stats overview for dashboard header/widgets.

    Lightweight endpoint for showing summary cards without loading full data.
    """
    if not _ci_history:
        return {
            "total_runs": 0,
            "overall_success_rate": 0,
            "avg_score": 0,
            "last_build": None,
            "trend": "no_data",
        }

    # Calculate from history
    total = len(_ci_history)
    rates = [h["success_rate"] for h in _ci_history]
    scores = [h["score"] for h in _ci_history]

    return {
        "total_runs": total,
        "overall_success_rate": round(sum(rates) / len(rates), 2) if rates else 0,
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "last_build": _ci_history[0] if _ci_history else None,
        "last_7day_rate": round(sum(rates[:7]) / min(7, len(rates)), 2) if rates else 0,
        "trend": "up"
        if (rates[-1] if rates else 0) > (rates[0] if len(rates) > 1 else 0)
        else "down"
        if total > 1
        else "stable",
        "top_branches": list(set(h.get("branch", "main") for h in _ci_history[:20]))[:5],
    }


# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════


@router.websocket("/ws/dashboard")
async def ci_dashboard_websocket(websocket: WebSocket, token: str = Query(...)):
    """
    WebSocket connection for real-time CI updates.

    Clients can subscribe to channels:
    - ci.summary: Full summary updates
    - jobs.status: Individual job status changes
    - metrics.update: System metric updates
    - alerts.emergency: Critical alerts

    Message format (server -> client):
    {
        "channel": "ci.summary",
        "type": "updated",
        "data": { ... CISummaryModel ... },
        "timestamp": "ISO-8601"
    }
    """
    # AUD-2.1: the token query param was previously accepted but never verified —
    # any anonymous client could stream CI runs/metrics/alerts. Verify it now.
    user = await authenticate_websocket(websocket, token)
    if user is None:
        return

    _ws_connections.append(websocket)
    logger.info(f"WebSocket connected. Total clients: {len(_ws_connections)}")

    # Send current state immediately
    if _ci_history:
        welcome_data = {
            "channel": "ci.system",
            "type": "connected",
            "data": {
                "message": "Connected to CI Dashboard",
                "available_runs": len(_ci_history),
                "latest_run": _ci_history[0] if _ci_history else None,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
        await websocket.send_json(welcome_data)

    try:
        # Keep connection alive and handle any client messages
        while True:
            # Wait for client message (ping, channel subscription, etc.)
            data = await websocket.receive_text()

            try:
                message = json.loads(data)

                # Handle ping/pong
                if message.get("type") == "ping":
                    await websocket.send_json(
                        {"type": "pong", "timestamp": datetime.utcnow().isoformat()}
                    )

                # Handle channel subscription
                elif message.get("action") == "subscribe":
                    channels = message.get("channels", [])
                    await websocket.send_json(
                        {
                            "type": "subscribed",
                            "channels": channels,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )

            except asyncio.CancelledError:
                raise
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(f"Silenced error: {e}")

    except Exception as e:
        logger.warning(f"WebSocket error: {e}")

    finally:
        # Cleanup on disconnect
        if websocket in _ws_connections:
            _ws_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Remaining clients: {len(_ws_connections)}")


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════


@router.get("/health")
async def health_check():
    """Health check for CI API"""
    return {
        "status": "healthy",
        "service": "ci-dashboard-api",
        "version": "2.0.0",
        "stored_summaries": len(_ci_summaries_store),
        "history_entries": len(_ci_history),
        "websocket_clients": len(_ws_connections),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.delete("/cache")
async def clear_cache(
    older_than_days: int = Query(30, ge=1, description="Remove entries older than N days"),
    confirm: bool = Query(False, description="Must be true to confirm deletion"),
):
    """
    Clear old cached CI data.

    Use with caution! This removes historical data used for trends.
    """
    if not confirm:
        raise HTTPException(
            status_code=400, detail="Set confirm=true to proceed with cache clearing"
        )

    global _ci_history, _ci_summaries_store

    cutoff = datetime.utcnow() - timedelta(days=older_than_days)
    before_count = len(_ci_history)

    # Remove old entries
    _ci_history = [h for h in _ci_history if datetime.fromisoformat(h["timestamp"]) >= cutoff]

    # Also clean up summaries store
    old_run_ids = [rid for rid, summ in _ci_summaries_store.items() if summ.timestamp < cutoff]
    for rid in old_run_ids:
        del _ci_summaries_store[rid]

    removed = before_count - len(_ci_history)

    return {
        "status": "completed",
        "entries_removed": removed,
        "remaining": len(_ci_history),
        "cutoff_date": cutoff.isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# APP INCLUDE HELPER
# ══════════════════════════════════════════════════════════════════════════════


def get_router() -> APIRouter:
    """Get the router for inclusion in main app."""
    return router
