"""This module provides a resilient and scalable verification queue mechanism, designed to manage asynchronous tasks within the SupremeAI project. It primarily utilizes Google Cloud Firestore for high-performance and distributed queuing, with an automatic fallback to a local SQLite database for development, testing, or environments where Firestore is inaccessible. The module offers a unified interface for enqueuing tasks, retrieving pending items, marking tasks as verified, deleting entries, and querying queue statistics, ensuring robust task management across different operational contexts.

Key Components:
- `GCPFirestoreVerificationQueue`: A class that implements the verification queue, abstracting away the underlying storage mechanism (GCP Firestore or SQLite) and providing methods for task management.
- `get_firestore_client()`: A deprecated function that returns a Firestore client, now delegating to a shared utility for consistency.

Dependencies:
- `json`: For serializing and deserializing task payloads and metadata.
- `os`: For accessing environment variables and managing file paths for the SQLite database.
- `sqlite3`: The standard library module for the local SQLite database fallback.
- `uuid`: For generating unique identifiers for queue items when using the SQLite backend.
- `datetime`: For handling timestamps related to task creation, updates, and verification.
- `typing`: For type hinting throughout the module.
- `loguru`: For flexible and structured logging of operational status and warnings.
- `google.cloud.firestore`: The official Google Cloud client library for interacting with Firestore.
- `utils.environment`: An internal utility for determining the application's execution environment.
- `utils.firestore_helpers`: An internal utility providing shared logic for obtaining Firestore client instances."""

import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from core.degraded_mode import InMemoryRing, sqlite_fallback_allowed
from core.logging_config import logger

try:
    from google.cloud import firestore  # type: ignore[import-untyped]

    FIRESTORE_AVAILABLE = True
except Exception:
    FIRESTORE_AVAILABLE = False


