"""Approval Manager — Human-in-the-Loop approval workflow with secure file operations.

বাংলা: মানবাধীন অনুমোদন কর্মকাণ্ড ও নিরাপদ ফাইল অপারেশন সহ।

AUD-4 hardening (P0):
- Approval state transitions are atomic (replay/duplicate/expired decisions rejected);
- Payload tampering is detected via canonical SHA-256 integrity hash;
- A cancel endpoint exists (authoritative cancellation);
- Executed approvals are recorded so side effects cannot run twice;
- The notification WebSocket requires an authenticated admin (previously open);
- Security audit events are emitted for every request/decision/failure.
"""

import asyncio
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from fastapi.websockets import WebSocketDisconnect
from pydantic import BaseModel

from api.dependencies import get_project_admin
from core.code_validator import AICodeValidator
from core.logging_config import logger
from core.security.ws_auth import authenticate_websocket
from models.pending_tasks import (
    ApprovalStateError,
    TaskStatus,
    cancel_task,
    list_pending,
    mark_executed,
    update_task_status,
)

router = APIRouter(prefix="/api/v1/hitl", tags=["hitl"])

_connections: list[WebSocket] = []

# Path validation for skill generation
_ALLOWED_SKILLS_DIR = None


def _get_allowed_skills_dir() -> str:
    """Get canonical skills directory path once."""
    global _ALLOWED_SKILLS_DIR
    if _ALLOWED_SKILLS_DIR is None:
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        _ALLOWED_SKILLS_DIR = os.path.join(backend_dir, "skills")
    return _ALLOWED_SKILLS_DIR


class ApproveRequest(BaseModel):
    resolved_by: str = "admin"
    reason: str | None = None
    otp: str | None = None


def _audit(event: str, task_id: str, actor: str, outcome: str, detail: str | None = None) -> None:
    """Persist an audit event for the approval workflow (AUD-4.9 / AUD-3.8).

    The canonical ``log_security_event`` is async; approval routes run in
    FastAPI's threadpool (sync ``def``), so we emit a structured log event and
    best-effort persist to the Redis audit stream synchronously.
    """
    try:
        import json
        import uuid
        from datetime import UTC, datetime

        from core.cache.redis_manager import redis_manager

        event_id = f"sec-{uuid.uuid4().hex[:12]}"
        event = {
            "event_id": event_id,
            "event_type": f"hitl.{event}",
            "user_id": actor,
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": "INFO",
            "details": {"resource": f"approval:{task_id}", "outcome": outcome, "detail": detail},
        }
        logger.bind(event_type=event["event_type"], severity="INFO").info(
            f"🛡️ HITL Audit: {event['event_type']} | approval={task_id} | {outcome} | by {actor}"
        )
        client = getattr(redis_manager, "client", None)
        if client is not None:
            try:
                payload = json.dumps(event, default=str)
                pipe = client.pipeline()
                pipe.setex(f"audit:event:{event_id}", 86400 * 30, payload)
                pipe.lpush("audit:recent:", payload)
                pipe.ltrim("audit:recent:", 0, 999)
                pipe.execute()
            except Exception as exc:
                logger.debug(f"HITL audit Redis persistence skipped: {exc}")
    except Exception as exc:  # audit failures must never block the decision path
        logger.debug(f"HITL audit event not persisted: {exc}")


@router.get("/pending")
def get_pending(
    user: dict = Depends(get_project_admin),
) -> list[dict[str, Any]]:
    """Get all pending tasks - REQUIRES admin authentication."""
    return [t.model_dump() for t in list_pending(user["tenant_id"])]


