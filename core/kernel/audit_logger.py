import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime

from core.config import settings
from core.degraded_mode import InMemoryRing, sqlite_fallback_allowed
from core.logging_config import logger
from core.persistence import pooled_pg
from core.persistence.write_behind import WriteBehindBatcher

_PG_SCHEMA = """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id SERIAL PRIMARY KEY,
        action_type TEXT,
        decision_details TEXT,
        reasoning TEXT,
        timestamp TIMESTAMPTZ DEFAULT now()
    )
"""

_INSERT_SQL = (
    "INSERT INTO audit_logs (action_type, decision_details, reasoning) VALUES (%s, %s, %s)"
)


class AuditLogger:
    """Tamper-evident audit trail for autonomous decisions.

    Persistence: pooled Postgres via a write-behind batcher — audit writes are
    high-frequency, so batching avoids a connection checkout per log line while
    still flushing at most every ~2s (or on graceful shutdown, see
    core/lifespan.py -> write_behind.flush_all()). Falls back to local SQLite
    (previous behavior) only if Postgres isn't configured.

    P0 (Task 9-c): in production the SQLite fallback is env-gated via
    core.degraded_mode. When refused, the logger degrades to a bounded
    IN-PROCESS buffer (5000 entries) — audit events stay gettable via
    get_audit_trail() within the process but are never written to an ephemeral
    SQLite file.
    """

    _batcher: WriteBehindBatcher | None = None
    _schema_initialized: bool = False

    def __init__(self, db_path: str | None = None):
        # P0: bounded in-process degraded mode (no SQLite file)
        self._degraded_memory = False
        self._memory_rows: InMemoryRing | None = None
        # Ripple-Effect Guard: explicit db_path (tests pass a tmp_path fixture
        # for isolation) must force local SQLite, matching prior behavior.
        explicit_path = db_path is not None
        # বাংলা মন্তব্য: স্টার্টআপে সিনক্রোনাস কানেকশন ও নেটওয়ার্ক ব্লক এড়াতে is_configured ব্যবহার করা হলো
        self._use_pg = (not explicit_path) and pooled_pg.is_configured()
        if self._use_pg:
            if AuditLogger._batcher is None:
                AuditLogger._batcher = WriteBehindBatcher(
                    name="audit_logs", flush_interval=2.0, max_batch=200
                )
            logger.info("AuditLogger: using pooled Postgres backend (write-behind batched).")

        if not self._use_pg:
            if db_path is None and not sqlite_fallback_allowed("audit_log"):
                self._enter_memory_mode()
            else:
                if db_path is None:
                    memory_db_dir = getattr(settings, "memory_db_dir", None) or os.path.dirname(
                        os.path.dirname(os.path.abspath(__file__))
                    )
                    if memory_db_dir and not os.path.exists(memory_db_dir):
                        os.makedirs(memory_db_dir, exist_ok=True)
                    self.db_path = (
                        os.path.join(memory_db_dir, "supreme_memory.db")
                        if memory_db_dir
                        else "supreme_memory.db"
                    )
                else:
                    self.db_path = db_path
                self._init_sqlite()
                logger.warning(
                    f"AuditLogger: running on local SQLite fallback at {self.db_path} — NOT durable across restarts."
                )

    def _enter_memory_mode(self) -> None:
        """P0: degrade to a bounded in-process buffer (no SQLite file opened)."""
        self.db_path = None
        self._degraded_memory = True
        self._memory_rows = InMemoryRing()
        logger.critical(
            "[P0] AuditLogger degraded IN-PROCESS ONLY: SQLite fallback refused in production "
            "and Postgres unavailable — audit events are buffered in memory (5000 entries) "
            "and are LOST on restart. The degradation flag no longer permits SQLite "
            "fallback; provision a durable backend (Postgres)."
        )

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            yield conn
        finally:
            conn.close()

    def _init_sqlite(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type TEXT,
                    decision_details TEXT,
                    reasoning TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

    def _ensure_schema(self) -> bool:
        if not self._use_pg:
            return False
        if AuditLogger._schema_initialized:
            return True
        try:
            # বাংলা মন্তব্য: প্রথম কুয়েরি বা ডেটা ইনসার্টের সময় অলসভাবে (lazily) স্কিমা তৈরি করা হচ্ছে
            pooled_pg.execute(_PG_SCHEMA)
            AuditLogger._schema_initialized = True
            return True
        except Exception as exc:
            logger.error(
                f"AuditLogger: Postgres schema lazy initialization failed, falling back to SQLite: {exc}"
            )
            self._use_pg = False
            # P0: production without the degradation opt-in must NOT silently
            # land on an ephemeral SQLite file — degrade to the in-process buffer.
            if not sqlite_fallback_allowed("audit_log"):
                self._enter_memory_mode()
                return False
            memory_db_dir = getattr(settings, "memory_db_dir", None) or os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
            if memory_db_dir and not os.path.exists(memory_db_dir):
                os.makedirs(memory_db_dir, exist_ok=True)
            self.db_path = (
                os.path.join(memory_db_dir, "supreme_memory.db")
                if memory_db_dir
                else "supreme_memory.db"
            )
            self._init_sqlite()
            return False

    def log_decision(self, action_type: str, decision_details: str, reasoning: str):
        """Logs an autonomous decision or rotation details to the tamper-evident audit trail."""
        logger.info(
            f"[AUDIT LOG] {action_type} - Details: {decision_details} - Reason: {reasoning}"
        )
        if self._degraded_memory:
            # P0: bounded in-process buffer — gettable via get_audit_trail().
            self._memory_rows.append(
                {
                    "action_type": action_type,
                    "decision_details": decision_details,
                    "reasoning": reasoning,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            return
        if self._ensure_schema() and AuditLogger._batcher is not None:
            AuditLogger._batcher.submit(_INSERT_SQL, (action_type, decision_details, reasoning))
            return
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO audit_logs (action_type, decision_details, reasoning) VALUES (?, ?, ?)",
                    (action_type, decision_details, reasoning),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to write to audit database: {e}")

    def get_audit_trail(self) -> list:
        if self._degraded_memory:
            # Newest first, mirroring the SQL ORDER BY timestamp DESC contract.
            rows = self._memory_rows.snapshot()
            rows.reverse()
            return [
                {
                    "id": len(rows) - idx,
                    **row,
                }
                for idx, row in enumerate(rows)
            ]
        if self._ensure_schema():
            try:
                # Ensure any not-yet-flushed rows are visible before reading.
                if AuditLogger._batcher is not None:
                    AuditLogger._batcher.flush()
                return pooled_pg.query_dicts("SELECT * FROM audit_logs ORDER BY timestamp DESC")
            except Exception as e:
                logger.error(f"Failed to query audit trail from Postgres: {e}")
                return []
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC")
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to query audit trail: {e}")
            return []
