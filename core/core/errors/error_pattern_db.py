"""This module defines the `ErrorPatternDB` class, a specialized component for managing a persistent database
dedicated to logging, retrieving, and analyzing AI model errors and specific AI mistakes. Within the SupremeAI
project, it serves as a crucial feedback mechanism, enabling the system to learn from past failures, identify
recurring patterns (e.g., hallucinations), and derive actionable prevention strategies to continuously improve
the reliability, accuracy, and robustness of AI agent outputs.

Persistence: backed by the shared pooled Postgres connection (core.persistence.pooled_pg) so learned error
patterns survive container restarts/redeploys. Falls back to a local SQLite file only if Postgres is
unavailable (e.g. local dev without SUPABASE_DATABASE_URL_POOLER set) — in that fallback case state is, as
before, not durable across restarts, but the system stays functional rather than crashing.

Key Components:
- `ErrorPatternDB`: Manages storage/retrieval of historical AI error and mistake data.
- `ErrorPatternDB.log_error()`: Records a general error pattern, its type, and a correction into the `errors` table.
- `ErrorPatternDB.log_ai_mistake()`: Logs comprehensive details about a specific AI model mistake into `ai_mistakes`.
- `ErrorPatternDB.get_prevention_strategy()`: Retrieves the most frequently recorded prevention strategy.
- `ErrorPatternDB.check_pattern()`: Analyzes AI output against known error patterns.
"""

import sqlite3
from datetime import UTC, datetime

from core.degraded_mode import InMemoryRing, sqlite_fallback_allowed
from core.logging_config import logger
from core.persistence import pooled_pg

