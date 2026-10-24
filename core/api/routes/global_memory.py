# backend/api/routes/global_memory.py
"""Feature S8: Global User Memory.

Exposes the existing memory_service for user-facing global memory management:
list, create, update, delete, semantic search, sync, and stats.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_current_user_token
from core.logging_config import logger
from database.supabase_client import db as supabase_db

router = APIRouter(
    prefix="/api/preferences/memory",
    tags=["Global Memory"],
    dependencies=[Depends(get_current_user_token)],
)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


ContentType = Literal["fact", "preference", "instruction"]


class MemoryCreateRequest(BaseModel):
    """Body for creating a new memory entry."""

    content: str = Field(..., min_length=1, description="The memory text to store.")
    content_type: ContentType = Field(default="fact", description="Category of the memory.")


class MemoryUpdateRequest(BaseModel):
    """Body for updating an existing memory entry."""

    content: str = Field(..., min_length=1, description="Updated memory text.")
    content_type: ContentType | None = Field(None, description="Optional category update.")


class MemorySearchRequest(BaseModel):
    """Body for semantic search across user memories."""

    query: str = Field(..., min_length=1, description="Search query text.")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum results to return.")
    threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score (0-1).",
    )


class MemorySyncRequest(BaseModel):
    """Body for syncing recent chat context into long-term memory."""

    conversation_id: str = Field(..., description="Conversation to sync from.")
    message_count: int = Field(
        default=20, ge=1, le=100, description="Number of recent messages to consider."
    )


class MemoryItemResponse(BaseModel):
    """Single memory entry returned to the frontend."""

    id: str
    content: str
    content_type: str
    score: float | None = None
    created_at: str


class MemoryStatsResponse(BaseModel):
    """Aggregated memory statistics for the current user."""

    total_memories: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    last_updated: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_supabase() -> None:
    """Raise 503 if the Supabase client is not initialised."""
    if not supabase_db.client:
        raise HTTPException(status_code=503, detail="Database is not available.")


def _row_to_memory(row: dict[str, Any], score: float | None = None) -> dict[str, Any]:
    """Normalise a raw DB row into the shape expected by the API."""
    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        import json

        try:
            metadata = json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            metadata = {}

    return {
        "id": row.get("id", "unknown"),
        "content": row.get("summary", ""),
        "content_type": metadata.get("content_type", "fact"),
        "session_id": row.get("session_id"),
        "agent_type": row.get("agent_type"),
        "task_type": row.get("task_type"),
        "metadata": metadata,
        "created_at": row.get("created_at", ""),
        "score": score,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=list[dict[str, Any]],
    summary="List all memories for the current user",
)
async def list_memories(
    user: dict = Depends(get_current_user_token),
) -> list[dict[str, Any]]:
    """Return every memory entry belonging to the authenticated user."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_supabase()

    try:
        from services.memory_service import memory_service

        raw = memory_service.retrieve_memories(user_id=user_id)
        return [_row_to_memory(r) for r in raw]
    except Exception as exc:
        logger.error(f"list_memories failed for user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to retrieve memories.") from exc


