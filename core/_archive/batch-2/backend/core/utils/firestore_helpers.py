"""
core/utils/firestore_helpers.py
================================
SupremeAI 2.0 — Firestore Client & Helper Utilities

বাংলা মন্তব্য: GCP Firestore কানেকশন পুল, ট্রানজ্যাকশন হেল্পার,
এবং কমন ডকুমেন্ট অপারেশনগুলোর ইউটিলিটি মডিউল।

Features:
- Singleton Firestore client with connection pooling
- Automatic fallback to SQLite for local dev/testing
- Batch operations with retry logic
- Document serialization/deserialization
- Collection existence helpers
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.degraded_mode import (
    InMemoryDocumentStore,
    SQLiteFallbackDisabledError,
    require_sqlite_allowed,
)
from core.errors.error_bus import with_error_bus
from core.logging_config import logger

# Lazy import for Google Cloud libraries
_FIRESTORE_CLIENT: Any | None = None
_FIRESTORE_LOCK = threading.Lock()
_SQLITE_FALLBACK_CONN: sqlite3.Connection | None = None
_INMEMORY_FALLBACK_STORE: InMemoryDocumentStore | None = None


def _get_inmemory_fallback() -> InMemoryDocumentStore:
    """P0: bounded in-process document store used when SQLite fallback is refused.

    Documents remain gettable in-process (get/stream) but are NEVER durable —
    the bounded store is cleared when the process exits.
    """
    global _INMEMORY_FALLBACK_STORE
    if _INMEMORY_FALLBACK_STORE is None:
        _INMEMORY_FALLBACK_STORE = InMemoryDocumentStore()
    return _INMEMORY_FALLBACK_STORE


def _get_sqlite_fallback() -> sqlite3.Connection:
    """Get or create SQLite fallback connection.

    P0 (Task 9-c + Wave 0.1): in production the SQLite fallback is refused
    unconditionally (the degradation flag no longer permits it) — raises
    :class:`SQLiteFallbackDisabledError`
    (callers degrade to the in-process document store instead of silently
    writing to an ephemeral file).
    """
    global _SQLITE_FALLBACK_CONN
    if _SQLITE_FALLBACK_CONN is None:
        require_sqlite_allowed("firestore_fallback")
        db_path = os.getenv("FIRESTORE_SQLITE_PATH", "data/firestore_fallback.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _SQLITE_FALLBACK_CONN = sqlite3.connect(db_path, check_same_thread=False)
        _SQLITE_FALLBACK_CONN.row_factory = sqlite3.Row
        _init_sqlite_schema(_SQLITE_FALLBACK_CONN)
    return _SQLITE_FALLBACK_CONN


def _init_sqlite_schema(conn: sqlite3.Connection) -> None:
    """Initialize SQLite fallback schema."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS firestore_documents (
            collection TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (collection, doc_id)
        );
        CREATE INDEX IF NOT EXISTS idx_collection ON firestore_documents(collection);
        CREATE INDEX IF NOT EXISTS idx_updated ON firestore_documents(updated_at);

        CREATE TABLE IF NOT EXISTS firestore_collections (
            name TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        );
    """)
    conn.commit()


def get_firestore_db(
    project_id: str | None = None,
    credentials: Any | None = None,
    use_emulator: bool | None = None,
) -> Any:
    """
    Get or create singleton Firestore client.

    বাংলা মন্তব্য: প্রথম কলে Firestore ক্লায়েন্ট তৈরি করে, পরবর্তীতে
    একই ইনস্ট্যান্স রিটার্ন করে। লোকাল ডেভেলপমেন্টে SQLite ফলব্যাক ব্যবহার করে।

    Args:
        project_id: GCP project ID (defaults to env var)
        credentials: Service account credentials
        use_emulator: Force emulator mode (auto-detected from env if None)

    Returns:
        Firestore client or SQLite fallback connection
    """
    global _FIRESTORE_CLIENT

    if _FIRESTORE_CLIENT is not None:
        return _FIRESTORE_CLIENT

    with _FIRESTORE_LOCK:
        if _FIRESTORE_CLIENT is not None:
            return _FIRESTORE_CLIENT

        # Check for emulator
        emulator_host = os.getenv("FIRESTORE_EMULATOR_HOST")
        if use_emulator is None:
            use_emulator = emulator_host is not None

        project_id = project_id or os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")

        try:
            from google.cloud import firestore

            if use_emulator and emulator_host:
                logger.info(f"🔧 Using Firestore emulator at {emulator_host}")
                _FIRESTORE_CLIENT = firestore.Client(
                    project=project_id or "demo-project",
                    credentials=credentials,
                )
            else:
                _FIRESTORE_CLIENT = firestore.Client(
                    project=project_id,
                    credentials=credentials,
                )

            logger.info(f"✅ Firestore client initialized (project: {project_id})")
            return _FIRESTORE_CLIENT

        except ImportError:
            logger.warning("⚠️ google-cloud-firestore not installed, using SQLite fallback")
            try:
                _FIRESTORE_CLIENT = _get_sqlite_fallback()
            except SQLiteFallbackDisabledError:
                # P0: production refused the ephemeral SQLite file — degrade to
                # the bounded in-process document store (CRITICAL logged once).
                logger.critical(
                    "[P0] Firestore unavailable and SQLite fallback refused — degrading to "
                    "bounded IN-PROCESS document store (documents are LOST on restart)."
                )
                _FIRESTORE_CLIENT = _get_inmemory_fallback()
            return _FIRESTORE_CLIENT

        except Exception as exc:
            logger.warning(f"⚠️ Firestore connection failed ({exc}), using SQLite fallback")
            try:
                _FIRESTORE_CLIENT = _get_sqlite_fallback()
            except SQLiteFallbackDisabledError:
                logger.critical(
                    "[P0] Firestore unavailable and SQLite fallback refused — degrading to "
                    "bounded IN-PROCESS document store (documents are LOST on restart)."
                )
                _FIRESTORE_CLIENT = _get_inmemory_fallback()
            return _FIRESTORE_CLIENT


def reset_firestore_client() -> None:
    """Reset the singleton (useful for testing)."""
    global _FIRESTORE_CLIENT, _SQLITE_FALLBACK_CONN, _INMEMORY_FALLBACK_STORE
    _FIRESTORE_CLIENT = None
    if _SQLITE_FALLBACK_CONN:
        _SQLITE_FALLBACK_CONN.close()
        _SQLITE_FALLBACK_CONN = None
    _INMEMORY_FALLBACK_STORE = None


@contextmanager
@with_error_bus("firestore_transaction")
def firestore_transaction(db: Any | None = None) -> Generator[Any, None, None]:
    """
    Context manager for Firestore transactions.

    বাংলা মন্তব্য: ট্রানজ্যাকশন ব্লকের জন্য কনটেক্সট ম্যানেজার।
    Firestore না থাকলে SQLite ফলব্যাকে সাধারণ কমিট/রোলব্যাক।
    """
    db = db or get_firestore_db()

    # Check if it's a SQLite connection
    if isinstance(db, sqlite3.Connection):
        try:
            db.execute("BEGIN")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
    else:
        # Firestore native transaction
        transaction = db.transaction()
        try:
            yield transaction
            transaction.commit()
        except Exception:
            transaction.rollback()
            raise


def doc_to_firestore(
    collection: str,
    doc_id: str | None,
    data: dict[str, Any],
    db: Any | None = None,
    merge: bool = False,
) -> str:
    """
    Upsert a document to Firestore or SQLite fallback.

    Returns:
        Document ID
    """
    db = db or get_firestore_db()
    doc_id = doc_id or str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    # SQLite fallback
    if isinstance(db, sqlite3.Connection):
        if merge:
            existing = get_doc_from_firestore(collection, doc_id, db)
            if existing:
                existing.update(data)
                data = existing

        db.execute(
            """INSERT OR REPLACE INTO firestore_documents
               (collection, doc_id, data, created_at, updated_at)
               VALUES (?, ?, ?, COALESCE(
                   (SELECT created_at FROM firestore_documents WHERE collection=? AND doc_id=?),
                   ?
               ), ?)""",
            (collection, doc_id, json.dumps(data), collection, doc_id, now, now),
        )
        db.execute(
            "INSERT OR IGNORE INTO firestore_collections (name, created_at) VALUES (?, ?)",
            (collection, now),
        )
        db.commit()
        return doc_id

    # Native Firestore
    doc_ref = db.collection(collection).document(doc_id)
    if merge:
        doc_ref.set(data, merge=True)
    else:
        doc_ref.set(data)
    return doc_id


def get_doc_from_firestore(
    collection: str,
    doc_id: str,
    db: Any | None = None,
) -> dict[str, Any] | None:
    """Retrieve a single document."""
    db = db or get_firestore_db()

    if isinstance(db, sqlite3.Connection):
        row = db.execute(
            "SELECT data FROM firestore_documents WHERE collection=? AND doc_id=?",
            (collection, doc_id),
        ).fetchone()
        return json.loads(row["data"]) if row else None

    # Native Firestore
    doc = db.collection(collection).document(doc_id).get()
    return doc.to_dict() if doc.exists else None


def delete_doc_from_firestore(
    collection: str,
    doc_id: str,
    db: Any | None = None,
) -> bool:
    """Delete a document. Returns True if existed."""
    db = db or get_firestore_db()

    if isinstance(db, sqlite3.Connection):
        cursor = db.execute(
            "DELETE FROM firestore_documents WHERE collection=? AND doc_id=?",
            (collection, doc_id),
        )
        db.commit()
        return cursor.rowcount > 0

    doc_ref = db.collection(collection).document(doc_id)
    if doc_ref.get().exists:
        doc_ref.delete()
        return True
    return False


def query_collection(
    collection: str,
    filters: list[tuple[str, str, Any]] | None = None,
    order_by: str | None = None,
    limit: int | None = None,
    db: Any | None = None,
) -> list[dict[str, Any]]:
    """
    Query a collection with optional filters.

    Args:
        filters: List of (field, op, value) tuples. op: "==", ">", "<", ">=", "<="
        order_by: Field to order by (prefix with - for descending)
        limit: Max results
    """
    db = db or get_firestore_db()
    results: list[dict[str, Any]] = []

    if isinstance(db, sqlite3.Connection):
        # SQLite fallback — simple filtering
        query = "SELECT data FROM firestore_documents WHERE collection=?"
        params: list[Any] = [collection]

        # Note: Full query emulation in SQLite is limited; this is basic
        if filters:
            for field_name, op, value in filters:
                if op == "==":
                    # JSON extraction for simple equality
                    query += f" AND json_extract(data, '$.{field_name}') = ?"
                    params.append(json.dumps(value) if isinstance(value, dict | list) else value)

        if order_by:
            direction = "DESC" if order_by.startswith("-") else "ASC"
            field = order_by.lstrip("-")
            query += f" ORDER BY json_extract(data, '$.{field}') {direction}"

        if limit:
            query += f" LIMIT {limit}"

        rows = db.execute(query, params).fetchall()
        results = [json.loads(row["data"]) for row in rows]
    else:
        # Native Firestore query
        query_ref = db.collection(collection)

        if filters:
            for field_name, op, value in filters:
                query_ref = query_ref.where(field_name, op, value)

        if order_by:
            direction = "DESCENDING" if order_by.startswith("-") else "ASCENDING"
            field = order_by.lstrip("-")
            query_ref = query_ref.order_by(field, direction=direction)

        if limit:
            query_ref = query_ref.limit(limit)

        results = [doc.to_dict() for doc in query_ref.stream()]

    return results


def batch_write(
    collection: str,
    documents: list[tuple[str | None, dict[str, Any]]],
    db: Any | None = None,
) -> list[str]:
    """
    Batch write multiple documents.

    Args:
        documents: List of (doc_id, data) tuples. doc_id=None for auto-generate.

    Returns:
        List of document IDs
    """
    db = db or get_firestore_db()
    doc_ids: list[str] = []

    if isinstance(db, sqlite3.Connection):
        now = datetime.now(UTC).isoformat()
        for doc_id, data in documents:
            doc_id = doc_id or str(uuid.uuid4())
            db.execute(
                """INSERT OR REPLACE INTO firestore_documents
                   (collection, doc_id, data, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (collection, doc_id, json.dumps(data), now, now),
            )
            doc_ids.append(doc_id)
        db.commit()
    else:
        batch = db.batch()
        for doc_id, data in documents:
            doc_id = doc_id or str(uuid.uuid4())
            doc_ref = db.collection(collection).document(doc_id)
            batch.set(doc_ref, data)
            doc_ids.append(doc_id)
        batch.commit()

    return doc_ids


