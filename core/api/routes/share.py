"""Feature S1: Public Share Links.

Allows users to generate public share links for conversations,
view shared conversations without authentication, list and revoke shares.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import get_current_user_token
from core.logging_config import logger
from database.supabase_client import SupabaseDB

router = APIRouter(prefix="/api/share", tags=["Sharing"])

# In-memory cache with 30-minute TTL for public share lookups
_share_cache: dict[str, dict[str, Any]] = {}
_CACHE_TTL_SECONDS = 30 * 60  # 30 minutes


def _cache_get(share_id: str) -> dict[str, Any] | None:
    """Retrieve a cached share entry if it has not expired."""
    entry = _share_cache.get(share_id)
    if entry is None:
        return None
    if time.monotonic() - entry["_cached_at"] > _CACHE_TTL_SECONDS:
        del _share_cache[share_id]
        return None
    return entry


def _cache_set(share_id: str, data: dict[str, Any]) -> None:
    """Store a share entry in the in-memory cache."""
    data["_cached_at"] = time.monotonic()
    _share_cache[share_id] = data


def _generate_share_id(length: int = 12) -> str:
    """Generate a cryptographically random alphanumeric share ID."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ---------- Pydantic Schemas ----------


class ShareGenerateRequest(BaseModel):
    conversation_id: str = Field(..., description="UUID of the conversation to share")


class ShareGenerateResponse(BaseModel):
    share_id: str
    share_url: str
    expires_at: str


class SharedConversationResponse(BaseModel):
    share_id: str
    conversation_id: str
    title: str | None
    is_public: bool
    view_count: int
    created_at: str
    expires_at: str


class SharedMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class PublicShareDetailResponse(BaseModel):
    conversation_id: str
    title: str | None
    messages: list[SharedMessageResponse]
    shared_at: str
    expires_at: str
    view_count: int


class ShareRevokeResponse(BaseModel):
    status: str
    share_id: str


# ---------- Routes ----------