@router.post("/approve/{task_id}")
def approve_task(
    task_id: str,
    req: ApproveRequest,
    _: dict = Depends(get_project_admin),
) -> dict[str, Any]:
    """Approve a pending task - REQUIRES admin authentication."""
    user = _
    _audit("request", task_id, req.resolved_by, "received")
    try:
        task = update_task_status(
            task_id,
            TaskStatus.APPROVED,
            user.get("subject") or req.resolved_by,
            req.reason,
            tenant_id=user.get("tenant_id"),
        )
    except Exception as exc:
        # AUD-4.3/4.4/4.5/4.6: replay, expiry, tampering and races are rejected here.
        status_code = 410 if type(exc).__name__ == "TaskExpiredError" else 409
        _audit("decision", task_id, req.resolved_by, "rejected", str(exc))
        safe_msg = (
            str(exc)
            if isinstance(exc, ApprovalStateError)
            else "Approval request could not be processed"
        )
        raise HTTPException(status_code=status_code, detail=safe_msg) from exc
    if not task:
        _audit("decision", task_id, req.resolved_by, "not_found")
        raise HTTPException(status_code=404, detail="Task not found")

    if task.task_type == "SKILL_GENERATION":
        try:
            skill_name = task.payload.get("skill_name")
            code = task.payload.get("generated_code")

            if not skill_name or not code:
                raise HTTPException(status_code=400, detail="Missing skill_name or generated_code")

            if not skill_name.replace("_", "").replace("-", "").isalnum():
                raise HTTPException(status_code=400, detail="Invalid skill name format")

            # বাংলা মন্তব্য: রেন্ডার ডকার লেআউটের জন্য সঠিক AICodeValidator ক্লাস এবং can_use ভ্যালিডেশন কী ব্যবহার করা হলো
            validator = AICodeValidator()
            validation_result = validator.validate_before_use(code)
            if not validation_result.get("can_use", False):
                raise HTTPException(
                    status_code=400,
                    detail=f"Code validation failed: {validation_result.get('checks', {})}",
                )

            skills_dir = _get_allowed_skills_dir()
            os.makedirs(skills_dir, exist_ok=True)
            path = os.path.join(skills_dir, f"{skill_name}.py")

            real_path = os.path.realpath(path)
            if not real_path.startswith(os.path.realpath(skills_dir)):
                raise HTTPException(status_code=403, detail="Path traversal attempt blocked")

            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
            logger.info(f"✅ Approved skill '{skill_name}' successfully written to {path}")

            # AUD-4.5: record execution so approving twice cannot rewrite the
            # skill file (duplicate-execution guard).
            mark_executed(task_id, req.resolved_by)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to execute approved skill generation: {e}")
            _audit("execution", task_id, req.resolved_by, "failed", str(e))
            raise HTTPException(status_code=500, detail="Skill execution failed") from e

    _audit("decision", task_id, req.resolved_by, "approved")
    return {"status": "approved", "task": task.model_dump()}


@router.post("/reject/{task_id}")
def reject_task(
    task_id: str,
    req: ApproveRequest,
    user: dict = Depends(get_project_admin),
) -> dict[str, Any]:
    """Reject a pending task - REQUIRES admin authentication."""
    try:
        task = update_task_status(
            task_id, TaskStatus.REJECTED, user["subject"], req.reason, tenant_id=user["tenant_id"]
        )
    except Exception as exc:
        status_code = 410 if type(exc).__name__ == "TaskExpiredError" else 409
        _audit("decision", task_id, req.resolved_by, "rejected", str(exc))
        safe_msg = (
            str(exc)
            if isinstance(exc, ApprovalStateError)
            else "Reject request could not be processed"
        )
        raise HTTPException(status_code=status_code, detail=safe_msg) from exc
    if not task:
        _audit("decision", task_id, req.resolved_by, "not_found")
        raise HTTPException(status_code=404, detail="Task not found")
    logger.info(f"❌ Task {task_id} rejected by {req.resolved_by}. Reason: {req.reason}")
    _audit("decision", task_id, req.resolved_by, "rejected", req.reason)
    return {"status": "rejected", "task": task.model_dump()}


@router.post("/cancel/{task_id}")
def cancel_task_route(
    task_id: str,
    req: ApproveRequest,
    user: dict = Depends(get_project_admin),
) -> dict[str, Any]:
    """Authoritative cancellation (AUD-4.7) - REQUIRES admin authentication."""
    try:
        task = cancel_task(task_id, user["subject"], req.reason, tenant_id=user["tenant_id"])
    except Exception as exc:
        status_code = 410 if type(exc).__name__ == "TaskExpiredError" else 409
        _audit("decision", task_id, req.resolved_by, "cancel_rejected", str(exc))
        safe_msg = (
            str(exc)
            if isinstance(exc, ApprovalStateError)
            else "Cancellation request could not be processed"
        )
        raise HTTPException(status_code=status_code, detail=safe_msg) from exc
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    _audit("decision", task_id, req.resolved_by, "cancelled", req.reason)
    return {"status": "cancelled", "task": task.model_dump()}


@router.websocket("/ws/hitl")
async def hitl_ws(ws: WebSocket):
    """WebSocket endpoint for HITL notifications.

    AUD-2.1: previously open to anyone; now requires a valid admin token
    (query string ``?token=`` or first-message auth handshake).
    """
    user = await authenticate_websocket(ws, ws.query_params.get("token"), require_admin=True)
    if user is None:
        return
    await ws.accept()
    _connections.append(ws)
    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        _connections.remove(ws)
    except asyncio.CancelledError:
        _connections.remove(ws)
        raise
