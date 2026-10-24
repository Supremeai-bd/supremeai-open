import ast
import asyncio
import hashlib
import json
import math
import os
import sqlite3
from datetime import UTC, datetime
from typing import Any

from core.config import settings
from core.degraded_mode import InMemoryRing, sqlite_fallback_allowed
from core.embeddings import hash_vectorize as _canonical_hash_vectorize
from core.logging_config import logger
from core.persistence import pooled_pg
from core.state_store import durable_state

# Using core.embeddings for 1536-dim embeddings to prevent zero-padding mismatch
HAS_SENTENCE_TRANSFORMERS = False


def hash_vectorize(text: str, size: int = 384) -> list[float]:
    """
    Pure Python Feature Hashing (Hashing Trick) to convert text into a 384-dimensional vector.
    Serves as a robust, zero-cost fallback when SentenceTransformer is unavailable.

    FIX(stable-hash): delegates to the canonical core.embeddings implementation,
    which uses a process-stable blake2b hash. The previous local copy used
    Python's built-in ``hash()``, which is randomized per process
    (PYTHONHASHSEED) — vectors were non-reproducible across workers/restarts
    and stored-vs-query cosine comparisons silently broke.
    """
    return _canonical_hash_vectorize(text, size=size)


_PG_SCHEMA = """
    CREATE TABLE IF NOT EXISTS ai_memory (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id TEXT DEFAULT NULL, -- NEW: nullable for backward compat
        session_id TEXT,
        agent_type TEXT,
        task_type TEXT,
        summary TEXT,
        embedding TEXT, -- Store as JSON string
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
"""

# FIX (P0, review 2026-09-12): cap candidate rows for in-Python cosine ranking.
# Previously the no-filter branch did a FULL-TABLE scan (all rows x 1536-dim
# JSON embeddings) inside the event loop — seconds of stall under load.
# pgvector RPC (match_ai_memory) is the scalable path; this caps the worst case.
_MEMORY_ROW_CAP = 2000


def memory_dedup_enabled() -> bool:
    """PLAN_006 P-A kill-switch — ``SUPREMEAI_MEMORY_DEDUP`` (ডিফল্ট true)।

    বাংলা: শূন্য-অতিরিক্ত-খরচ কনসোলিডেশন (M05 P-A-র মতো zero-cost default-ON);
    ``false`` দিলে আজকের blind-INSERT আচরণ (কিল-সুইচ রোলব্যাক)। অজানা মানে
    ডিফল্ট + loud warning — নীরব পছন্দ নিষিদ্ধ।
    """
    raw = os.environ.get("SUPREMEAI_MEMORY_DEDUP", "").strip().lower()
    if raw in ("", "true"):
        return True
    if raw == "false":
        return False
    logger.warning(f"SUPREMEAI_MEMORY_DEDUP={raw!r} অজানা মান — ডিফল্ট true ব্যবহৃত")
    return True


def _dedup_similarity_threshold() -> float:
    """Env-চালিত সদৃশতা-সীমা (``SUPREMEAI_MEMORY_DEDUP_THRESHOLD``, ডিফল্ট 0.92)।

    বাংলা: high-precision সীমা — ভুল মার্জ মেমোরি-অর্থ ভাঙে; অবৈধ env-মানে
    ডিফল্ট + loud warning।
    """
    raw = os.environ.get("SUPREMEAI_MEMORY_DEDUP_THRESHOLD", "").strip()
    if not raw:
        return 0.92
    try:
        value = float(raw)
    except ValueError:
        logger.warning(f"SUPREMEAI_MEMORY_DEDUP_THRESHOLD={raw!r} অবৈধ — ডিফল্ট 0.92 ব্যবহৃত")
        return 0.92
    if not 0.0 < value <= 1.0:
        logger.warning(f"SUPREMEAI_MEMORY_DEDUP_THRESHOLD={raw!r} সীমার-বাইরে (0,1] — ডিফল্ট ব্যবহৃত")
        return 0.92
    return value


