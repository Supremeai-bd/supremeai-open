import json
import os
import secrets
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from core.logging_config import logger
from pydantic import BaseModel

from admin.god import AdminGodLayer  # Your existing god.py
from api.dependencies import get_current_admin
from core.cache.redis_manager import redis_manager
from core.health.self_healer import SelfHealerService
from utils.firestore_helpers import get_firestore_db

router = APIRouter(
    prefix="/api/admin",
    tags=["Core Admin"],
    dependencies=[Depends(get_current_admin)],
)
_db_path = str(Path(__file__).resolve().parent.parent.parent / "data" / "admin_rules.db")
god_layer = AdminGodLayer(db_path=_db_path)


def get_healer_service() -> SelfHealerService:
    db = get_firestore_db()
    if not db:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return SelfHealerService(db)


def require_tenant_id(tenant_id: str | None) -> str:
    """Reject unscoped admin operations instead of using a shared tenant."""
    normalized = str(tenant_id or "").strip()
    if not normalized or normalized == "default":
        raise HTTPException(status_code=400, detail="Tenant context required")
    return normalized


class RuleUpdate(BaseModel):
    key: str
    value: str


@router.post("/rules")
async def update_constitutional_rule(
    payload: RuleUpdate, admin_user: dict = Depends(get_current_admin)
):
    """Update God.py constitutional rules directly from the Command Center UI.

    Issue #1497 path-disambiguation: /api/admin/rules is the CONSTITUTIONAL
    (GodLayer) rules surface — a different concept from the rules-engine
    feature switches served canonically at /admin-api/rules. The similar
    paths are intentional; do not merge them.
    """
    try:
        god_layer.set_rule(payload.key, payload.value)
        logger.critical(
            f"🔒 Constitutional rule '{payload.key}' changed to '{payload.value}' by {admin_user.get('sub')}"
        )
        return {
            "status": "success",
            "message": f"Rule {payload.key} updated to {payload.value}",
        }
    except Exception as e:
        # AUD-2.9 follow-up (MANUAL_STEPS 7.4): generic 500 + correlation id —
        # raw exception text must not reach even admin clients (defense in depth).
        correlation_id = uuid.uuid4().hex[:12]
        logger.exception(
            f"constitutional rule update failed key={payload.key!r} correlation_id={correlation_id}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (correlation_id: {correlation_id})",
        ) from e


