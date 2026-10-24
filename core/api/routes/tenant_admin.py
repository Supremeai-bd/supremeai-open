"""
Tenant Rate Limiter Admin API (Sprint G.4)
GET  /api/admin/tenant-limits        — list all tenants + live usage
POST /api/admin/tenant-limits        — create tenant
PUT  /api/admin/tenant-limits/{id}   — update limits
DELETE /api/admin/tenant-limits/{id} — remove tenant
GET  /api/admin/tenant-limits/{id}/usage — per-tenant usage stats
POST /api/admin/tenant-limits/{id}/reset-usage — reset today's counters
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_current_platform_admin
from core.logging_config import logger

router = APIRouter(
    prefix="/admin-api/tenant-limits",
    tags=["tenant-admin"],
    dependencies=[Depends(get_current_platform_admin)],
)

# Secondary router for /admin-api/tenants endpoints
tenants_router = APIRouter(
    prefix="/admin-api/tenants",
    tags=["tenants"],
    dependencies=[Depends(get_current_platform_admin)],
)


# ── Models ────────────────────────────────────────────────────────────────────


class TenantLimitCreate(BaseModel):
    tenant_id: str
    org_name: str = ""
    billing_tier: str = "free"  # free | starter | pro | enterprise
    requests_per_minute: int | None = None
    max_tokens_per_day: int | None = None
    max_concurrent_sessions: int | None = None
    stripe_customer_id: str | None = None
    notes: str | None = None


class TenantLimitUpdate(BaseModel):
    org_name: str | None = None
    billing_tier: str | None = None
    requests_per_minute: int | None = None
    max_tokens_per_day: int | None = None
    max_concurrent_sessions: int | None = None
    stripe_customer_id: str | None = None
    notes: str | None = None


# Tier defaults (match frontend TIER_LIMITS)
TIER_DEFAULTS: dict[str, dict[str, int]] = {
    "free": {
        "requests_per_minute": 20,
        "max_tokens_per_day": 50_000,
        "max_concurrent_sessions": 2,
    },
    "starter": {
        "requests_per_minute": 60,
        "max_tokens_per_day": 200_000,
        "max_concurrent_sessions": 5,
    },
    "pro": {
        "requests_per_minute": 200,
        "max_tokens_per_day": 1_000_000,
        "max_concurrent_sessions": 20,
    },
    "enterprise": {
        "requests_per_minute": 999,
        "max_tokens_per_day": 9_999_999,
        "max_concurrent_sessions": 100,
    },
}


# ── DB helpers ────────────────────────────────────────────────────────────────


def _get_db():
    try:
        from database.supabase_client import db

        return db.client if db and db.client else None
    except Exception:
        logger.exception("Unhandled exception")
        return None


async def _db_list_tenants() -> list[dict[str, Any]]:
    client = _get_db()
    if client:
        try:
            res = (
                await client.table("tenant_limits")
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            return res.data or []
        except Exception as exc:
            logger.warning(f"Supabase tenant list failed: {exc}")
    return _local_store.get("tenants", [])


async def _db_get_tenant(tenant_id: str) -> dict[str, Any] | None:
    client = _get_db()
    if client:
        try:
            res = (
                await client.table("tenant_limits").select("*").eq("tenant_id", tenant_id).execute()
            )
            return res.data[0] if res.data else None
        except Exception as exc:
            logger.warning(f"Supabase tenant get failed: {exc}")
    for t in _local_store.get("tenants", []):
        if t["tenant_id"] == tenant_id:
            return t
    return None


async def _db_upsert_tenant(data: dict[str, Any]) -> bool:
    client = _get_db()
    if client:
        try:
            await client.table("tenant_limits").upsert(data, on_conflict="tenant_id").execute()
            return True
        except Exception as exc:
            logger.warning(f"Supabase tenant upsert failed: {exc}")
    # local fallback
    tenants = _local_store.setdefault("tenants", [])
    for i, t in enumerate(tenants):
        if t["tenant_id"] == data["tenant_id"]:
            tenants[i] = data
            return True
    tenants.append(data)
    return True


async def _db_delete_tenant(tenant_id: str) -> bool:
    client = _get_db()
    if client:
        try:
            await client.table("tenant_limits").delete().eq("tenant_id", tenant_id).execute()
            return True
        except Exception as exc:
            logger.warning(f"Supabase delete failed: {exc}")
    tenants = _local_store.setdefault("tenants", [])
    _local_store["tenants"] = [t for t in tenants if t["tenant_id"] != tenant_id]
    return True


async def _get_tenant_usage(tenant_id: str) -> dict[str, Any]:
    """Pull live usage from Redis (TenantRateLimiter) + Supabase (token totals)."""
    usage: dict[str, Any] = {
        "tenant_id": tenant_id,
        "requests_today": 0,
        "tokens_today": 0,
        "cost_today": 0.0,
    }
    try:
        import core.services as app_mod

        q = getattr(app_mod, "redis_queue", None)
        if q and getattr(q, "configured", False):
            now = int(time.time())
            day_key = f"rate:{tenant_id}:{now // 86400}:rpd"
            tokens_key = f"rate:{tenant_id}:tokens"
            cost_key = f"rate:{tenant_id}:cost"
            usage["requests_today"] = int(q.get(day_key) or 0)
            usage["tokens_today"] = int(q.get(tokens_key) or 0)
            usage["cost_today"] = float(q.get(cost_key) or 0.0)
    except Exception as exc:
        logger.debug(f"Redis usage read failed: {exc}")

    # Supabase fallback
    if usage["requests_today"] == 0:
        client = _get_db()
        if client:
            try:
                today = time.strftime("%Y-%m-%d")
                res = (
                    client.table("tenant_usage")
                    .select("requests_count,tokens_used,cost_incurred")
                    .eq("tenant_id", tenant_id)
                    .eq("date", today)
                    .execute()
                )
                if res.data:
                    row = res.data[0]
                    usage["requests_today"] = row.get("requests_count", 0)
                    usage["tokens_today"] = row.get("tokens_used", 0)
                    usage["cost_today"] = float(row.get("cost_incurred", 0.0))
            except Exception as exc:
                logger.debug(f"Supabase usage read failed: {exc}")
    return usage


# Local in-memory fallback store
_local_store: dict[str, Any] = {}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("")
async def list_tenants(include_usage: bool = True):
    """List all tenants with their rate limits and (optionally) live usage."""
    tenants = await _db_list_tenants()

    # Add default tier limits where missing
    for t in tenants:
        tier = t.get("billing_tier", "free")
        defaults = TIER_DEFAULTS.get(tier, TIER_DEFAULTS["free"])
        for k, v in defaults.items():
            if t.get(k) is None:
                t[k] = v

    if include_usage:
        import asyncio

        usages = await asyncio.gather(*[_get_tenant_usage(t["tenant_id"]) for t in tenants])
        usage_map = {u["tenant_id"]: u for u in usages}
    else:
        usage_map = {}

    return {
        "status": "success",
        "total": len(tenants),
        "tenants": tenants,
        "usages": list(usage_map.values()),
        "tier_defaults": TIER_DEFAULTS,
    }


@router.post("")
async def create_tenant(payload: TenantLimitCreate):
    """Create a new tenant with rate limits."""
    existing = await _db_get_tenant(payload.tenant_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Tenant '{payload.tenant_id}' already exists")

    tier = payload.billing_tier if payload.billing_tier in TIER_DEFAULTS else "free"
    defaults = TIER_DEFAULTS[tier]

    record = {
        "tenant_id": payload.tenant_id,
        "org_name": payload.org_name,
        "billing_tier": tier,
        "requests_per_minute": payload.requests_per_minute or defaults["requests_per_minute"],
        "max_tokens_per_day": payload.max_tokens_per_day or defaults["max_tokens_per_day"],
        "max_concurrent_sessions": payload.max_concurrent_sessions
        or defaults["max_concurrent_sessions"],
        "stripe_customer_id": payload.stripe_customer_id,
        "notes": payload.notes,
        "is_active": True,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    await _db_upsert_tenant(record)

    # Cache tier in Redis
    try:
        from tools.tenant_rate_limiter import TenantRateLimiter

        limiter = TenantRateLimiter()
        await limiter.set_tier(payload.tenant_id, tier)
    except Exception as exc:
        logger.debug(f"Redis tier cache failed: {exc}")

    logger.info(f"Created tenant: {payload.tenant_id} tier={tier}")
    return {"status": "success", "tenant": record}


@router.get("/{tenant_id}")
async def get_tenant(tenant_id: str):
    """Get a single tenant's limits and usage."""
    tenant = await _db_get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
    usage = await _get_tenant_usage(tenant_id)
    return {"status": "success", "tenant": tenant, "usage": usage}