@router.post("/generate", response_model=ShareGenerateResponse)
async def generate_share_link(
    payload: ShareGenerateRequest,
    user: dict = Depends(get_current_user_token),
):
    """Generate a public share link for a conversation.

    Creates an entry in the shared_conversations table and returns
    the share URL that can be used to view the conversation without auth.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()

    try:
        # Verify the conversation belongs to the user
        conv_response = (
            await db.client.table("conversations")
            .select("id, user_id, title")
            .eq("id", payload.conversation_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not conv_response.data:
            raise HTTPException(
                status_code=404, detail="Conversation not found or you do not own it"
            )

        # Check for existing share for this conversation
        existing = (
            await db.client.table("shared_conversations")
            .select("share_id, expires_at")
            .eq("conversation_id", payload.conversation_id)
            .eq("user_id", user_id)
            .execute()
        )

        if existing.data:
            existing_share = existing.data[0]
            expires_at = existing_share["expires_at"]
            # Reuse if not expired
            if datetime.now(UTC) < datetime.fromisoformat(expires_at.replace("Z", "+00:00")):
                return ShareGenerateResponse(
                    share_id=existing_share["share_id"],
                    share_url=f"/share/{existing_share['share_id']}",
                    expires_at=expires_at,
                )

        # Generate new share
        share_id = _generate_share_id()
        expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()

        await (
            db.client.table("shared_conversations")
            .insert(
                {
                    "share_id": share_id,
                    "conversation_id": payload.conversation_id,
                    "user_id": user_id,
                    "is_public": True,
                    "view_count": 0,
                    "expires_at": expires_at,
                }
            )
            .execute()
        )

        logger.info(f"Share link generated: {share_id} for conversation {payload.conversation_id}")

        return ShareGenerateResponse(
            share_id=share_id,
            share_url=f"/share/{share_id}",
            expires_at=expires_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate share link: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate share link") from e


@router.get("/{share_id}", response_model=PublicShareDetailResponse)
async def get_shared_conversation(share_id: str):
    """Public endpoint to retrieve a shared conversation without authentication.

    Returns the conversation title, all messages, and metadata.
    Results are cached in-memory for 30 minutes.
    """
    # Check cache first
    cached = _cache_get(share_id)
    if cached is not None:
        # Increment view count asynchronously (best-effort)
        try:
            db = SupabaseDB()
            current_count = cached.get("view_count", 0)
            await (
                db.client.table("shared_conversations")
                .update({"view_count": current_count + 1})
                .eq("share_id", share_id)
                .execute()
            )
            cached["view_count"] = current_count + 1
        except asyncio.CancelledError:
            raise
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception(f"Silenced error: {e}")

        return PublicShareDetailResponse(
            conversation_id=cached["conversation_id"],
            title=cached.get("title"),
            messages=cached["messages"],
            shared_at=cached["created_at"],
            expires_at=cached["expires_at"],
            view_count=cached["view_count"],
        )

    db = SupabaseDB()

    try:
        # Fetch the share record
        share_response = (
            await db.client.table("shared_conversations")
            .select("*")
            .eq("share_id", share_id)
            .eq("is_public", True)
            .execute()
        )

        if not share_response.data:
            raise HTTPException(status_code=404, detail="Share link not found")

        share = share_response.data[0]

        # Check expiration
        expires_at = share["expires_at"]
        if datetime.now(UTC) >= datetime.fromisoformat(expires_at.replace("Z", "+00:00")):
            raise HTTPException(status_code=410, detail="This share link has expired")

        conversation_id = share["conversation_id"]

        # Fetch conversation
        conv_response = (
            await db.client.table("conversations")
            .select("id, title")
            .eq("id", conversation_id)
            .execute()
        )

        if not conv_response.data:
            raise HTTPException(status_code=404, detail="Conversation not found")

        title = conv_response.data[0].get("title")

        # Fetch messages ordered by created_at
        messages_response = (
            db.client.table("messages")
            .select("id, role, content, created_at")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=False)
            .execute()
        )

        messages = [SharedMessageResponse(**msg) for msg in messages_response.data]

        # Increment view count
        new_view_count = share.get("view_count", 0) + 1
        db.client.table("shared_conversations").update({"view_count": new_view_count}).eq(
            "share_id", share_id
        ).execute()

        # Cache the result
        cache_data = {
            "conversation_id": conversation_id,
            "title": title,
            "messages": messages,
            "created_at": share["created_at"],
            "expires_at": expires_at,
            "view_count": new_view_count,
        }
        _cache_set(share_id, cache_data)

        return PublicShareDetailResponse(
            conversation_id=conversation_id,
            title=title,
            messages=messages,
            shared_at=share["created_at"],
            expires_at=expires_at,
            view_count=new_view_count,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve shared conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve shared conversation") from e


@router.get("/list", response_model=list[SharedConversationResponse])
async def list_shared_conversations(
    user: dict = Depends(get_current_user_token),
):
    """List all conversations shared by the authenticated user.

    Returns share metadata including view counts and expiration dates.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()

    try:
        response = (
            db.client.table("shared_conversations")
            .select(
                "share_id, conversation_id, user_id, is_public, view_count, created_at, expires_at"
            )
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )

        # Enrich with conversation titles
        results: list[SharedConversationResponse] = []
        for row in response.data:
            conv_resp = (
                db.client.table("conversations")
                .select("title")
                .eq("id", row["conversation_id"])
                .execute()
            )
            title = conv_resp.data[0]["title"] if conv_resp.data else None

            results.append(
                SharedConversationResponse(
                    share_id=row["share_id"],
                    conversation_id=row["conversation_id"],
                    title=title,
                    is_public=row["is_public"],
                    view_count=row["view_count"],
                    created_at=row["created_at"],
                    expires_at=row["expires_at"],
                )
            )

        return results
    except Exception as e:
        logger.error(f"Failed to list shared conversations: {e}")
        raise HTTPException(status_code=500, detail="Failed to list shared conversations") from e


@router.delete("/{share_id}", response_model=ShareRevokeResponse)
async def revoke_share(
    share_id: str,
    user: dict = Depends(get_current_user_token),
):
    """Revoke a share link. Only the owner of the conversation can revoke.

    Deletes the shared_conversations entry and clears the cache.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()

    try:
        # Verify ownership
        share_response = (
            db.client.table("shared_conversations")
            .select("share_id, user_id")
            .eq("share_id", share_id)
            .execute()
        )

        if not share_response.data:
            raise HTTPException(status_code=404, detail="Share link not found")

        if share_response.data[0]["user_id"] != user_id:
            raise HTTPException(
                status_code=403, detail="You do not have permission to revoke this share"
            )

        # Delete the share
        await db.client.table("shared_conversations").delete().eq("share_id", share_id).execute()

        # Clear cache
        _share_cache.pop(share_id, None)

        logger.info(f"Share link revoked: {share_id}")

        return ShareRevokeResponse(status="revoked", share_id=share_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to revoke share link: {e}")
        raise HTTPException(status_code=500, detail="Failed to revoke share link") from e
