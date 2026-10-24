# backend/api/routes/branch_conversations.py
"""Feature S10: Branch Conversations.

Manages conversation trees. Users can branch a conversation at any message,
creating a new conversation that inherits all messages up to that point.
Branches can later be merged back.

Required schema additions:
  - conversations.parent_conversation_id  UUID REFERENCES conversations(id)
  - messages.parent_message_id          UUID REFERENCES messages(id)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_current_user_token
from core.logging_config import logger
from database.supabase_client import db as supabase_db

router = APIRouter(
    prefix="/api/conversations",
    tags=["Branch Conversations"],
    dependencies=[Depends(get_current_user_token)],
)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class BranchRequest(BaseModel):
    """Body for creating a conversation branch."""

    message_id: str = Field(..., description="The message to branch from (inclusive).")
    new_title: str | None = Field(None, description="Title for the new branched conversation.")


class MergeRequest(BaseModel):
    """Body for merging a source branch back into a target conversation."""

    source_conversation_id: str = Field(
        ..., description="ID of the branch conversation to merge into this one."
    )


class ConversationNode(BaseModel):
    """A flat node in the conversation tree, suitable for frontend rendering."""

    id: str
    title: str | None
    parent_conversation_id: str | None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_supabase() -> None:
    if not supabase_db.client:
        raise HTTPException(status_code=503, detail="Database is not available.")


def _ensure_schema_columns() -> None:
    """Add parent_conversation_id to conversations and parent_message_id to messages
    if the columns do not already exist. We attempt an RPC first; if unavailable we
    silently continue (the column may already be there)."""
    _ensure_supabase()
    try:
        supabase_db.client.rpc(
            "exec_sql",
            {
                "query_string": (
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS "
                    "parent_conversation_id UUID REFERENCES conversations(id);"
                )
            },
        ).execute()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception(f"Silenced error: {e}")
    try:
        supabase_db.client.rpc(
            "exec_sql",
            {
                "query_string": (
                    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS "
                    "parent_message_id UUID REFERENCES messages(id);"
                )
            },
        ).execute()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception(f"Silenced error: {e}")


def _normalise_conversation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id", ""),
        "user_id": row.get("user_id", ""),
        "title": row.get("title"),
        "parent_conversation_id": row.get("parent_conversation_id"),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
    }


def _normalise_message(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id", ""),
        "conversation_id": row.get("conversation_id", ""),
        "role": row.get("role", ""),
        "content": row.get("content", ""),
        "parent_message_id": row.get("parent_message_id"),
        "created_at": row.get("created_at", ""),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{conversation_id}/branch",
    response_model=dict[str, Any],
    summary="Branch a conversation at a specific message",
    status_code=201,
)
async def branch_conversation(
    conversation_id: str,
    payload: BranchRequest,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Create a new conversation that copies all messages up to and including
    *message_id* from the parent conversation. The new conversation's
    ``parent_conversation_id`` is set to *conversation_id*."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema_columns()
    _ensure_supabase()

    try:
        # 1. Verify the parent conversation belongs to the user
        parent_resp = (
            await supabase_db.client.table("conversations")
            .select("id, title")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not parent_resp.data:
            raise HTTPException(status_code=404, detail="Parent conversation not found.")
        parent_title = parent_resp.data[0].get("title") or "Conversation"

        # 2. Fetch messages up to and including message_id
        #    We need the message's created_at to know where to slice.
        target_msg_resp = (
            await supabase_db.client.table("messages")
            .select("id, created_at")
            .eq("id", payload.message_id)
            .eq("conversation_id", conversation_id)
            .execute()
        )
        if not target_msg_resp.data:
            raise HTTPException(status_code=404, detail="Message not found in conversation.")
        target_created_at = target_msg_resp.data[0]["created_at"]

        # 3. Get all messages up to that timestamp (inclusive)
        all_msgs_resp = (
            await supabase_db.client.table("messages")
            .select("*")
            .eq("conversation_id", conversation_id)
            .lte("created_at", target_created_at)
            .order("created_at", desc=False)
            .execute()
        )
        messages_to_copy = all_msgs_resp.data or []
        if not messages_to_copy:
            raise HTTPException(
                status_code=400,
                detail="No messages found to branch from.",
            )

        # 4. Create the new conversation
        now = datetime.now(UTC).isoformat()
        new_conv = {
            "user_id": user_id,
            "title": payload.new_title or f"Branch of {parent_title}",
            "parent_conversation_id": conversation_id,
            "created_at": now,
            "updated_at": now,
        }
        new_conv_resp = await supabase_db.client.table("conversations").insert(new_conv).execute()
        if not new_conv_resp.data:
            raise HTTPException(status_code=500, detail="Failed to create branched conversation.")
        new_conv_id = new_conv_resp.data[0]["id"]

        # 5. Copy messages (without IDs — new IDs will be generated)
        #    Maintain parent_message_id mapping: old_id -> new_id
        id_map: dict[str, str] = {}
        for msg in messages_to_copy:
            old_parent = msg.get("parent_message_id")
            new_msg: dict[str, Any] = {
                "conversation_id": new_conv_id,
                "role": msg["role"],
                "content": msg["content"],
                "created_at": msg["created_at"],
                "parent_message_id": id_map.get(old_parent) if old_parent else None,
            }
            inserted = await supabase_db.client.table("messages").insert(new_msg).execute()
            if inserted.data:
                id_map[msg["id"]] = inserted.data[0]["id"]

        return {
            "id": new_conv_id,
            "title": new_conv["title"],
            "parent_conversation_id": conversation_id,
            "messages_copied": len(messages_to_copy),
            "created_at": now,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"branch_conversation failed for {conversation_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to branch conversation.") from exc


@router.get(
    "/{conversation_id}/branches",
    response_model=list[dict[str, Any]],
    summary="List all branches of a conversation",
)
async def list_branches(
    conversation_id: str,
    user: dict = Depends(get_current_user_token),
) -> list[dict[str, Any]]:
    """Return all conversations whose ``parent_conversation_id`` equals
    *conversation_id* for the authenticated user."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema_columns()
    _ensure_supabase()

    try:
        resp = (
            await supabase_db.client.table("conversations")
            .select("*")
            .eq("parent_conversation_id", conversation_id)
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .execute()
        )
        return [_normalise_conversation(r) for r in (resp.data or [])]
    except Exception as exc:
        logger.error(f"list_branches failed for {conversation_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to list branches.") from exc


