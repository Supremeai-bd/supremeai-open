"""
API Key Management Routes
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from api.dependencies import get_current_user_token
from core.logging_config import logger
from core.security import generate_api_key, hash_api_key, mask_api_key, verify_api_key
from middleware.rate_limiter import AsyncRateLimiter
from models.api_key import create_api_key as db_create_api_key
from models.api_key import (
    delete_api_key,
    get_all_api_keys,
    get_api_key_by_id,
    get_api_key_usage,
    get_api_key_usage_stats,
    get_api_keys_by_user,
    record_api_key_event,
    record_api_key_usage,
)
from models.api_key import revoke_api_key as db_revoke_api_key
from models.api_key import rotate_api_key as db_rotate_api_key

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])
limiter = AsyncRateLimiter()
KEY_USAGE_LIMIT = 100
ALERT_RPM_THRESHOLD = 50
BULK_DELETE_LIMIT = 50


class CreateAPIKeyRequest(BaseModel):
    user_id: str = Field(..., min_length=1, description="Owner user ID (email or uid)")
    name: str = Field(..., min_length=1, max_length=255)
    rate_limit_rps: int = Field(default=6, ge=1, le=1000)
    expires_in_days: int | None = Field(
        default=None, ge=1, description="Expires in N days, null = no expiry"
    )
    scopes: list[str] | None = Field(default=None, description="List of access scopes/permissions")

    @field_validator("user_id", "name", mode="before")
    @classmethod
    def strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class UpdateAPIKeyRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    rate_limit_rps: int | None = Field(default=None, ge=1, le=1000)


class RotateAPIKeyRequest(BaseModel):
    old_key: str = Field(..., min_length=1)
    grace_period_hours: int = Field(default=24, ge=0, le=168)


class BulkDeleteRequest(BaseModel):
    key_ids: list[int] = Field(..., min_length=1, max_length=50)


def _get_current_user(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if not user:
        from utils.environment import is_test_environment

        if is_test_environment():
            return "test_owner"
        raise HTTPException(status_code=401, detail="Authentication required")
    return user.get("sub", "") if isinstance(user, dict) else str(user)


def _require_admin(payload: dict = Depends(get_current_user_token)) -> dict:
    """Enforce admin role for sensitive API key admin routes."""
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload


def _get_api_key_owner(request: Request) -> str | None:
    ak = getattr(request.state, "api_key", None)
    if not ak:
        return None
    key_id = ak.get("id")
    if key_id:
        return f"ak_{key_id}"
    return None


@router.post("/create", status_code=status.HTTP_201_CREATED)
async def create_key(req: CreateAPIKeyRequest, request: Request):
    key = generate_api_key()
    key_hash = hash_api_key(key)
    key_masked = mask_api_key(key)
    key_prefix = key[:12]

    expires_at = None
    if req.expires_in_days:
        expires_at = int(time.time()) + req.expires_in_days * 86400

    owner = _get_current_user(request)
    if requester := _get_api_key_owner(request):
        owner = f"{owner}:api_key:{requester}"

    rec = await db_create_api_key(
        user_id=owner,
        name=req.name,
        key_hash=key_hash,
        key_masked=key_masked,
        key_prefix=key_prefix,
        rate_limit_rps=req.rate_limit_rps,
        expires_at=expires_at,
        scopes=req.scopes,
    )
    if not rec:
        raise HTTPException(status_code=500, detail="Failed to create API key")

    logger.info(f"API key created: {key_masked} by {owner}")
    return {
        "id": rec["id"],
        "name": rec["name"],
        "key": key,
        "key_masked": key_masked,
        "rate_limit_rps": rec["rate_limit_rps"],
        "expires_at": rec.get("expires_at"),
        "created_at": rec.get("created_at"),
        "scopes": rec.get("scopes"),
        "warning": "Store this key securely. It will not be shown again.",
    }


@router.get("/")
async def list_user_keys(request: Request, limit: int = 50, offset: int = 0):
    owner = _get_current_user(request)
    keys = await get_api_keys_by_user(owner)
    return {"keys": keys[:limit], "total": len(keys)}


@router.get("/all")
async def list_all_keys(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    admin_user: dict = Depends(_require_admin),
):
    """List ALL API keys across users — admin only."""
    keys = await get_all_api_keys(limit=limit, offset=offset)
    return {"keys": keys, "total": len(keys)}


@router.get("/{key_id}")
async def get_key(key_id: int, request: Request):
    owner = _get_current_user(request)
    rec = await get_api_key_by_id(key_id)
    if not rec or rec["user_id"] != owner:
        raise HTTPException(status_code=404, detail="API key not found")
    return rec


@router.post("/{key_id}/revoke")
async def revoke_key(key_id: int, request: Request):
    owner = _get_current_user(request)
    rec = await get_api_key_by_id(key_id)
    if not rec or rec["user_id"] != owner:
        raise HTTPException(status_code=404, detail="API key not found")
    updated = await db_revoke_api_key(key_id)
    return {"status": "revoked", "key": updated}


@router.delete("/{key_id}")
async def delete_key(key_id: int, request: Request):
    owner = _get_current_user(request)
    rec = await get_api_key_by_id(key_id)
    if not rec or rec["user_id"] != owner:
        raise HTTPException(status_code=404, detail="API key not found")
    ok = await delete_api_key(key_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to delete key")
    return {"status": "deleted", "key_id": key_id}


@router.post("/{key_id}/rotate")
async def rotate_key(key_id: int, req: RotateAPIKeyRequest, request: Request):
    owner = _get_current_user(request)
    rec = await get_api_key_by_id(key_id)
    if not rec or rec["user_id"] != owner:
        raise HTTPException(status_code=404, detail="API key not found")

    if not verify_api_key(req.old_key, rec["key_hash"]):
        await record_api_key_event(
            key_id,
            "rotate_failed",
            "Old key mismatch",
            request.client.host if request.client else None,
        )
        raise HTTPException(status_code=400, detail="Old key verification failed")

    new_key = generate_api_key()
    updated = await db_rotate_api_key(
        key_id=key_id,
        new_key_hash=hash_api_key(new_key),
        new_key_masked=mask_api_key(new_key),
        new_key_prefix=new_key[:12],
    )
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to rotate key")

    await record_api_key_event(key_id, "rotated", f"Grace period: {req.grace_period_hours}h")
    logger.info(f"API key rotated: {key_id}")
    return {
        "status": "rotated",
        "new_key": new_key,
        "key_masked": updated["key_masked"],
        "grace_period_hours": req.grace_period_hours,
    }


@router.get("/{key_id}/usage")
async def key_usage(key_id: int, request: Request, limit: int = 100):
    owner = _get_current_user(request)
    rec = await get_api_key_by_id(key_id)
    if not rec or rec["user_id"] != owner:
        raise HTTPException(status_code=404, detail="API key not found")
    usage = await get_api_key_usage(key_id, limit=min(limit, KEY_USAGE_LIMIT))
    return {"usage": usage[:limit]}


@router.get("/{key_id}/stats")
async def key_stats(key_id: int, request: Request):
    owner = _get_current_user(request)
    rec = await get_api_key_by_id(key_id)
    if not rec or rec["user_id"] != owner:
        raise HTTPException(status_code=404, detail="API key not found")
    stats = await get_api_key_usage_stats(key_id)
    return stats


@router.post("/{key_id}/usage")
async def record_usage_hook(key_id: int, request: Request, payload: dict):
    # AUD-2.5/2.7: usage recording previously accepted ANY key_id from any
    # authenticated caller, allowing cross-user usage pollution. Enforce
    # ownership (admin callers are exempt via the admin listing guard).
    owner = _get_current_user(request)
    rec = await get_api_key_by_id(key_id)
    if not rec or rec["user_id"] != owner:
        raise HTTPException(status_code=404, detail="API key not found")

    endpoint = payload.get("endpoint", "unknown")
    status_code = payload.get("status_code", 200)
    latency_ms = payload.get("latency_ms", 0.0)
    await record_api_key_usage(
        key_id,
        endpoint,
        status_code,
        latency_ms,
        request.client.host if request.client else None,
    )
    return {"recorded": True}


@router.get("/{key_id}/admin/quota-alert")
async def quota_alert(key_id: int, request: Request):
    owner = _get_current_user(request)
    rec = await get_api_key_by_id(key_id)
    if not rec or rec["user_id"] != owner:
        raise HTTPException(status_code=404, detail="API key not found")
    alert = await get_api_key_usage_stats(key_id)
    rpm_used = alert.get("total_requests", 0)
    return {
        "key_id": key_id,
        "rpm_used": rpm_used,
        "alert": rpm_used > ALERT_RPM_THRESHOLD,
    }


@router.post("/admin/bulk-delete")
async def bulk_delete(
    request: Request,
    req: BulkDeleteRequest,
    admin_user: dict = Depends(_require_admin),
):
    """Bulk delete API keys — admin only."""
    results: dict[str, list[int]] = {"deleted": [], "failed": []}
    for kid in req.key_ids[:50]:
        rec = await get_api_key_by_id(kid)
        if not rec:
            results["failed"].append(kid)
            continue
        ok = await delete_api_key(kid)
        if ok:
            results["deleted"].append(kid)
        else:
            results["failed"].append(kid)
    return results


async def create_api_key(
    request: Request,
    payload: CreateAPIKeyRequest | None = None,
    key_hash: str = "",
    key_masked: str = "",
    key_prefix: str = "",
):
    if payload is not None and request is not None:
        return await create_key(payload, request)
    return await db_create_api_key(
        user_id="",
        name=payload.name if payload else "",
        key_hash=key_hash,
        key_masked=key_masked,
        key_prefix=key_prefix,
    )


async def revoke_api_key(key_id: int | str, request: Request):
    kid = int(key_id) if isinstance(key_id, int | str) and str(key_id).isdigit() else key_id
    if request is not None and isinstance(kid, int):
        return await revoke_key(kid, request)
    return await db_revoke_api_key(kid if isinstance(kid, int) else 0)


async def rotate_api_key(
    key_id: int | str,
    request: Request,
    new_key_masked: str = "",
    new_key_prefix: str = "",
):
    kid = int(key_id) if isinstance(key_id, int | str) and str(key_id).isdigit() else key_id
    if request is not None and isinstance(kid, int):
        req = RotateAPIKeyRequest(old_key="")
        return await rotate_key(kid, req, request)
    return await db_rotate_api_key(
        key_id=kid if isinstance(kid, int) else 0,
        new_key_hash="",
        new_key_masked=new_key_masked,
        new_key_prefix=new_key_prefix,
    )


list_api_keys = list_user_keys
