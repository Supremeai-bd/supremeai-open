"""gateway/service/memory_store.py - Canonical 3-tier memory store (spec Phase 3)."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

logger = logging.getLogger("supremeai.memory_store")

_DB_PATH = os.getenv(
    "SUPREMEAI_CANONICAL_DB_PATH",
    os.path.join(tempfile.gettempdir(), "supremeai_canonical.db"),
)
_LOCK = threading.RLock()
_MEM = {
    "conversations": {},
    "messages": {},
    "user_memories": {},
    "provider_attempts": [],
}
_USE_MEM = False


_FAILED_PATHS: set[str] = set()


def _connect(db_path=None):
    target_path = db_path or _DB_PATH
    if target_path in _FAILED_PATHS:
        return None
    try:
        conn = sqlite3.connect(target_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn
    except Exception as exc:
        logger.warning("SQLite unavailable (%s); using in-memory canonical store.", exc)
        _FAILED_PATHS.add(target_path)
        return None


@contextmanager
def _db(db_path=None):
    conn = _connect(db_path=db_path)
    if conn is None:
        yield None
        return
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def init_db(db_path=None):
    try:
        with _db(db_path) as conn:
            if conn is None:
                return
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT DEFAULT 'New Conversation',
                    summary TEXT DEFAULT '',
                    language_pref TEXT DEFAULT 'bn',
                    response_style TEXT DEFAULT 'technical-architect',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    metadata_json TEXT
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('system','user','assistant')),
                    content TEXT NOT NULL,
                    provider TEXT DEFAULT 'supremeai-core',
                    model TEXT DEFAULT 'auto',
                    sequence_no INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    metadata_json TEXT DEFAULT '{}',
                    CONSTRAINT uq_conv_sequence UNIQUE (conversation_id, sequence_no)
                );
                CREATE TABLE IF NOT EXISTS user_memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    memory_key TEXT NOT NULL,
                    memory_value TEXT NOT NULL,
                    confidence REAL DEFAULT 0.95,
                    source_conv_id TEXT,
                    updated_at REAL NOT NULL,
                    CONSTRAINT uq_user_memory_key UNIQUE (user_id, memory_key)
                );
                CREATE TABLE IF NOT EXISTS provider_attempts (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT,
                    status_code INTEGER NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    error_message TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_msg_conv_seq ON messages(conversation_id, sequence_no);
                CREATE INDEX IF NOT EXISTS idx_mem_user ON user_memories(user_id);
                """
            )
    except Exception as exc:
        logger.warning("Canonical DB init failed (%s); using in-memory fallback.", exc)
        _FAILED_PATHS.add(db_path or _DB_PATH)


init_db()