@router.post(
    "/",
    response_model=dict[str, Any],
    summary="Save a new memory",
    status_code=201,
)
async def create_memory(
    payload: MemoryCreateRequest,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Persist a new user memory via the memory service."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    try:
        from services.memory_service import save_memory

        result = await save_memory(
            session_id=f"user_memory:{user_id}",
            summary=payload.content,
            task_type="user_memory",
            agent_type="user",
            metadata={"content_type": payload.content_type},
            user_id=user_id,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Memory save failed."))
        return {"success": True, "id": result.get("id")}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"create_memory failed for user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to save memory.") from exc


@router.delete(
    "/{memory_id}",
    summary="Delete a specific memory",
)
async def delete_memory(
    memory_id: str,
    user: dict = Depends(get_current_user_token),
) -> dict[str, str]:
    """Remove a memory entry by its UUID."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_supabase()

    try:
        # Verify ownership before deleting
        resp = (
            await supabase_db.client.table("ai_memory")
            .select("id")
            .eq("id", memory_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=404, detail="Memory not found.")

        await supabase_db.client.table("ai_memory").delete().eq("id", memory_id).execute()
        return {"status": "deleted", "id": memory_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"delete_memory failed for {memory_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to delete memory.") from exc


@router.delete(
    "/user-data",
    summary="Erase ALL memories owned by the current user (GDPR right-to-erasure)",
)
async def delete_all_user_memories(
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Self-service data erasure (issue #1109): delete every ``ai_memory`` row
    whose ``user_id`` equals the authenticated caller's ``sub``.

    Scope: the caller can only erase their own data — the user_id comes from
    the verified JWT, never from the request. Embeddings, content and metadata
    for that user are removed in the same operation (no soft-delete)."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_supabase()

    from core.ai_memory.retention import delete_user_memories

    try:
        result = await delete_user_memories(user_id)
        return {
            "status": "erased",
            "deleted": result.deleted,
            "mode": result.mode,
        }
    except Exception as exc:
        logger.error(f"delete_all_user_memories failed for {user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to erase user memories.") from exc


@router.put(
    "/{memory_id}",
    response_model=dict[str, Any],
    summary="Update memory content",
)
async def update_memory(
    memory_id: str,
    payload: MemoryUpdateRequest,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Update the text and optionally the type of an existing memory."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_supabase()

    try:
        # Verify ownership
        resp = (
            await supabase_db.client.table("ai_memory")
            .select("id")
            .eq("id", memory_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=404, detail="Memory not found.")

        update_fields: dict[str, Any] = {"summary": payload.content}
        if payload.content_type is not None:
            # Merge content_type into existing metadata
            existing_resp = (
                await supabase_db.client.table("ai_memory")
                .select("metadata")
                .eq("id", memory_id)
                .execute()
            )
            metadata: dict[str, Any] = {}
            if existing_resp.data and existing_resp.data[0].get("metadata"):
                metadata = existing_resp.data[0]["metadata"]
                if isinstance(metadata, str):
                    import json

                    metadata = json.loads(metadata)
            metadata["content_type"] = payload.content_type
            update_fields["metadata"] = metadata

        await (
            supabase_db.client.table("ai_memory")
            .update(update_fields)
            .eq("id", memory_id)
            .execute()
        )
        return {"status": "updated", "id": memory_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"update_memory failed for {memory_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update memory.") from exc


@router.post(
    "/search",
    response_model=list[dict[str, Any]],
    summary="Semantic search across user memories",
)
async def search_memories(
    payload: MemorySearchRequest,
    user: dict = Depends(get_current_user_token),
) -> list[dict[str, Any]]:
    """Perform vector-similarity search over the user's stored memories."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    try:
        from services.memory_service import memory_service

        results = memory_service.query_context(
            prompt=payload.query,
            top_k=payload.limit,
            user_id=user_id,
        )
        # Filter by threshold and normalise
        filtered = [
            _row_to_memory(r, score=r.get("score"))
            for r in results
            if (r.get("score") or 0) >= payload.threshold
        ]
        return filtered
    except Exception as exc:
        logger.error(f"search_memories failed for user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Memory search failed.") from exc


@router.post(
    "/sync",
    response_model=dict[str, Any],
    summary="Sync recent chat messages to long-term memory",
)
async def sync_memory(
    payload: MemorySyncRequest,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Summarize recent messages from a conversation and persist as memory."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_supabase()

    try:
        # Fetch recent messages
        resp = (
            await supabase_db.client.table("messages")
            .select("role, content")
            .eq("conversation_id", payload.conversation_id)
            .order("created_at", desc=False)
            .limit(payload.message_count)
            .execute()
        )
        messages = resp.data or []
        if not messages:
            return {"status": "no_messages", "synced": False}

        from services.memory_service import summarize_and_save_session

        result = await summarize_and_save_session(
            session_id=payload.conversation_id,
            messages=messages,
            task_type="user_memory",
        )
        return {"status": "synced", "result": result}
    except Exception as exc:
        logger.error(f"sync_memory failed for conversation {payload.conversation_id}: {exc}")
        raise HTTPException(status_code=500, detail="Memory sync failed.") from exc


@router.get(
    "/stats",
    response_model=MemoryStatsResponse,
    summary="Get memory statistics for the current user",
)
async def memory_stats(
    user: dict = Depends(get_current_user_token),
) -> MemoryStatsResponse:
    """Return aggregated counts: total memories, breakdown by type, last updated."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_supabase()

    try:
        # বাংলা মন্তব্য (Wave-3 perf): আগে প্রতি request-এ ai_memory-র প্রতিটি row
        # (id, metadata, created_at) পুরোটা ডাউনলোড করে Python-এ len()/লুপ চালিয়ে
        # ৩টা সংখ্যা বের করা হতো — ইউজারের মেমোরি যত বড়, নেটওয়ার্ক + payload তত
        # নষ্ট (full-scan অপচয়)। এখন total সংখ্যাটা PostgREST-এর server-side
        # `count=exact` header থেকে আসে (same single query, আলাদা round-trip নেই),
        # আর row fetch-এ শুধু দরকারি দুটি কলাম (metadata, created_at) নামানো হয় —
        # পুরনো কোডের `id` কলামটা কোথাও ব্যবহৃতই হতো না। by_type/last_updated
        # প্রতি-row metadata ছাড়া সার্ভারে aggregate করা সম্ভব নয় (PostgREST-এ
        # JSON group-by নেই, RPC/DB function বানানো এই cycle-এর স্কোপে নেই),
        # তাই contract ঠিক রেখে সবচেয়ে ছোট fetch-ই honest সমাধান।
        resp = (
            await supabase_db.client.table("ai_memory")
            .select("metadata, created_at", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        rows = resp.data or []

        # বাংলা মন্তব্য: server-side exact count পেলে সেটাই সত্যি; কোনো কারণে
        # transport count echo না করলে (None) len(rows) একই সংখ্যা দেয় — এটা
        # fabricated fallback নয়, deterministic একই মান।
        total_memories = resp.count if resp.count is not None else len(rows)

        by_type: dict[str, int] = {}
        last_updated: str | None = None

        for row in rows:
            metadata = row.get("metadata") or {}
            if isinstance(metadata, str):
                import json

                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}
            ct = metadata.get("content_type", "fact")
            by_type[ct] = by_type.get(ct, 0) + 1

            ts = row.get("created_at")
            if ts:
                if last_updated is None or ts > last_updated:
                    last_updated = ts

        return MemoryStatsResponse(
            total_memories=total_memories,
            by_type=by_type,
            last_updated=last_updated,
        )
    except Exception as exc:
        logger.error(f"memory_stats failed for user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to retrieve memory stats.") from exc
