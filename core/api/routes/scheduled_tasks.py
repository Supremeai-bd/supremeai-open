# backend/api/routes/scheduled_tasks.py
"""Feature S11: Scheduled Tasks.

Enables users to create, manage, and manually trigger scheduled chat tasks
(one-time, daily, weekly, or custom cron). Execution history is tracked.

Required table:
  scheduled_tasks (see _BOOTSTRAP_SQL below)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_current_user_token
from core.logging_config import logger
from database.supabase_client import db as supabase_db

router = APIRouter(
    prefix="/api/schedule",
    tags=["Scheduled Tasks"],
    dependencies=[Depends(get_current_user_token)],
)

ScheduleType = Literal["once", "daily", "weekly", "custom"]

# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL,
    schedule_type TEXT NOT NULL DEFAULT 'once',
    scheduled_time TIMESTAMPTZ,
    cron_expression TEXT,
    conversation_id UUID,
    is_active BOOLEAN DEFAULT true,
    last_run_at TIMESTAMPTZ,
    last_run_status TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scheduled_task_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES scheduled_tasks(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,
    error TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
"""

_schema_bootstrapped = False


def _ensure_schema() -> None:
    global _schema_bootstrapped
    if _schema_bootstrapped:
        return
    if not supabase_db.client:
        raise HTTPException(status_code=503, detail="Database is not available.")
    try:
        supabase_db.client.rpc("exec_sql", {"query_string": _BOOTSTRAP_SQL}).execute()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception(f"Silenced error: {e}")
    _schema_bootstrapped = True


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ScheduledTaskCreate(BaseModel):
    """Body for creating a scheduled task."""

    title: str = Field(..., min_length=1, max_length=300)
    prompt: str = Field(..., min_length=1)
    schedule_type: ScheduleType = "once"
    scheduled_time: str | None = Field(None, description="ISO-8601 timestamp for one-time tasks.")
    cron_expression: str | None = Field(
        None, description="Cron expression for 'custom' schedule type."
    )
    conversation_id: str | None = Field(
        None, description="Optional conversation to attach the task to."
    )
    is_active: bool = True


class ScheduledTaskUpdate(BaseModel):
    """Body for updating a scheduled task."""

    title: str | None = None
    prompt: str | None = None
    schedule_type: ScheduleType | None = None
    scheduled_time: str | None = None
    cron_expression: str | None = None
    conversation_id: str | None = None
    is_active: bool | None = None


class ScheduledTaskResponse(BaseModel):
    """Serialised scheduled task."""

    id: str
    user_id: str
    title: str
    prompt: str
    schedule_type: str
    scheduled_time: str | None
    cron_expression: str | None
    conversation_id: str | None
    is_active: bool
    last_run_at: str | None
    last_run_status: str | None
    created_at: str
    updated_at: str


class ExecutionHistoryItem(BaseModel):
    """A single execution record."""

    id: str
    task_id: str
    status: str
    result: str | None
    error: str | None
    started_at: str
    completed_at: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_task(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id", ""),
        "user_id": row.get("user_id", ""),
        "title": row.get("title", ""),
        "prompt": row.get("prompt", ""),
        "schedule_type": row.get("schedule_type", "once"),
        "scheduled_time": row.get("scheduled_time"),
        "cron_expression": row.get("cron_expression"),
        "conversation_id": row.get("conversation_id"),
        "is_active": row.get("is_active", True),
        "last_run_at": row.get("last_run_at"),
        "last_run_status": row.get("last_run_status"),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
    }


def _row_to_execution(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id", ""),
        "task_id": row.get("task_id", ""),
        "status": row.get("status", ""),
        "result": row.get("result"),
        "error": row.get("error"),
        "started_at": row.get("started_at", ""),
        "completed_at": row.get("completed_at"),
    }


async def _execute_task_prompt(prompt: str, user_id: str) -> str:
    """Run a task's prompt through the LLM gateway and return the response text."""
    try:
        from core.llm.llm_gateway import llm_gateway
        from core.llm.llm_gateway.context import InferenceContext

        resp = await llm_gateway.acompletion(
            prompt=prompt,
            # M03 P0-পূর্ণাংশ: context বাধ্যতামূলক — scheduled task-এর খরচ
            # টেন্যান্ট user_id-তে অ্যাট্রিবিউটেড হয়।
            context=InferenceContext(
                tenant_id=str(user_id) if user_id else "anonymous",
                task_type="scheduled_task",
                stream=False,
            ),
        )
        if isinstance(resp, dict):
            return resp.get("text", "") or str(resp)
        return str(resp)
    except Exception as exc:
        raise RuntimeError(f"LLM execution failed: {exc}") from exc


