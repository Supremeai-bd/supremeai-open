from typing import Any

from core.llm.llm_gateway import GatewayManager
from core.logging_config import logger

from .chromadb_store import ChromaDBStore


class RAGPipeline:
    """Retrieval-Augmented Generation Pipeline."""

    def __init__(self, vector_store: ChromaDBStore = None):
        self.vector_store = vector_store or ChromaDBStore()

    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
        words = text.split()
        chunks = []
        i = 0
        while i < len(words):
            chunk = " ".join(words[i : i + chunk_size])
            chunks.append(chunk)
            i += chunk_size - overlap
            if i + chunk_size >= len(words) and i < len(words):
                chunks.append(" ".join(words[i:]))
                break
        return chunks

    def ingest_document(self, doc_id: str, content: str, metadata: dict[str, Any] | None = None):
        if metadata is None:
            metadata = {}
        chunks = self.chunk_text(content)
        for idx, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{idx}"
            chunk_meta = {**metadata, "chunk_index": idx, "document_id": doc_id}
            self.vector_store.add_document(chunk_id, chunk, chunk_meta)

    def retrieve_context(self, query: str, limit: int = 3) -> str:
        results = self.vector_store.query(query, n_results=limit)
        context_parts = []
        for _doc_id, score, doc_data in results:
            if score > 0.05:  # threshold
                context_parts.append(doc_data["text"])
        return "\n---\n".join(context_parts)

    async def retrieve_context_hyde(self, query: str, limit: int = 3) -> str:
        """
        বাংলা মন্তব্য: LlamaIndex এর HyDE (Hypothetical Document Embeddings) প্যাটার্ন।
        LLM দিয়ে প্রথমে একটি কাল্পনিক উত্তর তৈরি করে, তারপর সেই উত্তরটি দিয়ে ভেক্টর সার্চ করে
        যাতে অনেক বেশি সঠিক কনটেক্সট খুঁজে পাওয়া যায়।
        """
        gateway = GatewayManager()
        try:
            # Generate hypothetical answer
            hypo_response = await gateway.acompletion(
                prompt=f"Write a short, hypothetical but factual answer to this query to help find relevant documents: '{query}'",
                model="gemini/gemini-2.5-flash",
            )
            hypothetical_answer = hypo_response.get("text", query)
            logger.debug(
                f"HyDE generated hypothetical answer for search: {hypothetical_answer[:50]}..."
            )

            # Search using the hypothetical answer
            results = self.vector_store.query(hypothetical_answer, n_results=limit)
            context_parts = []
            for _doc_id, score, doc_data in results:
                if score > 0.05:
                    context_parts.append(doc_data["text"])
            return "\n---\n".join(context_parts)
        except Exception as e:
            logger.error(f"HyDE retrieval failed, falling back to standard retrieval: {e}")
            return self.retrieve_context(query, limit)
