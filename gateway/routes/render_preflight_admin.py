"""Render Deployment Preflight and Account State Admin API.

Provides:
  - GET /api/v1/admin/render/preflight
  - POST /api/v1/admin/render/accounts/{role}/recheck
  - POST /api/v1/admin/render/accounts/{role}/override
  - GET /api/v1/admin/render/events
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.dependencies import get_current_admin
from api.routes.admin_auth import admin_rate_limit, require_admin_token
from database.supabase_client import db
from services.render_account_service import RenderAccountService

router = APIRouter(
    prefix="/api/v1/admin/render",
    tags=["admin-render-preflight"],
    dependencies=[Depends(require_admin_token), Depends(admin_rate_limit)],
)


class ManualOverrideRequest(BaseModel):
    status: Literal["ready", "blocked", "cooldown", "recheck_required"] = Field(
        ..., description="Desired overridden status"
    )
    reason: str = Field(..., min_length=3, description="Audit reason for manual override")


class RecheckRequest(BaseModel):
    force: bool = Field(default=False, description="Force recheck even during cooldown")


@router.get("/preflight")
async def get_render_deploy_preflight(admin: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """Return preflight status, limits, and deployment authorization across Render roles.

    Can also be used directly as the target of RENDER_PREFLIGHT_URL in GitHub Actions CI.
    """
    return RenderAccountService.get_status_overview()


@router.post("/accounts/{role}/recheck")
async def recheck_render_account(
    role: str,
    payload: RecheckRequest = RecheckRequest(),
    admin: dict = Depends(get_current_admin),
) -> dict[str, Any]:
    """Trigger a live audit/refresh against Render for a given account role."""
    admin_user = admin.get("sub", admin.get("email", "admin"))
    result = RenderAccountService.refresh_account_status(
        account_role=role,
        force=payload.force,
        manual_by=admin_user,
    )
    return {
        "status": "success",
        "role": role,
        "account_state": result,
    }


@router.post("/accounts/{role}/override")
async def override_render_account(
    role: str,
    payload: ManualOverrideRequest,
    admin: dict = Depends(get_current_admin),
) -> dict[str, Any]:
    """Apply an explicit manual override with a logged reason."""
    admin_user = admin.get("sub", admin.get("email", "admin"))
    result = RenderAccountService.manual_override(
        account_role=role,
        status=payload.status,
        reason=payload.reason,
        admin_user=admin_user,
    )
    return {
        "status": "success",
        "role": role,
        "overridden_state": result,
    }


@router.get("/events")
async def get_render_preflight_events(
    account_key: str | None = Query(None, description="Filter by account key/role"),
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(get_current_admin),
) -> list[dict[str, Any]]:
    """Get audit trail of preflight events, cooldowns, and overrides."""
    return db.get_render_preflight_events(account_key=account_key, limit=limit)


@router.get("/accounts/health")
async def get_multi_account_health(
    admin: dict = Depends(get_current_admin),
) -> dict[str, Any]:
    """Audit and surface aggregated health across all multi-account pools (Resolves Issue #757 / OB-01).

    Aggregates:
    - Render roles (RenderAccountService overview)
    - Cloudflare Edge Federation (5 accounts)
    - Upstash Redis REST & TCP Federation (5 accounts)
    - LLM Provider Key Pools & Cooling States
    - Kaggle accounts
    """
    import os
    import time

    from core.config import settings
    from core.llm.llm_gateway.registry import _provider_key_pool
    from core.routing.cloudflare_edge_pool import cloudflare_edge_pool

    # 1. Render health
    render_health = RenderAccountService.get_status_overview()

    # 2. Cloudflare Edge Federation
    cf_nodes = []
    for node in cloudflare_edge_pool.nodes:
        cf_nodes.append(
            {
                "role": node.role,
                "account_id": f"{node.account_id[:6]}...{node.account_id[-4:]}"
                if len(node.account_id) > 10
                else (node.account_id or "configured"),
                "worker_url": node.worker_url,
                "is_active": node.is_active,
            }
        )

    # 3. Upstash Redis REST Pool
    upstash_pool = []
    rest_pool = getattr(settings, "upstash_redis_rest_pool", [])
    for idx, (u, t) in enumerate(rest_pool, 1):
        upstash_pool.append(
            {
                "account_index": idx,
                "url": u,
                "token_configured": bool(t),
                "status": "active",
            }
        )

    # 4. LLM Provider Key Pools & Cooling
    llm_pools: dict[str, Any] = {}
    providers = ["gemini", "openai", "groq", "mistral", "deepseek", "bynara", "bai", "v0"]
    now = time.monotonic()
    for prov in providers:
        raw_key = (
            getattr(settings, f"{prov}_api_key", None) or os.getenv(f"{prov.upper()}_API_KEY") or ""
        )
        keys = _provider_key_pool._keys_for(raw_key, provider=prov)
        key_statuses = []
        for k in keys:
            cooling_until = _provider_key_pool._cooldown_until.get((prov, k), 0.0)
            is_cooling = cooling_until > now
            key_statuses.append(
                {
                    "masked": f"{k[:4]}...{k[-4:]}" if len(k) > 8 else "***",
                    "cooling": is_cooling,
                    "cooldown_remaining_sec": max(0, int(cooling_until - now)) if is_cooling else 0,
                }
            )
        llm_pools[prov] = {
            "total_keys": len(keys),
            "healthy_keys": sum(1 for ks in key_statuses if not ks["cooling"]),
            "keys": key_statuses,
        }

    # 5. Kaggle tokens
    kaggle_keys = getattr(settings, "kaggle_api_keys", [])

    return {
        "status": "healthy",
        "timestamp": time.time(),
        "pools": {
            "render": render_health,
            "cloudflare_edge": {
                "total_accounts": len(cf_nodes),
                "nodes": cf_nodes,
            },
            "upstash_redis": {
                "total_accounts": len(upstash_pool),
                "instances": upstash_pool,
            },
            "llm_gateways": llm_pools,
            "kaggle": {
                "total_tokens": len(kaggle_keys),
            },
        },
    }
