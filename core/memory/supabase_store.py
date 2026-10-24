from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

from core.config import settings
from memory.sqlite_store import SQLiteMemoryStore


class SupabaseStore(SQLiteMemoryStore):
    def __init__(self, database_url: str | None = None, local_path: str | None = None):
        self.database_url = (
            database_url
            or os.getenv("SUPABASE_DATABASE_URL_POOLER")
            or os.getenv("SUPABASE_DATABASE_URL")
            or os.getenv("SUPABASE_DB_URL")
            # Audit fix (patch v3): canonical settings field (the previous
            # ``settings.database_url`` attribute does not exist → latent
            # AttributeError when all env vars above are unset).
            or getattr(settings, "supabase_database_url", "")
        )
        self.local_path = local_path or os.getenv("SQLITE_PATH", "data/supremeai.db")
        self._provider: str | None = None  # Will be determined after health check
        self._supabase_client = None
        self._last_health_check = 0
        self._health_check_interval = 300  # 5 minutes
        self._pgvector_available = False
        self._stats = {
            "pgvector_success": 0,
            "pgvector_failure": 0,
            "sqlite_fallback": 0,
            "embeddings_generated": 0,
            "total_queries": 0,
        }
        super().__init__(str(self.local_path))

        # Initialize provider status
        self._check_provider_status()

    def _check_provider_status(self) -> None:
        """Determine if we can use Supabase/pgvector or must fall back to SQLite."""
        if self.database_url and self._is_supabase_url(self.database_url):
            try:
                # Try to initialize client
                client = self._get_supabase_client()
                if client:
                    # Verify pgvector extension is available
                    self._pgvector_available = self._verify_pgvector_schema(client)
                    if self._pgvector_available:
                        self._provider = "supabase"
                        from core.logging_config import logger

                        logger.info("✅ Supabase pgvector connection established successfully")
                        return
            except Exception as e:
                from core.logging_config import logger

                logger.warning(f"⚠️ Supabase init failed, using SQLite fallback: {e}")

        # Fall back to SQLite
        self._provider = "sqlite"
        from core.logging_config import logger

        logger.info("📦 Using SQLite as memory backend")

    def _is_supabase_url(self, url: str) -> bool:
        """Check if URL looks like a Supabase connection string."""
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            return hostname.endswith("supabase.co") or "supabase" in hostname.lower()
        except Exception:
            return False

    def _verify_pgvector_schema(self, client) -> bool:
        """Verify that pgvector schema and RPC functions exist.

        Issue #442 fix: ai_memory.embedding is vector(384), not vector(1536).
        The test vector must match the actual schema dimension.
        """
        try:
            # Test the match_learned_facts RPC function — 384-dim per ai_memory schema
            test_embedding = [0.0] * 384
            client.rpc(
                "match_learned_facts",
                {
                    "query_embedding": test_embedding,
                    "match_threshold": 0.99,  # Very high threshold, should return empty
                    "match_count": 1,
                },
            ).execute()
            return True
        except Exception as e:
            from core.logging_config import logger

            logger.warning(f"⚠️ pgvector schema verification failed: {e}")
            return False

    @property
    def provider(self) -> str:
        return self._provider or "sqlite"

    def _get_supabase_client(self):
        # Health check cache - don't recheck too often
        current_time = time.time()
        if self._supabase_client is None or (
            current_time - self._last_health_check > self._health_check_interval
        ):
            self._last_health_check = current_time
            self._supabase_client = None  # Force reconnection

            try:
                from supabase import create_client

                url = settings.supabase_url
                if not url and self.database_url:
                    parsed = urlparse(self.database_url)
                    hostname = parsed.hostname or ""
                    if hostname.endswith("supabase.co"):
                        if hostname.startswith("db."):
                            hostname = hostname[3:]
                        url = f"https://{hostname}"
                    elif parsed.scheme in ("http", "https"):
                        url = self.database_url.rstrip("/")

                if not url:
                    # Cannot derive URL - this is not a fatal error, will use SQLite
                    return None

                key = os.getenv("SUPABASE_KEY", "")
                if not key:
                    # No key - cannot use Supabase
                    return None

                # CRITICAL FIX: Check if create_client is callable before calling
                # This fixes the 'NoneType' object is not callable error
                if callable(create_client):
                    client = create_client(url, key)
                    # Verify client is usable
                    if hasattr(client, "table") and hasattr(client, "rpc"):
                        self._supabase_client = client
                    else:
                        from core.logging_config import logger

                        logger.error("❌ Supabase client created but missing required methods")
                        return None
                else:
                    from core.logging_config import logger

                    logger.error(
                        "❌ supabase.create_client is not callable - module may be corrupted"
                    )
                    return None

            except Exception as exc:
                from core.logging_config import logger

                logger.error(f"❌ Supabase client initialization failed: {exc}")
                return None
        return self._supabase_client

    def get_stats(self) -> dict:
        """Get memory store statistics."""
        return {
            **self._stats,
            "provider": self._provider,
            "pgvector_enabled": self._pgvector_available,
        }

    def save_conversation(
        self, session_id: str, messages: list, tenant_id: str | None = None
    ) -> None:
        if self._provider == "supabase":
            tenant_id = str(tenant_id or "").strip()
            if not tenant_id or tenant_id == "default":
                raise ValueError("Tenant context required for conversation persistence")
            client = self._get_supabase_client()
            client.table("conversations").upsert(
                {
                    "session_id": session_id,
                    "tenant_id": tenant_id,
                    "messages": json.dumps(messages),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ).execute()
        else:
            self.get_session_messages(session_id)
            for msg in messages:
                if isinstance(msg, dict):
                    self.save_message(session_id, msg.get("role", "user"), msg.get("content", ""))

    def get_conversation(self, session_id: str) -> list:
        if self._provider == "supabase":
            client = self._get_supabase_client()
            result = (
                client.table("conversations")
                .select("messages")
                .eq("session_id", session_id)
                .execute()
            )
            rows = result.data
            if rows:
                return json.loads(rows[0]["messages"])
            return []
        return self.get_session_messages(session_id)

    def _generate_embedding(self, text: str) -> list[float] | None:
        """Generate a 384-dimensional embedding for pgvector storage.

        Issue #442 fix: ai_memory.embedding is vector(384). The old
        implementation requested pg_dim=1536 which triggered a warning in
        embed_for_pgvector and returned a 384-dim vector anyway — but it
        also silenced real errors with 'Ignored exception' log messages.
        All exceptions are now logged with their actual cause.
        """
        from core.logging_config import logger

        self._stats["embeddings_generated"] += 1
        try:
            from core.embeddings import embed_for_pgvector

            # 384 = exact ai_memory.embedding schema dimension (issue #442)
            return embed_for_pgvector(text, pg_dim=384)
        except Exception as primary_exc:
            logger.warning(
                "[supabase_store] embed_for_pgvector failed (%s): %s",
                type(primary_exc).__name__,
                primary_exc,
            )

        # Graceful fallback: sentence-transformers (only if available)
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer("all-MiniLM-L6-v2")
            embedding = model.encode(text, normalize_embeddings=True).tolist()
            if len(embedding) == 384:
                return embedding
            logger.warning(
                "[supabase_store] sentence-transformers returned %d dims; expected 384",
                len(embedding),
            )
        except Exception as st_exc:
            logger.debug("[supabase_store] sentence-transformers unavailable: %s", st_exc)

        # All embedding paths failed — caller must handle None gracefully
        logger.error(
            "[supabase_store] All embedding paths exhausted for text '%.60s...'; "
            "storing without embedding (pgvector recall will degrade).",
            text,
        )
        return None

    def _save_learned_fact_sqlite(self, fact_id: str, fact: dict) -> None:
        # বাংলা মন্তব্য: SQLite-এ ফ্যাক্ট লেখার একমাত্র জায়গা — Supabase পাথ এবং fallback পাথ উভয়েই এটাই ব্যবহার করে
        # 🐛 BUGFIX (2026-09-15): tasks.id হলো INTEGER PRIMARY KEY AUTOINCREMENT
        # (sqlite_store.py:56) — TEXT fact_id ("fact_<ts>") সরাসরি লিখলে
        # sqlite3.IntegrityError: datatype mismatch হত, অর্থাৎ SQLite fallback
        # পথে learned fact কখনোই persist হত না (DB-degradation-এ data loss)।
        # সমাধান: fact_id-কে stable 63-bit integer-এ ম্যাপ করা হলো (sha256) —
        # একই fact_id → একই row id, ফলে INSERT OR REPLACE-এর dedup অর্থ
        # অক্ষুণ্ণ থাকে; আসল fact_id task_description-এর JSON payload-এর ভেতরে
        # ("id" ফিল্ড) সংরক্ষিত থাকে। Integer id অপরিবর্তিত পাস করে।
        try:
            row_id = int(fact_id)
        except (TypeError, ValueError):
            digest = hashlib.sha256(str(fact_id).encode("utf-8")).digest()
            row_id = int.from_bytes(digest[:8], "big") >> 1  # 63-bit, sign-safe
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO tasks (id, task_description, task_type, success, cost, outcome_text) VALUES (?, ?, ?, ?, ?, ?)",
            (row_id, json.dumps(fact), "learned_fact", 1, 0.0, json.dumps(fact)),
        )
        conn.commit()
        self._close_connection(conn)

    def save_learned_fact(self, fact: dict) -> None:
        fact_id = fact.get("id")
        if not fact_id:
            fact_id = f"fact_{datetime.now(UTC).timestamp()}"
            fact["id"] = fact_id
        fact["created_at"] = fact.get("created_at", datetime.now(UTC).isoformat())
        if self._provider == "supabase":
            try:
                self._stats["total_queries"] += 1

                content_text = fact.get("content", fact.get("text", ""))
                embedding = self._generate_embedding(content_text)

                client = self._get_supabase_client()
                data = {
                    "id": fact_id,
                    "content": json.dumps(fact),
                    "tags": json.dumps(fact.get("tags", [])),
                    "created_at": fact["created_at"],
                }
                if embedding:
                    data["embedding"] = embedding

                client.table("learned_facts").upsert(data).execute()
            except Exception as e:
                self._stats["pgvector_failure"] += 1
                # CRITICAL FIX - fallback to SQLite on failure
                from core.logging_config import logger

                logger.error(f"Failed to save fact to Supabase, falling back to local SQLite: {e}")
                try:
                    self._stats["sqlite_fallback"] += 1
                    self._save_learned_fact_sqlite(fact_id, fact)
                except Exception as fallback_error:
                    logger.error(
                        f"SQLite fallback also failed — fact '{fact_id}' was NOT persisted: {fallback_error}"
                    )
                    raise
        else:
            # SQLite path
            self._stats["sqlite_fallback"] += 1
            self._save_learned_fact_sqlite(fact_id, fact)

    async def save_learned_fact_async(self, fact: dict) -> None:
        """Async version of save_learned_fact for non-blocking writes."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.save_learned_fact, fact)

    def search_facts(self, query: str) -> list:
        self._stats["total_queries"] += 1

        if self._provider == "supabase":
            try:
                self._stats["pgvector_success"] += 1
                # Semantic search via pgvector RPC
                query_embedding = self._generate_embedding(query)
                if query_embedding:
                    client = self._get_supabase_client()
                    response = client.rpc(
                        "match_learned_facts",
                        {
                            "query_embedding": query_embedding,
                            "match_threshold": 0.3,
                            "match_count": 5,
                        },
                    ).execute()
                    if response.data:
                        return [
                            (
                                json.loads(row["content"])
                                if isinstance(row["content"], str)
                                else row["content"]
                            )
                            for row in response.data
                        ]
            except Exception as e:
                self._stats["pgvector_failure"] += 1
                try:
                    from core.logging_config import logger

                    logger.warning(f"pgvector RPC failed, falling back to ilike: {e}")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).exception(f"Silenced error: {e}")

            try:
                client = self._get_supabase_client()
                result = (
                    client.table("learned_facts")
                    .select("content")
                    .ilike("content", f"%{query}%")
                    .execute()
                )
                return [
                    (
                        json.loads(row["content"])
                        if isinstance(row["content"], str)
                        else row["content"]
                    )
                    for row in result.data
                ]
            except Exception as e:
                try:
                    from core.logging_config import logger

                    logger.error(f"Fallback search failed: {e}")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).exception(f"Silenced error: {e}")
                return []
        return []

    def batch_save_facts(self, facts: list[dict]) -> dict:
        """Save multiple facts in a batch operation."""
        success_count = 0
        failed_count = 0
        errors = []

        for fact in facts:
            try:
                self.save_learned_fact(fact)
                success_count += 1
            except Exception as e:
                failed_count += 1
                errors.append(str(e))

        return {"success": success_count, "failed": failed_count, "errors": errors}

    def similarity_search(self, query: str, threshold: float = 0.3, limit: int = 5) -> list:
        """Enhanced similarity search with configurable parameters."""
        if self._provider == "supabase" and self._pgvector_available:
            try:
                query_embedding = self._generate_embedding(query)
                if query_embedding:
                    client = self._get_supabase_client()
                    response = client.rpc(
                        "match_learned_facts",
                        {
                            "query_embedding": query_embedding,
                            "match_threshold": threshold,
                            "match_count": limit,
                        },
                    ).execute()
                    if response.data:
                        return [
                            (
                                json.loads(row["content"])
                                if isinstance(row["content"], str)
                                else row["content"]
                            )
                            for row in response.data
                        ]
            except Exception as e:
                from core.logging_config import logger

                logger.warning(f"Similarity search failed: {e}")

        # Fallback to basic search
        return self.search_facts(query)

    def force_reconnect(self) -> bool:
        """Force reconnection to Supabase (useful after network issues)."""
        self._supabase_client = None
        self._provider = None
        self._check_provider_status()
        return self._provider == "supabase"
