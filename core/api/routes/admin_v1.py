"""Admin API v1 aliases.

বাংলা মন্তব্য: লাইভ (deployed) অ্যাডমিন ফ্রন্টএন্ড /api/v1/agents কল করে, কিন্তু ব্যাকএন্ডে
সেই পাথটি ছিল না → 404। Command Center-এর Agents/Tasks tab গুলো এর জন্য error দেখাত।
এখানে /api/v1/agents alias যোগ করা হলো যাতে লাইভ সাইটেও tab গুলো সঠিকভাবে render করে।

MASTER_PLAN Phase 1 ("Admin surface"): /api/v1/admin/stats, /api/v1/admin/users,
/api/v1/admin/audit-logs — তিনটিই আগে 404 দিত। এখানে সত্যিকারের ডেটা সহ alias
যোগ করা হলো (reuse: admin_dashboard.py-র load_users/audit bridge —
Reuse Before Creation)। প্রতিটি এন্ডপয়েন্ট admin token + rate limit guard-এর
অধীনে (router-level dependencies)।
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_current_admin
from api.routes.admin_auth import admin_rate_limit, require_admin_token
from core.agent_registry import get_agent_registry

router = APIRouter(
    prefix="/api/v1",
    tags=["admin-v1-aliases"],
    dependencies=[Depends(require_admin_token), Depends(admin_rate_limit)],
)


# Red-CI fix (#1753 follow-through): this module previously ALSO registered
# GET /api/v1/agents as a stub returning [] — "alias of /admin-api/agents for
# the deployed frontend build". #1562 later mounted the real agent-registry
# router on the same path/method, creating a first-match shadow caught by the
# M17 P-A ratchet (test_hitl_route_ownership). Ownership decision: the
# registry owns GET /api/v1/agents (it serves the actual records the
# dashboard dropdown reads — a stub returning [] was lying about an empty
# registry). The /admin/agents alias below keeps the #1475 contract alive by
# delegating to the registry instead.


@router.get("/admin/users")
async def list_users_v1(admin: dict = Depends(get_current_admin)) -> list[dict[str, Any]]:
    """Alias of /admin-api/users for the /api/v1/admin/* contract."""
    try:
        from api.routes.admin_dashboard import load_users

        users = load_users()
        return users if isinstance(users, list) else []
    except Exception as exc:
        raise HTTPException(status_code=503, detail="User store unavailable") from exc


@router.get("/admin/audit-logs")
async def audit_logs_v1(
    limit: int = Query(default=100, ge=1, le=500),
    admin: dict = Depends(get_current_admin),
) -> list[dict[str, Any]]:
    """Alias of /admin-api/audit for the /api/v1/admin/* contract."""
    try:
        from api.routes.admin_dashboard import get_admin_audit_logs

        logs = get_admin_audit_logs(limit=limit)
        return logs if isinstance(logs, list) else []
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Audit log store unavailable") from exc


@router.get("/admin/stats")
async def admin_stats_v1(admin: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """Honest system stats for the deployed admin dashboard (no fabricated numbers)."""
    stats: dict[str, Any] = {
        "service": "supremeai-core",
        "generated_at": datetime.now(UTC).isoformat(),
        "users": 0,
        "audit_logs": 0,
        "agents": 0,
        "crawler_policies": 0,
        "crawler_crawls_24h": 0,
    }
    try:
        from api.routes.admin_dashboard import load_users

        users = load_users()
        stats["users"] = len(users) if isinstance(users, list) else 0
    except Exception as exc:
        # বাংলা: সততাই নীতি — কাউন্ট না পেলে 0 দিয়ে degraded চিহ্ন থাকে, ভুয়া সংখ্যা নয়।
        stats["users_degraded"] = str(exc)

    try:
        from api.routes.admin_dashboard import get_admin_audit_logs

        logs = get_admin_audit_logs(limit=500)
        stats["audit_logs"] = len(logs) if isinstance(logs, list) else 0
    except Exception as exc:
        stats["audit_degraded"] = str(exc)

    try:
        from scout.persistence import list_history, list_policies

        tenant_id = str(admin.get("tenant_id") or admin.get("org_id") or "").strip()
        if not tenant_id:
            stats["crawler_degraded"] = "Tenant context required for crawler metrics"
            return stats
        policies = await list_policies(tenant_id)
        stats["crawler_policies"] = len(policies)
        history = await list_history(tenant_id, limit=100)
        day_ago = datetime.now(UTC).timestamp() - 86400
        recent = 0
        for rec in history:
            try:
                if rec.created_at.timestamp() >= day_ago:
                    recent += 1
            except Exception:
                continue
        stats["crawler_crawls_24h"] = recent
    except Exception as exc:
        stats["crawler_degraded"] = str(exc)

    return stats


# ---------------------------------------------------------------------------
# Issue #1475 — /api/v1/admin/* contract completion
#
# The audit contract lists 17 admin endpoints under /api/v1/admin/*; most had
# real implementations living under other prefixes (/admin-api/*, /api/admin/*)
# while the contract path answered 404. Each alias below delegates to the SAME
# real handler/data source (Reuse Before Creation) under the router-level
# admin-token + rate-limit guards. Where no implementation exists anywhere in
# the codebase, the endpoint answers an explicit, honest 501 instead of a
# misleading 404 — and never fabricates data.
# ---------------------------------------------------------------------------


async def _admin_stats_payload(admin: dict) -> dict[str, Any]:
    """Shared real-data stats builder (used by /stats and /dashboard)."""
    from api.routes.admin_dashboard import load_users

    stats: dict[str, Any] = {"generated_at": datetime.now(UTC).isoformat(), "users": 0}
    try:
        users = load_users()
        stats["users"] = len(users) if isinstance(users, list) else 0
    except Exception:
        stats["users_degraded"] = "user store unavailable"

    try:
        from api.routes.admin_dashboard import get_admin_audit_logs

        logs = get_admin_audit_logs(limit=500)
        stats["audit_logs"] = len(logs) if isinstance(logs, list) else 0
    except Exception:
        stats["audit_degraded"] = "audit store unavailable"
    return stats


@router.get("/admin/metrics")
async def admin_metrics_v1(admin: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """Alias of /admin-api/metrics (real instrumentation pipeline)."""
    from api.routes.admin_dashboard.endpoints_metrics import get_metrics

    return get_metrics()


@router.get("/admin/health")
async def admin_health_v1(admin: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """Alias of /admin-api/health-map (real service health probes)."""
    from api.routes.admin_dashboard.endpoints_health import get_health_map

    return await get_health_map()


@router.get("/admin/system-status")
async def admin_system_status_v1(admin: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """Real process-level system status (collector summary, no fabrications)."""
    from core.monitoring import get_metrics_collector

    summary = get_metrics_collector().get_summary()
    return {
        "service": "supremeai-core",
        "generated_at": datetime.now(UTC).isoformat(),
        **summary,
    }


@router.get("/admin/dashboard")
async def admin_dashboard_v1(admin: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """Composite dashboard payload: real metrics + real stats + real health."""
    from api.routes.admin_dashboard.endpoints_health import get_health_map
    from api.routes.admin_dashboard.endpoints_metrics import get_metrics

    dashboard: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics": get_metrics(),
        "stats": await _admin_stats_payload(admin),
    }
    try:
        dashboard["health"] = await get_health_map()
    except Exception:
        dashboard["health_degraded"] = "health map unavailable"
    return dashboard


@router.get("/admin/analytics")
async def admin_analytics_v1(admin: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """Real traffic analytics from the live rolling window (no fabricated DAU)."""
    from core.observability.metrics_registry import get_window_metrics

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "traffic": get_window_metrics(),
    }


@router.get("/admin/tiers")
async def admin_tiers_v1(admin: dict = Depends(get_current_admin)) -> list[dict[str, Any]]:
    """Alias of /admin-api/tenant-limits listing (real per-tenant limits + usage)."""
    from api.routes.tenant_admin import list_tenants

    tenants = await list_tenants(include_usage=True)
    return tenants if isinstance(tenants, list) else []


@router.get("/admin/billing")
async def admin_billing_v1(admin: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """Alias of /admin-api/costs — real CostAuditor report (admin cost view)."""
    from api.routes.admin_dashboard import get_costs

    return get_costs()


@router.get("/admin/skills")
async def admin_skills_v1(admin: dict = Depends(get_current_admin)) -> list[dict[str, Any]]:
    """Alias of /skills/catalog — real filesystem-manifest skill catalog."""
    from api.routes.skills import get_active_skill_catalog

    catalog = await get_active_skill_catalog()
    return catalog if isinstance(catalog, list) else []


@router.get("/admin/api-keys")
async def admin_api_keys_v1(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin: dict = Depends(get_current_admin),
) -> dict[str, Any]:
    """Alias of /api/api-keys/all — real cross-user key listing (admin only)."""
    from api.routes.api_keys import get_all_api_keys

    keys = await get_all_api_keys(limit=limit, offset=offset)
    return {"keys": keys, "total": len(keys)}


@router.get("/admin/security")
async def admin_security_v1(admin: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """Composite of the real /admin-api/security/* handlers."""
    from api.routes.admin_dashboard.endpoints_security_memory import (
        get_security_memory,
        get_security_tasks,
    )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "tasks": await get_security_tasks(),
        "memory": await get_security_memory(),
    }


@router.get("/admin/config")
async def admin_config_v1(admin: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """Alias of /admin-api/config (real .env-backed config view)."""
    from api.routes.admin_dashboard.endpoints_config import get_config

    return get_config()


@router.get("/admin/audit")
async def admin_audit_v1(
    limit: int = Query(default=100, ge=1, le=500),
    admin: dict = Depends(get_current_admin),
) -> list[dict[str, Any]]:
    """Alias of /admin-api/audit-logs."""
    return await audit_logs_v1(limit=limit, admin=admin)


@router.get("/admin/webhooks")
async def admin_webhooks_v1(admin: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """Honest 501: no webhook store exists anywhere in the codebase yet."""
    raise HTTPException(
        status_code=501,
        detail="Webhook management is not implemented yet — tracked separately from this contract.",
    )


@router.get("/admin/notifications")
async def admin_notifications_v1(admin: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """Honest 501: no notification store exists anywhere in the codebase yet."""
    raise HTTPException(
        status_code=501,
        detail="Admin notifications are not implemented yet — tracked separately from this contract.",
    )


@router.get("/admin/deployments")
async def admin_deployments_v1(admin: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """Honest 501: no deployment registry exists anywhere in the codebase yet."""
    raise HTTPException(
        status_code=501,
        detail="Deployment registry is not implemented yet — tracked separately from this contract.",
    )


@router.get("/admin/agents")
async def admin_agents_v1(admin: dict = Depends(get_current_admin)) -> list[dict[str, Any]]:
    """Alias of /api/v1/agents for the /api/v1/admin/* contract (issue #1475)."""
    return [record.model_dump(mode="json") for record in get_agent_registry().list_agents()]