class GCPFirestoreVerificationQueue:
    """Firestore-backed verification queue with SQLite local fallback."""

    def __init__(
        self,
        collection_name: str | None = None,
        project_id: str | None = None,
        db_path: str | None = None,
        credentials: Any = None,
    ):
        self.collection_name = collection_name or os.getenv(
            "GCP_FIRESTORE_COLLECTION", "verification_queue"
        )
        self.project_id = (
            project_id or os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        )
        self.client = None
        self._memory_conn: sqlite3.Connection | None = None
        # P0 (Task 9-c2): bounded in-process degraded queue (set when the local
        # SQLite fallback is refused in production). NEVER durable.
        self._memory_rows: InMemoryRing | None = None
        self.mode = "local_sqlite"
        self.db_path = db_path or os.getenv("GCP_FIRESTORE_SQLITE_PATH")

        from utils.environment import is_test_environment

        is_test = is_test_environment()
        if FIRESTORE_AVAILABLE and self.project_id and not is_test:
            try:
                if credentials:
                    self.client = firestore.Client(project=self.project_id, credentials=credentials)
                else:
                    self.client = firestore.Client(project=self.project_id)
                self.mode = "gcp_firestore"
            except Exception as e:
                logger.warning(f"Failed to initialize Firestore: {e}. Falling back to SQLite.")

        if self.client is None:
            # P0 (Task 9-c2): production refusal is centralised in core.degraded_mode
            # and NON-CRASHING — the queue degrades to a bounded in-process buffer.
            if not sqlite_fallback_allowed("firestore_verification_queue"):
                self.mode = "in_memory_degraded"
                self.db_path = None
                self._memory_rows = InMemoryRing()
                logger.warning(
                    "[P0] GCPFirestoreVerificationQueue degraded to a bounded IN-PROCESS "
                    "queue — queued verifications are LOST on restart. The degradation "
                    "flag no longer permits SQLite fallback — provision GCP Firestore."
                )
                return
            if not self.db_path:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                self.db_path = os.path.join(base_dir, "data", "gcp_firestore_queue.db")
            if self.db_path != ":memory:":
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._init_db()

    def _init_db(self) -> None:
        if self.db_path == ":memory:":
            self._memory_conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn = self._memory_conn
        else:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)

        assert conn is not None

        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS verification_queue (
                    queue_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 50,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    verified_at TEXT
                )
                """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_verification_status ON verification_queue(status, priority)"
            )
            conn.commit()
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def _get_connection(self):
        if self.db_path == ":memory:":
            return self._memory_conn
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def enqueue(
        self,
        task_id: str,
        payload: dict[str, Any],
        priority: int = 50,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        document = {
            "task_id": task_id,
            "payload": payload,
            "priority": int(priority),
            "metadata": metadata or {},
            "status": "pending",
            "created_at": now,
            "updated_at": now,
        }

        if self.client is not None:
            _, ref = self.client.collection(str(self.collection_name)).add(document)
            return {
                "success": True,
                "provider": "gcp_firestore",
                "queue_id": ref.id,
                "task_id": task_id,
                "status": "pending",
            }

        queue_id = uuid.uuid4().hex
        if self._memory_rows is not None:
            # P0: bounded in-process degraded mode — buffer the full record.
            self._memory_rows.append(
                {
                    "queue_id": queue_id,
                    "task_id": task_id,
                    "payload": payload,
                    "priority": int(priority),
                    "metadata": dict(metadata or {}),
                    "status": "pending",
                    "created_at": now,
                    "updated_at": now,
                    "verified_at": None,
                }
            )
            return {
                "success": True,
                "provider": self.mode,
                "queue_id": queue_id,
                "task_id": task_id,
                "status": "pending",
                "degraded": True,
            }

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO verification_queue
                (queue_id, task_id, payload, priority, metadata, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    queue_id,
                    task_id,
                    json.dumps(payload, default=str),
                    int(priority),
                    json.dumps(metadata or {}, default=str),
                    now,
                    now,
                ),
            )
            conn.commit()
        return {
            "success": True,
            "provider": "local_sqlite",
            "queue_id": queue_id,
            "task_id": task_id,
            "status": "pending",
        }

    def get_pending(self, limit: int = 10) -> list[dict[str, Any]]:
        if self.client is not None:
            rows = (
                self.client.collection(str(self.collection_name))
                .where("status", "==", "pending")
                .order_by("priority", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            return [self._firestore_doc_to_dict(row) for row in rows]

        if self._memory_rows is not None:
            # P0: pending items from the bounded in-process buffer (priority desc).
            rows = [r for r in self._memory_rows.snapshot() if r.get("status") == "pending"]
            rows.sort(key=lambda r: (-int(r.get("priority", 50)), r.get("created_at", "")))
            return [dict(r) for r in rows[:limit]]

        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT queue_id, task_id, payload, priority, metadata, status, created_at, updated_at, verified_at
                FROM verification_queue
                WHERE status = 'pending'
                ORDER BY priority DESC, created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def peek(self, limit: int = 10) -> list[dict[str, Any]]:
        return self.get_pending(limit=limit)

    def mark_verified(self, task_id: str) -> dict[str, Any]:
        now = self._now()
        if self.client is not None:
            query = (
                self.client.collection(str(self.collection_name))
                .where("task_id", "==", task_id)
                .where("status", "==", "pending")
                .limit(1)
            )
            updated = 0
            for doc in query.stream():
                doc.reference.update({"status": "verified", "updated_at": now, "verified_at": now})
                updated += 1
            return {
                "success": True,
                "provider": "gcp_firestore",
                "task_id": task_id,
                "verified": updated,
            }

        if self._memory_rows is not None:
            # P0: rewrite matching in-process records as verified.
            rows = self._memory_rows.snapshot()
            updated = 0
            for row in rows:
                if row.get("task_id") == task_id and row.get("status") == "pending":
                    row["status"] = "verified"
                    row["updated_at"] = now
                    row["verified_at"] = now
                    updated += 1
            if updated:
                self._memory_rows.remove_matching(lambda _r: True)
                for row in rows:
                    self._memory_rows.append(row)
            return {
                "success": True,
                "provider": self.mode,
                "task_id": task_id,
                "verified": updated,
            }

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE verification_queue
                SET status = 'verified', updated_at = ?, verified_at = ?
                WHERE task_id = ? AND status = 'pending'
                """,
                (now, now, task_id),
            )
            conn.commit()
        return {
            "success": True,
            "provider": "local_sqlite",
            "task_id": task_id,
            "verified": cursor.rowcount,
        }

    def delete(self, queue_id: str) -> dict[str, Any]:
        if self.client is not None:
            doc = self.client.collection(str(self.collection_name)).document(queue_id)
            doc.delete()
            return {
                "success": True,
                "provider": "gcp_firestore",
                "queue_id": queue_id,
                "deleted": True,
            }

        if self._memory_rows is not None:
            removed = self._memory_rows.remove_matching(lambda r: r.get("queue_id") == queue_id)
            return {
                "success": True,
                "provider": self.mode,
                "queue_id": queue_id,
                "deleted": removed > 0,
            }

        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM verification_queue WHERE queue_id = ?", (queue_id,))
            conn.commit()
        return {
            "success": True,
            "provider": "local_sqlite",
            "queue_id": queue_id,
            "deleted": cursor.rowcount > 0,
        }

    def stats(self) -> dict[str, Any]:
        if self.client is not None:
            pending = len(
                list(
                    self.client.collection(str(self.collection_name))
                    .where("status", "==", "pending")
                    .stream()
                )
            )
            verified = len(
                list(
                    self.client.collection(str(self.collection_name))
                    .where("status", "==", "verified")
                    .stream()
                )
            )
            return {
                "provider": "gcp_firestore",
                "collection": self.collection_name,
                "pending": pending,
                "verified": verified,
                "total": pending + verified,
            }

        if self._memory_rows is not None:
            snapshot = self._memory_rows.snapshot()
            pending = sum(1 for r in snapshot if r.get("status") == "pending")
            verified = sum(1 for r in snapshot if r.get("status") == "verified")
            return {
                "provider": self.mode,
                "collection": self.collection_name,
                "pending": pending,
                "verified": verified,
                "total": len(snapshot),
                "degraded": True,
            }

        with self._get_connection() as conn:
            pending = conn.execute(
                "SELECT COUNT(*) FROM verification_queue WHERE status = 'pending'"
            ).fetchone()[0]
            verified = conn.execute(
                "SELECT COUNT(*) FROM verification_queue WHERE status = 'verified'"
            ).fetchone()[0]
            total = conn.execute("SELECT COUNT(*) FROM verification_queue").fetchone()[0]
        return {
            "provider": "local_sqlite",
            "db_path": self.db_path,
            "pending": pending,
            "verified": verified,
            "total": total,
        }

    def close(self) -> None:
        if self.client is not None:
            self.client = None
        self._memory_rows = None
        if self._memory_conn is not None:
            self._memory_conn.close()

    @property
    def provider(self) -> str:
        return "gcp_firestore" if self.client else self.mode

    def _firestore_doc_to_dict(self, doc: Any) -> dict[str, Any]:
        data = doc.to_dict()
        data["queue_id"] = doc.id
        return data

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "queue_id": row["queue_id"],
            "task_id": row["task_id"],
            "payload": json.loads(row["payload"]),
            "priority": row["priority"],
            "metadata": json.loads(row["metadata"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "verified_at": row["verified_at"],
        }

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()


def get_firestore_client(project_id: str | None = None):
    """Firestore ক্লায়েন্ট রিটার্ন করে।

    নোট: এই ফাংশনটি পুরানো কোডের সাথে সামঞ্জস্যতার জন্য রাখা হয়েছে।
    নতুন কোডের জন্য utils.firestore_helpers.get_firestore_db() ব্যবহার করুন।
    """
    # রিফ্যাক্টর: শেয়ার্ড ইউটিলিটিতে ডেলিগেট করা হচ্ছে
    from utils.firestore_helpers import get_firestore_db as _get_db

    return _get_db(project_id)
