"""Simulator admin API — device profile / install / session management admin endpoints.

বাংলা মন্তব্য: সিমুলেটর অ্যাডমিন এপিআই যা সিমুলেটর ব্যবহারের স্ট্যাটিস্টিকস ও কোটা ম্যানেজ করে।
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_current_admin
from api.routes.simulator import (
    _IN_MEMORY_KNOWN_USERS,
    _KNOWN_USERS_SET,
    _redis,
    _save_profile,
    _use_redis,
    get_or_create_profile,
)

router = APIRouter(prefix="/api/simulator", tags=["simulator-admin"])


@router.get("/admin/usage")
async def get_all_usage(admin_user: dict = Depends(get_current_admin)):
    if not _use_redis():
        user_ids = list(_IN_MEMORY_KNOWN_USERS)
    else:
        redis_mgr = _redis()
        user_ids = await redis_mgr.client.smembers(_KNOWN_USERS_SET)

    deployments = []
    for user_id in user_ids:
        profile = await get_or_create_profile(user_id)
        for app in profile["installedApps"]:
            deployments.append(
                {
                    "appId": app["appId"],
                    "deviceType": profile["device"]["type"],
                    "previewUrl": app["previewUrl"],
                    "status": app["status"],
                    "deployedAt": app["installedAt"],
                }
            )
    return {"totalDeployments": len(deployments), "deployments": deployments}


@router.post("/admin/set-quota/{userId}")
async def admin_set_quota(userId: str, quota: int, admin_user: dict = Depends(get_current_admin)):
    profile = await get_or_create_profile(userId)
    profile["installQuota"] = max(1, min(20, quota))
    await _save_profile(userId, profile)
    return profile