async def execute_task_and_record(task: dict[str, Any], user_id: str) -> dict[str, Any]:
    """Execute a task's prompt through the manual-run safe path and record the outcome.

    বাংলা মন্তব্য (M22 P-A): manual-run endpoint আর AgentSupervisor due-sweep একই
    নির্বাহ-পথ ভাগ করে — execution record তৈরি → LLM নির্বাহ → ফল সৎভাবে লেখা
    (সফলতা/ব্যর্থতা + প্রকৃত error টেক্সট) → last_run_* আপডেট → conversation
    append। কোনো ব্যর্থতা নীরবে গিলে ফেলা হয় না; error টেক্সট ডাটাবেজেই থাকে।
    """
    task_id = task["id"]

    # Create execution record
    now = datetime.now(UTC).isoformat()
    exec_row = {
        "task_id": task_id,
        "status": "running",
        "started_at": now,
    }
    exec_resp = (
        await supabase_db.client.table("scheduled_task_executions").insert(exec_row).execute()
    )
    exec_id = exec_resp.data[0]["id"] if exec_resp.data else str(uuid.uuid4())

    # Execute prompt — failures are recorded honestly, never swallowed
    result_text = ""
    status = "success"
    error_text = None
    try:
        result_text = await _execute_task_prompt(task["prompt"], user_id)
    except Exception as run_exc:
        status = "failed"
        error_text = str(run_exc)
        logger.error(f"Task {task_id} execution failed: {run_exc}")

    completed_at = datetime.now(UTC).isoformat()

    # Update execution record
    await (
        supabase_db.client.table("scheduled_task_executions")
        .update(
            {
                "status": status,
                "result": result_text[:5000] if result_text else None,
                "error": error_text[:2000] if error_text else None,
                "completed_at": completed_at,
            }
        )
        .eq("id", exec_id)
        .execute()
    )

    # Update task's last_run fields
    await (
        supabase_db.client.table("scheduled_tasks")
        .update(
            {
                "last_run_at": completed_at,
                "last_run_status": status,
                "updated_at": completed_at,
            }
        )
        .eq("id", task_id)
        .execute()
    )

    # Optionally append result as a message to the linked conversation
    if task.get("conversation_id") and result_text:
        try:
            await (
                supabase_db.client.table("messages")
                .insert(
                    {
                        "conversation_id": task["conversation_id"],
                        "role": "assistant",
                        "content": f"[Scheduled Task: {task['title']}]\n\n{result_text}",
                    }
                )
                .execute()
            )
        except Exception as msg_exc:
            # বাংলা মন্তব্য: conversation-append ঐচ্ছিক পরিণতি — মূল নির্বাহ-ফল
            # ইতোমধ্যেই execution record-এ সৎভাবে সংরক্ষিত; এখানে ব্যর্থতা চিৎকার
            # করে লগ হয় কিন্তু নির্বাহ-ফলাফল পাল্টায় না।
            logger.warning(f"Failed to append task result to conversation: {msg_exc}")

    return {
        "execution_id": exec_id,
        "task_id": task_id,
        "status": status,
        "result": result_text[:2000] if result_text else None,
        "error": error_text,
        "started_at": now,
        "completed_at": completed_at,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=dict[str, Any],
    summary="Create a scheduled task",
    status_code=201,
)
async def create_scheduled_task(
    payload: ScheduledTaskCreate,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Create a new scheduled task for the authenticated user."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema()

    if payload.schedule_type == "custom" and not payload.cron_expression:
        raise HTTPException(
            status_code=400,
            detail="Cron expression is required for 'custom' schedule type.",
        )
    if payload.schedule_type == "once" and not payload.scheduled_time:
        raise HTTPException(
            status_code=400,
            detail="scheduled_time is required for 'once' schedule type.",
        )

    try:
        now = datetime.now(UTC).isoformat()
        row = {
            "user_id": user_id,
            "title": payload.title,
            "prompt": payload.prompt,
            "schedule_type": payload.schedule_type,
            "scheduled_time": payload.scheduled_time,
            "cron_expression": payload.cron_expression,
            "conversation_id": payload.conversation_id,
            "is_active": payload.is_active,
            "created_at": now,
            "updated_at": now,
        }
        resp = await supabase_db.client.table("scheduled_tasks").insert(row).execute()
        if not resp.data:
            raise HTTPException(status_code=500, detail="Task creation returned no data.")
        return _row_to_task(resp.data[0])
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"create_scheduled_task failed for user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to create scheduled task.") from exc