@router.put("/{tenant_id}")
async def update_tenant(tenant_id: str, payload: TenantLimitUpdate):
    """Update a tenant's rate limits or billing tier."""
    existing = await _db_get_tenant(tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")

    updates: dict[str, Any] = payload.model_dump(exclude_none=True)

    # If tier changed, apply new defaults (unless overridden explicitly)
    if "billing_tier" in updates:
        new_tier = updates["billing_tier"]
        if new_tier not in TIER_DEFAULTS:
            raise HTTPException(status_code=400, detail=f"Invalid tier: {new_tier}")
        defaults = TIER_DEFAULTS[new_tier]
        for k, v in defaults.items():
            if k not in updates:
                updates[k] = v
        # Update Redis tier cache
        try:
            from tools.tenant_rate_limiter import TenantRateLimiter

            limiter = TenantRateLimiter()
            await limiter.set_tier(tenant_id, new_tier)
        except Exception as exc:
            logger.debug(f"Redis tier update failed: {exc}")

    updates["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record = {**existing, **updates}
    await _db_upsert_tenant(record)

    logger.info(f"Updated tenant: {tenant_id} → {updates}")
    return {"status": "success", "tenant": record}


@router.delete("/{tenant_id}")
async def delete_tenant(tenant_id: str):
    """Remove a tenant."""
    existing = await _db_get_tenant(tenant_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
    await _db_delete_tenant(tenant_id)
    logger.info(f"Deleted tenant: {tenant_id}")
    return {"status": "deleted", "tenant_id": tenant_id}


@router.get("/{tenant_id}/usage")
async def get_usage(tenant_id: str):
    """Get live usage stats for a tenant."""
    tenant = await _db_get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
    usage = await _get_tenant_usage(tenant_id)
    limits = {
        "requests_per_minute": tenant.get("requests_per_minute"),
        "max_tokens_per_day": tenant.get("max_tokens_per_day"),
    }
    return {
        "status": "success",
        "tenant_id": tenant_id,
        "usage": usage,
        "limits": limits,
    }


@router.post("/{tenant_id}/reset")
@router.post("/{tenant_id}/reset-usage")
@tenants_router.post("/{tenant_id}/reset")
async def reset_usage(tenant_id: str):
    """Reset today's request/token counters for a tenant (Redis)."""
    try:
        import core.services as app_mod

        q = getattr(app_mod, "redis_queue", None)
        if q and getattr(q, "configured", False):
            now = int(time.time())
            day_key = f"rate:{tenant_id}:{now // 86400}:rpd"
            tokens_key = f"rate:{tenant_id}:tokens"
            cost_key = f"rate:{tenant_id}:cost"
            q.delete(day_key)
            q.delete(tokens_key)
            q.delete(cost_key)
            logger.info(f"Reset Redis usage for tenant: {tenant_id}")
            return {"status": "reset", "tenant_id": tenant_id, "source": "redis"}
    except Exception as exc:
        logger.debug(f"Redis reset failed: {exc}")

    # Supabase fallback
    client = _get_db()
    if client:
        try:
            today = time.strftime("%Y-%m-%d")
            client.table("tenant_usage").delete().eq("tenant_id", tenant_id).eq(
                "date", today
            ).execute()
            return {"status": "reset", "tenant_id": tenant_id, "source": "supabase"}
        except Exception as exc:
            logger.warning(f"Supabase reset failed: {exc}")

    return {"status": "reset", "tenant_id": tenant_id, "source": "none"}


@router.get("/tiers/defaults")
async def get_tier_defaults():
    """Return the default limits for each billing tier."""
    return {"status": "success", "tiers": TIER_DEFAULTS}


# Include secondary router for full compatibility
router.include_router(tenants_router)
