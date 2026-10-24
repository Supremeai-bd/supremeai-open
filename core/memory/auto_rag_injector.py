"""
AutoRAGInjector — Persistent Cross-Session Memory, Auto-Injected (audit G-3).

বাংলা: Agent/চ্যাট প্রতিটি নতুন অনুরোধের আগে ব্যবহারকারীর অতীত প্রাসঙ্গিক
স্মৃতি (pgvector `ai_memory`) থেকে semantic recall করে স্বয়ংক্রিয়ভাবে
prompt-এর শুরুতে যুক্ত করে — ChatGPT Persistent Memory / Mem0-ধাঁচের
আচরণ। কোনো কারণে recall ব্যর্থ হলে **নীরব graceful degradation** — মূল
prompt অপরিবর্তিত থাকে, ব্যবহারকারী কখনো এরর দেখেন না।

ইন্টিগ্রেশন পয়েন্ট:
- ``api/routes/stream_chat_sse.py`` — SafeSSEGenerator (আগে কোনো memory
  injection ছিলই না — এটিই ছিল সবচেয়ে বড় গ্যাপ)
- ``api/routes/chat.py`` — stream_chat-এ user_id ছাড়া recall হতো (tenant
  miss bug); AutoRAGInjector এখন user/tenant-scoped recall নিশ্চিত করে

Zero-Hardcoding: কোনো provider/model নাম এখানে নেই — embedding আসে
``core.embeddings`` (local-first) থেকে, store আসে ``core.ai_memory`` থেকে।
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from core.logging_config import logger


class AutoRAGInjector:
    """Retrieves top-K relevant past memories and prepends them to the prompt.

    The injected block is placed BEFORE the user prompt so the model treats it
    as recalled context, not as the user's own words.
    """

    MEMORY_PREFIX = "\n\n--- 🧠 Past Context (Auto-Recalled) ---\n"
    MEMORY_SUFFIX = "--- End of Past Context ---\n\n"
    TOP_K = 5
    MAX_CHARS_PER_MEMORY = 400
    # বাংলা: এর নিচের স্কোরের মেমরি inject করা হয় না — noise এড়াতে।
    MIN_RELEVANCE_SCORE = 0.55
    # বাংলা: store-এর সময় minimum importance — অর্থহীন ছোট এক্সচেঞ্জ বাদ।
    MIN_IMPORTANCE_TO_STORE = 0.5

    def __init__(self, vector_store: Any | None = None) -> None:
        self._vs = vector_store
        self._vs_lock = asyncio.Lock()

    # ── internal helpers ────────────────────────────────────────────────
    def _get_vector_store(self) -> Any | None:
        """Lazy singleton for FreeTierOptimizedVectorStore (never raises)."""
        if self._vs is not None:
            return self._vs
        try:
            from core.ai_memory.vector_store import FreeTierOptimizedVectorStore
            from core.config import settings

            supabase_url = getattr(settings, "supabase_url", "") or ""
            supabase_key = (
                getattr(settings, "supabase_service_role_key", "")
                or getattr(settings, "supabase_anon_key", "")
                or ""
            )
            if not supabase_url or not supabase_key:
                logger.debug("[AutoRAG] Supabase not configured - injection disabled")
                return None
            self._vs = FreeTierOptimizedVectorStore(
                supabase_url=supabase_url, supabase_key=supabase_key
            )
            return self._vs
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"[AutoRAG] Vector store init failed (degraded): {exc}")
            return None

    async def _get_query_embedding(self, text: str) -> list[float] | None:
        """Embed via the local-first pipeline off the event loop (never raises)."""
        try:
            from core.embeddings import embed_for_pgvector

            return await asyncio.to_thread(embed_for_pgvector, text)
        except Exception as exc:
            logger.debug(f"[AutoRAG] Embedding failed (degraded): {exc}")
            return None

    # ── public API ──────────────────────────────────────────────────────
    async def enrich_system_prompt(
        self,
        system_prompt: str,
        user_query: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """Recall past memories similar to ``user_query`` and prepend them.

        Failure policy: ANY error → return the original prompt untouched
        (silent graceful degradation — memory is an enhancement, never a
        dependency).
        """
        if not user_query or not user_query.strip():
            return system_prompt

        # Issue #1689 (CRITICAL): tenant-less recall এখন অসম্ভব —
        # vector_store.similarity_search-এ user_id REQUIRED। user_id ছাড়া
        # ইনজেকশন করলে অন্য ইউজারের প্রাইভেট মেমরি প্রম্পটে ফাঁস হতো।
        # Memory is an enhancement, never a dependency → এখানে স্কিপ করে
        # graceful degradation করা হয় (fail-closed অর্থে কোনো recall নয়)।
        if not user_id or not str(user_id).strip():
            logger.warning(
                "[AutoRAG] Skipping memory recall: no user_id provided "
                "(tenant isolation mandatory — issue #1689)"
            )
            return system_prompt

        try:
            vector_store = self._get_vector_store()
            if vector_store is None:
                return system_prompt

            embedding = await self._get_query_embedding(user_query)
            if not embedding:
                return system_prompt

            async with self._vs_lock:
                memories = await vector_store.similarity_search(
                    query_embedding=embedding,
                    user_id=str(user_id),
                    limit=self.TOP_K,
                )

            # বাংলা: low-relevance noise বাদ + tenant isolation।
            memories = [
                m for m in memories if float(m.get("score") or 0) >= self.MIN_RELEVANCE_SCORE
            ]
            if not memories:
                return system_prompt

            memory_block = self.MEMORY_PREFIX
            for i, mem in enumerate(memories, 1):
                content = str(mem.get("content", ""))[: self.MAX_CHARS_PER_MEMORY]
                score = float(mem.get("score") or 0)
                memory_block += f"{i}. [{score:.2f}] {content}\n"
            memory_block += self.MEMORY_SUFFIX

            logger.info(
                f"[AutoRAG] Injected {len(memories)} memories for user={user_id} "
                f"(session={session_id or 'n/a'})"
            )
            return memory_block + (system_prompt or "")

        except Exception as exc:
            logger.warning(f"[AutoRAG] Graceful degradation: {exc}")
            return system_prompt

    async def store_session_memory(
        self,
        content: str,
        user_id: str | None = None,
        session_id: str | None = None,
        importance: float = 0.7,
    ) -> bool:
        """Persist an important exchange into pgvector for future recall.

        importance < MIN_IMPORTANCE_TO_STORE হলে skip (low-value noise avoid)।
        Never raises — returns False on any failure.
        """
        if not content or not content.strip():
            return False
        if importance < self.MIN_IMPORTANCE_TO_STORE:
            return False

        try:
            vector_store = self._get_vector_store()
            if vector_store is None:
                return False

            embedding = await self._get_query_embedding(content)
            if not embedding:
                return False

            user_key = user_id or "anonymous"
            session_key = session_id or "default"
            # বাংলা: deterministic id — একই content দ্বিতীয়বার store হলে upsert।
            digest = hashlib.sha256(f"{user_key}:{content}".encode()).hexdigest()[:24]
            memory_id = f"{user_key}:{session_key}:{digest}"

            payload = {
                "content": content,
                "user_id": user_key,
                "session_id": session_key,
                "importance": importance,
            }
            async with self._vs_lock:
                ok = await vector_store.upsert_batch(
                    embeddings=[embedding],
                    payloads=[payload],
                    ids=[memory_id],
                )
            if ok:
                logger.info(
                    f"[AutoRAG] Stored session memory user={user_key} "
                    f"session={session_key} importance={importance:.2f}"
                )
            return bool(ok)

        except Exception as exc:
            logger.debug(f"[AutoRAG] Store failed (non-fatal): {exc}")
            return False


# Module-level singleton (chat routes import this directly).
auto_rag_injector = AutoRAGInjector()
