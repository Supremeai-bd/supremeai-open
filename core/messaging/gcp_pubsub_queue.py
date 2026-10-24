import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from core.degraded_mode import DEFAULT_IN_MEMORY_MAXLEN, InMemoryRing, sqlite_fallback_allowed
from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus

# P0: WARN-at-most-once flag for in-memory FIFO drop events.
_drop_warned = False

try:
    from google.cloud import pubsub_v1  # type: ignore[import-untyped]

    PUBSUB_AVAILABLE = True
except Exception:
    PUBSUB_AVAILABLE = False


class GCPPubSubQueue:
    """Google Pub/Sub task queue with SQLite local fallback."""

    def __init__(
        self,
        project_id: str | None = None,
        topic_id: str | None = None,
        subscription_id: str | None = None,
        db_path: str | None = None,
    ):
        self.project_id = (
            project_id or os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        )
        self.topic_id = topic_id or os.getenv("GCP_PUBSUB_TOPIC", "supremeai-tasks")
        self.subscription_id = (
            subscription_id or os.getenv("GCP_PUBSUB_SUBSCRIPTION") or f"{self.topic_id}-sub"
        )
        self.db_path = db_path or os.getenv("GCP_PUBSUB_SQLITE_PATH")
        self.publisher = None
        self.subscriber = None
        self._memory_conn = None
        # P0 (Task 9-c2): bounded in-process degraded queue (set when the local
        # SQLite fallback is refused in production). NEVER durable.
        self._memory_queue: InMemoryRing | None = None
        self.mode = "local_sqlite"

        if PUBSUB_AVAILABLE and self.project_id:
            try:
                self.publisher = pubsub_v1.PublisherClient()
                self.subscriber = pubsub_v1.SubscriberClient()
                self.topic_path = self.publisher.topic_path(self.project_id, self.topic_id)
                self.subscription_path = self.subscriber.subscription_path(
                    self.project_id, self.subscription_id
                )
                self.mode = "gcp_pubsub"
                logger.info("Using GCP Pub/Sub task queue")
            except Exception as exc:
                logger.warning(f"Pub/Sub unavailable, falling back to SQLite: {exc}")

        if self.mode == "local_sqlite":
            # P0 (Task 9-c2): the production refusal is centralised in
            # core.degraded_mode and is NON-CRASHING — the queue degrades to a
            # bounded in-process buffer instead of raising from __init__ (boot
            # must never die because of the gate). Dev/test behaviour unchanged.
            if not sqlite_fallback_allowed("pubsub_queue"):
                self.mode = "in_memory_degraded"
                self.db_path = None
                self._memory_queue = InMemoryRing(maxlen=DEFAULT_IN_MEMORY_MAXLEN)
                logger.warning(
                    "[P0] GCPPubSubQueue degraded to a bounded IN-PROCESS queue "
                    f"(max {DEFAULT_IN_MEMORY_MAXLEN} messages) — messages are LOST on "
                    "restart and dropped FIFO beyond the cap. The degradation flag no "
                    "longer permits SQLite fallback — provision GCP Pub/Sub."
                )
                return
            if not self.db_path:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                self.db_path = os.path.join(base_dir, "data", "gcp_pubsub_queue.db")
            if self.db_path != ":memory:":
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._init_db()

    @property
    def provider(self) -> str:
        return self.mode

    def _warn_drop(self) -> None:
        """P0: announce FIFO drops loudly, but at most once per process."""
        global _drop_warned
        if not _drop_warned:
            _drop_warned = True
            logger.warning(
                "[P0] GCPPubSubQueue in-memory buffer FULL — oldest messages are being "
                "DROPPED (FIFO). Messages will be lost until a durable queue backend "
                "(GCP Pub/Sub) is configured."
            )

    def _init_db(self) -> None:
        if self.db_path == ":memory:":
            self._memory_conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn = self._memory_conn
        else:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        assert conn is not None

        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pubsub_queue (
                    message_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    acked INTEGER NOT NULL DEFAULT 0
                )
                """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pubsub_acked ON pubsub_queue(acked)")
            conn.commit()
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def _get_connection(self):
        if self.db_path == ":memory:":
            return self._memory_conn
        return sqlite3.connect(str(self.db_path), check_same_thread=False)

    def publish(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = self._now()
        if self.publisher is not None:
            data = json.dumps(
                {
                    "task_id": task_id,
                    "payload": payload,
                    "published_at": now,
                },
                default=str,
            ).encode("utf-8")
            future = self.publisher.publish(self.topic_path, data=data)
            message_id = future.result(timeout=10)
            return {
                "success": True,
                "provider": "gcp_pubsub",
                "topic": self.topic_id,
                "message_id": message_id,
                "task_id": task_id,
            }

        message_id = uuid.uuid4().hex
        if self._memory_queue is not None:
            # P0: bounded in-process degraded mode — accept, buffer, WARN on drop.
            if len(self._memory_queue) >= self._memory_queue._maxlen:
                self._warn_drop()
            self._memory_queue.append(
                {
                    "message_id": message_id,
                    "task_id": task_id,
                    "payload": payload,
                    "published_at": now,
                    "acked": False,
                }
            )
            return {
                "success": True,
                "provider": self.mode,
                "topic": self.topic_id,
                "message_id": message_id,
                "task_id": task_id,
                "degraded": True,
            }

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO pubsub_queue (message_id, task_id, payload, published_at, acked)
                VALUES (?, ?, ?, ?, 0)
                """,
                (message_id, task_id, json.dumps(payload, default=str), now),
            )
            conn.commit()
        return {
            "success": True,
            "provider": "local_sqlite",
            "topic": self.topic_id,
            "message_id": message_id,
            "task_id": task_id,
        }

    @with_error_bus("pull")
    def pull(self, max_messages: int = 10) -> list[dict[str, Any]]:
        if self.subscriber is not None:
            response = self.subscriber.pull(
                request={
                    "subscription": self.subscription_path,
                    "max_messages": max_messages,
                }
            )
            messages = []
            for received in response.received_messages:
                try:
                    data = json.loads(received.message.data.decode("utf-8"))
                    messages.append(
                        {
                            "message_id": received.ack_id,
                            "task_id": data.get("task_id"),
                            "payload": data.get("payload"),
                            "attributes": dict(received.message.attributes),
                            "published_at": data.get("published_at"),
                        }
                    )
                except Exception as exc:
                    logger.error(f"Failed to decode message {received.ack_id}: {exc}")
                    error_event_bus.emit(
                        ErrorEvent(
                            module="gcp_pubsub_queue",
                            error_type="MessageDecodeError",
                            message=f"Failed to decode message {received.ack_id}: {exc}",
                            severity="ERROR",
                            structured_context=ErrorContext(module="gcp_pubsub_queue"),
                        )
                    )
            return messages

        if self._memory_queue is not None:
            # P0: serve unacked messages from the bounded in-process buffer (FIFO).
            pending = [m for m in self._memory_queue.snapshot() if not m.get("acked")]
            return [
                {
                    "message_id": m["message_id"],
                    "task_id": m["task_id"],
                    "payload": m["payload"],
                    "attributes": {},
                    "published_at": m["published_at"],
                }
                for m in pending[:max_messages]
            ]

        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT message_id, task_id, payload, published_at
                FROM pubsub_queue
                WHERE acked = 0
                ORDER BY published_at ASC
                LIMIT ?
                """,
                (max_messages,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    @with_error_bus("ack")
    def ack(self, message_id: str) -> dict[str, Any]:
        if self.subscriber is not None:
            try:
                self.subscriber.acknowledge(
                    request={
                        "subscription": self.subscription_path,
                        "ack_ids": [message_id],
                    }
                )
                return {
                    "success": True,
                    "provider": "gcp_pubsub",
                    "message_id": message_id,
                    "acked": True,
                }
            except Exception as exc:
                logger.error(f"Failed to ack message {message_id}: {exc}")
                error_event_bus.emit(
                    ErrorEvent(
                        module="gcp_pubsub_queue",
                        error_type="AckError",
                        message=f"Failed to ack message {message_id}: {exc}",
                        severity="ERROR",
                        structured_context=ErrorContext(module="gcp_pubsub_queue"),
                    )
                )
                raise

        if self._memory_queue is not None:
            # P0: acking in degraded mode removes the message from the ring buffer.
            removed = self._memory_queue.remove_matching(
                lambda m: m.get("message_id") == message_id
            )
            return {
                "success": True,
                "provider": self.mode,
                "message_id": message_id,
                "acked": removed > 0,
            }

        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE pubsub_queue SET acked = 1 WHERE message_id = ?", (message_id,)
            )
            conn.commit()
        return {
            "success": True,
            "provider": "local_sqlite",
            "message_id": message_id,
            "acked": cursor.rowcount > 0,
        }

    def stats(self) -> dict[str, Any]:
        if self.subscriber is not None:
            return {
                "provider": "gcp_pubsub",
                "topic": self.topic_id,
                "subscription": self.subscription_id,
                "pending": None,
                "acked": None,
            }

        if self._memory_queue is not None:
            snapshot = self._memory_queue.snapshot()
            pending = sum(1 for m in snapshot if not m.get("acked"))
            acked = len(snapshot) - pending
            return {
                "provider": self.mode,
                "db_path": None,
                "topic": self.topic_id,
                "subscription": self.subscription_id,
                "pending": pending,
                "acked": acked,
                "total": pending + acked,
                "degraded": True,
            }

        with self._get_connection() as conn:
            pending = conn.execute("SELECT COUNT(*) FROM pubsub_queue WHERE acked = 0").fetchone()[
                0
            ]
            acked = conn.execute("SELECT COUNT(*) FROM pubsub_queue WHERE acked = 1").fetchone()[0]
        return {
            "provider": "local_sqlite",
            "db_path": self.db_path,
            "topic": self.topic_id,
            "subscription": self.subscription_id,
            "pending": pending,
            "acked": acked,
            "total": pending + acked,
        }

    def close(self) -> None:
        if self.publisher is not None:
            self.publisher.transport.close()
        if self.subscriber is not None:
            self.subscriber.transport.close()
        self.publisher = None
        self.subscriber = None
        self._memory_queue = None
        if self._memory_conn is not None:
            self._memory_conn.close()

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "message_id": row["message_id"],
            "task_id": row["task_id"],
            "payload": json.loads(row["payload"]),
            "published_at": row["published_at"],
        }

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