@router.post("/actions/{action_type}")
async def trigger_quick_action(action_type: str, admin_user: dict = Depends(get_current_admin)):
    """Trigger 1-click Quick Actions from Dashboard"""
    # Verify if admin actions are currently allowed by god.py
    god_layer.enforce("admin_action")
    # বাংলা মন্তব্য: Structured audit log entry
    import uuid

    audit_id = uuid.uuid4().hex[:12]
    admin_email = admin_user.get("sub", "unknown")
    logger.critical(
        f"🔒 [ADMIN_ACTION] audit_id={audit_id} action={action_type} admin={admin_email} timestamp={datetime.now(UTC).isoformat()}"
    )

    # বাংলা মন্তব্য: অ্যাকশন সম্পন্ন হওয়ার পর result log করা হবে
    def _admin_action_audit(result: str) -> None:
        logger.critical(
            f"🔒 [ADMIN_ACTION_RESULT] audit_id={audit_id} action={action_type} admin={admin_email} result={result}"
        )

    logger.critical(f"🔒 Admin quick-action '{action_type}' requested by {admin_user.get('sub')}")

    # বাংলা মন্তব্য: প্রতিটি কুইক অ্যাকশনের জন্য রিয়েল ইমপ্লিমেন্টেশন করা হয়েছে
    if action_type == "cache":
        redis_client = redis_manager.client
        if redis_client:
            # সেশন ও ওটিপি কী সুরক্ষিত রাখতে শুধুমাত্র সাধারণ ক্যাশ প্যাটার্নগুলো স্ক্যান করে ডিলেট করা হচ্ছে
            patterns = [
                "bhasha_bot:*",
                "user_profile:*",
                "user_session:*",
                "semantic_cache:*",
                "cache:*",
                "health:*",
            ]
            total_deleted = 0
            for pattern in patterns:
                keys = await redis_client.keys(pattern)
                if keys:
                    await redis_client.delete(*keys)
                    total_deleted += len(keys)
            logger.info(f"Successfully cleared {total_deleted} cache keys from Redis.")
            _admin_action_audit("success")
            return {
                "status": "success",
                "message": f"Selective cache cleared. Deleted {total_deleted} keys.",
                "audit_id": audit_id,
            }
        else:
            _admin_action_audit("failed - redis unavailable")
            raise HTTPException(status_code=503, detail="Redis client unavailable")

    elif action_type == "backup":
        # বাংলা মন্তব্য: ডাটাবেস টেবিল স্ক্যান করে JSON ব্যাকআপ ফাইল তৈরি করার ব্যাকগ্রাউন্ড টাস্ক
        try:
            import re

            from sqlalchemy import text

            from database.session import get_db_session

            # বাংলা মন্তব্য: টেবিল নামের বৈধতা যাচাই করতে রেগুলার এক্সপ্রেশন প্যাটার্ন ডিফাইন করা হলো।
            _VALID_TABLE_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,64}$")

            backup_data = {}
            async for session in get_db_session():
                result = await session.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
                    )
                )
                tables = [row[0] for row in result.fetchall()]
                # ISSUE-1588: SQL identifiers cannot be bound as query parameters,
                # so quoting MUST go through SQLAlchemy's dialect identifier
                # preparer — never a hand-rolled f-string inside text().
                preparer = session.bind.dialect.identifier_preparer
                for table in tables:
                    if not _VALID_TABLE_PATTERN.match(table):
                        logger.warning(f"Skipping table '{table}' due to invalid naming pattern.")
                        continue
                    safe_table = preparer.quote(table)
                    rows_res = await session.execute(text(f"SELECT * FROM {safe_table}"))
                    columns = rows_res.keys()
                    rows = [dict(zip(columns, row, strict=False)) for row in rows_res.fetchall()]
                    for row in rows:
                        for k, v in row.items():
                            if hasattr(v, "isoformat"):
                                row[k] = v.isoformat()
                    backup_data[table] = rows

            backend_dir = Path(__file__).resolve().parent.parent.parent
            backup_dir = backend_dir / "backup"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"db_backup_{int(datetime.now(UTC).timestamp())}.json"

            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, indent=2)

            logger.info(f"Database backup saved successfully to {backup_path}")
            _admin_action_audit("success")
            return {
                "status": "success",
                "message": f"Database backup saved successfully to {backup_path.name}",
                "audit_id": audit_id,
            }
        except Exception as e:
            logger.error(f"Database backup failed: {e}")
            _admin_action_audit(f"failed - {str(e)}")
            raise HTTPException(status_code=500, detail=f"Database backup failed: {e}") from e

    elif action_type == "rollback":
        # বাংলা মন্তব্য: Alembic প্রোগ্রামাটিক রোলব্যাক মেকানিজম
        try:
            # ruff: noqa: I001
            from alembic import command
            from alembic.config import Config

            alembic_cfg = Config("backend/alembic.ini")
            alembic_cfg.set_main_option("script_location", "backend/alembic_migrations")
            command.downgrade(alembic_cfg, "-1")

            logger.info("Alembic rollback to previous revision completed successfully.")
            _admin_action_audit("success")
            return {
                "status": "success",
                "message": "Database rollback to previous revision executed successfully.",
                "audit_id": audit_id,
            }
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            _admin_action_audit(f"failed - {str(e)}")
            raise HTTPException(status_code=500, detail=f"Rollback operation failed: {e}") from e

    else:
        raise HTTPException(status_code=404, detail="Action not found")


@router.get("/fixes")
async def get_fixes(
    tenant_id: str | None = None,
    status: str = "pending_review",
    admin_user: dict = Depends(get_current_admin),
    healer: SelfHealerService = Depends(get_healer_service),
):
    """Fetch fixes with a specific status (admin read model).

    Issue #1470 (HIGH): GET /api/admin/fixes used to hard-fail with
    400 "Tenant context required" whenever no tenant_id was supplied — the
    admin fixes view was unusable even for authenticated admins. Admins hold
    god-level visibility, so the read endpoint now supports both modes:

    - ``tenant_id`` given → tenant-scoped query (behaviour unchanged);
    - no ``tenant_id``    → cross-tenant collectionGroup('fixes') query,
      each fix tagged with its owning tenant.

    Mutating endpoints (apply/approve/reject) still require an explicit
    tenant_id — a mass mutation must never be implicit.
    """
    db = get_firestore_db()
    if not db:
        raise HTTPException(status_code=503, detail="Database unavailable")

    if tenant_id:
        tenant_id = require_tenant_id(tenant_id)
        fixes_ref = db.collection("tenants").document(tenant_id).collection("fixes")
        query = fixes_ref.where("status", "==", status)
        try:
            results = await query.get()
        except TypeError:
            # Fallback for sync mock
            results = query.get()

        fixes = []
        for doc in results:
            fix_data = doc.to_dict()
            fix_data["id"] = doc.id
            fixes.append(fix_data)

        return {"fixes": fixes}

    # Cross-tenant read: tenants/<tid>/fixes/<fid> via collectionGroup.
    query = db.collection_group("fixes").where("status", "==", status)
    try:
        results = await query.get()
    except TypeError:
        # Fallback for sync mock
        results = query.get()

    fixes = []
    for doc in results:
        fix_data = doc.to_dict()
        fix_data["id"] = doc.id
        # Owning tenant lives two levels up the doc path
        # (…/tenants/<tid>/fixes/<doc>); resolve defensively so simple
        # mocks without a reference chain still serialize.
        reference = getattr(doc, "reference", None)
        fixes_collection = getattr(reference, "parent", None)
        tenant_doc = getattr(fixes_collection, "parent", None)
        owning_tenant = getattr(tenant_doc, "id", None)
        if owning_tenant:
            fix_data["tenant_id"] = owning_tenant
        fixes.append(fix_data)

    return {"fixes": fixes}


