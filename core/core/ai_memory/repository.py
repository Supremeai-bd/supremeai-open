# backend/core/ai_memory/repository.py
# SupremeAI 2.0 — Canonical Memory Repository
# ==============================================================================
# বাংলা মন্তব্য: এটি সুপ্রিমএআই-এর মেমোরির একক ক্যানোনিকাল রিপোজিটরি (MemoryRepository)।
# বিভিন্ন ডুপ্লিকেট রাইটার এবং RPC চিড়িয়াখানা ('RPC Zoo') দূর করে Supabase pgvector
# `ai_memory` টেবিল (vector(384)) এবং কনসিস্টেন্ট কোসাইন ডিসট্যান্স কুয়েরি নিশ্চিত করে।

from __future__ import annotations

import asyncio
import math
import uuid
from datetime import UTC, datetime
from typing import Any

from core.embeddings import hash_vectorize
from core.logging_config import logger

EMBEDDING_DIM = 384


def _coerce_uuid(raw: str | None) -> str:
    """Ensure a deterministic valid UUID string."""
    if not raw:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(str(raw)))
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, str(raw)))


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if not vec_a or not vec_b:
        return 0.0
    dim = min(len(vec_a), len(vec_b))
    dot = sum(vec_a[i] * vec_b[i] for i in range(dim))
    norm_a = math.sqrt(sum(vec_a[i] ** 2 for i in range(dim)))
    norm_b = math.sqrt(sum(vec_b[i] ** 2 for i in range(dim)))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class MemoryRepository:
    """
    বাংলা মন্তব্য: সুপ্রিমএআই-এর একক ইউনিফাইড মেমরি রিপোজিটরি।
    - Supabase Postgres `ai_memory` টেবিল-এ pgvector (384-dim) রাইট/রিড পরিচালনা করে।
    - ডাটাবেজ বিচ্ছিন্ন থাকলে ইন-মেমোরি সেফ ফলব্যাকে চলে।
    """

    TABLE_NAME = "ai_memory"

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._in_memory_store: dict[str, dict[str, Any]] = {}

    def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        try:
            from core.config import settings

            if not getattr(settings, "supabase_url", None) or not getattr(
                settings, "supabase_service_role_key", None
            ):
                return None
            from database.supabase_client import db

            if db:
                return db.service_client or db.client
        except Exception as exc:
            logger.debug(f"[MemoryRepository] Supabase client init fallback: {exc}")
        return None

    async def save(
        self,
        session_id: str,
        content: str,
        summary: str = "",
        embedding: list[float] | None = None,
        user_id: str | None = None,
        agent_type: str = "main",
        task_type: str = "general",
        metadata: dict[str, Any] | None = None,
        memory_id: str | None = None,
    ) -> dict[str, Any]:
        """
        বাংলা মন্তব্য: মেমোরি আইটেম সেভ করে। এম্বেডিং না থাকলে অটো hash_vectorize (384-dim) করে।
        """
        record_id = _coerce_uuid(memory_id)
        now_iso = datetime.now(UTC).isoformat()
        final_meta = dict(metadata or {})

        if embedding is None:
            embedding = hash_vectorize(content or summary, size=EMBEDDING_DIM)

        record: dict[str, Any] = {
            "id": record_id,
            "session_id": session_id or "default",
            "content": content or "",
            "summary": summary or content[:200] if content else "",
            "embedding": embedding,
            "user_id": user_id,
            "agent_type": agent_type,
            "task_type": task_type,
            "metadata": final_meta,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        client = self._get_client()
        if client:
            try:

                def _do_upsert() -> None:
                    client.table(self.TABLE_NAME).upsert(record, on_conflict="id").execute()

                await asyncio.to_thread(_do_upsert)
                return record
            except Exception as exc:
                logger.warning(
                    f"[MemoryRepository] Remote upsert failed, saving in local fallback: {exc}"
                )

        # Local fallback store
        self._in_memory_store[record_id] = record
        return record

    async def search_similar(
        self,
        query_embedding: list[float] | str,
        user_id: str | None = None,
        session_id: str | None = None,
        limit: int = 10,
        threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """
        বাংলা মন্তব্য: কোসাইন ডিসট্যান্স অনুযায়ী সাদৃশ্যপূর্ণ মেমরি খুঁজে বের করে।
        RPC zoo (match_ai_memory, match_memories ইত্যাদি) কনসোলিডেট করে।
        """
        if isinstance(query_embedding, str):
            query_embedding = hash_vectorize(query_embedding, size=EMBEDDING_DIM)

        client = self._get_client()
        if client:
            # 1. Try unified RPC call if configured on Supabase
            rpc_candidates = ["match_ai_memory", "match_memories", "match_learned_facts"]
            for rpc_name in rpc_candidates:
                try:
                    rpc_params: dict[str, Any] = {
                        "query_embedding": query_embedding,
                        "match_threshold": threshold,
                        "match_count": limit,
                    }
                    if user_id:
                        rpc_params["p_user_id"] = str(user_id)

                    def _run_rpc(name=rpc_name, params=rpc_params):
                        return client.rpc(name, params).execute()

                    resp = await asyncio.to_thread(_run_rpc)
                    if resp and hasattr(resp, "data") and isinstance(resp.data, list):
                        return resp.data
                except Exception as exc:
                    logger.debug("RPC %s query failed: %s", rpc_name, exc)
                    continue

            # 2. Direct table fetch fallback
            try:

                def _fetch_rows():
                    q = client.table(self.TABLE_NAME).select("*")
                    if user_id:
                        q = q.eq("user_id", str(user_id))
                    if session_id:
                        q = q.eq("session_id", str(session_id))
                    return q.limit(max(limit * 3, 50)).execute()

                resp = await asyncio.to_thread(_fetch_rows)
                rows = resp.data if resp and hasattr(resp, "data") else []
                if rows:
                    scored = []
                    for row in rows:
                        emb = row.get("embedding")
                        if isinstance(emb, list):
                            sim = _cosine_similarity(query_embedding, emb)
                            if sim >= threshold:
                                scored.append({**row, "similarity": round(sim, 4)})
                    scored.sort(key=lambda x: x.get("similarity", 0.0), reverse=True)
                    return scored[:limit]
            except Exception as exc:
                logger.debug(f"[MemoryRepository] Direct table search failed: {exc}")

        # Local in-memory search
        scored = []
        for record in self._in_memory_store.values():
            if user_id and record.get("user_id") != user_id:
                continue
            if session_id and record.get("session_id") != session_id:
                continue
            emb = record.get("embedding")
            if isinstance(emb, list):
                sim = _cosine_similarity(query_embedding, emb)
                if sim >= threshold:
                    scored.append({**record, "similarity": round(sim, 4)})
        scored.sort(key=lambda x: x.get("similarity", 0.0), reverse=True)
        return scored[:limit]

    async def get_by_id(self, memory_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        """Fetch memory record by ID.

        বাংলা (#3222): user_id দিলে শুধু সেই user-এর record return হবে —
        cross-user read বন্ধ (fail-closed: অন্য user-এর record হলে None)।
        """
        rec_id = _coerce_uuid(memory_id)
        client = self._get_client()
        if client:
            try:

                def _fetch():
                    q = client.table(self.TABLE_NAME).select("*").eq("id", rec_id)
                    # বাংলা (#3222): user_id filter — cross-user access block
                    if user_id:
                        q = q.eq("user_id", str(user_id))
                    return q.limit(1).execute()

                res = await asyncio.to_thread(_fetch)
                if res and res.data and len(res.data) > 0:
                    return res.data[0]
            except Exception as exc:
                logger.debug(f"[MemoryRepository] get_by_id fetch error: {exc}")
        # বাংলা (#3222): in-memory fallback-এও user_id check
        rec = self._in_memory_store.get(rec_id)
        if rec and user_id and rec.get("user_id") != user_id:
            return None  # fail-closed — cross-user access blocked
        return rec

    async def delete(self, memory_id: str, user_id: str | None = None) -> bool:
        """Delete memory record by ID."""
        rec_id = _coerce_uuid(memory_id)
        client = self._get_client()
        if client:
            try:

                def _do_delete():
                    q = client.table(self.TABLE_NAME).delete().eq("id", rec_id)
                    if user_id:
                        q = q.eq("user_id", str(user_id))
                    return q.execute()

                await asyncio.to_thread(_do_delete)
                self._in_memory_store.pop(rec_id, None)
                return True
            except Exception as exc:
                logger.warning(f"[MemoryRepository] delete error: {exc}")
        if rec_id in self._in_memory_store:
            self._in_memory_store.pop(rec_id, None)
            return True
        return False

    async def get_session_memories(
        self, session_id: str, limit: int = 50, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get all memories for a session ordered by creation.

        বাংলা (#3222): user_id দিলে শুধু সেই user-এর session memories return হবে —
        cross-user session-id enumeration এর মাধ্যমে read block।
        """
        client = self._get_client()
        if client:
            try:

                def _fetch_session():
                    q = client.table(self.TABLE_NAME).select("*").eq("session_id", str(session_id))
                    # বাংলা (#3222): user_id filter — cross-user block
                    if user_id:
                        q = q.eq("user_id", str(user_id))
                    return q.order("created_at", desc=False).limit(limit).execute()

                res = await asyncio.to_thread(_fetch_session)
                if res and res.data:
                    return res.data
            except Exception as exc:
                logger.debug(f"[MemoryRepository] get_session_memories error: {exc}")

        # বাংলা (#3222): in-memory fallback-এও user_id filter
        matched = [
            r
            for r in self._in_memory_store.values()
            if r.get("session_id") == session_id and (not user_id or r.get("user_id") == user_id)
        ]
        matched.sort(key=lambda x: x.get("created_at", ""))
        return matched[:limit]


_memory_repo_instance: MemoryRepository | None = None


def get_memory_repository(client: Any | None = None) -> MemoryRepository:
    """Singleton getter for the canonical MemoryRepository."""
    global _memory_repo_instance
    if _memory_repo_instance is None or client is not None:
        _memory_repo_instance = MemoryRepository(client=client)
    return _memory_repo_instance
