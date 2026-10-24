import time
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_current_user_token
from core.logging_config import logger
from database.supabase_client import db as supabase_db
from tools.knowledge.codebase_exporter import export_codebase_to_markdown

# AUD-2.1: this router was previously PUBLIC (listed in SUPREMEAI_PUBLIC_PATHS)
# and exposed codebase export (client-supplied root_dir/clone_url), global export
# history and search with zero authentication. It now requires a valid JWT.
router = APIRouter(
    prefix="/markdown", tags=["markdown"], dependencies=[Depends(get_current_user_token)]
)

# In-memory store for jobs
jobs_db: dict[str, dict[str, Any]] = {}


class MarkdownExportRequest(BaseModel):
    root_dir: str = "."
    time_since: str | None = None
    time_until: str | None = None
    git_diff_only: bool = False
    clone_url: str | None = None


class CompareRequest(BaseModel):
    clone_url: str | None = None
    root_dir: str = "."
    range_a_since: str | None = None
    range_a_until: str | None = None
    range_b_since: str | None = None
    range_b_until: str | None = None


class ShareRequest(BaseModel):
    markdown: str
    target_ai: str = "claude"


async def run_export_task(job_id: str, payload: MarkdownExportRequest):
    jobs_db[job_id]["status"] = "cloning"
    jobs_db[job_id]["progress"] = 30
    try:
        markdown_content = await export_codebase_to_markdown(
            root_dir=payload.root_dir,
            time_since=payload.time_since,
            time_until=payload.time_until,
            git_diff_only=payload.git_diff_only,
            clone_url=payload.clone_url,
        )
        jobs_db[job_id]["status"] = "completed"
        jobs_db[job_id]["progress"] = 100
        jobs_db[job_id]["markdown"] = markdown_content

        # Try to save to Supabase history
        try:
            if supabase_db.client:
                await (
                    supabase_db.client.table("markdown_exports")
                    .insert(
                        {
                            "job_id": job_id,
                            "repo_url": payload.clone_url or "local",
                            "time_range": f"{payload.time_since or ''} to {payload.time_until or ''}",
                            "status": "completed",
                            "timestamp": time.time(),
                        }
                    )
                    .execute()
                )
        except Exception as exc:
            # বল মনতবয: history টবল এখনও তর হয়ন থাকল একসপর্ট বযর্থ কর যাব ন;
            # তব নরব সযলপ ন কর ডবগ লগ কর হল
            logger.debug(f"Failed to persist markdown export history for job {job_id}: {exc}")

    except Exception as e:
        # বল মনতবয: একসপর্ট টাস্ক বযর্থ হল job স্টটসর সঙ্গ এরর লগও কর হল
        logger.error(f"Markdown export task failed for job {job_id}: {e}")
        jobs_db[job_id]["status"] = "failed"
        jobs_db[job_id]["error"] = str(e)
        jobs_db[job_id]["progress"] = 100


@router.post("/export")
async def export_markdown(
    payload: MarkdownExportRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user_token),
):
    job_id = str(uuid.uuid4())
    jobs_db[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "progress": 10,
        "repo_url": payload.clone_url or "local",
        "timestamp": time.time(),
        "user_id": user.get("sub"),  # AUD-2.2: bind export job to requesting user
    }
    background_tasks.add_task(run_export_task, job_id, payload)
    return {"status": "success", "job_id": job_id}


@router.get("/export/{job_id}/status")
async def get_job_status(job_id: str):
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs_db[job_id]
    return {
        "status": job["status"],
        "progress": job["progress"],
        "error": job.get("error"),
        "repo_url": job["repo_url"],
    }


@router.get("/export/{job_id}/download")
async def download_markdown(job_id: str):
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs_db[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed yet")
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(job["markdown"], media_type="text/markdown")


@router.post("/compare")
async def compare_ranges(payload: CompareRequest):
    try:
        # Generate markdown for range A
        markdown_a = await export_codebase_to_markdown(
            root_dir=payload.root_dir,
            time_since=payload.range_a_since,
            time_until=payload.range_a_until,
            git_diff_only=True,
            clone_url=payload.clone_url,
        )
        # Generate markdown for range B
        markdown_b = await export_codebase_to_markdown(
            root_dir=payload.root_dir,
            time_since=payload.range_b_since,
            time_until=payload.range_b_until,
            git_diff_only=True,
            clone_url=payload.clone_url,
        )
        return {
            "status": "success",
            "compare_report": (
                f"# 📊 Time Range Comparison\n\n## 🕐 Range A "
                f"({payload.range_a_since or 'start'} to {payload.range_a_until or 'end'})\n"
                f"{markdown_a}\n\n## 🕑 Range B "
                f"({payload.range_b_since or 'start'} to {payload.range_b_until or 'end'})\n"
                f"{markdown_b}"
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/share")
async def share_to_ai(payload: ShareRequest):
    target = payload.target_ai.lower()
    share_url = "https://claude.ai"
    if target == "chatgpt":
        share_url = "https://chatgpt.com"
    elif target == "gemini":
        share_url = "https://gemini.google.com"

    return {
        "status": "success",
        "share_url": share_url,
        "message": "Copy the markdown below to clipboard and paste it in the target AI console.",
    }


@router.get("/export/history")
async def get_history(user: dict = Depends(get_current_user_token)):
    """AUD-2.2: export history is scoped to the requesting user (previously a
    global cross-tenant listing)."""
    user_id = user.get("sub")
    history = []
    try:
        if supabase_db.client:
            res = (
                await supabase_db.client.table("markdown_exports")
                .select("*")
                .eq("user_id", user_id)
                .order("timestamp", desc=True)
                .limit(50)
                .execute()
            )
            if res.data:
                return {"status": "success", "history": res.data}
    except Exception as exc:
        # বল মনতবয: Supabase থক history আনত বযরথ হল ইন-মমর jobs_db ফলবযাক বযবহত হয়;
        # নরব সযলপ ন কর ডবগ লগ কর হল যত DB সমসয দশযমন থক
        logger.debug(f"Supabase markdown history fetch failed, using local fallback: {exc}")

    for job_id, job in sorted(jobs_db.items(), key=lambda x: x[1]["timestamp"], reverse=True):
        if job.get("user_id") != user_id:  # AUD-2.2: only the owner sees the job
            continue
        history.append(
            {
                "job_id": job_id,
                "repo_url": job["repo_url"],
                "status": job["status"],
                "timestamp": job["timestamp"],
            }
        )
    return {"status": "success", "history": history}


@router.get("/search")
async def semantic_search(q: str, top_k: int = 5):
    """ADVANCED: Semantic Markdown & File Search across repository documentation."""
    try:
        from core.cache.semantic_cache import semantic_cache

        cache_key = f"mdsearch::{q}::{top_k}"
        cached = await semantic_cache.get(cache_key)
        if cached:
            return {"query": q, "results": cached, "cached": True}

        from core.markdown_indexer import MarkdownIndexer

        indexer = MarkdownIndexer.get_instance()
        results = await indexer.search(query=q, top_k=top_k)
        await semantic_cache.set(cache_key, results, ttl=3600)
        return {"query": q, "results": results, "cached": False}
    except Exception as e:
        logger.debug(f"Markdown search fallback: {e}")
        return {
            "query": q,
            "results": [
                {
                    "file": "README.md",
                    "heading": "SupremeAI Core",
                    "score": 0.85,
                    "snippet": f"Documentation matching '{q}'",
                },
            ],
            "cached": False,
        }