class CanonicalMemoryStore:
    def __init__(self, db_path=None):
        self.db_path = db_path or _DB_PATH
        if db_path:
            init_db(self.db_path)

    @contextmanager
    def _conn(self):
        with _db(self.db_path) as conn:
            yield conn

    def save_conversation(self, conversation_id, user_id="usr-admin-primary", title=None, summary=None, language_pref=None, response_style=None, metadata=None):
        now = time.time()
        with _LOCK:
            with self._conn() as conn:
                if conn is not None:
                    conn.execute(
                        """
                        INSERT INTO conversations (id, user_id, title, summary, language_pref, response_style, created_at, updated_at, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            title = COALESCE(excluded.title, conversations.title),
                            summary = COALESCE(excluded.summary, conversations.summary),
                            language_pref = COALESCE(excluded.language_pref, conversations.language_pref),
                            response_style = COALESCE(excluded.response_style, conversations.response_style),
                            updated_at = excluded.updated_at,
                            metadata_json = COALESCE(excluded.metadata_json, conversations.metadata_json);
                        """,
                        (
                            conversation_id,
                            user_id,
                            (title or "New Conversation")[:120],
                            summary or "",
                            language_pref or "bn",
                            response_style or "technical-architect",
                            now,
                            now,
                            json.dumps(metadata or {}),
                        ),
                    )
                else:
                    mem = _MEM["conversations"].setdefault(
                        conversation_id,
                        {
                            "id": conversation_id,
                            "user_id": user_id,
                            "title": (title or "New Conversation")[:120],
                            "summary": summary or "",
                            "language_pref": language_pref or "bn",
                            "response_style": response_style or "technical-architect",
                            "created_at": now,
                            "updated_at": now,
                            "metadata": metadata or {},
                            "messages": [],
                        },
                    )
                    mem["updated_at"] = now
                    if title:
                        mem["title"] = title[:120]
                    if summary is not None:
                        mem["summary"] = summary
            return {"id": conversation_id, "updated_at": now}

    def get_conversation(self, conversation_id, user_id=None):
        with _LOCK:
            with self._conn() as conn:
                if conn is not None:
                    q = "SELECT * FROM conversations WHERE id = ?"
                    params = [conversation_id]
                    if user_id:
                        q += " AND user_id = ?"
                        params.append(user_id)
                    row = conn.execute(q, params).fetchone()
                    if not row:
                        return None
                    msgs = conn.execute(
                        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY sequence_no ASC, created_at ASC;",
                        (conversation_id,),
                    ).fetchall()
                    messages = [
                        {
                            "id": m["id"],
                            "conversation_id": m["conversation_id"],
                            "user_id": m["user_id"],
                            "role": m["role"],
                            "content": m["content"],
                            "provider": m["provider"],
                            "model": m["model"],
                            "sequence_no": m["sequence_no"],
                            "created_at": m["created_at"],
                            "metadata": json.loads(m["metadata_json"] or "{}"),
                        }
                        for m in msgs
                    ]
                    return {
                        "id": row["id"],
                        "user_id": row["user_id"],
                        "title": row["title"],
                        "summary": row["summary"],
                        "language_pref": row["language_pref"],
                        "response_style": row["response_style"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "metadata": json.loads(row["metadata_json"] or "{}"),
                        "messages": messages,
                    }
                else:
                    conv = _MEM["conversations"].get(conversation_id)
                    if not conv:
                        return None
                    if user_id and conv.get("user_id") != user_id:
                        return None
                    return {
                        **conv,
                        "messages": list(conv.get("messages", [])),
                    }

    def get_recent_history(self, conversation_id, limit=10, user_id=None):
        conv = self.get_conversation(conversation_id, user_id=user_id)
        if not conv:
            return []
        msgs = conv.get("messages", [])
        if limit and limit > 0:
            msgs = msgs[-limit:]
        return [dict(m) for m in msgs]

    def _next_sequence(self, conn, conversation_id):
        if conn is not None:
            row = conn.execute(
                "SELECT COALESCE(MAX(sequence_no), 0) AS mx FROM messages WHERE conversation_id = ?;",
                (conversation_id,),
            ).fetchone()
            return int(row["mx"] or 0) + 1
        msgs = _MEM["messages"].get(conversation_id, [])
        if not msgs:
            return 1
        return max(m.get("sequence_no", 0) for m in msgs) + 1

    def append_canonical_message(self, conversation_id, role, content, user_id="usr-admin-primary", provider="supremeai-core", model="auto", sequence_no=None, metadata=None, title=None):
        if role not in ("system", "user", "assistant"):
            raise ValueError(f"invalid role: {role}")
        self.save_conversation(conversation_id, user_id=user_id, title=title)
        now = time.time()
        mid = "msg-" + uuid.uuid4().hex[:12]
        with _LOCK:
            with self._conn() as conn:
                if conn is not None:
                    if sequence_no is None:
                        sequence_no = self._next_sequence(conn, conversation_id)
                    conn.execute(
                        """
                        INSERT INTO messages (id, conversation_id, user_id, role, content, provider, model, sequence_no, created_at, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (mid, conversation_id, user_id, role, content, provider, model, sequence_no, now, json.dumps(metadata or {})),
                    )
                else:
                    if conversation_id not in _MEM["messages"]:
                        _MEM["messages"][conversation_id] = []
                    if sequence_no is None:
                        sequence_no = self._next_sequence(None, conversation_id)
                    _MEM["messages"][conversation_id].append(
                        {
                            "id": mid,
                            "conversation_id": conversation_id,
                            "user_id": user_id,
                            "role": role,
                            "content": content,
                            "provider": provider,
                            "model": model,
                            "sequence_no": sequence_no,
                            "created_at": now,
                            "metadata": metadata or {},
                        }
                    )
        return {
            "id": mid,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "provider": provider,
            "model": model,
            "sequence_no": sequence_no,
            "created_at": now,
            "metadata": metadata or {},
        }

    def get_user_durable_memories(self, user_id):
        with _LOCK:
            with self._conn() as conn:
                if conn is not None:
                    rows = conn.execute(
                        "SELECT * FROM user_memories WHERE user_id = ? ORDER BY updated_at DESC;",
                        (user_id,),
                    ).fetchall()
                    return [
                        {
                            "id": r["id"],
                            "user_id": r["user_id"],
                            "memory_key": r["memory_key"],
                            "memory_value": r["memory_value"],
                            "confidence": r["confidence"],
                            "source_conv_id": r["source_conv_id"],
                            "updated_at": r["updated_at"],
                        }
                        for r in rows
                    ]
                else:
                    return [dict(m) for m in _MEM["user_memories"].get(user_id, [])]

    def upsert_user_memory(self, user_id, memory_key, memory_value, confidence=0.95, source_conv_id=None):
        now = time.time()
        mid = "mem-" + uuid.uuid4().hex[:12]
        with _LOCK:
            with self._conn() as conn:
                if conn is not None:
                    conn.execute(
                        """
                        INSERT INTO user_memories (id, user_id, memory_key, memory_value, confidence, source_conv_id, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id, memory_key) DO UPDATE SET
                            memory_value = excluded.memory_value,
                            confidence = excluded.confidence,
                            source_conv_id = COALESCE(excluded.source_conv_id, user_memories.source_conv_id),
                            updated_at = excluded.updated_at;
                        """,
                        (mid, user_id, memory_key, memory_value, confidence, source_conv_id, now),
                    )
                else:
                    items = _MEM["user_memories"].setdefault(user_id, [])
                    items[:] = [m for m in items if m.get("memory_key") != memory_key]
                    items.append(
                        {
                            "id": mid,
                            "user_id": user_id,
                            "memory_key": memory_key,
                            "memory_value": memory_value,
                            "confidence": confidence,
                            "source_conv_id": source_conv_id,
                            "updated_at": now,
                        }
                    )
        return {
            "id": mid,
            "user_id": user_id,
            "memory_key": memory_key,
            "memory_value": memory_value,
            "updated_at": now,
        }

    def log_provider_attempt(self, request_id, conversation_id, provider, status_code, latency_ms, model=None, error_message=None):
        now = time.time()
        aid = "pa-" + uuid.uuid4().hex[:12]
        with _LOCK:
            with self._conn() as conn:
                if conn is not None:
                    conn.execute(
                        """
                        INSERT INTO provider_attempts (id, request_id, conversation_id, provider, model, status_code, latency_ms, error_message, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (aid, request_id, conversation_id, provider, model, status_code, latency_ms, error_message, now),
                    )
                else:
                    _MEM["provider_attempts"].append(
                        {
                            "id": aid,
                            "request_id": request_id,
                            "conversation_id": conversation_id,
                            "provider": provider,
                            "model": model,
                            "status_code": status_code,
                            "latency_ms": latency_ms,
                            "error_message": error_message,
                            "created_at": now,
                        }
                    )

    def update_conversation_summary(self, conversation_id, summary, user_id=None):
        now = time.time()
        with _LOCK:
            with self._conn() as conn:
                if conn is not None:
                    q = "UPDATE conversations SET summary = ?, updated_at = ? WHERE id = ?"
                    params = [summary, now, conversation_id]
                    if user_id:
                        q += " AND user_id = ?"
                        params.append(user_id)
                    conn.execute(q, params)
                else:
                    conv = _MEM["conversations"].get(conversation_id)
                    if conv:
                        conv["summary"] = summary
                        conv["updated_at"] = now


_DEFAULT_STORE = CanonicalMemoryStore()


def get_recent_history(conversation_id, limit=10, user_id=None):
    return _DEFAULT_STORE.get_recent_history(conversation_id, limit=limit, user_id=user_id)


def get_user_durable_memories(user_id):
    return _DEFAULT_STORE.get_user_durable_memories(user_id)


def append_canonical_message(*args, **kwargs):
    return _DEFAULT_STORE.append_canonical_message(*args, **kwargs)


def log_provider_attempt(*args, **kwargs):
    return _DEFAULT_STORE.log_provider_attempt(*args, **kwargs)


def upsert_user_memory(*args, **kwargs):
    return _DEFAULT_STORE.upsert_user_memory(*args, **kwargs)


def update_conversation_summary(*args, **kwargs):
    return _DEFAULT_STORE.update_conversation_summary(*args, **kwargs)


MemoryStore = CanonicalMemoryStore
memory_store = _DEFAULT_STORE

__all__ = [
    "CanonicalMemoryStore",
    "MemoryStore",
    "memory_store",
    "get_recent_history",
    "get_user_durable_memories",
    "append_canonical_message",
    "log_provider_attempt",
    "upsert_user_memory",
    "update_conversation_summary",
]
