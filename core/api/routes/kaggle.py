"""
Kaggle Callback API
Receives job completion notifications from Kaggle kernels.
"""

import json
import secrets
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel

from core.kaggle_orchestrator import KaggleOrchestrator, KaggleTaskType
from core.logging_config import logger

router = APIRouter(prefix="/api/v1/kaggle", tags=["kaggle"])


class KaggleCallbackRequest(BaseModel):
    """Callback payload from Kaggle kernel."""

    job_id: str
    status: str  # "success" or "failed"
    result: dict[str, Any] | None = None
    error: str | None = None
    completed_at: str
    kaggle_metadata: dict[str, Any] | None = None


@router.post("/callback")
async def kaggle_callback(
    request: KaggleCallbackRequest,
    background_tasks: BackgroundTasks,
    x_callback_token: str | None = Header(default=None, alias="X-Callback-Token"),
):
    """
    Receive job completion notification from Kaggle.

    This endpoint is called by Kaggle kernels when they finish execution.
    It updates job status and processes results.

    Issue #439: the path is public-path-exempt (kernels cannot hold a JWT —
    the old setup 401'd every real callback) but is TOKEN-authenticated with
    the per-job callback token; forged completions are rejected.
    """
    logger.info(f"📥 Kaggle callback received: job_id={request.job_id}, status={request.status}")

    try:
        orchestrator = KaggleOrchestrator.get_instance()
        if not orchestrator.redis_client:
            raise HTTPException(status_code=503, detail="Redis connection unavailable")

        expected_token = await orchestrator.get_callback_token(request.job_id)
        if (
            not expected_token
            or not x_callback_token
            or not secrets.compare_digest(x_callback_token, expected_token)
        ):
            raise HTTPException(status_code=401, detail="Invalid or missing callback token")

        job_key = f"kaggle:job:{request.job_id}"

        update_data = {
            "status": request.status,
            "completed_at": request.completed_at,
            "result": json.dumps(request.result) if request.result else "{}",
            "error": request.error or "",
        }

        await orchestrator.redis_client.hset(job_key, mapping=update_data)

        # Remove from queue
        await orchestrator.redis_client.zrem("kaggle:jobs:queue", request.job_id)

        # Release account quota
        if request.status == "success":
            account_id = await orchestrator.redis_client.hget(job_key, "assigned_account")
            if account_id:
                account_key = f"kaggle:account:{account_id}"
                await orchestrator.redis_client.hset(
                    account_key, mapping={"status": "available", "current_task": ""}
                )

        # Process results in background
        background_tasks.add_task(process_kaggle_results, request)

        return {
            "status": "received",
            "job_id": request.job_id,
            "message": "Callback processed successfully",
        }

    except Exception as e:
        logger.error(f"❌ Failed to process Kaggle callback: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


async def process_kaggle_results(callback: KaggleCallbackRequest):
    """Process completed Kaggle job results."""
    try:
        if callback.status == "success" and callback.result:
            logger.info(f"✅ Processed results for job {callback.job_id}")

        elif callback.status == "failed":
            logger.error(f"❌ Job {callback.job_id} failed: {callback.error}")

    except Exception as e:
        logger.error(f"❌ Error processing results: {e}")


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get status of a specific Kaggle job."""
    orchestrator = KaggleOrchestrator.get_instance()
    if not orchestrator.redis_client:
        raise HTTPException(status_code=503, detail="Redis connection unavailable")

    job_key = f"kaggle:job:{job_id}"
    job_data = await orchestrator.redis_client.hgetall(job_key)

    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")

    # parse json fields
    if "payload" in job_data:
        job_data["payload"] = json.loads(job_data["payload"])
    if "result" in job_data:
        job_data["result"] = json.loads(job_data["result"])

    return {"job": job_data}


@router.get("/stats")
async def kaggle_statistics():
    """Get Kaggle usage statistics."""
    orchestrator = KaggleOrchestrator.get_instance()
    return await orchestrator.get_queue_stats()


class JobSubmitRequest(BaseModel):
    task_type: str
    payload: dict[str, Any]
    priority: int = 5
    estimated_hours: float = 2.0


@router.post("/submit")
async def submit_kaggle_job(request: JobSubmitRequest):
    """Submit a new job to Kaggle queue."""
    orchestrator = KaggleOrchestrator.get_instance()

    try:
        task_type_enum = KaggleTaskType(request.task_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid task_type: {request.task_type}")

    try:
        job_id = await orchestrator.submit_job(
            task_type=task_type_enum,
            payload=request.payload,
            priority=request.priority,
            estimated_hours=request.estimated_hours,
        )
        return {"job_id": job_id, "status": "queued"}
    except Exception as e:
        logger.error(f"❌ Failed to submit job: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
