# SupremeAI 2.0 - Episodic Memory Engine
# বাংলা মন্তব্য: এটি ব্যবহারকারীর সমস্ত অতীত টাস্ক এক্সিকিউশন হিস্ট্রি ও সাফল্য/ব্যর্থতার অভিজ্ঞতা সংরক্ষণ ও ভেক্টর সার্চের জন্য ব্যবহৃত হয়।
# বাংলা (Persistence root-cause fix, live evidence 2026-10-30, Job 486718):
# আগে store_episode() শুধু প্রসেস-লোকাল self._episodes তালিকায় লিখত — প্রসেস
# বন্ধ হলেই রেকর্ড বাষ্প হয়ে যেত, অথচ CLI সফল-বার্তা দেখাত (false-success)।
# ফলে "Collective Agent Memory" আসলে কোনো collective memory-ই ছিল না:
# record/gap করা প্রতিটি এজেন্টের জ্ঞান পরের এজেন্ট কখনো খুঁজে পেত না
# (search_database_memory সবসময় খালি ফেরত দিত)। এখন store_episode()
# best-effort ভেক্টর-স্টোর পারসিসটেন্সে লেখে এবং recall_episodes() কোয়েরি-মোডে
# পারসিসটেন্ট স্তর থেকেও ফেরত পড়ে — প্রসেস-রিস্টার্ট পেরোনো recall সম্ভব হল।

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
            # additive provenance: caller-supplied metadata (e.g. task_id) stays
            # visible on the in-memory episode and rides along to persistence.
            "metadata": dict(kwargs.get("metadata") or {}),
        }
        self._episodes.append(episode)
        if kwargs.get("_persist", True):
            try:
                episode["doc_id"] = self._persist_episode(episode)
            except Exception as err:  # noqa: BLE001 — persistence must never break the write contract
                logger.warning(
                    "EpisodicMemory: vector persistence skipped (%s); episode kept in session memory only",
                    type(err).__name__,
                )
        return episode

    def _persist_episode(self, episode: dict[str, Any]) -> str:
        """Persist one episode to the underlying vector store (best-effort).

        Returns the deterministic doc_id. Task-backed records upsert under
        ``episode_<task_id>`` so re-recording the same task is idempotent;
        session-only records get a timestamp+content-hash id.
        """
        extra = episode.get("metadata") or {}
        task_id = str(extra.get("task_id") or "").strip()
        if task_id:
            doc_id = f"episode_{task_id}"
        else:
            context_key = str(episode.get("context", ""))[:200]
            doc_id = f"episode_{int(time.time() * 1000)}_{abs(hash(context_key)) % 10_000_000}"
        metadata: dict[str, Any] = {
            "event_type": str(episode.get("event_type", "general")),
            "outcome": str(episode.get("outcome", ""))[:2000],
            "importance": float(episode.get("importance", 0.0)),
            "success": "true" if episode.get("success") else "false",
            "latency_ms": float(episode.get("latency_ms", 0.0) or 0.0),
            "timestamp": float(episode.get("timestamp", time.time()) or 0.0),
            "category": "episodic_memory",
            "tags": ",".join(str(t) for t in (episode.get("tags") or [])),
        }
        for key, value in extra.items():
            metadata[str(key)] = value if isinstance(value, (str, int, float, bool)) else str(value)
        self.vector_store.add_document(
            doc_id=doc_id, text=str(episode.get("context", "")), metadata=metadata
        )
        return doc_id

    def _recall_persisted(
        self,
        query: str,
        target_event: str | None,
        min_importance: float | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Cross-process recall: map vector-store docs back to episode dicts."""
        try:
            results = self.vector_store.query(query_text=query, n_results=max(limit * 3, 20))
        except Exception as err:  # noqa: BLE001 — recall degradation, never a crash
            logger.warning(
                "EpisodicMemory: persisted recall unavailable (%s); serving session memory only",
                type(err).__name__,
            )
            return []
        out: list[dict[str, Any]] = []
        for doc_id, score, doc_data in results:
            meta = doc_data.get("metadata") or {}
            event_type_v = str(meta.get("event_type", "general"))
            if target_event and event_type_v != target_event:
                continue
            try:
                importance_v = float(meta.get("importance", 0.0) or 0.0)
            except (TypeError, ValueError):
                importance_v = 0.0
            if min_importance is not None and importance_v < min_importance:
                continue
            text = str(doc_data.get("text", ""))
            outcome_v = str(meta.get("outcome", ""))
            out.append(
                {
                    "episode_id": doc_id,
                    "id": doc_id,
                    "event_type": event_type_v,
                    "task_type": event_type_v,
                    "context": text,
                    "input_data": text,
                    "outcome": outcome_v,
                    "output_data": outcome_v,
                    "importance": importance_v,
                    "success": str(meta.get("success", "true")).lower() == "true",
                    "latency_ms": float(meta.get("latency_ms", 0.0) or 0.0),
                    "tags": [t for t in str(meta.get("tags", "")).split(",") if t],
                    "task_id": str(meta.get("task_id", "") or doc_id),
                    "metadata": dict(meta),
                    "timestamp": float(meta.get("timestamp", 0.0) or 0.0),
                    "similarity_score": float(score),
                    "source": "vector_store",
                }
            )
        return out

    def recall_episodes(
        self,
        event_type: str | None = None,
        task_type: str | None = None,
        min_importance: float | None = None,
        limit: int = 10,
        query: str | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        target_event = event_type or task_type
        episodes = list(self._episodes)
        if query:
            # Cross-process recall: merge persisted vector-store hits (relevance
            # ordered) after the session-local list, deduped on task_id when
            # both sides describe the same task, else on episode/doc id.
            episodes.extend(self._recall_persisted(query, target_event, min_importance, limit))
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for ep in episodes:
            key = str((ep.get("metadata") or {}).get("task_id") or "").strip() or str(ep.get("episode_id") or "")
            if key:
                if key in seen:
                    continue
                seen.add(key)
            deduped.append(ep)
        episodes = deduped
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
            # _persist=False: this path already persisted the rich
            # "Prompt:/Response:" doc above (doc_id=episode_<task_id>); letting
            # store_episode persist again would upsert-collide on the same
            # doc_id and change the stored text shape for get_similar_past_tasks
            # consumers. In-memory episode list behavior is unchanged.
            self.store_episode(
                event_type="task.completed",
                context=prompt,
                outcome=response,
                importance=5.0,
                _persist=False,
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