# CI FIX: frontend OneClickPatch.tsx:29 calls POST /api/admin/fixes/apply
# and ArchitectTower.tsx:18 calls POST /api/admin/fixes to trigger one-click
# fix application. Added POST aliases.
@router.post("/fixes")
@router.post("/fixes/apply")
async def apply_fixes(
    tenant_id: str | None = None,
    admin_user: dict = Depends(get_current_admin),
    healer: SelfHealerService = Depends(get_healer_service),
):
    """Apply all pending fixes for a tenant (one-click patch)."""
    tenant_id = require_tenant_id(tenant_id)
    admin_id = admin_user.get("sub", "unknown_admin")
    logger.info(f"Admin {admin_id} applying all pending fixes for tenant {tenant_id}")

    # Get all pending fixes
    db = get_firestore_db()
    if not db:
        return {"status": "success", "applied": 0, "message": "No Firestore available"}

    fixes_ref = db.collection("tenants").document(tenant_id).collection("fixes")
    query = fixes_ref.where("status", "==", "pending_review")
    docs = query.stream()

    applied = 0
    for doc in docs:
        success = await healer.apply_fix(tenant_id, doc.id, admin_id)
        if success:
            applied += 1

    return {
        "status": "success",
        "applied": applied,
        "message": f"Applied {applied} fix(es) for tenant {tenant_id}",
    }


@router.post("/fixes/{fix_id}/approve")
async def approve_fix(
    fix_id: str,
    tenant_id: str | None = None,
    admin_user: dict = Depends(get_current_admin),
    healer: SelfHealerService = Depends(get_healer_service),
):
    """Approve a pending fix."""
    tenant_id = require_tenant_id(tenant_id)
    admin_id = admin_user.get("sub", "unknown_admin")
    logger.info(f"Admin {admin_id} approving fix {fix_id} for tenant {tenant_id}")

    success = await healer.apply_fix(tenant_id, fix_id, admin_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to apply fix. It may not exist or is already processed.",
        )

    return {"status": "success", "fix_id": fix_id}


@router.post("/fixes/{fix_id}/reject")
async def reject_fix(
    fix_id: str,
    tenant_id: str | None = None,
    admin_user: dict = Depends(get_current_admin),
):
    """Reject a pending fix."""
    tenant_id = require_tenant_id(tenant_id)
    admin_id = admin_user.get("sub", "unknown_admin")
    logger.info(f"Admin {admin_id} rejecting fix {fix_id} for tenant {tenant_id}")

    db = get_firestore_db()
    doc_ref = db.collection("tenants").document(tenant_id).collection("fixes").document(fix_id)

    update_data = {
        "status": "rejected",
        "reviewed_by": admin_id,
        "applied_at": datetime.now(UTC).isoformat(),
    }

    try:
        await doc_ref.update(update_data)
    except TypeError:
        doc_ref.update(update_data)

    return {"status": "success", "fix_id": fix_id}


class VerifyOtpRequest(BaseModel):
    code: str


