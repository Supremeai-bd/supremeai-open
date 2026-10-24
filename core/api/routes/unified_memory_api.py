"""
API Routes for the Unified Memory Interface.

Provides endpoints to interact with long-term, short-term, and checkpoint memory
through a single, consistent API.

AUD-5.1 (P0): this router previously had authentication explicitly stripped and
queried the global ``ai_memory`` table across ALL users. Every endpoint now
requires a valid JWT and scopes reads/writes to the authenticated user.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_user_token
from core.unified_memory import unified_memory

router = APIRouter(prefix="/unified-memory", tags=["Unified Memory"])


@router.post("/long-term/store")
async def store_long_term_memory_endpoint(
    session_id: str = Query(..., description="Session or Task ID"),
    agent_type: str = Query(..., description="Type of the agent (e.g., SyncGuard)"),
    task_type: str = Query(..., description="Type of the task (e.g., System_Audit)"),
    content: str = Query(..., description="The content to store"),
    metadata: str | None = Query(None, description="Optional metadata as JSON string"),
    distill: bool = Query(
        False,
        description="PLAN-004: opt-in write-time distillation (dense summary + structured facts); on failure falls back to legacy truncation",
    ),
    user: dict = Depends(get_current_user_token),
):
    """
    Store information in the long-term 'Eternal Brain' memory (owner-scoped).
    """
    import json

    metadata_dict = None
    if metadata:
        try:
            metadata_dict = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON in metadata")

    # PLAN-004: opt-in distilled variant; default behavior unchanged.
    if distill:
        success = await unified_memory.store_long_term_memory_distilled(
            session_id=session_id,
            agent_type=agent_type,
            task_type=task_type,
            content=content,
            metadata=metadata_dict,
            user_id=user.get("sub"),  # AUD-5.1: bind memory to the requesting user
        )
    else:
        success = unified_memory.store_long_term_memory(
            session_id=session_id,
            agent_type=agent_type,
            task_type=task_type,
            content=content,
            metadata=metadata_dict,
            user_id=user.get("sub"),  # AUD-5.1: bind memory to the requesting user
        )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to store memory")
    return {"message": "Long-term memory stored successfully", "session_id": session_id}


@router.get("/long-term/query")
async def query_long_term_memory_endpoint(
    query: str = Query(..., description="Query to search for in memory"),
    top_k: int = Query(default=5, le=20, description="Number of top results to return"),
    session_id: str | None = Query(None, description="Filter by session ID"),
    user: dict = Depends(get_current_user_token),
):
    """
    Query the long-term 'Eternal Brain' memory (owner-scoped).
    """
    results = unified_memory.query_long_term_memory(
        query=query, top_k=top_k, session_id=session_id, user_id=user.get("sub")
    )
    return {"results": results}