def collection_exists(collection: str, db: Any | None = None) -> bool:
    """Check if a collection has any documents."""
    db = db or get_firestore_db()

    if isinstance(db, sqlite3.Connection):
        row = db.execute(
            "SELECT 1 FROM firestore_collections WHERE name=?",
            (collection,),
        ).fetchone()
        return row is not None

    # Firestore: check if any documents exist
    docs = list(db.collection(collection).limit(1).stream())
    return len(docs) > 0


def get_collection_stats(collection: str, db: Any | None = None) -> dict[str, Any]:
    """Get statistics for a collection."""
    db = db or get_firestore_db()

    if isinstance(db, sqlite3.Connection):
        row = db.execute(
            "SELECT COUNT(*) as count FROM firestore_documents WHERE collection=?",
            (collection,),
        ).fetchone()
        return {
            "collection": collection,
            "document_count": row["count"] if row else 0,
            "backend": "sqlite",
        }

    # Firestore doesn't have efficient count; estimate
    docs = list(db.collection(collection).limit(1000).stream())
    return {
        "collection": collection,
        "document_count": len(docs),
        "backend": "firestore",
        "note": "Count limited to 1000 for performance",
    }


# Convenience re-export for backward compatibility
__all__ = [
    "batch_write",
    "collection_exists",
    "delete_doc_from_firestore",
    "doc_to_firestore",
    "firestore_transaction",
    "get_collection_stats",
    "get_doc_from_firestore",
    "get_firestore_db",
    "query_collection",
    "reset_firestore_client",
]