class CascadeMemoryService:
    """
    Handles context memory ("Summary of Functions" / "File Structure") operations for SupremeAI.
    Persists to pooled Postgres by default (durable across restarts). Pass an explicit `db_path`
    (or omit Postgres config) to force the local SQLite fallback — used by the __main__ self-test
    below so it never touches the live memory store.

    P0 (Task 9-c): in production, the default SQLite fallback (``data/memory.db``) is
    env-gated via core.degraded_mode. When refused, the service degrades to a bounded
    IN-PROCESS buffer (5000 entries) — memories remain gettable in-process, are never
    written to an ephemeral SQLite file, and the API stays alive.
    """

    def __init__(self, db_path: str | None = None):
        self._use_pg = db_path is None and pooled_pg.is_available()
        # P0: bounded in-process degraded mode (no SQLite file, no data loss silence)
        self._degraded_memory = False
        self._memory_rows: InMemoryRing | None = None
        if self._use_pg:
            try:
                # PATCH v4 (2026-08-30): Use execute_ddl() instead of execute().
                # `execute()` runs DDL against the read-only pooler URL, which
                # raised `ReadOnlySqlTransaction` and cascaded to CRITICAL in
                # production. `execute_ddl()` routes through the writer URL
                # (SUPABASE_DATABASE_URL_WRITER) and never raises on read-only
                # failure — it logs a single warning and returns silently,
                # so the fallback to SQLite is clean and pattern-escalation-free.
                pooled_pg.execute_ddl(_PG_SCHEMA)
                self.db_path = None
                logger.info("CascadeMemoryService: using pooled Postgres backend.")
            except Exception as exc:
                logger.warning(
                    f"CascadeMemoryService: Postgres schema init failed, falling back to SQLite: {exc}"
                )
                self._use_pg = False

        if not self._use_pg:
            if db_path is None and not sqlite_fallback_allowed("memory"):
                self.db_path = None
                self._degraded_memory = True
                self._memory_rows = InMemoryRing()
                # Issue #451: degraded ring now MIRRORS to the durable state
                # store — a deploy/restart no longer silently erases memories.
                self._state = durable_state("cascade_memory")
                self._degraded_hydrated = False
                logger.critical(
                    "[P0] CascadeMemoryService degraded IN-PROCESS ONLY: SQLite fallback "
                    "refused in production and Postgres unavailable — memories are kept in "
                    "a bounded buffer mirrored to Redis state store (issue #451); rows "
                    "written before this fix are still lost. The degradation flag no "
                    "longer permits SQLite fallback; provision a durable backend."
                )
            else:
                self.db_path = db_path or "data/memory.db"
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
                self._init_db()
                logger.warning(
                    f"CascadeMemoryService: running on local SQLite fallback at {self.db_path} — NOT durable across restarts."
                )
        self.encoder = None
        # Relying on core.embeddings to fetch 1536-dim embeddings natively

        # Production-readiness plan, item 4b: pgvector RPC availability probe
        # (lazy, cached). None = not probed yet; True/False after first probe.
        self._pgvector_rpc: bool | None = None

    # ── issue #451: durable mirror helpers (degraded mode only) ──────
    @staticmethod
    def _state_key(file_path: str) -> str:
        # identifier may contain ':' / whitespace — hash it; the value keeps
        # the original file_path so hydration can rebuild the ring.
        return hashlib.sha1(file_path.encode()).hexdigest()[:16]

    def _hydrate_degraded(self) -> None:
        """Load durable rows into the ring once per process (best-effort)."""
        if self._degraded_hydrated or self._memory_rows is None:
            return
        self._degraded_hydrated = True
        try:
            existing = {r.get("file_path") for r in self._memory_rows.snapshot()}
            for data in self._state.mirror_items().values():
                fp = data.get("file_path")
                if fp and fp not in existing:
                    self._memory_rows.append(data)
        except Exception as exc:
            logger.warning("CascadeMemoryService: durable hydrate failed: %s", exc)

    # ═══════════════════════════════════════════════════════════════════
    # pgvector RPC support (production-readiness plan, item 4b)
    #
    # `match_ai_memories` RPC (database/migrations/legacy/001_pgvector_match_fn.sql)
    # থাকলে similarity ranking সম্পূর্ণ ডাটাবেসেই হয় — ২০০০ রো × ১৫৩৬-ডিম
    # ভেক্টর Python-এ লোড + কসাইন লুপের ইভেন্ট-লুপ স্তাল ঝুঁকি দূর হয়।
    # Extension/কলাম না পাওয়া গেলে পুরনো ইন-পাইথন কসাইন fallback চলে।
    # ═══════════════════════════════════════════════════════════════════
    def _pgvector_rpc_available(self) -> bool:
        """Probe (once, cached) whether ai_memory.embedding is a pgvector column."""
        if self._pgvector_rpc is not None:
            return self._pgvector_rpc
        try:
            rows = pooled_pg.query_dicts(
                """
                SELECT (EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector'))
                   AND COALESCE(
                       (SELECT udt_name = 'vector'
                          FROM information_schema.columns
                         WHERE table_name = 'ai_memory'
                           AND column_name = 'embedding'
                         LIMIT 1), False
                   ) AS pgvector_ready
                """
            )
            self._pgvector_rpc = bool(rows and rows[0].get("pgvector_ready"))
        except Exception as exc:
            logger.debug(f"pgvector RPC probe failed (fallback stays active): {exc}")
            self._pgvector_rpc = False
        if self._pgvector_rpc:
            logger.info("CascadeMemoryService: pgvector RPC match_ai_memories enabled.")
        return self._pgvector_rpc

    def _query_via_pgvector_rpc(
        self,
        query_vector: list[float],
        top_k: int,
        session_id: str | None,
        user_id: str | None,
    ) -> list[dict[str, Any]]:
        """Run similarity ranking inside Postgres via match_ai_memories RPC.

        বাংলা: threshold 0.0 রাখা হয়েছে যাতে পুরনো brute-force পথের সাথে
        সেমান্টিক প্যারিটি থাকে (ওই পথেও score-এর উপর কোনো থ্রেশহোল্ড ছিল না),
        তারপর top_k কেটে ফেরত দেওয়া হয়।
        """
        vector_literal = "[" + ",".join(f"{float(x):.7f}" for x in query_vector) + "]"
        rows = pooled_pg.query_dicts(
            """
            SELECT id, user_id, session_id, agent_type, task_type,
                   summary, metadata, created_at, similarity AS score
              FROM match_ai_memories(%s::vector, %s::float, %s::int, %s::text, %s::text)
            """,
            (vector_literal, 0.0, max(1, int(top_k)), user_id, session_id),
        )
        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "id": row.get("id"),
                    "user_id": row.get("user_id"),
                    "session_id": row.get("session_id"),
                    "agent_type": row.get("agent_type"),
                    "task_type": row.get("task_type"),
                    "summary": row.get("summary"),
                    # embedding vector আর Python-এ লাগে না — shape parity-র জন্য key রাখা হলো।
                    "embedding": None,
                    "metadata": row.get("metadata") or {},
                    "created_at": row.get("created_at"),
                    "score": float(row.get("score") or 0.0),
                }
            )
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS file_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE,
                    content TEXT,
                    summary TEXT,
                    structure TEXT,
                    embedding TEXT
                )
                """
            )
            conn.commit()

    def _embed(self, text: str) -> list[float]:
        from core.embeddings import _PG_DIM, embed_for_pgvector

        try:
            # বাংলা: embed_for_pgvector সিঙ্ক্রোনাস — তবে এটি লোকাল-ফার্স্ট (384-dim)
            # এবং সবসময় _PG_DIM-এ নরমালাইজ করে। আগে pg_dim=1536 দেওয়া হতো —
            # ফলে প্রতি কলে dimension-mismatch WARNING ছাড়ত এবং fallback hash
            # 1536-dim বানাত, যেখানে বাকি সিস্টেমের ডিম কন্ট্রাক্ট 384 — এই অসঙ্গতি
            # এখন ঠিক করা হলো (production-readiness plan, item 4b সহায়ক ফিক্স)।
            embedding = embed_for_pgvector(text, pg_dim=_PG_DIM)
            if embedding:
                return embedding
        except Exception as e:
            logger.warning(
                f"Embedding failed: {e}. Falling back to hash vectorizer ({_PG_DIM} dim)."
            )

        return hash_vectorize(text, size=_PG_DIM)

    def _parse_code_structure(self, file_path: str, content: str) -> dict[str, Any]:
        """
        Parses Python file AST structure and extracts function/class names and docstrings.
        """
        if not file_path.endswith(".py"):
            # Simple line-based fallback for non-python files
            lines = content.splitlines()
            summary = f"File: {file_path}\nLines: {len(lines)}"
            return {"summary": summary, "structure": json.dumps({"lines": len(lines)})}

        try:
            tree = ast.parse(content)
            summary_parts = [f"File: {file_path}"]
            structure: dict[str, list[Any]] = {"classes": [], "functions": []}

            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    # mypy-এর জন্য class_info-এ explicit type দেওয়া হচ্ছে যাতে .append() কাজ করে
                    class_info: dict[str, Any] = {
                        "name": node.name,
                        "methods": [],
                        "docstring": ast.get_docstring(node) or "",
                    }
                    summary_parts.append(f"Class: {node.name}")
                    if class_info["docstring"]:
                        summary_parts.append(f"  Docstring: {class_info['docstring']}")

                    for subnode in node.body:
                        if isinstance(subnode, ast.FunctionDef):
                            method_info = {
                                "name": subnode.name,
                                "docstring": ast.get_docstring(subnode) or "",
                            }
                            class_info["methods"].append(method_info)
                            summary_parts.append(f"  Method: {subnode.name}")
                            if method_info["docstring"]:
                                summary_parts.append(f"    Docstring: {method_info['docstring']}")
                    structure["classes"].append(class_info)

                elif isinstance(node, ast.FunctionDef):
                    func_info = {
                        "name": node.name,
                        "docstring": ast.get_docstring(node) or "",
                    }
                    summary_parts.append(f"Function: {node.name}")
                    if func_info["docstring"]:
                        summary_parts.append(f"  Docstring: {func_info['docstring']}")
                    structure["functions"].append(func_info)

            return {
                "summary": "\n".join(summary_parts),
                "structure": json.dumps(structure),
            }
        except Exception as e:
            logger.warning(f"AST parsing failed for {file_path}: {e}")
            return {
                "summary": f"File: {file_path} (AST parsing error)",
                "structure": json.dumps({"error": str(e)}),
            }

    def store_memory(
        self,
        file_path: str,  # Could map to session_id or task_id
        content: str,
        summary: str,
        structure: str,  # Could map to metadata
        session_id: str = "",
        agent_type: str = "unknown",
        task_type: str = "general",
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> None:
        """Stores or updates a memory entry in the database.

        বাংলা মন্তব্য: ডেটাবেসে মেমোরি এন্ট্রি স্টোর বা আপডেট করার কোর মেথড।
        """
        if metadata is None:
            metadata = {}
        embedding = self._embed(summary)
        embedding_str = json.dumps(embedding)

        if self._use_pg:
            try:
                # PLAN_006 P-A (M01): similarity-gated consolidation — একই তথ্য
                # = একটি সারি। সদৃশ হলে UPDATE (summary refresh + metadata-
                # importance bump); সদৃশ না হলে/dedup অফ হলে/probe ব্যর্থ হলে
                # আজকের blind INSERT (আচরণ-নিরপেক্ষ ফলব্যাক)।
                if memory_dedup_enabled() and self._consolidate_into_existing(
                    summary=summary,
                    embedding=embedding,
                    session_id=session_id,
                    user_id=user_id,
                    metadata=metadata,
                ):
                    return
                # Insert into ai_memory table
                pooled_pg.execute(
                    """
                    INSERT INTO ai_memory (user_id, session_id, agent_type, task_type, summary, embedding, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        session_id,
                        agent_type,
                        task_type,
                        summary,
                        embedding_str,
                        json.dumps(metadata),
                    ),
                )
            except Exception as exc:
                logger.error(f"CascadeMemoryService.store_memory: Postgres write failed: {exc}")
            return

        if self._degraded_memory:
            # P0: bounded in-process buffer (upsert semantics on file_path key)
            # + issue #451 durable mirror so restarts stop erasing memories.
            self._hydrate_degraded()
            self._memory_rows.remove_matching(lambda r: r.get("file_path") == file_path)
            row = {
                "file_path": file_path,
                "content": content,
                "summary": summary,
                "structure": structure,
                "embedding": embedding_str,
            }
            self._memory_rows.append(row)
            try:
                self._state.set(self._state_key(file_path), row)
            except Exception as exc:
                logger.warning("CascadeMemoryService: durable mirror write failed: %s", exc)
            return

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Update SQLite table schema to match ai_memory if needed, or keep file_memories for local dev
            # For consistency, let's also update the local SQLite schema in the _init_db method if we want full parity
            # For now, keeping the insert statement compatible with the new table conceptually
            cursor.execute(
                """
                INSERT INTO file_memories (file_path, content, summary, structure, embedding)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    content=excluded.content,
                    summary=excluded.summary,
                    structure=excluded.structure,
                    embedding=excluded.embedding
                """,
                (file_path, content, summary, structure, embedding_str),
            )
            conn.commit()

    def _consolidate_into_existing(
        self,
        *,
        summary: str,
        embedding: list[float],
        session_id: str,
        user_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> bool:
        """PLAN_006 P-A: similarity-gated consolidation probe (zero schema change)।

        বাংলা: ``(user_id, session_id)``-স্কোপড সারিগুলোর সাথে কসাইন-সদৃশতা
        পরীক্ষা — সীমার উপরে হলে বিদ্যমান সারি UPDATE হয় (summary/embedding
        রিফ্রেশ + metadata-ভিত্তিক importance bump; নতুন কলাম নয়)। tenant
        isolation-অক্ষুণ্ণ: স্কোপ-শূন্য লেখায় dedup অচেষ্টিত — সরাসরি blind
        INSERT-পথ (False)। probe/update ব্যর্থতা = False (আজকের আচরণ)।
        """
        if not (user_id and session_id):
            return False
        threshold = _dedup_similarity_threshold()
        try:
            rows = pooled_pg.query_dicts(
                "SELECT id, summary, embedding, metadata FROM ai_memory "
                "WHERE user_id = %s AND session_id = %s "
                f"ORDER BY created_at DESC LIMIT {_MEMORY_ROW_CAP}",
                (user_id, session_id),
            )
        except Exception as exc:
            logger.warning(f"store_memory dedup probe failed — falling back to insert: {exc}")
            return False

        best_id: Any = None
        best_score = 0.0
        best_row: dict[str, Any] | None = None
        for row in rows or []:
            try:
                stored_vector = json.loads(row.get("embedding") or "[]")
                score = self._cosine_similarity(embedding, stored_vector)
            except Exception:
                continue  # বিকৃত embedding-সারি প্রার্থী নয় — অন্যান্য সারি দেখা চলছে
            if score > best_score:
                best_id, best_score, best_row = row.get("id"), score, row

        if best_id is None or best_score < threshold:
            return False

        try:
            try:
                existing_meta = json.loads(best_row.get("metadata") or "{}") if best_row else {}
                if not isinstance(existing_meta, dict):
                    existing_meta = {}
            except Exception:
                existing_meta = {}
            merged_meta: dict[str, Any] = {**existing_meta, **(metadata or {})}
            consolidation = dict(merged_meta.get("consolidation") or {})
            consolidation["count"] = int(consolidation.get("count") or 1) + 1
            consolidation["last_consolidated_at"] = datetime.now(UTC).isoformat()
            merged_meta["consolidation"] = consolidation
            merged_meta["importance_score"] = min(
                1.0, float(merged_meta.get("importance_score") or 0.5) + 0.1
            )

            pooled_pg.execute(
                "UPDATE ai_memory SET summary = %s, embedding = %s, metadata = %s WHERE id = %s",
                (summary, json.dumps(embedding), json.dumps(merged_meta), best_id),
            )
            logger.info(
                f"CascadeMemoryService.store_memory: consolidated duplicate "
                f"(id={best_id}, cosine={best_score:.3f} ≥ {threshold}) into existing row"
            )
            return True
        except Exception as exc:
            logger.warning(f"store_memory dedup update failed — falling back to insert: {exc}")
            return False

    def retrieve_memories(
        self, session_id: str | None = None, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Retrieves all memory entries from the database or filtered by session_id.

        বাংলা মন্তব্য: ডেটাবেসে থাকা সকল মেমোরি এন্ট্রি রিট্রিভ করার কোর মেথড।
        """
        results = []
        if self._use_pg:
            try:
                if user_id and session_id:
                    rows = pooled_pg.query_dicts(
                        "SELECT id, user_id, session_id, agent_type, task_type, summary, embedding, metadata, created_at FROM ai_memory WHERE session_id = %s AND user_id = %s",
                        (session_id, user_id),
                    )
                elif session_id:
                    rows = pooled_pg.query_dicts(
                        "SELECT id, user_id, session_id, agent_type, task_type, summary, embedding, metadata, created_at FROM ai_memory WHERE session_id = %s",
                        (session_id,),
                    )
                elif user_id:
                    rows = pooled_pg.query_dicts(
                        "SELECT id, user_id, session_id, agent_type, task_type, summary, embedding, metadata, created_at FROM ai_memory WHERE user_id = %s",
                        (user_id,),
                    )
                else:
                    rows = pooled_pg.query_dicts(
                        "SELECT id, user_id, session_id, agent_type, task_type, summary, embedding, metadata, created_at FROM ai_memory"
                    )
            except Exception as exc:
                logger.error(f"CascadeMemoryService.retrieve_memories: Postgres read failed: {exc}")
                rows = []
            for row in rows:
                results.append(
                    {
                        "id": row.get("id"),
                        "user_id": row.get("user_id"),
                        "session_id": row["session_id"],
                        "agent_type": row["agent_type"],
                        "task_type": row["task_type"],
                        "summary": row["summary"],
                        "embedding": row["embedding"],  # This is a JSON string
                        "metadata": row["metadata"],  # This is a dict
                        "created_at": row["created_at"],
                    }
                )
            return results

        if self._degraded_memory:
            return [
                {
                    "file_path": row.get("file_path"),
                    "content": row.get("content"),
                    "summary": row.get("summary"),
                    "structure": row.get("structure"),
                }
                for row in self._memory_rows.snapshot()
            ]

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT file_path, content, summary, structure FROM file_memories")
            rows = cursor.fetchall()
            for row in rows:
                results.append(
                    {
                        "file_path": row["file_path"],
                        "content": row["content"],
                        "summary": row["summary"],
                        "structure": row["structure"],
                    }
                )
        return results

    def delete_memory(self, file_path: str) -> None:
        """Deletes a memory entry from the database by its session_id (mapped from file_path).

        বাংলা মন্তব্য: ফাইল পাথ (এখন সেশন আইডি হিসেবে ব্যবহৃত) দিয়ে ডেটাবেস থেকে কোনো নির্দিষ্ট মেমোরি এন্ট্রি মুছে ফেলে।
        """
        if self._use_pg:
            try:
                pooled_pg.execute("DELETE FROM ai_memory WHERE session_id = %s", (file_path,))
            except Exception as exc:
                logger.error(f"CascadeMemoryService.delete_memory: Postgres delete failed: {exc}")
            return

        if self._degraded_memory:
            self._memory_rows.remove_matching(lambda r: r.get("file_path") == file_path)
            return

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM file_memories WHERE file_path = ?", (file_path,))
            conn.commit()

    def chunk_and_embed(self, file_path: str, content: str) -> list[dict[str, Any]]:
        """
        Parses raw code, extracts function summaries and structure,
        generates vector embeddings, and saves them to the local SQLite database.
        """
        logger.info(f"Extracting summary and embedding for {file_path}")
        parsed_data = self._parse_code_structure(file_path, content)
        summary = parsed_data["summary"]
        structure = parsed_data["structure"]

        # Generate embedding for the structural summary
        embedding = self._embed(summary)

        # Save memory
        self.store_memory(file_path, content, summary, structure)

        return [{"file": file_path, "summary": summary, "vector": embedding}]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        # Dimension-safe cosine (#2257): the fallback Python ranking path
        # deserializes stored embeddings that may predate the vector(384)
        # typmod contract (e.g. legacy rows in side stores). The previous
        # implementation used zip(a, b, strict=False), which silently
        # truncated the DOT PRODUCT to the shorter length while the NORMS
        # ran over full lengths — mathematically wrong scores with no
        # error and no log (a silent ranking corruption). Policy now:
        # score over the deterministic min-length prefix (legacy-tolerant,
        # best-effort) and make every mismatch OBSERVABLE via a warning.
        # Re-encoding to the canonical 384-dim contract is the real fix:
        # scripts/migrate_embeddings.py.
        if len(a) != len(b):
            logger.warning(
                f"cosine similarity dimension mismatch: {len(a)} vs {len(b)} dims — "
                f"scoring over the {min(len(a), len(b))}-dim prefix (legacy-tolerant mode; "
                "re-encode via scripts/migrate_embeddings.py)"
            )
        dim = min(len(a), len(b))
        if dim == 0:
            return 0.0
        a = a[:dim]
        b = b[:dim]
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if not norm_a or not norm_b:
            return 0.0
        return dot / (norm_b * norm_a)

    def query_context(
        self, prompt: str, top_k: int = 5, session_id: str | None = None, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Takes the user's prompt, embeds it, and queries PostgreSQL or local SQLite for the top_k
        most relevant structural contexts using cosine similarity.
        Can be filtered by session_id.
        """
        logger.info(f"Querying context for prompt: {prompt[:30]}...")
        query_vector = self._embed(prompt)

        results = []

        if self._use_pg:
            # Production-readiness plan, item 4b: database-side ranking first —
            # pgvector RPC উপলব্ধ থাকলে ২০০০-রো Python কসাইন লুপ এড়িয়ে যাওয়া হয়।
            if self._pgvector_rpc_available():
                try:
                    return self._query_via_pgvector_rpc(query_vector, top_k, session_id, user_id)
                except Exception as exc:
                    logger.warning(
                        "CascadeMemoryService.query_context: pgvector RPC failed, "
                        f"falling back to in-Python cosine: {exc}"
                    )
            try:
                _base_cols = "SELECT id, user_id, session_id, agent_type, task_type, summary, embedding, metadata, created_at FROM ai_memory"
                _row_cap = f" ORDER BY created_at DESC LIMIT {_MEMORY_ROW_CAP}"
                if user_id and session_id:
                    rows = pooled_pg.query_dicts(
                        _base_cols + " WHERE session_id = %s AND user_id = %s" + _row_cap,
                        (session_id, user_id),
                    )
                elif session_id:
                    rows = pooled_pg.query_dicts(
                        _base_cols + " WHERE session_id = %s" + _row_cap,
                        (session_id,),
                    )
                elif user_id:
                    rows = pooled_pg.query_dicts(
                        _base_cols + " WHERE user_id = %s" + _row_cap,
                        (user_id,),
                    )
                else:
                    rows = pooled_pg.query_dicts(_base_cols + _row_cap)
            except Exception as exc:
                logger.error(f"CascadeMemoryService.query_context: Postgres read failed: {exc}")
                rows = []
            for row in rows:
                try:
                    stored_vector = json.loads(row["embedding"])
                    score = self._cosine_similarity(query_vector, stored_vector)
                    results.append(
                        {
                            "id": row.get("id"),
                            "user_id": row.get("user_id"),
                            "session_id": row["session_id"],
                            "agent_type": row["agent_type"],
                            "task_type": row["task_type"],
                            "summary": row["summary"],
                            "embedding": row["embedding"],  # JSON string
                            "metadata": row["metadata"],  # Dict
                            "created_at": row["created_at"],
                            "score": score,
                        }
                    )
                except Exception as e:
                    logger.warning(
                        f"Error calculating similarity for {row.get('session_id', row.get('file_path', 'unknown'))}: {e}"
                    )
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]

        if self._degraded_memory:
            for row in self._memory_rows.snapshot():
                try:
                    stored_vector = json.loads(row.get("embedding") or "null")
                    if not stored_vector:
                        continue
                    score = self._cosine_similarity(query_vector, stored_vector)
                    results.append(
                        {
                            "file": row.get("file_path"),
                            "summary": row.get("summary"),
                            "structure": json.loads(row.get("structure") or "{}"),
                            "score": score,
                        }
                    )
                except Exception as e:
                    logger.warning(f"Error calculating similarity for degraded memory row: {e}")
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT file_path, summary, structure, embedding FROM file_memories")
            rows = cursor.fetchall()

            for row in rows:
                try:
                    stored_vector = json.loads(row["embedding"])
                    score = self._cosine_similarity(query_vector, stored_vector)
                    results.append(
                        {
                            "file": row["file_path"],
                            "summary": row["summary"],
                            "structure": json.loads(row["structure"]),
                            "score": score,
                        }
                    )
                except Exception as e:
                    logger.warning(f"Error calculating similarity for {row['file_path']}: {e}")

        # Sort by similarity score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # Backward-compatible aliases for test compatibility
    def store(self, user_id: str, agent_id: str, content: str, metadata: dict[str, Any]) -> None:
        """Backward-compatible alias for store_memory."""
        summary = metadata.get("summary", content[:200])
        structure = metadata.get("structure", json.dumps({}))
        self.store_memory(f"{user_id}/{agent_id}", content, summary, structure)

    def get_memories(self, user_id: str) -> list[dict[str, Any]]:
        """Backward-compatible alias for retrieve_memories."""
        return self.retrieve_memories(user_id=user_id)

    def search_memories(self, user_id: str, query: str) -> list[dict[str, Any]]:
        """Backward-compatible alias for query_context."""
        return self.query_context(query, user_id=user_id)

    def delete(self, memory_id: str) -> None:
        """Backward-compatible alias for delete_memory."""
        self.delete_memory(memory_id)

    def clear_user_memories(self, user_id: str) -> None:
        """Backward-compatible alias to clear all memories."""
        if self._use_pg:
            try:
                pooled_pg.execute("DELETE FROM ai_memory WHERE user_id = %s", (user_id,))
            except Exception as exc:
                logger.error(f"clear_user_memories PG failed: {exc}")
            return

        if self._degraded_memory:
            self._memory_rows.remove_matching(
                lambda r: str(r.get("file_path") or "").startswith(f"{user_id}/")
            )
            return

        with sqlite3.connect(self.db_path) as conn:
            # Note: local sqlite still uses file_path as session_id representation
            conn.execute("DELETE FROM file_memories WHERE file_path LIKE ?", (f"{user_id}/%",))
            conn.commit()

    def get_context_window(self, user_id: str, agent_id: str, limit: int) -> list[dict[str, Any]]:
        """Backward-compatible alias for query_context."""
        return self.query_context(f"{user_id} {agent_id}", top_k=limit, user_id=user_id)

    def update_context_window(self, user_id: str, messages: list[dict[str, Any]]) -> None:
        """Backward-compatible method to store messages in context window."""
        for msg in messages:
            content = msg.get("content", str(msg))
            self.store_memory(
                f"{user_id}/context",
                content,
                content,
                json.dumps({"role": msg.get("role", "user")}),
            )

    def semantic_search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Backward-compatible alias for query_context."""
        return self.query_context(query, top_k=limit)

    def get_recent_interactions(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Backward-compatible method to get recent interactions."""
        return self.retrieve_memories(user_id=user_id)[:limit]


class LazyCascadeMemoryService:
    def __init__(self) -> None:
        self._instance: CascadeMemoryService | None = None

    def _get_instance(self) -> CascadeMemoryService:
        if self._instance is None:
            self._instance = CascadeMemoryService()
        return self._instance

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_instance(), name)


