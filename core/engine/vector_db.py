"""engine/vector_db.py — Free-tier vector memory adapter.

বাংলা মন্তব্য: এই ফাইলটি আর Pinecone-এর উপর নির্ভর করে না।
এটি core/services.py-তে থাকা shared `experience_db` singleton-এর একটি adapter,
যে একই instance crew_departments.py, auto_skill_creator.py এবং task.py ব্যবহার করে।
ফলে সমস্ত agent এখন সত্যিকারের একটিই memory pool শেয়ার করে।
Pinecone-shaped interface (save_experience, find_similar_experiences) অক্ষত রাখা হয়েছে
যাতে কোনো caller ভাঙে না।
"""

from __future__ import annotations

from typing import Any

from core.logging_config import logger


class VectorDatabaseClient:
    """
    Free-tier vector memory adapter backed by the shared ExperienceDatabase singleton.
    Previously used Pinecone (paid). Now delegates to the shared ChromaDB/Qdrant/SQLite
    free backend that is already initialised in core/services.py.
    """

    def __init__(self) -> None:
        self.degraded: bool = False
        logger.debug(
            "VectorDatabaseClient initialised (free-tier adapter, delegating to CascadeMemoryService)"
        )

    async def save_experience(self, vector: list[float], metadata: dict[str, Any]) -> None:
        """
        Saves an experience into the shared memory pool using CascadeMemoryService.
        """
        try:
            from services.memory_service import memory_service

            request_text = metadata.get("request", metadata.get("patch_id", ""))

            # Pack detailed experience into metadata
            stored_metadata = {
                "action_taken": metadata.get("solution", metadata.get("action", "")),
                "result": metadata.get("result", "success"),
                "generated_code": metadata.get("generated_code"),
                "what_worked": metadata.get("what_worked", []),
                "what_failed": metadata.get("what_failed", []),
                # Include the original metadata
                "original": metadata,
            }

            memory_service.store_memory(
                file_path=metadata.get("patch_id", "vector_db_legacy"),
                content="",
                summary=request_text,
                structure="",
                session_id=metadata.get("session_id", "vector_db_legacy"),
                agent_type="legacy_experience",
                task_type="legacy_experience",
                metadata=stored_metadata,
            )
            logger.debug(
                f"🧠 Saved neural memory experience via CascadeMemoryService: {metadata.get('patch_id', 'n/a')}"
            )
        except Exception as exc:
            self.degraded = True
            logger.error(f"save_experience() failed (experience NOT persisted, DEGRADED): {exc!r}")

    async def find_similar_experiences(
        self, vector: list[float], top_k: int = 3
    ) -> list[dict[str, Any]]:
        """
        Retrieves past experiences from the CascadeMemoryService.
        """
        # Issue #443 fix: the old code silently degraded any non-str payload
        # (e.g. the documented list[float] vectors) to "" and returned [] at
        # DEBUG level — a lying contract.  Be loud about the mismatch instead.
        if isinstance(vector, list):
            logger.warning(
                "find_similar_experiences() received a %d-dim vector payload; this "
                "method only supports text queries (issue #443) — returning empty "
                "LOUDLY instead of the old silent [].",
                len(vector),
            )
            return []

        query_text = vector.strip() if isinstance(vector, str) else ""

        if not query_text:
            logger.warning(
                "find_similar_experiences(): empty/blank query text — returning "
                "empty (issue #443: was silent DEBUG-level before)."
            )
            return []

        try:
            from services.memory_service import memory_service

            # BUGFIX: query_context-এর সঠিক সিগনেচার (prompt, top_k, session_id,
            # user_id) — আগে query=/limit=/threshold= kwargs দেওয়া হচ্ছিল, যা
            # প্রতিবার TypeError করত এবং except ব্লক তা চুপচাপ গিলে ফেলত
            # (ফলাফল সবসময় খালি)।
            hits = memory_service.query_context(prompt=query_text, top_k=top_k)

            # Transform Cascade format back to Pinecone-shaped format
            return [
                {
                    "id": h.get("session_id") or h.get("id"),
                    "score": h.get("score", 0.0),
                    "metadata": h.get("metadata", {}).get("original", h.get("metadata", {})),
                    "solution": h.get("metadata", {}).get("action_taken", ""),
                }
                for h in hits
            ]
        except Exception as exc:
            self.degraded = True
            logger.error(
                f"find_similar_experiences() failed (returning empty, DEGRADED state): {exc!r}"
            )
            return []


# Global instance — lazy singleton
vector_db = VectorDatabaseClient()
