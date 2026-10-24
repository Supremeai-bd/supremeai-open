"""Task lifecycle endpoints (Neon-backed canonical implementations).

Hygiene note (2026-09-17 cleanup): the legacy in-memory duplicate handlers
(``TASKS``-backed POST /tasks/{id}/complete, /fail and DELETE /tasks/{id})
that were shadowed by the Neon versions registered above them have been
removed — they were dead code (first-registered route wins at match time)
and carried an unreachable block after ``return``. Only ``FINDINGS`` remains
in-process (bounded, see ``MAX_FINDINGS``) because it is the sole
implementation of the findings endpoints.
"""

import uuid
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_current_tenant, get_current_user_token
from api.routes.browser import router
from core.neon_repository import (
    create_task as create_neon_task,
)
from core.neon_repository import (
    delete_task as delete_neon_task,
)
from core.neon_repository import (
    update_task_status as update_neon_task_status,
)
from core.task_policy import evaluate_goal

FINDINGS: list[dict[str, Any]] = []

# বাংলা মন্তব্য: সার্কিট ব্রেকার থ্রেশোল্ড — টাস্ক এক্সিকিউশন ক্যাপ (৪৫ সেকেন্ড)
EXECUTION_CAP_MS = 45000

# বাংলা মন্তব্য: in-memory FINDINGS আনবাউন্ডেড বৃদ্ধি রোধ — সর্বশেষ ৫০০টি রাখা হয়
MAX_FINDINGS = 500


class GoalRequest(BaseModel):
    goal: str


class TaskPreviewRequest(BaseModel):
    url: str | None = Field(default=None, max_length=2048)
    goal: str = Field(min_length=1, max_length=10_000)
    approved: bool = False


@router.post("/tasks/preview")
async def preview_task(
    req: TaskPreviewRequest,
    user: dict = Depends(get_current_user_token),
    tenant_id: str = Depends(get_current_tenant),
):
    actor_id = str(user.get("sub") or "")
    decision = evaluate_goal(req.goal, actor_id)
    if not actor_id:
        raise HTTPException(status_code=401, detail="Authenticated user required")
    if not decision.allowed:
        return {"status": "manual", "risk": decision.risk, "message": decision.message}
    if decision.risk == "approval" and not req.approved:
        return {"status": "approval_required", "risk": decision.risk, "message": decision.message}
    task_id = uuid.uuid4()
    task = await create_neon_task(
        task_id=task_id,
        tenant_id=tenant_id,
        user_id=actor_id,
        url=req.url,
        goal=req.goal,
        status="ACTIVE",
        plan=[{"risk": decision.risk, "message": decision.message}],
    )
    return {
        "status": "started",
        "message": "Your safe task has started. SupremeAI will pause if it needs your approval.",
        "task": task,
    }


@router.post("/tasks")
async def create_task(
    req: GoalRequest,
    user: dict = Depends(get_current_user_token),
    tenant_id: str = Depends(get_current_tenant),
):
    owner_id = str(user.get("sub") or "")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Authenticated user required")
    return await create_neon_task(
        task_id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=owner_id,
        url=None,
        goal=req.goal,
        status="ACTIVE",
    )


async def _set_task_status(
    task_id: str,
    status: str,
    user: dict = Depends(get_current_user_token),
    tenant_id: str = Depends(get_current_tenant),
):
    owner_id = str(user.get("sub") or "")
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    updated = await update_neon_task_status(
        task_id=task_uuid, tenant_id=tenant_id, user_id=owner_id, status=status
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "status": status}


@router.post("/tasks/{id}/circuit-open")
async def set_task_circuit_open(
    task_id: str,
    user: dict = Depends(get_current_user_token),
    tenant_id: str = Depends(get_current_tenant),
):
    return await _set_task_status(task_id, "CIRCUIT_OPEN", user, tenant_id)


@router.post("/tasks/{id}/complete")
async def set_task_complete(
    task_id: str,
    user: dict = Depends(get_current_user_token),
    tenant_id: str = Depends(get_current_tenant),
):
    return await _set_task_status(task_id, "SUCCESS", user, tenant_id)


@router.post("/tasks/{id}/fail")
async def set_task_failed(
    task_id: str,
    user: dict = Depends(get_current_user_token),
    tenant_id: str = Depends(get_current_tenant),
):
    return await _set_task_status(task_id, "FAILED", user, tenant_id)


@router.delete("/tasks/{id}")
async def delete_task(
    task_id: str,
    user: dict = Depends(get_current_user_token),
    tenant_id: str = Depends(get_current_tenant),
):
    owner_id = str(user.get("sub") or "")
    try:
        deleted = await delete_neon_task(
            task_id=uuid.UUID(task_id), tenant_id=tenant_id, user_id=owner_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True}


@router.get("/tasks/{id}/findings")
def get_findings(task_id: str):
    task_findings = [f for f in FINDINGS if f.get("taskId") == task_id]
    return {"findings": task_findings}


@router.post("/findings")
def add_finding(finding: dict[str, Any]):
    FINDINGS.append(finding)
    # বাংলা মন্তব্য: সর্বশেষ MAX_FINDINGS-টি ছাড়া বাকি ফেলে দিয়ে unbounded growth বন্ধ
    del FINDINGS[:-MAX_FINDINGS]
    return finding