memory_service = LazyCascadeMemoryService()


def get_embedding(text: str) -> list[float]:
    """Return a 384-d embedding for *text*.

    M0.6 (roadmap / PR #303 §10): was 1536 — the ai_memory column is
    vector(384) (typmod-enforced; core/embeddings.py _PG_DIM = 384), so a
    1536-d hash fallback either got rejected by the column or silently
    poisoned the dimension contract.
    """
    from core.embeddings import embed_for_pgvector

    try:
        embedding = embed_for_pgvector(text, pg_dim=384)
        if embedding:
            return embedding
    except Exception as e:
        logger.debug(f"LiteLLM encoding error: {e}")
    return hash_vectorize(text, size=384)


# ---------------------------------------------------------------------------
# Supabase client helper
# ---------------------------------------------------------------------------

_supabase_client = None


def _get_supabase():
    """Return a cached Supabase client (service-role)."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    try:
        from supabase import create_client

        url = settings.supabase_url
        key = (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_KEY")
            or os.getenv("SUPABASE_ANON_KEY")
        )
        if not url or not key:
            return None
        _supabase_client = create_client(url, key)
        return _supabase_client
    except Exception as exc:
        logger.debug(f"Supabase client not initialized ({exc}), using local/pooled storage.")
        return None


# ---------------------------------------------------------------------------
# Public Vector Memory API
# ---------------------------------------------------------------------------


async def save_memory(
    *,
    session_id: str,
    summary: str,
    task_type: str = "general",
    agent_type: str = "main",
    metadata: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Insert a vector memory row into Supabase/Postgres ai_memory.

    Returns ``{"success": True, "id": <id>}`` on success.
    """
    try:
        from datetime import datetime

        embedding = get_embedding(summary)
        supabase = _get_supabase()
        now = datetime.now(UTC).isoformat()
        record = {
            "user_id": user_id,
            "session_id": session_id,
            "agent_type": agent_type,
            "task_type": task_type,
            "summary": summary,
            "embedding": embedding,
            "metadata": metadata or {},
            "created_at": now,
        }

        if supabase:
            try:
                # FIX (P0, review 2026-09-12): supabase-py is a SYNC client —
                # `await ...execute()` raised TypeError every time (caught &
                # swallowed), so the Supabase memory path NEVER worked and every
                # save silently fell back to the cascade. Run the sync call on a
                # worker thread instead.
                result = await asyncio.to_thread(
                    lambda: supabase.table("ai_memory").insert(record).execute()
                )
                if result.data:
                    mem_id = result.data[0].get("id", "unknown")
                    logger.info(
                        f"Memory saved (Supabase) | id={mem_id} | task={task_type} | session={session_id}"
                    )
                    return {"success": True, "id": mem_id}
            except Exception as sb_err:
                logger.warning(
                    f"Supabase insert failed ({sb_err}), falling back to cascade service."
                )

        # Local / PostgreSQL Cascade Fallback
        memory_service.store_memory(
            file_path=f"{session_id}:{task_type}",
            content=summary,
            summary=summary,
            structure=summary,
            session_id=session_id,
            agent_type=agent_type,
            task_type=task_type,
            metadata=metadata or {},
            user_id=user_id,
        )
        return {"success": True, "id": str(session_id), "backend": "cascade"}
    except Exception as exc:
        logger.error(f"Memory save exception: {exc}")
        return {"success": False, "error": str(exc)}


