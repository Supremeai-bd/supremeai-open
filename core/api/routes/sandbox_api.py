"""
Sandbox API Routes
==================

Persistent cloud sandbox এর জন্য REST + SSE এন্ডপয়েন্ট।
Devin-এর মতো স্বায়ত্তশাসিত কোডিং ক্ষমতার জন্য এই রাউটগুলো ব্যবহৃত হয়।

Endpoints:
  POST /api/v1/sandbox/create       — নতুন persistent sandbox তৈরি
  POST /api/v1/sandbox/{id}/execute — কমান্ড রান করা
  GET  /api/v1/sandbox/{id}/logs    — লাইভ লগ স্ট্রিমিং (SSE)
  DELETE /api/v1/sandbox/{id}       — sandbox মুছে ফেলা
  GET  /api/v1/sandbox/list         — নিজের sandbox-গুলোর তালিকা

BREAKING-BUG FIX (AUDIT-SEC-7, HIGH):
  আগে এই ফাইলটি `tools.cloud_sandbox_orchestrator.PersistentSandbox` import করত —
  এই মডিউল বা ক্লাস কোডবেসের কোথাও বিদ্যমানই নেই (শুধু প্রকৃত ক্লাস:
  core/orchestration/cloud_sandbox_orchestrator.py::CloudSandboxOrchestrator)।
  import lazy হওয়ায় রাউটার মাউন্ট হত, কিন্তু ৫টি এন্ডপয়েন্টের প্রতিটি
  রানটাইমে 500 (ModuleNotFoundError) দিত — অর্থাৎ পুরো সারফেস ১০০% ভাঙা।
  এখন প্রকৃত CloudSandboxOrchestrator API-র বিরুদ্ধে রিরাইট করা হয়েছে।

🛡️ SECURITY FIX (CRITICAL): এই router-এর কোনো endpoint-এই আগে কোনো
authentication ছিল না — POST /{sandbox_id}/execute সরাসরি শেল কমান্ড চালায়
(প্রকৃত remote code execution)। router-level auth + per-user OWNERSHIP যাচাই
যোগ করা হয়েছে: ইউজার শুধু নিজের তৈরি sandbox দেখতে/চালাতে/মুছতে পারবে
(আগে /list সব ইউজারের sandbox id লিক করত এবং যে কেউ অন্যের sandbox-এ
কমান্ড চালাতে পারত — cross-tenant RCE)।
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.dependencies import get_current_user_token
from core.state_store import durable_state

router = APIRouter(
    prefix="/api/v1/sandbox", tags=["sandbox"], dependencies=[Depends(get_current_user_token)]
)

# বাংলা মন্তব্য: অ্যাপ্লিকেশন-স্কোপ স্যান্ডবক্স ম্যানেজার (singleton)।
_sandbox_manager: Any = None

# Issue #448: log the "no sandbox provider configured" CRITICAL only once per
# process instead of on every request (production /api/v1/sandbox/* used to
# surface as a wall of ValueError-driven 500s).
_sandbox_unavailable_announced = False


def _sandbox_unavailable_detail() -> dict[str, str]:
    """Honest, actionable 503 payload for every sandbox endpoint."""
    return {
        "error": "SANDBOX_UNAVAILABLE",
        "message": (
            "No sandbox provider is configured on this deployment. The 'local' "
            "provider is a development dry-run only and is refused in production. "
            "Configure a real provider (E2B / RUNPOD sandbox credentials) to "
            "enable this feature."
        ),
    }


# SECURITY FIX: sandbox_id -> owner (JWT 'sub') mapping. Issue #451: the map
# now ALSO mirrors to the durable state store (Redis federation) — ownership
# survives process restarts, so a stale sandbox can no longer be claimed by a
# different user after a deploy. Mirror hydrates at boot (lifespan).
_OWNERSHIP: dict[str, str] = {}
_ownership_state = durable_state("sandbox_ownership")

# SECURITY FIX: প্রতি ইউজারের sandbox কোটা — রিসোর্স এক্সহসশন রোধে।
_MAX_SANDBOXES_PER_USER = 5


def _get_manager():
    """CloudSandboxOrchestrator ম্যানেজার লেজি-লোড করা হচ্ছে।

    Issue #448: construction previously raised ValueError("Local sandbox
    provider is not permitted in production environments") on every request in
    non-local deployments, surfacing as HTTP 500 across the whole
    /api/v1/sandbox/* surface. Now returns None when no usable provider is
    configured; routes translate that into an honest 503 SANDBOX_UNAVAILABLE.
    """
    global _sandbox_manager, _sandbox_unavailable_announced
    if _sandbox_manager is None:
        # FIX (AUDIT-SEC-7): আগে অসম্ভর মডিউল/ক্লাস (tools.cloud_sandbox_orchestrator.
        # PersistentSandbox) import করা হত। প্রকৃত ক্যানোনিকাল ক্লাস এটি।
        from core.orchestration.cloud_sandbox_orchestrator import CloudSandboxOrchestrator

        try:
            _sandbox_manager = CloudSandboxOrchestrator(provider="local")
        except ValueError as exc:
            if not _sandbox_unavailable_announced:
                _sandbox_unavailable_announced = True
                from core.logging_config import logger

                logger.critical(
                    "Sandbox API unavailable: %s. Configure a real sandbox provider "
                    "(E2B/RUNPOD) — returning honest 503 for all /api/v1/sandbox/* calls.",
                    exc,
                )
            return None
    return _sandbox_manager


def _require_manager():
    """Raise an honest 503 when no sandbox provider is configured (issue #448)."""
    manager = _get_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail=_sandbox_unavailable_detail())
    return manager


def _current_user(payload: dict = Depends(get_current_user_token)) -> str:
    """JWT 'sub' থেকে owner id বের করা (ownership যাচাইয়ের জন্য)।"""
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token structure")
    return str(sub)


def _require_owned(sandbox_id: str, owner: str) -> None:
    """sandbox-টি requester-এর কিনা যাচাই — cross-tenant access ব্লক।"""
    if _OWNERSHIP.get(sandbox_id) != owner:
        # অন্যের sandbox-এর অস্তিত্ব পর্যন্ত ফাঁস করা যাবে না — uniform 404।
        raise HTTPException(status_code=404, detail=f"Sandbox {sandbox_id} not found")


class CreateSandboxRequest(BaseModel):
    spec: dict[str, Any] | None = None
    provider: str = "local"


class ExecuteRequest(BaseModel):
    command: str
    timeout: int = 300


@router.post("/create")
async def create_sandbox(
    req: CreateSandboxRequest, owner: str = Depends(_current_user)
) -> dict[str, Any]:
    """নতুন persistent sandbox সেশন তৈরি করে (owner রেজিস্ট্রি করা হয়)।"""
    mine = [sid for sid, o in _OWNERSHIP.items() if o == owner]
    if len(mine) >= _MAX_SANDBOXES_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=f"Sandbox quota reached ({_MAX_SANDBOXES_PER_USER}); destroy one first",
        )
    try:
        manager = _require_manager()
        session = await manager.create_sandbox(req.spec or {})
        if not session or not isinstance(session, dict) or not session.get("id"):
            raise HTTPException(status_code=502, detail="Sandbox provider did not return a session")
        sandbox_id = str(session["id"])
        _OWNERSHIP[sandbox_id] = owner
        await _ownership_state.set_async(sandbox_id, owner)
        return {
            "status": "success",
            "session_id": sandbox_id,
            "provider": getattr(manager, "provider", req.provider),
            "mock": bool(session.get("mock", False)),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Sandbox creation failed") from e


@router.post("/{sandbox_id}/execute")
async def execute_command(
    sandbox_id: str, req: ExecuteRequest, owner: str = Depends(_current_user)
) -> dict[str, Any]:
    """স্যান্ডবক্স সেশনে একটি কমান্ড রান করে (শুধু owner)।"""
    _require_owned(sandbox_id, owner)
    manager = _require_manager()
    result = await manager.run_command(sandbox_id, req.command, timeout=req.timeout)
    if result is None:
        raise HTTPException(status_code=502, detail="Sandbox command execution failed")
    return result


@router.get("/{sandbox_id}/logs")
async def stream_logs(
    sandbox_id: str,
    request: Request,
    command: str,
    timeout: int = 300,
    owner: str = Depends(_current_user),
):
    """লাইভ লগ স্ট্রিমিং (Server-Sent Events) — শুধু owner।

    বাংলা মন্তব্য: orchestrator-এ persistent log-tail API নেই, তাই কমান্ড রান করে
    stdout/stderr লাইন-বাই-লাইন SSE হিসেবে স্ট্রিম করা হচ্ছে।
    """
    _require_owned(sandbox_id, owner)
    manager = _require_manager()

    async def event_generator():
        # বাংলা মন্তব্য: ক্লায়েন্ট ডিসকানেক্ট করলে স্ট্রিম বন্ধ করা হচ্ছে।
        result = await manager.run_command(sandbox_id, command, timeout=timeout)
        if await request.is_disconnected():
            return
        if result is None:
            yield "data: [error] command execution failed\n\n"
            return
        for line in str(result.get("stdout", "")).splitlines():
            if await request.is_disconnected():
                break
            yield f"data: {line}\n\n"
        for line in str(result.get("stderr", "")).splitlines():
            if await request.is_disconnected():
                break
            yield f"data: [stderr] {line}\n\n"
        yield f"data: [exit] {result.get('exitCode', '?')}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.delete("/{sandbox_id}")
async def destroy_sandbox(sandbox_id: str, owner: str = Depends(_current_user)) -> dict[str, Any]:
    """স্যান্ডবক্স সেশন ও তার ভলিউম মুছে ফেলে (শুধু owner)।"""
    _require_owned(sandbox_id, owner)
    manager = _require_manager()
    success = await manager.destroy_sandbox(sandbox_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Sandbox {sandbox_id} not found or already destroyed",
        )
    _OWNERSHIP.pop(sandbox_id, None)
    await _ownership_state.delete_async(sandbox_id)
    return {"status": "success", "destroyed": sandbox_id}


@router.get("/list")
async def list_sandboxes(owner: str = Depends(_current_user)) -> dict[str, Any]:
    """বর্তমান ইউজারের স্যান্ডবক্স সেশনের তালিকা।

    SECURITY FIX: আগে সব ইউজারের সব sandbox id ফেরত দিত (info leak) —
    এখন শুধু requester-এর মালিকানাধীন সেশনগুলো।
    """
    manager = _require_manager()
    sessions: list[dict[str, Any]] = []
    active = getattr(manager, "_active_sandboxes", {}) or {}
    for sid in _OWNERSHIP:
        if _OWNERSHIP[sid] != owner:
            continue
        info = active.get(sid) if isinstance(active, dict) else None
        status_val = "unknown"
        if isinstance(info, dict):
            status_val = str(info.get("status", "unknown"))
        else:
            remote = await manager.get_sandbox_status(sid)
            if remote:
                status_val = str(remote.get("status", "unknown"))
        sessions.append({"session_id": sid, "status": status_val})
    return {"status": "success", "sessions": sessions}
