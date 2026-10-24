from __future__ import annotations

import asyncio
from typing import Any

from core.logging_config import logger

try:
    from brain.model_router import ModelRouter  # kept for other potential usages
    from database.supabase_client import db

    _DEPENDENCIES_AVAILABLE = True
except ImportError:
    _DEPENDENCIES_AVAILABLE = False


async def _run_embed(embed_fn, text: str) -> list[float]:
    """Run a synchronous embedding function in the default thread executor.

    embed_for_pgvector is a blocking I/O call (httpx.Client for CF Workers AI).
    Wrapping it via run_in_executor prevents it from blocking the event loop
    while still keeping the async interface clean.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, embed_fn, text)


class MemoryManager:
    """Manages the agent's long-term memory using a vector database.

    Issue #443 fix: the original implementation called
    ``self.model_router.get_embedding()`` which does not exist on ModelRouter
    (AttributeError at runtime).  Embedding is now handled by the canonical
    ``core.embeddings.embed_for_pgvector`` provider chain (local ST →
    Cloudflare Workers AI → improved hash fallback).
    """

    def __init__(self):
        if not _DEPENDENCIES_AVAILABLE:
            raise ImportError("MemoryManager requires Supabase client and ModelRouter.")
        self.db_client = db.client
        logger.info("Initialized MemoryManager.")

    async def add_memory(self, learning: str, url: str, metadata: dict[str, Any] | None = None):
        """Adds a new learning to the long-term memory."""
        from core.embeddings import embed_for_pgvector

        logger.info(f"Adding new memory: '{learning}' from {url}")
        try:
            embedding = await _run_embed(embed_for_pgvector, learning)
        except Exception as exc:
            logger.error("Failed to generate embedding for memory: %s", exc)
            return

        # Store in Supabase 'agent_memories' table.
        # Issue #443 fix: supabase-py v2's client is SYNC — ``await ...execute()``
        # raised TypeError (object APIResponse can't be used in 'await') on every
        # call, so browser-agent learnings were never persisted.  Run the
        # blocking PostgREST chain in a worker thread (same pattern as
        # services/memory_service.py save_memory).
        await asyncio.to_thread(
            lambda: (
                self.db_client.table("agent_memories")
                .insert(
                    {
                        "content": learning,
                        "embedding": embedding,
                        "source_url": url,
                        "metadata": metadata or {},
                    }
                )
                .execute()
            )
        )

    async def retrieve_relevant_memories(self, query: str, top_k: int = 3) -> list[str]:
        """Retrieves the most relevant memories for a given query."""
        from core.embeddings import embed_for_pgvector

        logger.info(f"Retrieving memories relevant to: '{query}'")
        try:
            query_embedding = await _run_embed(embed_for_pgvector, query)
        except Exception as exc:
            logger.error("Failed to generate embedding for memory retrieval: %s", exc)
            return []

        # Call a Supabase RPC function to perform vector similarity search
        # (issue #443 fix: sync client must not be awaited — use to_thread).
        # Issue #1689 (CRITICAL): p_user_id এখন RPC-তে mandatory — NULL/অনুপস্থিত
        # p_user_id আর tenant-বিহীন স্ক্যান নয়। এটি agent-নিজস্ব learning recall,
        # তাই agent-scope sentinel ব্যবহৃত হয়: DB-তে এই কল শুধু user_id IS NULL
        # (agent-own) rows পায় — কোনো ইউজারের প্রাইভেট মেমরি এখানে আসে না।
        result = await asyncio.to_thread(
            lambda: self.db_client.rpc(
                "match_memories",
                {
                    "query_embedding": query_embedding,
                    "match_threshold": 0.75,
                    "match_count": top_k,
                    "p_user_id": "__agent_internal__",
                },
            ).execute()
        )

        memories = [item["content"] for item in result.data] if result.data else []
        logger.info(f"Retrieved {len(memories)} relevant memories.")
        return memories


class LongTermMemory:
    def __init__(self, db_path: str = ":memory:", session_id: str = "default"):
        self.memory_manager = MemoryManager()
        self.session_id = session_id
        self._facts: list[dict[str, Any]] = []
        self._summaries: list[dict[str, Any]] = []

    def remember_fact(
        self,
        content: str,
        category: str = "general",
        importance: float = 0.5,
        source: str = "unknown",
    ) -> dict[str, Any]:
        """Store a simple fact in memory for later recall and context building."""
        fact = {
            "content": content,
            "category": category,
            "importance": importance,
            "source": source,
        }
        self._facts.append(fact)
        return fact

    def recall_facts(self, category: str | None = None) -> list[dict[str, Any]]:
        """Return stored facts, optionally filtered by category."""
        if category is None:
            return list(self._facts)
        return [fact for fact in self._facts if fact.get("category") == category]

    def save_summary(self, content: str, turn_count: int = 1) -> dict[str, Any]:
        """Store a summary entry used by context generation."""
        summary = {"content": content, "turn_count": turn_count}
        self._summaries.append(summary)
        return summary

    def build_context(self) -> str:
        """Build a simple human-readable context string from stored facts and summaries."""
        parts: list[str] = []
        if self._summaries:
            parts.append("Summary: " + "; ".join(item["content"] for item in self._summaries))
        if self._facts:
            parts.append("Facts: " + "; ".join(item["content"] for item in self._facts))
        return "\n".join(parts) if parts else "No memory available."

    def store_user_preference(self, user_id: str, key: str, value: Any) -> dict[str, Any]:
        """Store a personalized user preference in long-term memory."""
        pref_fact = f"User Preference [{user_id}] {key}: {value}"
        return self.remember_fact(
            content=pref_fact,
            category=f"user_pref_{user_id}",
            importance=0.9,
            source="user_setting",
        )

    def get_context_for_user(self, user_id: str) -> str:
        """Retrieve personalized facts and preferences for a specific user context."""
        user_facts = self.recall_facts(category=f"user_pref_{user_id}")
        general_facts = self.recall_facts(category="general")
        all_facts = user_facts + general_facts
        if not all_facts:
            return f"User context for {user_id}: Default settings."
        return f"User context for {user_id}:\n" + "\n".join(f"- {f['content']}" for f in all_facts)
