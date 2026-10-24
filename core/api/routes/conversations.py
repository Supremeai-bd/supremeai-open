"""User Conversations API — read-projection over the ai_memory store (#1823).

বাংলা (#1823 conversation-history split-brain fix):
**`ai_memory` (pgvector, Supabase `ai_memory` টেবিল) হলো চ্যাট কনভারসেশন
হিস্টরির একমাত্র source of truth** — chat flow (stream_chat_sse →
AutoRAGInjector.store_session_memory) এখানেই লেখে। এই router-এর GET
endpoints সেই store-এর read-projection; আর POST endpoints branch-fork
metadata-র জন্য Supabase `conversations` relational টেবিলে লেখে
(branch_conversations.py যেখানে relational columns দরকার সেখানে)।

আগে: GET /conversations/ Supabase `conversations` টেবিল পড়ত — যেখানে
চ্যাট flow কখনো লেখে না, তাই dashboard খালি দেখাত।
"""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.logging_config import logger
from core.security.authentication.rbac import get_current_user_token as verify_token_dependency
from database.supabase_client import SupabaseDB


def _internal_error(e: Exception) -> HTTPException:
    """AUD-2.9 follow-up (MANUAL_STEPS 7.4): generic 500 with correlation id.

    Raw exception text (DSN/SQL/provider payloads) must never reach clients;
    full stack is logged server-side, the client gets a correlation id only.
    Raises the HTTPException (so ``raise _internal_error(e)`` keeps typing).
    """
    correlation_id = uuid.uuid4().hex[:12]
    logger.exception(f"conversations route failed correlation_id={correlation_id}")
    raise HTTPException(
        status_code=500,
        detail=f"Internal server error (correlation_id: {correlation_id})",
    ) from e


router = APIRouter(prefix="/conversations", tags=["User Conversations"])

# বাংলা মন্তব্য (Wave-3 perf): GET /conversations/ আগে .limit() ছাড়া ইউজারের সব
# conversation একবারে নামাত, অথচ একমাত্র caller (frontend UserDashboard) প্রথম ৩টা
# client-side slice করে — বাকিটা নেটওয়ার্ক ট্রাফিক হিসেবে বিশুদ্ধ অপচয়। Cap দুটি
# magic number নয় — module constant হিসেবে রাখা হলো যাতে owner সহজে টিউন করতে পারে;
# list আগে থেকেই updated_at desc (recent-first) order-এ আসে, তাই প্রথম N-টাই সবচেয়ে
# সাম্প্রতিক।
DEFAULT_CONVERSATIONS_LIMIT = 50
MAX_CONVERSATIONS_LIMIT = 100

# বাংলা (#1823): stream_chat_sse store_session_memory-র content ফরম্যাট
# "Q: <prompt>\nA: <reply>" — Q/A parse করে structured role messages বানানো হয়।
_QA_RE = re.compile(r"^Q:\s*(.*?)\nA:\s*(.*)$", re.DOTALL)


class ConversationResponse(BaseModel):
    id: str
    title: str | None
    created_at: str
    updated_at: str
    message_count: int = 0


class MessageCreate(BaseModel):
    conversation_id: str
    role: str
    content: str


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: str


def _get_vector_store():
    """Lazy FreeTierOptimizedVectorStore for the ai_memory projection (#1823).

    Supabase unconfigured → None (routes degrade to honest empty lists).
    Isolated as a module function so tests can monkeypatch it.
    """
    try:
        from core.ai_memory.vector_store import FreeTierOptimizedVectorStore
        from core.config import settings

        supabase_url = getattr(settings, "supabase_url", "") or ""
        supabase_key = (
            getattr(settings, "supabase_service_role_key", "")
            or getattr(settings, "supabase_anon_key", "")
            or ""
        )
        if not supabase_url or not supabase_key:
            return None
        return FreeTierOptimizedVectorStore(supabase_url=supabase_url, supabase_key=supabase_key)
    except Exception as exc:
        logger.warning(f"ai_memory vector store unavailable for conversations projection: {exc}")
        return None


