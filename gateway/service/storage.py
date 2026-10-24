"""
service/storage.py — Resilient SQLite/In-Memory Persistence for SupremeAI Gateway.

Provides persistent storage for:
1. Conversation-ID & Session carry-over with message history persistence.
2. User preferences (hidden tool cards, pinned tools, dashboard layout, theme).
3. Thread-safe execution with automated schema migrations.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

logger = logging.getLogger("supremeai.gateway.storage")

_DATA_DIR = os.getenv("SUPREMEAI_DATA_DIR", "").strip()
if not _DATA_DIR:
    if os.name == "nt":
        _DATA_DIR = os.path.join(os.getenv("TEMP", "C:/tmp"), "supremeai_data")
    else:
        _DATA_DIR = "/tmp/supremeai_data"

os.makedirs(_DATA_DIR, exist_ok=True)
_DB_PATH = os.getenv("SUPREMEAI_DB_PATH", os.path.join(_DATA_DIR, "gateway_state.db")).strip()

_MEM_FALLBACK: Dict[str, Any] = {
    "conversations": {},
    "messages": {},
    "preferences": {},
}
_USE_MEM_FALLBACK = False


@contextmanager
def get_db():
    """Provides a SQLite connection with WAL mode and row factory."""
    global _USE_MEM_FALLBACK
    if _USE_MEM_FALLBACK:
        yield None
        return

    conn = None
    try:
        conn = sqlite3.connect(_DB_PATH, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        yield conn
        conn.commit()
    except Exception as exc:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.warning(f"SQLite DB error ({exc}), falling back to in-memory store.")
        yield None
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def init_db() -> None:
    """Initialize database tables for conversations, messages, and user preferences."""
    global _USE_MEM_FALLBACK
    try:
        with get_db() as conn:
            if conn is None:
                _USE_MEM_FALLBACK = True
                return
            conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                metadata_json TEXT
            );
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL,
                extra_json TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY,
                preferences_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id);")
        logger.info(f"Gateway SQLite storage initialized at {_DB_PATH}")
    except Exception as exc:
        logger.warning(f"Failed to initialize SQLite storage: {exc}. Using memory fallback.")
        _USE_MEM_FALLBACK = True


# ── Conversation & Message Persistence ───────────────────────────────────────

def save_conversation(
    conv_id: str,
    user_id: str = "usr-admin-primary",
    title: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Creates or updates a conversation record."""
    now = time.time()
    clean_title = (title or "New Conversation").strip()[:120]
    meta_str = json.dumps(metadata or {})

    with get_db() as conn:
        if conn is not None:
            conn.execute(
                """
                INSERT INTO conversations (id, user_id, title, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = COALESCE(excluded.title, conversations.title),
                    updated_at = excluded.updated_at,
                    metadata_json = COALESCE(excluded.metadata_json, conversations.metadata_json);
                """,
                (conv_id, user_id, clean_title, now, now, meta_str),
            )
        else:
            if conv_id not in _MEM_FALLBACK["conversations"]:
                _MEM_FALLBACK["conversations"][conv_id] = {
                    "id": conv_id,
                    "user_id": user_id,
                    "title": clean_title,
                    "created_at": now,
                    "updated_at": now,
                    "metadata": metadata or {},
                }
            else:
                _MEM_FALLBACK["conversations"][conv_id]["updated_at"] = now
                if title:
                    _MEM_FALLBACK["conversations"][conv_id]["title"] = clean_title

    return {
        "id": conv_id,
        "user_id": user_id,
        "title": clean_title,
        "updated_at": now,
    }


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    msg_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
    user_id: str = "usr-admin-primary",
) -> Dict[str, Any]:
    """Appends a message to a conversation, updating the conversation's timestamp."""
    mid = msg_id or f"msg-{uuid.uuid4().hex[:12]}"
    now = time.time()
    extra_str = json.dumps(extra or {})

    # Auto-create conversation if missing
    save_conversation(conversation_id, user_id=user_id, title=(content[:40] if role == "user" else None))

    with get_db() as conn:
        if conn is not None:
            conn.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, created_at, extra_json)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (mid, conversation_id, role, content, now, extra_str),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?;",
                (now, conversation_id),
            )
        else:
            if conversation_id not in _MEM_FALLBACK["messages"]:
                _MEM_FALLBACK["messages"][conversation_id] = []
            _MEM_FALLBACK["messages"][conversation_id].append({
                "id": mid,
                "role": role,
                "content": content,
                "created_at": now,
                "extra": extra or {},
            })

    return {
        "id": mid,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "created_at": now,
        "extra": extra or {},
    }


