import os
import sqlite3
from dataclasses import dataclass
from typing import Any

from core.logging_config import logger

# শেয়ার্ড ইউটিলিটি — টাইমস্ট্যাম্প কেন্দ্রীভূত
from utils.timestamps import utc_now_iso


@dataclass
class SlidingWindowConfig:
    max_tokens: int = 4000
    overlap_ratio: float = 0.15
    summarize: bool = True
    store_summaries: bool = True
    auto_compact: bool = True
    compaction_threshold: int = 50


@dataclass
class MemoryWindowRecord:
    window_index: int
    text: str
    token_count: int
    summary: str | None = None
    created_at: str = ""


class SlidingWindowMemory:
    def __init__(self, config: SlidingWindowConfig = None, db_path: str | None = None):
        self.config = config or SlidingWindowConfig()
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, "data", "sliding_window_memory.db")
        self.db_path = db_path
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._memory_conn: sqlite3.Connection | None = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(self.db_path, check_same_thread=False)
            return self._memory_conn
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversation_windows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    window_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    summary TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS session_compact_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    level INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    window_count INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_windows_session ON conversation_windows(session_id, created_at);
            """)
            conn.commit()
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def _token_count(self, text: str) -> int:
        return max(1, len(text.split()))

    def _make_windows(self, text: str) -> list[str]:
        max_tokens = self.config.max_tokens
        words = text.split()
        if len(words) <= max_tokens:
            return [text]
        overlap = int(max_tokens * self.config.overlap_ratio)
        step = max(1, max_tokens - overlap)
        windows: list[str] = []
        start = 0
        while start < len(words):
            chunk = words[start : start + max_tokens]
            windows.append(" ".join(chunk))
            start += step
        return windows

    def _now(self) -> str:
        # রিফ্যাক্টর: শেয়ার্ড টাইমস্ট্যাম্প ইউটিলিটি ব্যবহার
        return utc_now_iso()

    def _summarize_text(self, text: str) -> str:
        if not text:
            return ""
        first_sentence_end = text.find(". ")
        snippet = text[: first_sentence_end + 2] if first_sentence_end != -1 else text[:120]
        return snippet.replace("\n", " ").strip()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def persist(self, session_id: str, records: list[MemoryWindowRecord]) -> bool:
        conn = self._connect()
        try:
            for rec in records:
                conn.execute(
                    """
                    INSERT INTO conversation_windows
                    (session_id, window_index, text, token_count, summary, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        rec.window_index,
                        rec.text,
                        rec.token_count,
                        rec.summary or self._summarize_text(rec.text),
                        rec.created_at or self._now(),
                    ),
                )
            conn.commit()
            if self.config.auto_compact:
                self._compact_if_needed(session_id)
            return True
        except Exception as exc:
            logger.error(f"Failed to persist sliding window records: {exc}")
            return False
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def recall(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT window_index, text, token_count, summary, created_at
                FROM conversation_windows
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def clear(self, session_id: str) -> bool:
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM conversation_windows WHERE session_id = ?",
                (session_id,),
            )
            conn.execute(
                "DELETE FROM session_compact_summaries WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return True
        except Exception as exc:
            logger.error(f"Failed to clear sliding window memory: {exc}")
            return False
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def chunk(self, text: str, session_id: str = "default") -> list[dict[str, Any]]:
        windows = self._make_windows(text)
        records: list[MemoryWindowRecord] = []
        items: list[dict[str, Any]] = []
        for idx, win in enumerate(windows):
            summary = self._summarize_text(win) if self.config.summarize else None
            rec = MemoryWindowRecord(
                window_index=idx,
                text=win,
                token_count=self._token_count(win),
                summary=summary,
                created_at=self._now(),
            )
            records.append(rec)
            items.append(
                {
                    "window_index": idx,
                    "text": win,
                    "token_count": rec.token_count,
                    "summary": summary,
                }
            )
        self.persist(session_id, records)
        logger.info(
            "SlidingWindow session={} created {} windows from {} tokens",
            session_id,
            len(items),
            self._token_count(text),
        )
        return items

    # ------------------------------------------------------------------
    # Hierarchical compaction
    # ------------------------------------------------------------------
    def _compact_if_needed(self, session_id: str) -> None:
        conn = self._connect()
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM conversation_windows WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            if count < self.config.compaction_threshold:
                return
            rows = conn.execute(
                "SELECT window_index, text, token_count, summary FROM conversation_windows WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        finally:
            if self.db_path != ":memory:":
                conn.close()

        window_count = len(rows)
        existing_level = 0
        conn2 = self._connect()
        try:
            existing_level = (
                conn2.execute(
                    "SELECT MAX(level) FROM session_compact_summaries WHERE session_id = ?",
                    (session_id,),
                ).fetchone()[0]
                or 0
            )
        finally:
            if self.db_path != ":memory:":
                conn2.close()

        level = existing_level + 1
        parent_summaries = [r[3] or r[1] for r in rows]
        combined = " ".join(parent_summaries)
        flat_summary = combined[:800]
        conn3 = self._connect()
        try:
            conn3.execute(
                """
                INSERT INTO session_compact_summaries
                (session_id, level, summary, window_count, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, level, flat_summary, window_count, self._now()),
            )
            conn3.commit()
            logger.info(
                "SlidingWindow session={} compacted {} windows into level {} summary",
                session_id,
                window_count,
                level,
            )
        finally:
            if self.db_path != ":memory:":
                conn3.close()

    def get_compact_summaries(self, session_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT level, summary, window_count, created_at
                FROM session_compact_summaries
                WHERE session_id = ?
                ORDER BY level ASC
                """,
                (session_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            if self.db_path != ":memory:":
                conn.close()

    # ------------------------------------------------------------------
    # Context builder with summary tree fallback
    # ------------------------------------------------------------------
    def build_context(
        self,
        documents: list[str],
        query: str = "",
        session_id: str = "default",
        budget: int | None = None,
    ) -> str:
        budget = budget or self.config.max_tokens
        chunks: list[str] = []
        recalled = self.recall(session_id, limit=10)
        for rec in recalled:
            chunks.append(rec.get("summary") or rec.get("text", ""))
        compact = self.get_compact_summaries(session_id)
        if compact:
            chunks.insert(0, " ".join(c["summary"] for c in compact))
        for doc in documents:
            for w in self.chunk(doc, session_id=session_id):
                chunks.append(w["text"])
        if not chunks:
            return ""
        selected: list[str] = []
        total = 0
        if query:
            first, rest = chunks[0], chunks[1:]
            chunks = [first, *sorted(rest, key=len)]
        for part in chunks:
            tc = self._token_count(part)
            if total + tc <= budget:
                selected.append(part)
                total += tc
        return "\n---\n".join(selected)

    def get_session_stats(self, session_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            window_count = conn.execute(
                "SELECT COUNT(*) FROM conversation_windows WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            compact_count = conn.execute(
                "SELECT COUNT(*) FROM session_compact_summaries WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            total_tokens = conn.execute(
                "SELECT COALESCE(SUM(token_count), 0) FROM conversation_windows WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
        finally:
            if self.db_path != ":memory:":
                conn.close()
        return {
            "session_id": session_id,
            "window_count": window_count,
            "compact_summary_count": compact_count,
            "total_token_count": total_tokens,
        }