_PG_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS error_patterns (
        id SERIAL PRIMARY KEY,
        output TEXT,
        error_type TEXT,
        correction TEXT,
        timestamp TIMESTAMPTZ DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_mistakes (
        id SERIAL PRIMARY KEY,
        model_name TEXT,
        mistake_type TEXT,
        task_description TEXT,
        original_output TEXT,
        correct_output TEXT,
        root_cause TEXT,
        prevention_strategy TEXT,
        timestamp TIMESTAMPTZ DEFAULT now()
    )
    """,
)


class ErrorPatternDB:
    """Manages storage/retrieval of historical AI error and mistake data.

    P0 (Task 9-c2 + Wave 0.1): in production the local SQLite fallback is
    refused unconditionally (centralised gate in core.degraded_mode — the
    degradation flag no longer permits SQLite fallback).
    The DB then degrades to a bounded IN-PROCESS buffer: ``log_error``/``log_ai_mistake``
    keep working in-process (so the feedback loop stays functional), reads return
    in-process-only matches, and NOTHING is written to an ephemeral file.
    """

    def __init__(self, db_path: str | None = None):
        # Ripple-Effect Guard: an explicitly-passed db_path (used by tests for
        # isolation, e.g. a temp file or ":memory:") must force local SQLite —
        # only the no-args default is eligible for the shared Postgres backend.
        explicit_path = db_path is not None
        self.db_path = db_path or "hallucination_patterns.db"
        self._use_pg = (not explicit_path) and pooled_pg.is_available()
        if self._use_pg:
            try:
                for stmt in _PG_SCHEMA:
                    pooled_pg.execute(stmt)
                logger.info("ErrorPatternDB: using pooled Postgres backend.")
            except Exception as exc:
                logger.error(
                    f"ErrorPatternDB: Postgres schema init failed, falling back to SQLite: {exc}"
                )
                self._use_pg = False
        # ":memory:" is a special SQLite path: every sqlite3.connect() call against
        # it opens an *independent*, empty in-memory database. Since every method
        # below opens its own short-lived connection, a plain ":memory:" path would
        # lose its schema (and all data) the instant _init_sqlite()'s connection
        # closes. Use a shared-cache URI instead, and keep one connection open for
        # the lifetime of this object so the shared in-memory DB stays alive.
        self._is_memory = self.db_path == ":memory:"
        self._sqlite_uri = (
            f"file:error_pattern_db_{id(self)}?mode=memory&cache=shared"
            if self._is_memory
            else None
        )
        self._memory_keepalive = None
        # P0 (Task 9-c2): bounded in-process degraded stores (SQLite refused).
        self._use_memory = False
        self._memory_errors: InMemoryRing | None = None
        self._memory_mistakes: InMemoryRing | None = None
        if not self._use_pg:
            if not explicit_path and not sqlite_fallback_allowed("error_patterns"):
                self._use_memory = True
                self._memory_errors = InMemoryRing()
                self._memory_mistakes = InMemoryRing()
                logger.warning(
                    "[P0] ErrorPatternDB degraded to a bounded IN-PROCESS buffer — error "
                    "patterns are NOT durable and are LOST on restart. The degradation "
                    "flag no longer permits SQLite fallback — provision Postgres."
                )
                return
            if self._is_memory:
                self._memory_keepalive = sqlite3.connect(
                    self._sqlite_uri, uri=True, check_same_thread=False
                )
            self._init_sqlite()
            logger.warning(
                f"ErrorPatternDB: running on local SQLite fallback at {self.db_path} — NOT durable across restarts."
            )

    def _connect(self) -> sqlite3.Connection:
        """Open a SQLite connection, routing ":memory:" through the shared-cache URI."""
        if self._is_memory:
            return sqlite3.connect(self._sqlite_uri, uri=True, check_same_thread=False)
        return sqlite3.connect(self.db_path, check_same_thread=False)

    # ---------------------------------------------------------------- SQLite fallback (unchanged behavior) ----
    def _init_sqlite(self):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                output TEXT,
                error_type TEXT,
                correction TEXT,
                timestamp TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_mistakes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT,
                mistake_type TEXT,
                task_description TEXT,
                original_output TEXT,
                correct_output TEXT,
                root_cause TEXT,
                prevention_strategy TEXT,
                timestamp TEXT
            )
        """)
        conn.commit()
        conn.close()

    # ---------------------------------------------------------------- Public API (unchanged signatures) -------
    def log_error(self, output: str, error_type: str, correction: str):
        if self._use_pg:
            try:
                pooled_pg.execute(
                    "INSERT INTO error_patterns (output, error_type, correction) VALUES (%s, %s, %s)",
                    (output, error_type, correction),
                )
                return
            except Exception as exc:
                logger.error(f"ErrorPatternDB.log_error: Postgres write failed: {exc}")
                return
        if self._use_memory:
            # P0: bounded in-process degraded mode — write stays functional in-process.
            self._memory_errors.append(
                {
                    "output": output,
                    "error_type": error_type,
                    "correction": correction,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            return
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO errors (output, error_type, correction, timestamp) VALUES (?, ?, ?, ?)",
            (output, error_type, correction, datetime.now(UTC).isoformat()),
        )
        conn.commit()
        conn.close()

    def log_ai_mistake(self, mistake: dict):
        args = (
            mistake.get("model", "unknown"),
            mistake.get("type", "unknown"),
            mistake.get("task", "unknown"),
            mistake.get("original", ""),
            mistake.get("correct", ""),
            mistake.get("root_cause", ""),
            mistake.get("prevention", ""),
        )
        if self._use_pg:
            try:
                pooled_pg.execute(
                    "INSERT INTO ai_mistakes (model_name, mistake_type, task_description, "
                    "original_output, correct_output, root_cause, prevention_strategy) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    args,
                )
                return
            except Exception as exc:
                logger.error(f"ErrorPatternDB.log_ai_mistake: Postgres write failed: {exc}")
                return
        if self._use_memory:
            # P0: bounded in-process degraded mode.
            self._memory_mistakes.append(
                {
                    "model": mistake.get("model", "unknown"),
                    "type": mistake.get("type", "unknown"),
                    "task": mistake.get("task", "unknown"),
                    "original": mistake.get("original", ""),
                    "correct": mistake.get("correct", ""),
                    "root_cause": mistake.get("root_cause", ""),
                    "prevention": mistake.get("prevention", ""),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            return
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO ai_mistakes (model_name, mistake_type, task_description, "
            "original_output, correct_output, root_cause, prevention_strategy, "
            "timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (*args, datetime.now(UTC).isoformat()),
        )
        conn.commit()
        conn.close()

    def get_prevention_strategy(self, model: str, task_type: str) -> str:
        if self._use_pg:
            try:
                rows = pooled_pg.query(
                    "SELECT prevention_strategy FROM ai_mistakes WHERE model_name = %s AND "
                    "task_description LIKE %s GROUP BY prevention_strategy ORDER BY COUNT(*) DESC LIMIT 1",
                    (model, f"%{task_type}%"),
                )
                return rows[0][0] if rows else "No historical data - use default validation"
            except Exception as exc:
                logger.error(f"ErrorPatternDB.get_prevention_strategy: Postgres read failed: {exc}")
                return "No historical data - use default validation"
        if self._use_memory:
            # P0: in-process match only (bounded buffer, never durable).
            counts: dict[str, int] = {}
            for row in self._memory_mistakes.snapshot():
                if row.get("model") == model and task_type in str(row.get("task", "")):
                    strategy = str(row.get("prevention") or "")
                    if strategy:
                        counts[strategy] = counts.get(strategy, 0) + 1
            if counts:
                return max(counts.items(), key=lambda kv: kv[1])[0]
            return "No historical data - use default validation"
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT prevention_strategy FROM ai_mistakes WHERE model_name = ? AND "
            "task_description LIKE ? GROUP BY prevention_strategy ORDER BY COUNT(*) DESC LIMIT 1",
            (model, f"%{task_type}%"),
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else "No historical data - use default validation"

    def check_pattern(self, output: str) -> dict:
        if self._use_pg:
            try:
                rows = pooled_pg.query(
                    "SELECT error_type, correction, COUNT(*) FROM error_patterns WHERE %s LIKE '%%' || output || '%%' "
                    "GROUP BY error_type, correction",
                    (output,),
                )
                return {"known_patterns": rows, "should_prevent": len(rows) > 0}
            except Exception as exc:
                logger.error(f"ErrorPatternDB.check_pattern: Postgres read failed: {exc}")
                return {"known_patterns": [], "should_prevent": False}
        if self._use_memory:
            # P0: mirror of the SQL semantics (query output CONTAINS stored output).
            counts: dict[tuple, int] = {}
            for row in self._memory_errors.snapshot():
                stored = str(row.get("output") or "")
                if stored and stored in output:
                    key = (row.get("error_type"), row.get("correction"))
                    counts[key] = counts.get(key, 0) + 1
            patterns = [(k[0], k[1], v) for k, v in counts.items()]
            return {"known_patterns": patterns, "should_prevent": len(patterns) > 0}
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT error_type, correction, COUNT(*) FROM errors WHERE ? LIKE '%' || output || '%' GROUP BY error_type",
            (output,),
        )
        patterns = cursor.fetchall()
        conn.close()
        return {"known_patterns": patterns, "should_prevent": len(patterns) > 0}
