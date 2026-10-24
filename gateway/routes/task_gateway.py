"""Canonical Core API task gateway with durable tenant-scoped records."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.deps import get_current_tenant, get_current_user_token
from core.logging_config import logger
from database.session import get_db_session_context
from models.task_record import TaskRecord

router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["TaskGateway"],
    dependencies=[Depends(get_current_user_token)],
)


class TaskSubmission(BaseModel):
    goal: str = Field(min_length=1, max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskHandle(BaseModel):
    task_id: str
    status: str
    goal: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    result: Any = None
    error: str | None = None


def _handle(record: TaskRecord) -> TaskHandle:
    return TaskHandle(
        task_id=record.task_id,
        status=record.status,
        goal=record.goal,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
        result=record.result,
        error=record.error,
    )


async def _owned_record(task_id: str, tenant_id: str) -> TaskRecord:
    async with get_db_session_context() as session:
        result = await session.execute(
            select(TaskRecord).where(
                TaskRecord.task_id == task_id,
                TaskRecord.tenant_id == str(tenant_id),
            )
        )
        record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return record


@router.post("", response_model=TaskHandle)
async def submit_task(
    submission: TaskSubmission,
    user_token: dict[str, Any] = Depends(get_current_user_token),
    tenant_id: str = Depends(get_current_tenant),
) -> TaskHandle:
    """Create a durable, tenant-scoped task record."""
    now = datetime.now(UTC)
    actor_id = str(
        user_token.get("sub") or user_token.get("uid") or user_token.get("user_id") or "anonymous"
    )
    record = TaskRecord(
        task_id=f"task_{uuid.uuid4().hex[:16]}",
        goal=submission.goal,
        status="pending",
        actor_id=actor_id,
        tenant_id=str(tenant_id),
        metadata_json=submission.metadata,
        created_at=now,
        updated_at=now,
    )
    async with get_db_session_context() as session:
        session.add(record)
        await session.commit()
    logger.info(
        "[TaskGateway] Task submitted: id=%s tenant=%s actor=%s",
        record.task_id,
        tenant_id,
        actor_id,
    )
    return _handle(record)


@router.get("/{task_id}", response_model=TaskHandle)
async def get_task_status(
    task_id: str,
    user_token: dict[str, Any] = Depends(get_current_user_token),
    tenant_id: str = Depends(get_current_tenant),
) -> TaskHandle:
    return _handle(await _owned_record(task_id, str(tenant_id)))


@router.post("/{task_id}/cancel", response_model=TaskHandle)
async def cancel_task(
    task_id: str,
    user_token: dict[str, Any] = Depends(get_current_user_token),
    tenant_id: str = Depends(get_current_tenant),
) -> TaskHandle:
    """Cancel a pending or running task without permitting cross-tenant access."""
    async with get_db_session_context() as session:
        result = await session.execute(
            select(TaskRecord).where(
                TaskRecord.task_id == task_id,
                TaskRecord.tenant_id == str(tenant_id),
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        if record.status in {"completed", "failed", "cancelled"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Task is no longer cancellable"
            )
        record.status = "cancelled"
        record.updated_at = datetime.now(UTC)
        await session.commit()
    logger.info("[TaskGateway] Task cancelled: %s", task_id)
    return _handle(record)


__all__ = ["router"]