@router.get(
    "/tree",
    response_model=list[dict[str, Any]],
    summary="Get the full conversation tree for the current user",
)
async def get_conversation_tree(
    user: dict = Depends(get_current_user_token),
) -> list[dict[str, Any]]:
    """Return all of the user's conversations as a flat list with
    ``parent_conversation_id`` references, enabling the frontend to render
    a tree structure."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema_columns()
    _ensure_supabase()

    try:
        resp = (
            await supabase_db.client.table("conversations")
            .select("id, title, parent_conversation_id, created_at, updated_at")
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .execute()
        )
        return [_normalise_conversation(r) for r in (resp.data or [])]
    except Exception as exc:
        logger.error(f"get_conversation_tree failed for user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch conversation tree.") from exc


@router.patch(
    "/{conversation_id}/merge",
    response_model=dict[str, Any],
    summary="Merge a branch conversation back into this one",
)
async def merge_conversation(
    conversation_id: str,
    payload: MergeRequest,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Append messages from *source_conversation_id* that do not already exist
    in the target *conversation_id*. Both must belong to the authenticated user.
    Useful for merging a branch back into its parent."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_schema_columns()
    _ensure_supabase()

    try:
        # 1. Verify both conversations belong to the user
        target_resp = (
            await supabase_db.client.table("conversations")
            .select("id")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not target_resp.data:
            raise HTTPException(status_code=404, detail="Target conversation not found.")

        source_resp = (
            await supabase_db.client.table("conversations")
            .select("id")
            .eq("id", payload.source_conversation_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not source_resp.data:
            raise HTTPException(status_code=404, detail="Source conversation not found.")

        # 2. Fetch existing target message IDs for deduplication
        target_msgs = (
            await supabase_db.client.table("messages")
            .select("id, content, role, created_at")
            .eq("conversation_id", conversation_id)
            .execute()
        )
        target_msg_contents = {
            (m["role"], m["content"], m["created_at"]) for m in (target_msgs.data or [])
        }

        # 3. Fetch source messages and filter out duplicates
        source_msgs = (
            await supabase_db.client.table("messages")
            .select("*")
            .eq("conversation_id", payload.source_conversation_id)
            .order("created_at", desc=False)
            .execute()
        )
        to_insert: list[dict[str, Any]] = []
        for msg in source_msgs.data or []:
            key = (msg["role"], msg["content"], msg["created_at"])
            if key not in target_msg_contents:
                to_insert.append(
                    {
                        "conversation_id": conversation_id,
                        "role": msg["role"],
                        "content": msg["content"],
                        "parent_message_id": None,  # parent chain reset on merge
                        "created_at": msg["created_at"],
                    }
                )

        # 4. Insert new messages in a batch
        inserted_count = 0
        for msg_row in to_insert:
            await supabase_db.client.table("messages").insert(msg_row).execute()
            inserted_count += 1

        # 5. Update target's updated_at
        now = datetime.now(UTC).isoformat()
        await (
            supabase_db.client.table("conversations")
            .update({"updated_at": now})
            .eq("id", conversation_id)
            .execute()
        )

        return {
            "status": "merged",
            "target_id": conversation_id,
            "source_id": payload.source_conversation_id,
            "messages_appended": inserted_count,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"merge_conversation failed for {conversation_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to merge conversations.") from exc