async def recall_memories(
    *,
    task_description: str,
    limit: int = 10,
    threshold: float = 0.65,
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    """Semantic-search ai_memory and return the top *limit* matches."""
    try:
        embedding = get_embedding(task_description)
        supabase = _get_supabase()
        if supabase:
            try:
                # FIX (P1, review 2026-09-12): sync RPC call was blocking the event
                # loop (~100-300ms per recall). Offload to a worker thread.
                result = await asyncio.to_thread(
                    lambda: supabase.rpc(
                        "match_ai_memory",
                        {
                            "query_embedding": embedding,
                            "match_threshold": threshold,
                            "match_count": limit,
                            "p_user_id": user_id,  # Assume RPC handles it, or fails safely to fallback
                        },
                    ).execute()
                )
                memories = result.data or []
                logger.info(
                    f"Memory recall (Supabase) | query='{task_description[:60]}...' | found={len(memories)}"
                )
                return memories
            except Exception as sb_err:
                logger.debug(f"Supabase RPC failed ({sb_err}), falling back to cascade service.")

        # Local / Cascade Fallback
        matches = memory_service.query_context(task_description, top_k=limit, user_id=user_id)
        return matches
    except Exception as exc:
        logger.error(f"Memory recall exception: {exc}")
        return []


async def get_semantic_cache(
    prompt: str, threshold: float = 0.95, user_id: str | None = None
) -> str | None:
    """Check if a highly similar prompt has been cached in ai_memory."""
    try:
        memories = await recall_memories(
            task_description=prompt,
            limit=1,
            threshold=threshold,
            user_id=user_id,
        )
        for mem in memories:
            # Only consider memories explicitly marked as semantic_cache
            if mem.get("task_type") == "semantic_cache":
                metadata = mem.get("metadata", {})
                if isinstance(metadata, dict) and "response" in metadata:
                    logger.info("🧠 Semantic Cache HIT!")
                    return metadata["response"]
    except Exception as exc:
        logger.error(f"Semantic cache lookup failed: {exc}")
    return None


async def set_semantic_cache(
    prompt: str, response: str, session_id: str = "cache_layer", user_id: str | None = None
) -> None:
    """Store a successful LLM response into the semantic cache."""
    try:
        await save_memory(
            session_id=session_id,
            summary=prompt,
            task_type="semantic_cache",
            agent_type="system",
            metadata={"response": response},
            user_id=user_id,
        )
        logger.info("🧠 Semantic Cache SET")
    except Exception as exc:
        logger.error(f"Failed to set semantic cache: {exc}")


async def summarize_and_save_session(
    *,
    session_id: str,
    messages: list[dict[str, str]],
    task_type: str = "general",
    user_id: str | None = None,
) -> dict[str, Any]:
    """Summarize a chat session via the LLM gateway, then save as memory."""
    parts: list[str] = []
    for m in messages[-20:]:  # last 20 messages
        role = m.get("role", "unknown")
        content = m.get("content", "")
        parts.append(f"{role}: {content}")
    session_text = "\n".join(parts)

    summary = session_text  # fallback: raw text
    try:
        from core.llm.llm_gateway import get_llm_gateway

        gateway = get_llm_gateway()
        if gateway:
            prompt = (
                "Summarize the following AI coding session in 2-3 sentences. "
                "Focus on what was accomplished, what failed, and key decisions.\n\n"
                f"{session_text}"
            )
            resp = await gateway.acompletion(
                prompt=prompt,
                task_type="summarization",
                session_id=session_id,
            )
            if isinstance(resp, dict) and resp.get("text"):
                summary = resp["text"]
            elif hasattr(resp, "choices") and resp.choices:
                summary = resp.choices[0].message.content or session_text
    except Exception as exc:
        logger.warning(f"LLM summarization failed, using raw text: {exc}")

    return await save_memory(
        session_id=session_id,
        summary=summary,
        task_type=task_type,
        metadata={"message_count": len(messages)},
        user_id=user_id,  # AUD-5.1: bind session memory to owner
    )


# Test Execution (If run directly)
if __name__ == "__main__":
    import os
    import tempfile

    # Run audit/test with temporary DB to verify functionality without corrupting live DB
    # বাংলা মন্তব্য: tempfile.mktemp() deprecated ও race-condition-prone (path তৈরি করে
    # কিন্তু ফাইল খোলে না, ফলে অন্য প্রসেস মাঝখানে ঐ নামে ফাইল বানিয়ে ফেলতে পারে)।
    # mkstemp() ব্যবহার করে সরাসরি ফাইল তৈরি ও খোলা হচ্ছে, তারপর fd বন্ধ করে শুধু path রাখা হলো।
    _tmp_fd, temp_db = tempfile.mkstemp(suffix=".db")
    os.close(_tmp_fd)
    test_service = CascadeMemoryService(db_path=temp_db)

    test_code = """
class DataAnalyzer:
    \"\"\"Analyzes numerical datasets.\"\"\"
    def __init__(self, data):
        self.data = data

    def run_analysis(self):
        \"\"\"Runs complex calculations on data.\"\"\"
        return sum(self.data)

def helper_utils():
    \"\"\"Helper logic.\"\"\"
    return True
"""
    # 1. Test indexing
    indexed = test_service.chunk_and_embed("test_file.py", test_code)
    # বাংলা মন্তব্য: Ruff T201 print এরর এড়াতে logger.info ব্যবহার করা হলো।
    logger.info(f"Indexed output: {indexed}")

    # 2. Test semantic search query
    matches = test_service.query_context("Need a class to calculate and analyze data", top_k=1)
    logger.info(f"Semantic search match: {matches}")

    # Clean up temp file
    try:
        if os.path.exists(temp_db):
            os.remove(temp_db)
    except Exception as e:
        logger.debug(f"Temporary DB cleanup skipped: {e}")
