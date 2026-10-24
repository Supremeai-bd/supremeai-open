"""Simulator user API — device profile / install / session management.

State moved from in-memory dicts to Upstash Redis (2026-07-19) so the
User and Admin services (separate processes) see consistent data.

Falls back to in-memory dicts if Redis is unavailable (e.g. in test environments).

বাংলা মন্তব্য: সিমুলেটর ইউজার এপিআই যা আপস্ট্যাশ রেডিস ডেটাবেস ব্যবহার করে, কিন্তু টেস্ট এনভায়রনমেন্টে লোকাল মেমোরি ফলব্যাক ব্যবহার করে।
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.cache.redis_manager import redis_manager
from core.config import settings
from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.security.authentication.rbac import get_current_user_token

router = APIRouter(
    prefix="/api/simulator", tags=["simulator"], dependencies=[Depends(get_current_user_token)]
)

_PROFILE_KEY = "simulator:profile:{user_id}"
_SESSION_KEY = "simulator:session:{user_id}"
_KNOWN_USERS_SET = "simulator:known_users"
_PROFILE_TTL = 30 * 86400  # 30 days — mock/test data, not meant to be permanent

DEVICE_PROFILES = [
    {
        "type": "PIXEL_6",
        "name": "Google Pixel 6",
        "osVersion": "Android 12",
        "screenResolution": "1080x2400",
        "densityDpi": 411,
    },
    {
        "type": "IPHONE_13",
        "name": "Apple iPhone 13",
        "osVersion": "iOS 15",
        "screenResolution": "1170x2532",
        "densityDpi": 460,
    },
]

# Fallbacks for test/local environments when Redis is not running
_IN_MEMORY_PROFILES: dict[str, Any] = {}
_IN_MEMORY_SESSIONS: dict[str, Any] = {}
_IN_MEMORY_KNOWN_USERS: set[str] = set()


# ══════════════════════════════════════════════════════════════════════════════
# ✅ NEW: Dynamic URL Resolution using existing config system
# ══════════════════════════════════════════════════════════════════════════════
def _get_public_base_url() -> str:
    """
    Derive public-facing base URL using existing SupremeAI config infrastructure.

    Priority order:
    1. SUPREMEAI_PUBLIC_URL env var (explicit override for Docker/K8s)
    2. settings.auto_backend_url (your existing platform detection)
    3. SUPREMEAI_BACKEND_URL or BACKEND_URL env var
    4. Localhost ONLY when ENV=local/dev/test

    Raises:
        RuntimeError: If no valid URL in production (fail-fast)
    """
    # 1. Explicit public URL override (for reverse proxy scenarios)
    public_url = os.environ.get("SUPREMEAI_PUBLIC_URL")
    if public_url:
        return public_url.rstrip("/")

    # 2. Use existing platform detection system
    try:
        auto_url = settings.auto_backend_url
        if auto_url:
            return auto_url.rstrip("/")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception(f"Silenced error: {e}")

    # 3. Backend URL environment variables
    backend_url = os.environ.get("SUPREMEAI_BACKEND_URL") or os.environ.get("BACKEND_URL")
    if backend_url:
        # Remove /api/v1 suffix if present (we add our own paths)
        base = backend_url.rstrip("/")
        for suffix in ["/api/v1", "/api", "/v1"]:
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        return base

    # 4. Environment check — ONLY allow localhost in local/dev mode
    current_env = getattr(settings, "env", "local") or os.environ.get("ENV", "local")
    is_local = current_env.lower() in ("local", "development", "dev", "test")

    if is_local:
        logger.warning(
            "[simulator] No PUBLIC_URL/BACKEND_URL set; "
            f"using http://127.0.0.1:8000 (acceptable only in {current_env} mode)"  # is_local()
        )
        return "http://127.0.0.1:8000"  # is_local()

    # 5. Production fail-fast
    raise RuntimeError(
        f"[simulator] Cannot determine public URL for preview/websocket endpoints. "
        f"Set SUPREMEAI_PUBLIC_URL or BACKEND_URL environment variable. "
        f"Current ENV={current_env}"
    )


def _get_websocket_base_url() -> str:
    """Convert HTTP base URL to WebSocket URL."""
    http_base = _get_public_base_url()
    # Convert protocol: http -> ws, https -> wss
    ws_base = http_base.replace("https://", "wss://").replace("http://", "ws://")
    return ws_base


class DeviceUpdateRequest(BaseModel):
    type: str
    osVersion: str | None = None  # -- camelCase required to match frontend JSON API contract
    screenResolution: str | None = None  # -- camelCase required to match frontend JSON API contract
    densityDpi: int | None = None  # -- camelCase required to match frontend JSON API contract


class ProfileUpdateRequest(BaseModel):
    installQuota: int | None = None  # -- camelCase required to match frontend JSON API contract
    device: DeviceUpdateRequest | None = None


class InstallRequest(BaseModel):
    appId: str  # -- camelCase required to match frontend JSON API contract
    deviceProfile: str | None = (
        "PIXEL_6"  # -- camelCase required to match frontend JSON API contract
    )


@with_error_bus("_use_redis")
def _use_redis() -> bool:
    try:
        if redis_manager is None or redis_manager.client is None:
            return False
        # If client is mocked in test environment, fallback to in-memory store
        client_type = type(redis_manager.client).__name__
        if "Mock" in client_type:
            return False
        url = getattr(redis_manager, "url", "")
        if not url or "mock" in url.lower():
            return False
        return True
    except Exception:
        return False


def _redis():
    if not _use_redis():
        raise HTTPException(status_code=503, detail="Simulator state store unavailable")
    return redis_manager


async def get_or_create_profile(user_id: str) -> dict[str, Any]:
    if not _use_redis():
        if user_id not in _IN_MEMORY_PROFILES:
            _IN_MEMORY_PROFILES[user_id] = {
                "userId": user_id,
                "installQuota": 5,
                "activeInstalls": 0,
                "device": DEVICE_PROFILES[0],
                "installedApps": [],
            }
            _IN_MEMORY_KNOWN_USERS.add(user_id)
        return _IN_MEMORY_PROFILES[user_id]

    redis_mgr = redis_manager
    raw = await redis_mgr.get_cache(_PROFILE_KEY.format(user_id=user_id))
    if raw:
        return json.loads(raw)

    profile = {
        "userId": user_id,
        "installQuota": 5,
        "activeInstalls": 0,
        "device": DEVICE_PROFILES[0],
        "installedApps": [],
    }
    await _save_profile(user_id, profile)
    await redis_mgr.client.sadd(_KNOWN_USERS_SET, user_id)
    return profile


async def _save_profile(user_id: str, profile: dict[str, Any]) -> None:
    if not _use_redis():
        _IN_MEMORY_PROFILES[user_id] = profile
        return

    redis_mgr = redis_manager
    await redis_mgr.set_cache(
        _PROFILE_KEY.format(user_id=user_id),
        json.dumps(profile),
        ex_seconds=_PROFILE_TTL,
    )


async def _get_session(user_id: str) -> dict[str, Any] | None:
    if not _use_redis():
        return _IN_MEMORY_SESSIONS.get(user_id)

    redis_mgr = redis_manager
    raw = await redis_mgr.get_cache(_SESSION_KEY.format(user_id=user_id))
    return json.loads(raw) if raw else None


async def _save_session(user_id: str, session: dict[str, Any]) -> None:
    if not _use_redis():
        _IN_MEMORY_SESSIONS[user_id] = session
        return

    redis_mgr = redis_manager
    await redis_mgr.set_cache(
        _SESSION_KEY.format(user_id=user_id),
        json.dumps(session),
        ex_seconds=_PROFILE_TTL,
    )


async def _delete_session(user_id: str) -> None:
    if not _use_redis():
        _IN_MEMORY_SESSIONS.pop(user_id, None)
        return

    redis_mgr = redis_manager
    await redis_mgr.client.delete(_SESSION_KEY.format(user_id=user_id))


@router.get("/profile")
async def get_profile(userId: str = "default"):
    return await get_or_create_profile(userId)


@router.post("/profile")
async def update_profile(updates: ProfileUpdateRequest, userId: str = "default"):
    profile = await get_or_create_profile(userId)
    if updates.installQuota is not None:
        profile["installQuota"] = updates.installQuota
    if updates.device is not None:
        profile["device"].update(updates.device.model_dump(exclude_unset=True))
    await _save_profile(userId, profile)
    return profile


@router.post("/install")
async def install_app(req: InstallRequest, userId: str = "default"):
    profile = await get_or_create_profile(userId)
    if profile["activeInstalls"] >= profile["installQuota"]:
        raise HTTPException(status_code=400, detail="Install quota exceeded")

    existing = next((a for a in profile["installedApps"] if a["appId"] == req.appId), None)
    if existing:
        return {
            "success": True,
            "app": existing,
            "quota": {
                "used": profile["activeInstalls"],
                "total": profile["installQuota"],
            },
        }

    # ✅ FIXED: Use dynamic URL instead of hardcoded 127.0.0.1 # is_local()
    base_url = _get_public_base_url()

    app = {
        "appId": req.appId,
        "appName": f"App {req.appId}",
        "version": "1.0.0",
        "previewUrl": f"{base_url}/preview/{req.appId}",  # ✅ DYNAMIC
        "installedAt": datetime.now(UTC).isoformat(),
        "launchCount": 0,
        "lastLaunchedAt": None,
        "status": "INSTALLED",
    }
    profile["installedApps"].append(app)
    profile["activeInstalls"] += 1
    await _save_profile(userId, profile)
    return {
        "success": True,
        "app": app,
        "quota": {"used": profile["activeInstalls"], "total": profile["installQuota"]},
    }


@router.delete("/install/{appId}")
async def uninstall_app(appId: str, userId: str = "default"):
    profile = await get_or_create_profile(userId)
    initial_len = len(profile["installedApps"])
    profile["installedApps"] = [a for a in profile["installedApps"] if a["appId"] != appId]
    if len(profile["installedApps"]) < initial_len:
        profile["activeInstalls"] -= 1
    await _save_profile(userId, profile)
    return {"success": True}


@router.get("/installed")
async def get_installed_apps(userId: str = "default"):
    profile = await get_or_create_profile(userId)
    return {
        "installedApps": profile["installedApps"],
        "quota": {"used": profile["activeInstalls"], "total": profile["installQuota"]},
    }


@router.post("/session/start")
async def start_session(appId: str, userId: str = "default"):
    profile = await get_or_create_profile(userId)
    app = next((a for a in profile["installedApps"] if a["appId"] == appId), None)
    if not app:
        raise HTTPException(status_code=404, detail="App not installed")

    app["launchCount"] += 1
    app["lastLaunchedAt"] = datetime.now(UTC).isoformat()
    app["status"] = "RUNNING"
    await _save_profile(userId, profile)

    session_id = f"sess_{userId}_{appId}"

    # ✅ FIXED: Use dynamic websocket URL instead of hardcoded 127.0.0.1 # is_local()
    ws_base = _get_websocket_base_url()

    session = {
        "sessionId": session_id,
        "websocketUrl": f"{ws_base}/ws/simulator/{session_id}",  # ✅ DYNAMIC
        "previewUrl": app["previewUrl"],
        "state": "RUNNING",
        "startedAt": datetime.now(UTC).isoformat(),
        "activeAppId": appId,
        "lastHeartbeat": datetime.now(UTC).isoformat(),
    }
    await _save_session(userId, session)
    return session


@router.post("/session/stop")
async def stop_session(userId: str = "default"):
    session = await _get_session(userId)
    if session:
        app_id = session.get("activeAppId")
        profile = await get_or_create_profile(userId)
        app = next((a for a in profile["installedApps"] if a["appId"] == app_id), None)
        if app:
            app["status"] = "INSTALLED"
            await _save_profile(userId, profile)
        await _delete_session(userId)
    return {"success": True}


@router.get("/session/status")
async def get_session_status(userId: str = "default"):
    session = await _get_session(userId)
    if not session:
        return {"hasSession": False}
    return {
        "hasSession": True,
        "sessionId": session["sessionId"],
        "activeAppId": session["activeAppId"],
        "state": session["state"],
        "lastHeartbeat": session["lastHeartbeat"],
    }


@router.get("/devices")
def get_available_devices():
    return DEVICE_PROFILES