@router.post("/verify-otp")
async def verify_otp(payload: VerifyOtpRequest, admin_user: dict = Depends(get_current_admin)):
    """Validate a JIT OTP issued by AntiHackingContextMiddleware and promote the
    pending (mismatched) context to trusted, so the admin isn't re-challenged
    on their next request from this IP/fingerprint.

    বাংলা: অ্যাডমিন OTP সাবমিট করলে এখানে ভ্যালিডেট হয় এবং সফল হলে Redis-এ
    ট্রাস্টেড কনটেক্সট (last_context) আপডেট হয়ে যায়।
    """
    admin_id = admin_user.get("sub", "unknown_admin")

    if not redis_manager or not redis_manager.client:
        raise HTTPException(status_code=503, detail="Security store unavailable")

    pending_key = f"security:otp_pending:{admin_id}"
    raw_pending = await redis_manager.get_cache(pending_key)
    if not raw_pending:
        raise HTTPException(
            status_code=400,
            detail="No pending verification for this admin, or it has expired",
        )

    pending = json.loads(raw_pending)

    if not secrets.compare_digest(str(pending["code"]), str(payload.code)):
        logger.warning(f"❌ Failed OTP verification attempt for admin {admin_id}")
        raise HTTPException(status_code=401, detail="Invalid code")

    # বাংলা: সফল ভেরিফিকেশনে বর্তমান (আগে মিসম্যাচড) সিগন্যালকেই নতুন ট্রাস্টেড কনটেক্সট হিসেবে সেট করা হচ্ছে
    await redis_manager.set_cache(
        f"security:last_context:{admin_id}",
        json.dumps(pending["signal"]),
        ex_seconds=86400,
    )
    await redis_manager.client.delete(pending_key)

    logger.info(f"✅ Admin {admin_id} passed OTP verification — context promoted to trusted")
    return {"status": "verified"}


# বাংলা মন্তব্ত: AUDIT-018 ফিক্স — useAdminApi.ts-এর useAdminRules() হুক
# GET /api/admin/rules কল করে, কিন্তু আগে শুধু POST /rules ছিল।
# এখন GET endpoint যোগ করা হয়েছে যাতে rules লিস্ট ফেচ করা যায়।
@router.get("/rules")
async def get_rules(admin_user: dict = Depends(get_current_admin)):
    """Fetch all constitutional rules from God.py.

    Issue #1497 path-disambiguation: constitutional (GodLayer) rules — NOT the
    rules-engine switches at /admin-api/rules.
    """
    rules = god_layer.list_rules()
    return {"rules": rules}


# 🚨 System Alerts Endpoints
from fastapi import Header
from sqlalchemy import select, update

from database.session import get_db_session
from models.system_alert import SystemAlert


class AlertCreate(BaseModel):
    level: str
    message: str


@router.get("/alerts")
async def get_system_alerts(admin_user: dict = Depends(get_current_admin)):
    """Fetch all active system alerts."""
    async for session in get_db_session():
        stmt = select(SystemAlert).order_by(SystemAlert.created_at.desc()).limit(100)
        result = await session.execute(stmt)
        alerts = result.scalars().all()
        return {"alerts": alerts}


@router.post("/alerts", deprecated=True)
async def create_system_alert(payload: AlertCreate, x_api_key: str = Header(None)):
    """Deprecated legacy ingestion alias (issue #1497).

    Canonical internal alert ingestion is POST /api/v1/admin/alerts
    (api/routes/internal.py) — the AI Log Analyzer caller (scripts/devops/
    ai_log_analyzer.py) already uses it. This DB-persist variant is retained
    only for legacy-contract compatibility; new callers must use the
    canonical endpoint.
    """
    from core.config import settings

    expected_key = (
        settings.supremeai_api_key.get_secret_value() if settings.supremeai_api_key else None
    )
    if not expected_key or x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid internal API key")

    async for session in get_db_session():
        import uuid

        new_alert = SystemAlert(id=str(uuid.uuid4()), level=payload.level, message=payload.message)
        session.add(new_alert)
        await session.commit()
        return {"status": "success", "id": new_alert.id}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_system_alert(alert_id: str, admin_user: dict = Depends(get_current_admin)):
    """Mark an alert as resolved."""
    async for session in get_db_session():
        stmt = (
            update(SystemAlert)
            .where(SystemAlert.id == alert_id)
            .values(resolved=True, resolved_at=datetime.now(UTC))
        )
        await session.execute(stmt)
        await session.commit()
        return {"status": "success", "message": "Alert resolved"}


# ── Model branding (single source of truth for SupremeAI display names) ──
from utils.branding import MODEL_DISPLAY, PROVIDER_DISPLAY


@router.get("/model-branding")
async def model_branding(admin_user: dict = Depends(get_current_admin)):
    """Return the canonical SupremeAI model/provider branding maps.

    The frontend can call this to stay in sync instead of hardcoding labels.
    """
    return {
        "models": {k: v["label"] for k, v in MODEL_DISPLAY.items()},
        "providers": PROVIDER_DISPLAY,
    }


