"""
Optimized Vector Store for Free Tier
Reduces memory usage while maintaining search quality.
"""

import asyncio
import uuid
from datetime import UTC
from typing import Any

from supabase import create_client

from core.logging_config import logger


def _coerce_uuid(raw: str) -> str:
    """Return a valid UUID string for any id.

    M0.6 (roadmap M0.6 / PR #303 §10): the ai_memory PK is `id uuid`, but
    AutoRAG writers pass deterministic string ids like
    "user:session:<sha256[:24]>" — the upsert then fails with
    `invalid input syntax for type uuid` and (pre-fix) the exception block
    swallowed it as a debug log, so nothing persisted. uuid5 of the raw id
    keeps the dedupe semantics deterministic: same id -> same uuid.
    """
    try:
        return str(uuid.UUID(raw))
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, str(raw)))


class FreeTierOptimizedVectorStore:
    """
    Vector store optimized for 512MB memory constraint.

    Strategies:
    1. Batch operations (reduce connection overhead)
    2. Streaming results (don't load all into memory)
    3. Aggressive index tuning
    4. Connection pooling with limits
    """

    BATCH_SIZE = 50  # Smaller batches for less memory
    MAX_RESULTS = 20  # Limit results to save memory
    # Canonical production contract is `ai_memory.embedding vector(384)`
    # (see models/ai_memory.EMBEDDING_DIMENSIONS and core/embeddings._PG_DIM,
    # both enforced by tests/models/test_ai_memory_schema_contract.py).
    # The old value here (1536, OpenAI ada-002) was stale and drifted from
    # every writer — any consumer using it would create dimension-mismatched
    # vectors that pgvector would reject.
    EMBEDDING_DIM = 384

    def __init__(self, supabase_url: str, supabase_key: str):
        self.client = create_client(supabase_url, supabase_key)
        self.table_name = "ai_memory"

        # Connection settings for low memory
        self._connection_pool_size = 2  # Very small pool for free tier

    async def upsert_batch(
        self, embeddings: list[list[float]], payloads: list[dict[str, Any]], ids: list[str]
    ) -> bool:
        """
        Upsert embeddings in small batches to manage memory.

        BUGFIX: supabase-py একটি **sync** ক্লায়েন্ট — আগে `await ...execute()`
        লেখা হচ্ছিল যা প্রতিবার TypeError করত (exc ব্লক তা চুপচাপ গিলে
        `False` ফেরত দিত — অর্থাৎ কোনো মেমরি কখনোই persist হতো না)।
        এখন sync কলগুলো `asyncio.to_thread`-এ পাঠানো হয়।
        """
        try:
            # Process in small batches
            for i in range(0, len(embeddings), self.BATCH_SIZE):
                batch_embeddings = embeddings[i : i + self.BATCH_SIZE]
                batch_payloads = payloads[i : i + self.BATCH_SIZE]
                batch_ids = ids[i : i + self.BATCH_SIZE]

                from datetime import datetime

                now_str = datetime.now(UTC).isoformat()
                records = [
                    {
                        "id": _coerce_uuid(bid),
                        "embedding": emb,
                        "metadata": payload,
                        "created_at": now_str,
                        # M0.6 (roadmap M0.6 / PR #303 §10): promote writer
                        # fields into their first-class columns. Previously
                        # they only lived inside the `metadata` JSONB blob:
                        # row-level queries, RLS scoping and retention cleanup
                        # never saw them (session_id/content effectively
                        # discarded). `metadata` is kept for recall fallback.
                        "content": payload.get("content", ""),
                        "user_id": payload.get("user_id"),
                        "session_id": payload.get("session_id") or "default",
                        "importance_score": payload.get("importance"),
                    }
                    for bid, emb, payload in zip(
                        batch_ids, batch_embeddings, batch_payloads, strict=True
                    )
                ]

                # Insert batch (sync supabase client → offload to worker thread)
                def _upsert(records=records) -> None:
                    self.client.table(self.table_name).upsert(records, on_conflict="id").execute()

                await asyncio.to_thread(_upsert)

                # Small delay to prevent overwhelming free tier DB
                await asyncio.sleep(0.05)

            return True

        except Exception as e:
            logger.debug(f"Batch upsert failed: {e}")
            return False

    async def similarity_search(
        self,
        query_embedding: list[float],
        user_id: str,
        limit: int = MAX_RESULTS,
        filter_metadata: dict | None = None,
    ) -> list[dict]:
        """
        Search with memory-efficient streaming (pgvector RPC).

        Issue #1689 (CRITICAL): `user_id` এখন REQUIRED — আগে
        `user_id: str | None = None` এবং None হলে RPC-তে `p_user_id`
        যেত না, ফলে `match_memories` সব ইউজারের মেমরি ফেরত দিত
        (cross-tenant data leak)। এখন tenant scope ছাড়া কল করা
        fail-closed: খালি/সাদা user_id → ValueError, কোনো DB কল নয়।
        """
        if not user_id or not str(user_id).strip():
            raise ValueError(
                "similarity_search requires a non-empty user_id "
                "(tenant isolation is mandatory — issue #1689)"
            )
        try:
            rpc_params: dict[str, Any] = {
                "query_embedding": query_embedding,
                "match_threshold": 0.7,
                "match_count": min(limit, self.MAX_RESULTS),
                "p_user_id": str(user_id),
            }

            # Build query with filters
            query = self.client.rpc("match_memories", rpc_params)

            # Apply additional filters if provided
            if filter_metadata:
                for key, value in filter_metadata.items():
                    query = query.eq(f"metadata->>{key}", value)

            # Execute and get results (sync supabase client → offload to thread
            # যাতে ইভেন্ট লুপ ব্লক না হয়)
            result = await asyncio.to_thread(query.execute)

            # Return only what we need (don't cache large results)
            return [
                {
                    "id": r.get("id"),
                    "content": r.get("metadata", {}).get("content", "")[
                        :500
                    ],  # Truncate string to save memory
                    "score": r.get("similarity", 0),
                    "metadata": r.get("metadata", {}),
                }
                for r in (result.data or [])
            ]

        except Exception as e:
            logger.debug(f"Similarity search failed: {e}")
            return []

    async def list_conversation_sessions(
        self, user_id: str, limit: int = 50, max_rows: int = 400, max_exchanges: int = 40
    ) -> list[dict]:
        """List conversation sessions grouped from the ai_memory table (#1823).

        বাংলা: ai_memory (pgvector) এখন চ্যাট হিস্টরির একমাত্র source of truth —
        এই পদ্ধতি rows-কে session_id দিয়ে group করে conversation-list projection
        তৈরি করে (recent-first)। Tenant isolation mandatory: খালি user_id →
        ValueError (#1689 নীতি)। Failure → খালি list (graceful degradation)।
        """
        if not user_id or not str(user_id).strip():
            raise ValueError(
                "list_conversation_sessions requires a non-empty user_id "
                "(tenant isolation is mandatory — issue #1689)"
            )
        try:

            def _fetch() -> list[dict[str, Any]]:
                res = (
                    self.client.table(self.table_name)
                    .select("content, session_id, created_at")
                    .eq("user_id", str(user_id))
                    .order("created_at", desc=True)
                    .limit(max_rows)
                    .execute()
                )
                return res.data or []

            rows = await asyncio.to_thread(_fetch)

            sessions: dict[str, dict[str, Any]] = {}
            for row in rows:  # newest-first আসে; insert(0) দিয়ে ascending রাখা হয়
                sid = str(row.get("session_id") or "default")
                created = row.get("created_at")
                session = sessions.setdefault(
                    sid,
                    {
                        "session_id": sid,
                        "created_at": created,
                        "updated_at": created,
                        "exchanges": [],
                    },
                )
                session["exchanges"].insert(
                    0, {"content": str(row.get("content") or ""), "created_at": created}
                )
                if created:
                    if not session["created_at"] or created < session["created_at"]:
                        session["created_at"] = created
                    if not session["updated_at"] or created > session["updated_at"]:
                        session["updated_at"] = created

            ordered = sorted(sessions.values(), key=lambda s: s["updated_at"] or "", reverse=True)[
                :limit
            ]
            for session in ordered:
                # বাংলা: ফ্রি-টিয়ার মেমরি বাঁচাতে প্রতি session-এ শেষ N এক্সচেঞ্জ
                session["exchanges"] = session["exchanges"][-max_exchanges:]
            return ordered

        except Exception as e:
            logger.debug(f"List conversation sessions failed: {e}")
            return []

    async def get_session_messages(
        self, user_id: str, session_id: str, max_rows: int = 200
    ) -> list[dict[str, Any]]:
        """Fetch one session's exchanges ascending (raw rows: content + created_at)."""
        if not user_id or not str(user_id).strip():
            raise ValueError(
                "get_session_messages requires a non-empty user_id "
                "(tenant isolation is mandatory — issue #1689)"
            )
        if not session_id or not str(session_id).strip():
            return []
        try:

            def _fetch() -> list[dict[str, Any]]:
                res = (
                    self.client.table(self.table_name)
                    .select("content, created_at")
                    .eq("user_id", str(user_id))
                    .eq("session_id", str(session_id))
                    .order("created_at", desc=True)
                    .limit(max_rows)
                    .execute()
                )
                return res.data or []

            rows = await asyncio.to_thread(_fetch)
            rows.reverse()  # ascending
            return [
                {"content": str(r.get("content") or ""), "created_at": r.get("created_at")}
                for r in rows
            ]

        except Exception as e:
            logger.debug(f"Get session messages failed: {e}")
            return []

    async def delete_old_memories(self, days_old: int = 30, limit: int = 100):
        """Delete old memories to save space (free tier storage limit)."""
        try:
            from datetime import datetime, timedelta

            cutoff = (datetime.now(UTC) - timedelta(days=days_old)).isoformat()

            def _delete_old() -> None:
                (
                    self.client.table(self.table_name)
                    .filter(f"created_at.lt.{cutoff}")
                    .limit(limit)
                    .delete()
                    .execute()
                )

            await asyncio.to_thread(_delete_old)

            return True

        except Exception as e:
            logger.debug(f"Delete failed: {e}")
            return False
