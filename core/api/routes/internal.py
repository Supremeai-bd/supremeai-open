import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, SecretStr

from core.config import settings
from core.logging_config import logger
from core.security.authentication.rbac import get_current_admin
from core.self_evolution.evolution_engine import EvolutionEngine

router = APIRouter(dependencies=[Depends(get_current_admin)])

# বাংলা: পাবলিক রিপোর জানা ডেভ ফলব্যাক মান — এগুলো দিয়ে কখনো
# internal admin API-তে প্রবেশ করা যাবে না (defense-in-depth; বুটেও
# config_validation প্রোডাকশনে এই মানগুলো রিজেক্ট করে)。
_ADMIN_SECRET_PUBLIC_FALLBACKS = frozenset({"", "dev_password_only"})


def _resolve_admin_secret() -> str:
    """Return the configured internal admin secret (no docs_password fallback)."""
    raw = getattr(settings, "supremeai_admin_secret", None)
    if isinstance(raw, SecretStr):
        return raw.get_secret_value()
    return raw or ""


def _require_admin(request: Request):
    secret = request.headers.get("X-Admin-Secret")
    expected = _resolve_admin_secret()
    # Fail-closed: no docs_password fallback — a publicly-known dev fallback
    # must never authenticate the internal admin API (P0 policy).
    if not expected or expected.lower() in _ADMIN_SECRET_PUBLIC_FALLBACKS:
        raise HTTPException(status_code=500, detail="Admin secret not configured on server.")
    if not secrets.compare_digest(secret or "", expected):
        raise HTTPException(status_code=403, detail="Forbidden: Invalid admin secret.")


class RunEvolutionRequest(BaseModel):
    task_history: list[dict[str, Any]] | None = None
    days: int | None = 7


@router.post("/internal/run-daily-evolution")
async def run_daily_evolution(request: Request, payload: RunEvolutionRequest):
    _require_admin(request)
    # BUG FIX #2: Use shared FitnessEngine singleton via EvolutionEngine.
    from api.deps import get_fitness_engine

    engine = EvolutionEngine(fitness_engine=get_fitness_engine())
    task_history = payload.task_history or []
    try:
        # বাংলা মন্তব্য: run_daily_evolution অ্যাসিঙ্ক হওয়ায় এখানে await ব্যবহার করা হলো।
        report = await engine.run_daily_evolution(task_history)
    except Exception as exc:
        logger.error(f"EvolutionEngine failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Evolution failed: {exc}") from exc
    try:
        from services.storage.gcp_firestore import GCPFirestoreVerificationQueue

        fq = GCPFirestoreVerificationQueue()
        if hasattr(fq, "provider") and fq.provider != "disabled":
            db = getattr(fq, "client", None)
            if db:
                db.collection("evolution_logs").add(report)
    except Exception as exc:
        logger.debug(f"Failed to persist evolution log to Firestore: {exc}")
    try:
        from database.supabase_client import db as supabase_db

        if supabase_db.service_client:
            supabase_db.append_evolution_log(report)
    except Exception as exc:
        logger.debug(f"Failed to persist evolution log to Supabase: {exc}")
    return report


class SystemAlertPayload(BaseModel):
    level: str
    message: str


@router.post("/api/v1/admin/alerts")
async def report_system_alert(request: Request, payload: SystemAlertPayload):
    """Canonical internal alert ingestion (issue #1497).

    Machine-to-machine alert reporting (API key or admin secret). The AI Log
    Analyzer (scripts/devops/ai_log_analyzer.py) consumes this endpoint; the
    legacy DB-persist variant POST /api/admin/alerts is deprecated in favor of
    this one.
    """
    # Allow if valid API key is present
    if not hasattr(request.state, "api_key") or not request.state.api_key:
        # Fallback to Admin Secret if API key is missing
        _require_admin(request)

    logger.bind(alert_level=payload.level).warning(f"System Alert Received: {payload.message}")

    # Optionally store in DB/Redis or emit via ErrorEventBus
    from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus

    error_event_bus.emit(
        ErrorEvent(
            module="ClientMonitor",
            error_type="CLIENT_ALERT",
            message=payload.message,
            severity=payload.level.upper(),
            structured_context=ErrorContext(
                module="tests.e2e",
                env=settings.env,
            ),
        )
    )

    return {"status": "received", "level": payload.level}
