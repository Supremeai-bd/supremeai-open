# SupremeAI 2.0 - Episodic Memory Engine
# বাংলা মন্তব্য: এটি ব্যবহারকারীর সমস্ত অতীত টাস্ক এক্সিকিউশন হিস্ট্রি ও সাফল্য/ব্যর্থতার অভিজ্ঞতা সংরক্ষণ ও ভেক্টর সার্চের জন্য ব্যবহৃত হয়।

from __future__ import annotations

import time
from typing import Any

from core.logging_config import logger
from memory.chromadb_store import ChromaDBStore


class EpisodicMemory:
    """
    Episodic Memory Engine for SupremeAI 2.0.
    Stores task execution records, inputs, responses, latency, and success metrics.
    Supports similarity search to retrieve relevant past solutions.
    """

    def __init__(
        self,
        vector_store: ChromaDBStore | None = None,
        db_path: str | None = None,
        session_id: str | None = None,
        **kwargs,
    ):
        self.session_id = session_id or "default"
        self.vector_store = vector_store or ChromaDBStore(
            collection_name="supremeai_episodic_memory", db_path=db_path or ":memory:"
        )
        self._episodes: list[dict[str, Any]] = []
        self._memory_conn = None

    def store_episode(
        self,
        event_type: str = "general",
        context: Any = "",
        outcome: Any = "success",
        importance: float = 1.0,
        task_type: str | None = None,
        input_data: Any = None,
        output_data: Any = None,
        success: bool = True,
        latency_ms: float = 0.0,
        tags: list[str] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        actual_event = event_type if event_type != "general" or not task_type else task_type
        actual_context = context if context != "" or input_data is None else input_data
        actual_outcome = outcome if outcome != "success" or output_data is None else output_data

        ep_id = f"ep_{len(self._episodes) + 1}"
        episode = {
            "status": "ok",
            "episode_id": ep_id,
            "id": ep_id,
            "event_type": actual_event,
            "task_type": actual_event,
            "context": actual_context,
            "input_data": actual_context,
            "outcome": actual_outcome,
            "output_data": actual_outcome,
            "importance": float(importance),
            "success": success,
            "latency_ms": latency_ms,
            "tags": tags or [],
            "timestamp": time.time(),
        }
        self._episodes.append(episode)
        return episode

    def recall_episodes(
        self,
        event_type: str | None = None,
        task_type: str | None = None,
        min_importance: float | None = None,
        limit: int = 10,
        **kwargs,
    ) -> list[dict[str, Any]]:
        target_event = event_type or task_type
        episodes = self._episodes
        if target_event:
            episodes = [e for e in episodes if e.get("event_type") == target_event]
        if min_importance is not None:
            episodes = [e for e in episodes if e.get("importance", 0.0) >= min_importance]
        return episodes[:limit]

    def summarize_recent(self, limit: int = 5, **kwargs) -> str:
        recent = self.recall_episodes(limit=limit)
        if not recent:
            return ""
        lines = ["Recent episodes:"]
        for ep in recent:
            lines.append(f"- [{ep.get('event_type')}] {ep.get('context')} -> {ep.get('outcome')}")
        return "\n".join(lines)

    async def record_task(
        self,
        task_id: str,
        prompt: str,
        response: str,
        success: bool = True,
        latency_ms: float = 0.0,
        model_used: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Record a task execution event into episodic memory.
        """
        try:
            meta = {
                "task_id": task_id,
                "success": str(success).lower(),
                "latency_ms": float(latency_ms),
                "model_used": model_used,
                "timestamp": time.time(),
                "category": "episodic_memory",
            }
            if metadata:
                meta.update(metadata)

            content_text = f"Prompt: {prompt}\nResponse: {response}"
            self.vector_store.add_document(
                doc_id=f"episode_{task_id}", text=content_text, metadata=meta
            )
            self.store_episode(
                event_type="task.completed", context=prompt, outcome=response, importance=5.0
            )
            logger.info(f"Recorded episodic memory for task: {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to record episodic memory: {e}")
            return False

    async def get_similar_past_tasks(self, query: str, n: int = 3) -> list[dict[str, Any]]:
        """
        Retrieve top-N similar past task execution records for cognitive reflection.
        """
        try:
            results = self.vector_store.query(query_text=query, n_results=n)
            past_tasks = []
            for doc_id, score, doc_data in results:
                past_tasks.append(
                    {
                        "doc_id": doc_id,
                        "similarity_score": score,
                        "content": doc_data.get("text", ""),
                        "metadata": doc_data.get("metadata", {}),
                    }
                )
            return past_tasks
        except Exception as e:
            logger.error(f"Failed to query episodic memory: {e}")
            return []