def parse_exchange_messages(content: str, created_at: str | None) -> list[dict]:
    """Parse a stored exchange ("Q: ...\nA: ...") into structured role messages."""
    match = _QA_RE.match(content or "")
    if match:
        return [
            {"role": "user", "content": match.group(1).strip(), "created_at": created_at},
            {"role": "assistant", "content": match.group(2).strip(), "created_at": created_at},
        ]
    text = (content or "").strip()
    # বাংলা: "Q: <question>" (A ছাড়া) হলে prefix strip — নইলে raw prefix থেকে যায়।
    if text.startswith("Q: "):
        text = text[3:].strip()
    return [{"role": "user", "content": text, "created_at": created_at}] if text else []


def derive_session_title(exchanges: list[dict]) -> str:
    """Derive a human title from the OLDEST exchange's user question."""
    for exchange in exchanges:  # ascending order
        content = str(exchange.get("content") or "")
        question = content[3:].split("\nA:")[0].strip() if content.startswith("Q: ") else content
        question = question.split("\nA:")[0].strip()
        if question:
            return question[:80]
    return "Conversation"


@router.get("/", response_model=list[ConversationResponse])
async def list_conversations(
    limit: int = Query(
        default=DEFAULT_CONVERSATIONS_LIMIT,
        ge=1,
        le=MAX_CONVERSATIONS_LIMIT,
        description="Maximum conversations to return (recent-first).",
    ),
    user: dict = Depends(verify_token_dependency),
):
    """List the caller's conversations — read-projection over ai_memory (#1823)."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    vector_store = _get_vector_store()
    if vector_store is None:
        # বাংলা: store না থাকলে সৎ খালি list — history কখনো ছিল না এমন ভুল সংকেত নয়।
        return []

    sessions = await vector_store.list_conversation_sessions(user_id=str(user_id), limit=limit)
    return [
        ConversationResponse(
            id=session["session_id"],
            title=derive_session_title(session.get("exchanges") or []),
            created_at=session.get("created_at") or "",
            updated_at=session.get("updated_at") or "",
            message_count=len(session.get("exchanges") or []),
        )
        for session in sessions
    ]


@router.get("/{session_id}/messages", response_model=list[dict])
async def list_session_messages(session_id: str, user: dict = Depends(verify_token_dependency)):
    """Fetch one session's messages (structured user/assistant turns) — ai_memory."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    vector_store = _get_vector_store()
    if vector_store is None:
        return []

    exchanges = await vector_store.get_session_messages(user_id=str(user_id), session_id=session_id)
    messages: list[dict] = []
    for exchange in exchanges:
        messages.extend(
            parse_exchange_messages(exchange.get("content") or "", exchange.get("created_at"))
        )
    return messages


@router.post("/", response_model=ConversationResponse)
async def create_conversation(
    title: str | None = None, user: dict = Depends(verify_token_dependency)
):
    """Create a branch-metadata conversation row (Supabase relational store)."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()
    try:
        response = (
            await db.client.table("conversations")
            .insert({"user_id": user_id, "title": title or "New Conversation"})
            .execute()
        )
        return ConversationResponse(**response.data[0])
    except Exception as e:
        raise _internal_error(e)


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def add_message(
    conversation_id: str, message: MessageCreate, user: dict = Depends(verify_token_dependency)
):
    """Append a message to a branch-metadata conversation (Supabase relational store)."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()
    try:
        # AUD-2.3/2.5: verify the requesting user actually owns the conversation
        # before writing into it. The service-role client used here bypasses RLS,
        # so the previous "database policy should ensure" assumption did not hold.
        ownership = (
            await db.client.table("conversations")
            .select("id")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not ownership.data:
            raise HTTPException(status_code=404, detail="Conversation not found")

        response = (
            await db.client.table("messages")
            .insert(
                {
                    "conversation_id": conversation_id,
                    "role": message.role,
                    "content": message.content,
                }
            )
            .execute()
        )

        # Update conversation timestamp
        await (
            db.client.table("conversations")
            .update({"updated_at": "now()"})
            .eq("id", conversation_id)
            .execute()
        )

        return MessageResponse(**response.data[0])
    except HTTPException:
        # Audit fix: ownership 404 (AUD-2.5) must not be swallowed into a 500 —
        # re-raise deliberate HTTP errors untouched.
        raise
    except Exception as e:
        raise _internal_error(e)
