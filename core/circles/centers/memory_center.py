"""Memory Circle Center — retrieval, storage.

Owns (per FCC plan): retrieval, storage, promotion, forgetting.
Domain adapter: ``memory.rag_pipeline.RAGPipeline`` (lazy import; runs in a
worker thread because the ChromaDB store is blocking).
"""

from __future__ import annotations

import asyncio

from core.circles.centers.base import CircleCenter, ExecutionEnvelope, LocalCapability
from core.circles.contracts import CircleName, RiskLevel


class MemoryCenter(CircleCenter):
    circle = CircleName.MEMORY
    display_name = "Memory and knowledge"
    owner = "backend/memory"

    def __init__(self) -> None:
        super().__init__()
        self.register(
            LocalCapability(
                name="memory.recall",
                description="Retrieve context from the vector store",
                risk_level=RiskLevel.LOW,
                timeout_ms=15_000,
                cache_ttl_ms=15_000,
            ),
            self._recall,
        )
        self.register(
            LocalCapability(
                name="memory.store",
                description="Ingest a document into the vector store",
                risk_level=RiskLevel.LOW,
                timeout_ms=30_000,
            ),
            self._store,
        )

    def local_permission(self, envelope: ExecutionEnvelope) -> str | None:
        if (
            envelope.capability == "memory.recall"
            and not str(envelope.payload.get("query", "")).strip()
        ):
            return "query is required for memory.recall"
        if (
            envelope.capability == "memory.store"
            and not str(envelope.payload.get("content", "")).strip()
        ):
            return "content is required for memory.store"
        return None

    def resolve_adapter(self, envelope: ExecutionEnvelope):  # noqa: ANN201
        from memory.rag_pipeline import RAGPipeline  # local adapter selection

        return RAGPipeline()

    async def _recall(self, request) -> dict:
        pipeline = self.resolve_adapter(request)
        limit = int(request.payload.get("limit", 3))
        context = await asyncio.to_thread(
            pipeline.retrieve_context, str(request.payload.get("query", "")), limit
        )
        return {"query": request.payload.get("query", ""), "context": context, "limit": limit}

    async def _store(self, request) -> dict:
        pipeline = self.resolve_adapter(request)
        doc_id = str(request.payload.get("doc_id") or f"doc_{request.context.execution_id}")
        await asyncio.to_thread(
            pipeline.ingest_document,
            doc_id,
            str(request.payload.get("content", "")),
            dict(request.payload.get("metadata", {})) or None,
        )
        return {"doc_id": doc_id, "stored": True}


__all__ = ["MemoryCenter"]
