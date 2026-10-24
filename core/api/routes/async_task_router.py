from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from core.logging_config import logger
from core.orchestration.agent_orchestrator import async_task_manager

router = APIRouter(prefix="/api/task", tags=["async-task"])


class TaskResponse(BaseModel):
    task_id: str
    status: str
    progress: int = 0
    result: str | None = None
    error: str | None = None


@router.get("/{task_id}")
def get_task_status(task_id: str, request: Request) -> TaskResponse:
    # Issue #685 (Domain 15): high-traffic polling router — log lookups with the
    # request correlation id (also auto-injected into loguru records by
    # SupremeContextMiddleware's contextualize scope).
    correlation_id = getattr(request.state, "correlation_id", "")
    task = async_task_manager.get_task(task_id)
    if task:
        logger.info(
            "[task.status] task_id=%s status=%s correlation_id=%s",
            task_id,
            task["status"],
            correlation_id,
        )
        return TaskResponse(
            task_id=task["task_id"],
            status=task["status"],
            progress=task.get("progress", 0),
            result=task.get("result"),
            error=task.get("error"),
        )
    logger.warning("[task.status] task_id=%s not_found correlation_id=%s", task_id, correlation_id)
    return TaskResponse(task_id=task_id, status="not_found", progress=0)


@router.get("/_stats")
def get_task_stats() -> dict[str, Any]:
    return async_task_manager.get_stats()