@router.get(
    "/",
    response_model=list[dict[str, Any]],
    summary="List all scheduled tasks for the current user",
)
async def list_scheduled_tasks(
    user: dict = Depends(get_current_user_token),
) -> list[dict[str, Any]]:
    """Return every scheduled task owned by the authenticated user."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema()

    try:
        resp = (
            await supabase_db.client.table("scheduled_tasks")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return [_row_to_task(r) for r in (resp.data or [])]
    except Exception as exc:
        logger.error(f"list_scheduled_tasks failed for user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to list scheduled tasks.") from exc


@router.get(
    "/history",
    response_model=list[dict[str, Any]],
    summary="List past task executions with status",
)
async def list_execution_history(
    task_id: str | None = None,
    limit: int = 50,
    user: dict = Depends(get_current_user_token),
) -> list[dict[str, Any]]:
    """Return execution history. Optionally filter by *task_id*."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema()

    try:
        # First get the user's task IDs
        if task_id:
            task_ids = [task_id]
        else:
            tasks_resp = (
                await supabase_db.client.table("scheduled_tasks")
                .select("id")
                .eq("user_id", user_id)
                .execute()
            )
            task_ids = [r["id"] for r in (tasks_resp.data or [])]

        if not task_ids:
            return []

        # Build filter: task_id.in.(id1,id2,...)
        # Supabase .in_ expects a column name and a list
        query = (
            await supabase_db.client.table("scheduled_task_executions")
            .select("*")
            .in_("task_id", task_ids)
            .order("started_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [_row_to_execution(r) for r in (query.data or [])]
    except Exception as exc:
        logger.error(f"list_execution_history failed for user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch execution history.") from exc


@router.get(
    "/{task_id}",
    response_model=dict[str, Any],
    summary="Get a single scheduled task",
)
async def get_scheduled_task(
    task_id: str,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Retrieve a specific scheduled task by ID."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema()

    try:
        resp = (
            await supabase_db.client.table("scheduled_tasks")
            .select("*")
            .eq("id", task_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=404, detail="Scheduled task not found.")
        return _row_to_task(resp.data[0])
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_scheduled_task failed for {task_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch scheduled task.") from exc


@router.put(
    "/{task_id}",
    response_model=dict[str, Any],
    summary="Update a scheduled task",
)
async def update_scheduled_task(
    task_id: str,
    payload: ScheduledTaskUpdate,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Update fields of an existing scheduled task."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema()

    try:
        # Verify ownership
        existing = (
            await supabase_db.client.table("scheduled_tasks")
            .select("id")
            .eq("id", task_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="Scheduled task not found.")

        update_fields: dict[str, Any] = {"updated_at": datetime.now(UTC).isoformat()}
        if payload.title is not None:
            update_fields["title"] = payload.title
        if payload.prompt is not None:
            update_fields["prompt"] = payload.prompt
        if payload.schedule_type is not None:
            update_fields["schedule_type"] = payload.schedule_type
        if payload.scheduled_time is not None:
            update_fields["scheduled_time"] = payload.scheduled_time
        if payload.cron_expression is not None:
            update_fields["cron_expression"] = payload.cron_expression
        if payload.conversation_id is not None:
            update_fields["conversation_id"] = payload.conversation_id
        if payload.is_active is not None:
            update_fields["is_active"] = payload.is_active

        resp = (
            await supabase_db.client.table("scheduled_tasks")
            .update(update_fields)
            .eq("id", task_id)
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=500, detail="Update returned no data.")
        return _row_to_task(resp.data[0])
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"update_scheduled_task failed for {task_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update scheduled task.") from exc


@router.delete(
    "/{task_id}",
    summary="Delete a scheduled task",
)
async def delete_scheduled_task(
    task_id: str,
    user: dict = Depends(get_current_user_token),
) -> dict[str, str]:
    """Permanently delete a scheduled task and its execution history."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema()

    try:
        existing = (
            await supabase_db.client.table("scheduled_tasks")
            .select("id")
            .eq("id", task_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="Scheduled task not found.")

        await supabase_db.client.table("scheduled_tasks").delete().eq("id", task_id).execute()
        return {"status": "deleted", "id": task_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"delete_scheduled_task failed for {task_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to delete scheduled task.") from exc


@router.post(
    "/{task_id}/run",
    response_model=dict[str, Any],
    summary="Manually trigger a scheduled task immediately",
)
async def run_scheduled_task(
    task_id: str,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Execute the task's prompt through the LLM gateway right now and record
    the result in the execution history."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema()

    try:
        # Fetch task
        task_resp = (
            await supabase_db.client.table("scheduled_tasks")
            .select("*")
            .eq("id", task_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not task_resp.data:
            raise HTTPException(status_code=404, detail="Scheduled task not found.")
        task = task_resp.data[0]

        # M22 P-A: manual-run ও due-sweep এখন একই শেয়ার্ড নির্বাহ-পথ ব্যবহার করে —
        # ফলে ইতিহাস-রেকর্ড, last_run_* এবং conversation-append-এর অর্থ দুই পথে এক।
        return await execute_task_and_record(task, user_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"run_scheduled_task failed for {task_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to run scheduled task.") from exc


@router.post(
    "/{task_id}/toggle",
    response_model=dict[str, Any],
    summary="Activate or deactivate a scheduled task",
)
async def toggle_scheduled_task(
    task_id: str,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Flip the ``is_active`` flag on a scheduled task."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema()

    try:
        existing = (
            await supabase_db.client.table("scheduled_tasks")
            .select("id, is_active")
            .eq("id", task_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="Scheduled task not found.")

        new_state = not existing.data[0].get("is_active", True)
        now = datetime.now(UTC).isoformat()

        resp = (
            await supabase_db.client.table("scheduled_tasks")
            .update({"is_active": new_state, "updated_at": now})
            .eq("id", task_id)
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=500, detail="Toggle returned no data.")

        return {
            "id": task_id,
            "is_active": new_state,
            "updated_at": now,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"toggle_scheduled_task failed for {task_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to toggle scheduled task.") from exc