def get_conversation(conversation_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Returns conversation metadata along with ordered message history."""
    with get_db() as conn:
        if conn is not None:
            query = "SELECT * FROM conversations WHERE id = ?"
            params: List[Any] = [conversation_id]
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            conv_row = conn.execute(query, params).fetchone()
            if not conv_row:
                return None

            msg_rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC;",
                (conversation_id,),
            ).fetchall()

            messages = [
                {
                    "id": m["id"],
                    "role": m["role"],
                    "content": m["content"],
                    "created_at": m["created_at"],
                    "extra": json.loads(m["extra_json"] or "{}"),
                }
                for m in msg_rows
            ]

            return {
                "id": conv_row["id"],
                "user_id": conv_row["user_id"],
                "title": conv_row["title"],
                "created_at": conv_row["created_at"],
                "updated_at": conv_row["updated_at"],
                "metadata": json.loads(conv_row["metadata_json"] or "{}"),
                "messages": messages,
                "message_count": len(messages),
            }
        else:
            conv = _MEM_FALLBACK["conversations"].get(conversation_id)
            if not conv:
                return None
            if user_id and conv.get("user_id") != user_id:
                return None
            msgs = _MEM_FALLBACK["messages"].get(conversation_id, [])
            return {
                **conv,
                "messages": msgs,
                "message_count": len(msgs),
            }


def list_conversations(user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Returns summary list of recent conversations ordered by updated_at descending."""
    with get_db() as conn:
        if conn is not None:
            query = "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) as msg_count FROM conversations c"
            params: List[Any] = []
            if user_id:
                query += " WHERE c.user_id = ?"
                params.append(user_id)
            query += " ORDER BY c.updated_at DESC LIMIT ?;"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [
                {
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "title": r["title"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "message_count": r["msg_count"],
                }
                for r in rows
            ]
        else:
            all_convs = list(_MEM_FALLBACK["conversations"].values())
            if user_id:
                all_convs = [c for c in all_convs if c.get("user_id") == user_id]
            all_convs.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
            res = []
            for c in all_convs[:limit]:
                msgs = _MEM_FALLBACK["messages"].get(c["id"], [])
                res.append({
                    "id": c["id"],
                    "user_id": c.get("user_id"),
                    "title": c.get("title"),
                    "created_at": c.get("created_at"),
                    "updated_at": c.get("updated_at"),
                    "message_count": len(msgs),
                })
            return res


def delete_conversation(conversation_id: str, user_id: Optional[str] = None) -> bool:
    """Deletes conversation and associated messages."""
    with get_db() as conn:
        if conn is not None:
            query = "DELETE FROM conversations WHERE id = ?"
            params: List[Any] = [conversation_id]
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            cur = conn.execute(query, params)
            conn.execute("DELETE FROM messages WHERE conversation_id = ?;", (conversation_id,))
            return cur.rowcount > 0
        else:
            if conversation_id in _MEM_FALLBACK["conversations"]:
                del _MEM_FALLBACK["conversations"][conversation_id]
                _MEM_FALLBACK["messages"].pop(conversation_id, None)
                return True
            return False


# ── User Preferences & Tool Card Persistence ────────────────────────────────

import copy

DEFAULT_PREFERENCES: Dict[str, Any] = {
    "hidden_tool_cards": [],
    "pinned_tools": [],
    "theme": "cosmic-dark",
    "dashboard_layout": "standard",
    "auto_scroll": True,
}


def _default_prefs() -> Dict[str, Any]:
    return copy.deepcopy(DEFAULT_PREFERENCES)


def get_user_preferences(user_id: str = "usr-admin-primary") -> Dict[str, Any]:
    """Retrieves user preferences, returning defaults if not found."""
    with get_db() as conn:
        if conn is not None:
            row = conn.execute(
                "SELECT preferences_json, updated_at FROM user_preferences WHERE user_id = ?;",
                (user_id,),
            ).fetchone()
            if row:
                try:
                    loaded = json.loads(row["preferences_json"])
                    merged = {**_default_prefs(), **loaded}
                    return {
                        "user_id": user_id,
                        "preferences": merged,
                        "updated_at": row["updated_at"],
                    }
                except Exception:
                    pass
        else:
            if user_id in _MEM_FALLBACK["preferences"]:
                return {
                    "user_id": user_id,
                    "preferences": {**_default_prefs(), **_MEM_FALLBACK["preferences"][user_id]},
                    "updated_at": time.time(),
                }

    return {
        "user_id": user_id,
        "preferences": _default_prefs(),
        "updated_at": time.time(),
    }


def save_user_preferences(user_id: str, patch_data: Dict[str, Any]) -> Dict[str, Any]:
    """Merges and stores updated user preferences."""
    current = copy.deepcopy(get_user_preferences(user_id)["preferences"])

    # Support directly updating hidden_tool_cards
    if "hidden_tool_cards" in patch_data and isinstance(patch_data["hidden_tool_cards"], list):
        current["hidden_tool_cards"] = list(dict.fromkeys(patch_data["hidden_tool_cards"]))

    # Support action: "hide_tool" / "unhide_tool"
    action = patch_data.get("action")
    tool_id = patch_data.get("tool_id")
    if action == "hide_tool" and tool_id:
        if tool_id not in current["hidden_tool_cards"]:
            current["hidden_tool_cards"].append(tool_id)
    elif action == "unhide_tool" and tool_id:
        current["hidden_tool_cards"] = [t for t in current["hidden_tool_cards"] if t != tool_id]

    # Merge any other preference keys
    for k, v in patch_data.items():
        if k not in ("action", "tool_id", "user_id"):
            current[k] = v

    now = time.time()
    pref_str = json.dumps(current)

    with get_db() as conn:
        if conn is not None:
            conn.execute(
                """
                INSERT INTO user_preferences (user_id, preferences_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    preferences_json = excluded.preferences_json,
                    updated_at = excluded.updated_at;
                """,
                (user_id, pref_str, now),
            )
        else:
            _MEM_FALLBACK["preferences"][user_id] = current

    return {
        "user_id": user_id,
        "preferences": current,
        "updated_at": now,
    }


# Auto-run initialization on module load
init_db()
