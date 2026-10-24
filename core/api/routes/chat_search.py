"""Feature S6: Search Across All Chats.

Searches across all user conversations — both conversation titles
and message content — using PostgreSQL ILIKE pattern matching.
Returns ranked results with match type indicators.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import get_current_user_token
from core.logging_config import logger
from database.supabase_client import SupabaseDB

router = APIRouter(
    prefix="/api/chat/search",
    tags=["Chat Search"],
    dependencies=[Depends(get_current_user_token)],
)


# ---------- Pydantic Schemas ----------


class MatchedMessage(BaseModel):
    id: str
    content: str
    role: str
    created_at: str


class SearchResultItem(BaseModel):
    conversation_id: str
    title: str | None
    matched_message: MatchedMessage | None
    match_type: str  # "title" or "message"
    relevance_score: float


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    total: int
    query: str
    limit: int
    offset: int


# ---------- Helpers ----------


def _escape_like(query: str) -> str:
    """Escape special ILIKE wildcard characters in the search query."""
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _compute_title_relevance(title: str, query: str) -> float:
    """Compute a simple relevance score for a title match.

    Higher score if the query appears at the start of the title
    or matches the title exactly.
    """
    query_lower = query.lower()
    title_lower = title.lower()

    if title_lower == query_lower:
        return 1.0

    if title_lower.startswith(query_lower):
        return 0.9

    if query_lower in title_lower:
        return 0.7

    return 0.5


def _compute_message_relevance(content: str, query: str) -> float:
    """Compute a simple relevance score for a message content match.

    Considers how early the match appears and how many times the query
    occurs in the message.
    """
    content_lower = content.lower()
    query_lower = query.lower()

    count = content_lower.count(query_lower)
    if count == 0:
        return 0.0

    first_pos = content_lower.index(query_lower)
    length = len(content_lower)

    # Score based on position (earlier = better) and frequency
    position_score = max(0.0, 1.0 - (first_pos / max(length, 1)))
    frequency_score = min(count / 3.0, 1.0)  # Cap at 3 occurrences

    return 0.4 * position_score + 0.6 * frequency_score


# ---------- Route ----------


@router.get("/", response_model=SearchResponse)
async def search_chats(
    q: str = Query(..., min_length=1, description="Search query string"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results to return"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
    user: dict = Depends(get_current_user_token),
):
    """Search across all user conversations.

    Searches both conversation titles and message content using
    PostgreSQL ILIKE. Results are deduplicated by conversation_id
    and ranked by a simple relevance score.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()
    escaped_query = _escape_like(q)
    like_pattern = f"%{escaped_query}%"

    # Dictionary to hold best result per conversation
    results_map: dict[str, SearchResultItem] = {}

    try:
        # --- Search conversation titles ---
        try:
            title_results = (
                await db.client.table("conversations")
                .select("id, title")
                .eq("user_id", user_id)
                .ilike("title", like_pattern)
                .order("updated_at", desc=True)
                .execute()
            )

            for row in title_results.data:
                conv_id = row["id"]
                title = row.get("title", "")
                score = _compute_title_relevance(title, q)

                if conv_id not in results_map or score > results_map[conv_id].relevance_score:
                    results_map[conv_id] = SearchResultItem(
                        conversation_id=conv_id,
                        title=title,
                        matched_message=None,
                        match_type="title",
                        relevance_score=score,
                    )
        except Exception as e:
            logger.warning(f"Title search failed: {e}")

        # --- Search message content ---
        try:
            # First get all conversation IDs for this user
            conv_ids_resp = (
                await db.client.table("conversations").select("id").eq("user_id", user_id).execute()
            )

            user_conv_ids = [r["id"] for r in conv_ids_resp.data]

            if user_conv_ids:
                # Search messages across all user conversations
                # Supabase RPC or filter by conversation_id list
                # Use ilike on content
                message_results = (
                    await db.client.table("messages")
                    .select("id, conversation_id, role, content, created_at")
                    .ilike("content", like_pattern)
                    .order("created_at", desc=True)
                    .limit(limit * 3)  # Fetch more to have room for dedup
                    .execute()
                )

                for row in message_results.data:
                    conv_id = row["conversation_id"]

                    # Only include messages from the user's conversations
                    if conv_id not in user_conv_ids:
                        continue

                    content = row.get("content", "")
                    score = _compute_message_relevance(content, q)

                    # Only update if this match is better than existing
                    if conv_id not in results_map or score > results_map[conv_id].relevance_score:
                        # Get conversation title
                        title = None
                        if conv_id in results_map:
                            title = results_map[conv_id].title
                        else:
                            try:
                                conv_resp = (
                                    await db.client.table("conversations")
                                    .select("title")
                                    .eq("id", conv_id)
                                    .execute()
                                )
                                title = conv_resp.data[0]["title"] if conv_resp.data else None
                            except asyncio.CancelledError:
                                raise
                            except Exception as e:
                                import logging

                                logging.getLogger(__name__).exception(f"Silenced error: {e}")

                        results_map[conv_id] = SearchResultItem(
                            conversation_id=conv_id,
                            title=title,
                            matched_message=MatchedMessage(
                                id=row["id"],
                                content=content,
                                role=row["role"],
                                created_at=row["created_at"],
                            ),
                            match_type="message",
                            relevance_score=score,
                        )
        except Exception as e:
            logger.warning(f"Message search failed: {e}")

    except Exception as e:
        logger.error(f"Chat search failed: {e}")
        raise HTTPException(status_code=500, detail="Search failed. Please try again.") from e

    # Sort by relevance score descending
    sorted_results = sorted(results_map.values(), key=lambda r: r.relevance_score, reverse=True)

    total = len(sorted_results)
    paginated = sorted_results[offset : offset + limit]

    return SearchResponse(
        results=paginated,
        total=total,
        query=q,
        limit=limit,
        offset=offset,
    )