@router.post("/configs/refresh")
async def refresh_system_configs(admin_user: dict = Depends(get_current_admin)):
    """Hot-Reload model registries and system thresholds from the database without a restart.

    PATCH v4 (2026-08-30): Replaced `asyncio.gather(6 × sync_from_db(db))` with
    sequential `await` statements on the SAME shared `AsyncSession`. The
    gather pattern triggered asyncpg `isce` ("concurrent operations are not
    permitted") in production because SQLAlchemy AsyncSession does not support
    concurrent operations on a single underlying connection. This is the
    same fix already applied to `core/startup/services.py` in commit 3b6e09db05.
    """
    from database.session import get_db_session_context
    from brain.model_registry import ModelRegistry
    from brain.economic_optimizer import get_economic_optimizer
    from utils.branding import sync_from_db as sync_branding

    from core.resilience.circuit_breaker import sync_from_db as sync_circuit_breaker
    from core.health.health_monitor import get_health_monitor
    from core.middleware.health_aware_middleware import sync_from_db as sync_health_middleware

    try:
        async with get_db_session_context() as db:
            economic_opt = await get_economic_optimizer()
            health_monitor = get_health_monitor()
            # Sequential awaits — sharing a single AsyncSession concurrently
            # raises sqlalchemy.exc.InvalidRequestError (isce / "concurrent
            # operations are not permitted"). See commit 3b6e09db05.
            await ModelRegistry.sync_from_db(db)
            await economic_opt.sync_from_db(db)
            await sync_branding(db)
            await sync_circuit_breaker(db)
            await health_monitor.sync_from_db(db)
            await sync_health_middleware(db)
        logger.info(f"✅ Hot-Reload executed successfully by {admin_user.get('sub')}")
        return {
            "status": "success",
            "message": "System configs and model registries reloaded successfully",
        }
    except Exception as e:
        logger.error(f"❌ Hot-Reload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# SupremeAI 2.0 Infrastructure Agents — Admin Observability Endpoints
# বাংলা: ৪টা background agent-এর output দেখার জন্য endpoints। প্রতিটা try/except-এ
# wrapped — agent disabled বা unavailable হলে clear 503 message। এটি OBSERVE ধাপ।
# ══════════════════════════════════════════════════════════════════════════════


def _agent_enabled(env_var: str) -> bool:
    """env var check (default-OFF for all infra agents)."""
    import os

    return os.getenv(env_var, "false").lower() == "true"


@router.get("/infrastructure/status")
async def infrastructure_agents_status(admin_user: dict = Depends(get_current_admin)):
    """
    সব ৪টা infrastructure agent-এর overview: enabled কিনা, সংক্ষিপ্ত বিবরণ।
    """
    return {
        "agents": {
            "memory_augment": {
                "enabled": _agent_enabled("ENABLE_MEMORY_AUGMENT"),
                "description": "Neural Memory RAG (zero-cost sentence-transformers)",
                "wire_point": "api/routes/task.py (augment + intercept)",
            },
            "auto_scaling": {
                "enabled": _agent_enabled("ENABLE_AUTOSCALING_AGENT"),
                "description": "Autonomous resource scaling (5-min cycle)",
                "wire_point": "core/startup/agents.py (agent_supervisor)",
            },
            "performance_tuning": {
                "enabled": _agent_enabled("ENABLE_PERFORMANCE_TUNING_AGENT"),
                "description": "Continuous optimization with auto-apply (15-min cycle)",
                "wire_point": "core/startup/agents.py (agent_supervisor)",
            },
            "cost_optimization": {
                "enabled": _agent_enabled("ENABLE_COST_OPTIMIZATION_AGENT"),
                "description": "Strategic cost tracking + opportunities (1-hour cycle)",
                "wire_point": "core/startup/agents.py (agent_supervisor)",
            },
            "disaster_recovery": {
                "enabled": _agent_enabled("ENABLE_DISASTER_RECOVERY_AGENT"),
                "description": "Periodic incremental backups (6-hour cycle)",
                "wire_point": "core/startup/agents.py (agent_supervisor)",
            },
        },
        "note": "Enable via ENABLE_*_AGENT=true env var. See .env.example for details.",
    }


@router.get("/infrastructure/cost/report")
async def cost_optimization_report(admin_user: dict = Depends(get_current_admin)):
    """Cost optimization রিপোর্ট — spending, opportunities, forecast।"""
    if not _agent_enabled("ENABLE_COST_OPTIMIZATION_AGENT"):
        raise HTTPException(
            status_code=503,
            detail="CostOptimizationAgent disabled. Set ENABLE_COST_OPTIMIZATION_AGENT=true to enable.",
        )
    try:
        from agents.infrastructure.cost_optimization_agent import cost_optimization_agent

        return await cost_optimization_agent.get_cost_optimization_report()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ cost report failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/infrastructure/cost/forecast")
async def cost_forecast(
    days: int = 30,
    admin_user: dict = Depends(get_current_admin),
):
    """Cost forecast — পরের N দিনের projected cost (linear projection)।"""
    if not _agent_enabled("ENABLE_COST_OPTIMIZATION_AGENT"):
        raise HTTPException(
            status_code=503,
            detail="CostOptimizationAgent disabled. Set ENABLE_COST_OPTIMIZATION_AGENT=true to enable.",
        )
    try:
        from agents.infrastructure.cost_optimization_agent import cost_optimization_agent

        return await cost_optimization_agent.generate_cost_forecast(days_ahead=days)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ cost forecast failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/infrastructure/performance/summary")
async def performance_summary(
    hours: int = 24,
    admin_user: dict = Depends(get_current_admin),
):
    """Performance tuning summary — গত N ঘন্টার metrics + recommendations।"""
    if not _agent_enabled("ENABLE_PERFORMANCE_TUNING_AGENT"):
        raise HTTPException(
            status_code=503,
            detail="PerformanceTuningAgent disabled. Set ENABLE_PERFORMANCE_TUNING_AGENT=true to enable.",
        )
    try:
        from agents.infrastructure.performance_tuning_agent import performance_tuning_agent

        return await performance_tuning_agent.get_performance_summary(hours=hours)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ performance summary failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/infrastructure/disaster-recovery/backups")
async def backup_history(
    limit: int = 20,
    admin_user: dict = Depends(get_current_admin),
):
    """Backup history — সাম্প্রতিক backups-এর তালিকা (Redis থেকে)।"""
    if not _agent_enabled("ENABLE_DISASTER_RECOVERY_AGENT"):
        raise HTTPException(
            status_code=503,
            detail="DisasterRecoveryAgent disabled. Set ENABLE_DISASTER_RECOVERY_AGENT=true to enable.",
        )
    try:
        from agents.infrastructure.disaster_recovery_agent import disaster_recovery_agent

        raw = await redis_manager.get(disaster_recovery_agent.backup_history_key)
        backups = json.loads(raw) if raw else []
        return {
            "status": "success",
            "total_backups": len(backups),
            "recent": backups[-limit:] if backups else [],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ backup history failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/infrastructure/disaster-recovery/backup")
async def trigger_manual_backup(
    backup_type: str = "full",
    admin_user: dict = Depends(get_current_admin),
):
    """Manual backup trigger — admin চাইলে এখনই backup তৈরি করতে পারে।"""
    if not _agent_enabled("ENABLE_DISASTER_RECOVERY_AGENT"):
        raise HTTPException(
            status_code=503,
            detail="DisasterRecoveryAgent disabled. Set ENABLE_DISASTER_RECOVERY_AGENT=true to enable.",
        )
    if backup_type not in ("full", "incremental", "config_only"):
        raise HTTPException(
            status_code=400,
            detail="backup_type must be one of: full, incremental, config_only",
        )
    try:
        from agents.infrastructure.disaster_recovery_agent import disaster_recovery_agent

        result = await disaster_recovery_agent.create_backup(backup_type=backup_type)
        return {
            "status": "success",
            "backup_id": result.backup_id,
            "timestamp": result.timestamp.isoformat() if result.timestamp else None,
            "size_bytes": result.size_bytes,
            "location": result.location,
            "backup_status": result.status,
            "verification_hash": result.verification_hash,
            "components_backed_up": result.components_backed_up,
            "duration_seconds": result.duration_seconds,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ manual backup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/infrastructure/disaster-recovery/schedule")
async def backup_schedule_recommendations(
    admin_user: dict = Depends(get_current_admin),
):
    """Backup schedule recommendations — full/incremental frequency + retention পরামর্শ।"""
    if not _agent_enabled("ENABLE_DISASTER_RECOVERY_AGENT"):
        raise HTTPException(
            status_code=503,
            detail="DisasterRecoveryAgent disabled. Set ENABLE_DISASTER_RECOVERY_AGENT=true to enable.",
        )
    try:
        from agents.infrastructure.disaster_recovery_agent import disaster_recovery_agent

        return await disaster_recovery_agent.get_backup_schedule_recommendations()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ schedule recommendations failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/infrastructure/auto-scaling/status")
async def auto_scaling_status(
    limit: int = 20,
    admin_user: dict = Depends(get_current_admin),
):
    """Auto-scaling status — সাম্প্রতিক scaling actions (Redis থেকে)।"""
    if not _agent_enabled("ENABLE_AUTOSCALING_AGENT"):
        raise HTTPException(
            status_code=503,
            detail="AutoScalingAgent disabled. Set ENABLE_AUTOSCALING_AGENT=true to enable.",
        )
    try:
        # auto_scaling_agent সরাসরি history read করার method নেই, তাই Redis থেকে পড়ি
        raw = await redis_manager.get("auto_scaling:scaling_history")
        actions = json.loads(raw) if raw else []
        return {
            "status": "success",
            "total_actions": len(actions),
            "recent": actions[-limit:] if actions else [],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ auto-scaling status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Automation endpoints
# ══════════════════════════════════════════════════════════════════════════════


@router.get("/automation/workflows")
async def get_automation_workflows(admin_user: dict = Depends(get_current_admin)):
    """
    Fetch all automation workflows with full metadata (Plan Section 5).
    বাংলা: আগে শুধু {key: route} dict ফেরত দিত। এখন প্রতিটি workflow-এর
    full policy (timeout, retries, sync/async, sensitive, enabled, version)
    দেখায় — admin UI-তে workflow management সহজ করে।
    """
    from core.automation.registry import list_workflow_definitions

    defs = list_workflow_definitions()
    return {
        "total": len(defs),
        "workflows": [
            {
                "key": wf.key,
                "route": wf.route,
                "enabled": wf.enabled,
                "timeout_seconds": wf.timeout_seconds,
                "max_retries": wf.max_retries,
                "synchronous": wf.synchronous,
                "sensitive": wf.sensitive,
                "version": wf.version,
                "description": wf.description,
            }
            for wf in defs
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# Integration Governance — Plan Section 28 + 29
# বাংলা: সব optional integration-এর observability endpoints। কোনো secret expose
# করে না (Plan Section 29)। শুধু status, scope, fallback, capabilities দেখায়।
# ══════════════════════════════════════════════════════════════════════════════


@router.get("/integrations")
async def list_all_integrations(admin_user: dict = Depends(get_current_admin)):
    """
    Plan Section 29: সব optional integration-এর overview।
    Admin dashboard-এ দেখানোর জন্য status, scope, fallback সহ।
    কোনো secret expose করে না।
    """
    from core.integrations import list_integrations

    integs = list_integrations()
    return {
        "total": len(integs),
        "integrations": [
            {
                "key": i.key,
                "name": i.name,
                "category": i.category,
                "scope": i.scope.value,
                "enabled": i.enabled,
                "status": i.status.value,
                "required_for_core": i.required_for_core,
                "fallback": i.fallback,
                "privacy_mode": i.privacy_mode,
                "capabilities": list(i.capabilities),
                "config_note": i.config_note,
            }
            for i in integs
        ],
        "summary": {
            "enabled": sum(1 for i in integs if i.enabled),
            "disabled": sum(1 for i in integs if not i.enabled and i.status.value != "not-adopted"),
            "not_adopted": sum(1 for i in integs if i.status.value == "not-adopted"),
        },
    }


@router.get("/integrations/{key}/health")
async def get_integration_health(
    key: str,
    admin_user: dict = Depends(get_current_admin),
):
    """
    Plan Section 29: একটি specific integration-এর detailed health/status।
    ভুল key দিলে 404। Secret কখনো expose হয় না।
    """
    from core.integrations import get_integration

    info = get_integration(key)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown integration: {key}")

    return {
        "key": info.key,
        "name": info.name,
        "category": info.category,
        "scope": info.scope.value,
        "enabled": info.enabled,
        "status": info.status.value,
        "required_for_core": info.required_for_core,
        "fallback": info.fallback,
        "privacy_mode": info.privacy_mode,
        "capabilities": list(info.capabilities),
        "config_note": info.config_note,
        "core_independence": (
            "✅ Core works without this integration"
            if not info.required_for_core
            else "⚠️ Core depends on this integration"
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Automation Execution History — Plan Section 7
# বাংলা: dispatch lifecycle-এর audit trail। admin দেখতে পারে কোন event কখন
# dispatch হয়েছিল, কী status পেয়েছিল, কত সময় লেগেছিল। secrets expose হয় না।
# ══════════════════════════════════════════════════════════════════════════════


@router.get("/automation/executions")
async def list_automation_executions(
    limit: int = 50,
    workflow_key: str = "",
    status: str = "",
    admin_user: dict = Depends(get_current_admin),
):
    """
    Plan Section 7: automation execution history (audit trail)।
    optional filters: workflow_key, status। সর্বশেষ `limit` টা execution দেখায়।
    """
    try:
        from database.session import get_db_session_context
        from models.automation_execution import AutomationExecution
        from sqlalchemy import select, desc

        async with get_db_session_context() as session:
            stmt = (
                select(AutomationExecution)
                .order_by(desc(AutomationExecution.created_at))
                .limit(min(limit, 200))
            )  # cap at 200
            if workflow_key:
                stmt = stmt.where(AutomationExecution.workflow_key == workflow_key)
            if status:
                stmt = stmt.where(AutomationExecution.status == status.upper())

            result = await session.execute(stmt)
            records = result.scalars().all()

            return {
                "status": "success",
                "total": len(records),
                "executions": [
                    {
                        "id": r.id,
                        "event_id": r.event_id,
                        "workflow_key": r.workflow_key,
                        "provider": r.provider,
                        "status": r.status,
                        "attempt": r.attempt,
                        "started_at": r.started_at.isoformat() if r.started_at else None,
                        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                        "duration_ms": r.duration_ms,
                        "http_status": r.http_status,
                        "external_execution_id": r.external_execution_id,
                        "trace_id": r.trace_id,
                        "error_code": r.error_code,
                        # error_message truncate করি — সম্ভাব্য sensitive data না ফাঁসাতে
                        "error_message": (r.error_message[:200] + "...")
                        if r.error_message and len(r.error_message) > 200
                        else r.error_message,
                    }
                    for r in records
                ],
            }
    except Exception as e:
        logger.error(f"❌ automation executions list failed: {e}")
        return {
            "status": "error",
            "message": f"Could not retrieve execution history: {e}",
            "total": 0,
            "executions": [],
        }


@router.get("/automation/executions/{event_id}")
async def get_execution_by_event(
    event_id: str,
    admin_user: dict = Depends(get_current_admin),
):
    """
    Plan Section 7: একটি specific event_id-এর সব execution attempts দেখায়
    (retry history সহ)।
    """
    try:
        from database.session import get_db_session_context
        from models.automation_execution import AutomationExecution
        from sqlalchemy import select, desc

        async with get_db_session_context() as session:
            stmt = (
                select(AutomationExecution)
                .where(AutomationExecution.event_id == event_id)
                .order_by(desc(AutomationExecution.created_at))
            )
            result = await session.execute(stmt)
            records = result.scalars().all()

            if not records:
                raise HTTPException(
                    status_code=404,
                    detail=f"No executions found for event_id: {event_id}",
                )

            return {
                "status": "success",
                "event_id": event_id,
                "total_attempts": len(records),
                "executions": [
                    {
                        "id": r.id,
                        "workflow_key": r.workflow_key,
                        "provider": r.provider,
                        "status": r.status,
                        "attempt": r.attempt,
                        "started_at": r.started_at.isoformat() if r.started_at else None,
                        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                        "duration_ms": r.duration_ms,
                        "http_status": r.http_status,
                        "external_execution_id": r.external_execution_id,
                        "error_code": r.error_code,
                        "error_message": (r.error_message[:200] + "...")
                        if r.error_message and len(r.error_message) > 200
                        else r.error_message,
                    }
                    for r in records
                ],
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ execution lookup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class RenderOverrideRequest(BaseModel):
    reason: str


class RenderRecheckRequest(BaseModel):
    force: bool = True


@router.get("/render/preflight")
async def get_admin_render_preflight(admin_user: dict = Depends(get_current_admin)):
    """Expose operator-friendly Render deploy preflight and role statuses."""
    try:
        from services.render_preflight_service import RenderPreflightService

        svc = RenderPreflightService()
        return {
            "status": "success",
            "data": svc.get_deploy_preflight(),
            "events": svc.store.get_events(limit=20),
        }
    except Exception as e:
        logger.error(f"Render preflight query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch preflight data")


@router.post("/render/accounts/{role}/recheck")
async def recheck_admin_render_account(
    role: str,
    payload: RenderRecheckRequest = RenderRecheckRequest(),
    admin_user: dict = Depends(get_current_admin),
):
    """Trigger manual recheck for a specific Render role."""
    try:
        from services.render_preflight_service import RenderPreflightService

        svc = RenderPreflightService()
        api_key_env = f"RENDER_API_KEY_{role.upper()}"
        api_key = os.getenv(api_key_env) or os.getenv("RENDER_API_KEY", "")
        svc_id = os.getenv(f"RENDER_{role.upper()}_SVC_ID", "")

        result = svc.refresh_account_status(
            account_role=role,
            service_id=svc_id,
            api_key=api_key,
            force=payload.force,
        )
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Render recheck failed for role {role}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to recheck role {role}")


@router.post("/render/accounts/{role}/override")
async def override_admin_render_account(
    role: str,
    payload: RenderOverrideRequest,
    admin_user: dict = Depends(get_current_admin),
):
    """Manual override for a blocked/cooldown Render role with mandatory reason."""
    if not payload.reason or len(payload.reason.strip()) < 5:
        raise HTTPException(
            status_code=400, detail="A valid reason (min 5 chars) is required for manual override."
        )

    try:
        from services.render_preflight_service import RenderPreflightService

        svc = RenderPreflightService()
        approved_by = admin_user.get("sub", "admin")
        result = svc.manual_override(
            account_role=role, approved_by=approved_by, reason=payload.reason
        )
        return {"status": "success", "data": result}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Render manual override failed for role {role}: {e}")
        raise HTTPException(status_code=500, detail="Failed to apply manual override")
