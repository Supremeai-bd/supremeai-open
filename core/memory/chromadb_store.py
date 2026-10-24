from __future__ import annotations

import json
import math
import os
import uuid
from typing import Any

from core.logging_config import logger
from core.utils.lazy_loader import lazy_import

try:
    # বাংলা মন্তব্য: রেন্ডার ফ্রি টায়ারে মেমোরি সংকট এড়াতে LOW_MEMORY_MODE চেক করা হচ্ছে
    if os.getenv("LOW_MEMORY_MODE", "false").lower() == "true":
        raise ImportError("Low memory mode enabled. Skipping ChromaDB.")
    chromadb = lazy_import("chromadb", package_hint="ml")

    _CHROMA_AVAILABLE = True
except Exception:
    _CHROMA_AVAILABLE = False


class ChromaDBStore:
    """
    ChromaDB-backed vector store with local TF-IDF fallback.
    Provides add_document, add_documents, query, update, delete, and count APIs.
    """

    def __init__(self, db_path: str | None = None, collection_name: str = "supremeai_knowledge"):
        if db_path is None:
            # FIX: Allow configuring persistent storage via environment variable (vital for Docker/Cloud persistence)
            db_path = os.getenv("CHROMA_PERSIST_DIR")
            if not db_path:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                db_path = os.path.join(base_dir, "data", "chromadb_store")
        self.db_path = db_path
        self.collection_name = collection_name
        self._fallback_docs: dict[str, dict[str, Any]] = {}
        self._client = None
        self._collection = None
        self._init_chroma()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def _init_chroma(self) -> None:
        if not _CHROMA_AVAILABLE:
            self._load_fallback()
            return
        try:
            os.makedirs(self.db_path, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self.db_path)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as e:
            logger.warning(f"Failed to initialize ChromaDB client: {e}")
            self._client = None
            self._collection = None
            self._load_fallback()

    def _load_fallback(self) -> None:
        path = os.path.join(self.db_path, "fallback_docs.json")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self._fallback_docs = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load fallback docs: {e}")
                self._fallback_docs = {}

    def _save_fallback(self) -> None:
        if self.db_path == ":memory:":
            return
        os.makedirs(self.db_path, exist_ok=True)
        path = os.path.join(self.db_path, "fallback_docs.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._fallback_docs, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Tokenization / Similarity (fallback mode)
    # ------------------------------------------------------------------
    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [w.strip(".,!?;:()\"'").lower() for w in text.split() if w.strip()]

    @staticmethod
    def _get_vector(text: str) -> dict[str, int]:
        tokens = ChromaDBStore._tokenize(text)
        vector: dict[str, int] = {}
        for token in tokens:
            vector[token] = vector.get(token, 0) + 1
        return vector

    @staticmethod
    def _cosine_similarity(vec1: dict[str, int], vec2: dict[str, int]) -> float:
        intersection = set(vec1.keys()) & set(vec2.keys())
        numerator = sum(vec1[x] * vec2[x] for x in intersection)
        sum1 = sum(v**2 for v in vec1.values())
        sum2 = sum(v**2 for v in vec2.values())
        denominator = math.sqrt(sum1) * math.sqrt(sum2)
        return float(numerator) / denominator if denominator else 0.0

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def add_document(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        self.add_documents([{"id": doc_id, "text": text, "metadata": metadata or {}}])

    def add_documents(self, documents: list[dict[str, Any]]) -> None:
        if self._collection is not None:
            ids = []
            texts = []
            metadatas = []
            for doc in documents:
                doc_id = doc.get("id") or str(uuid.uuid4())
                text = doc.get("text") or doc.get("content") or ""
                metadata = doc.get("metadata") or {}
                metadata.setdefault("doc_id", doc_id)
                ids.append(doc_id)
                texts.append(text)
                metadatas.append(metadata)
            try:
                self._collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
                return
            except Exception as e:
                logger.warning(f"ChromaDB upsert failed, falling back to local storage: {e}")
        for doc in documents:
            doc_id = doc.get("id") or str(uuid.uuid4())
            text = doc.get("text") or doc.get("content") or ""
            metadata = doc.get("metadata") or {}
            self._fallback_docs[doc_id] = {
                "text": text,
                "metadata": metadata,
                "vector": self._get_vector(text),
            }
        self._save_fallback()

    def add_document_incremental(
        self, doc_id: str, text: str, metadata: dict[str, Any] | None = None
    ) -> bool:
        """Add or update document only if content hash changed (Bangla: ইনক্রিমেন্টাল ইনডেক্সিং).

        Returns:
            bool: True if indexed/updated, False if skipped due to identical hash.
        """
        import hashlib

        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        meta = metadata or {}
        meta["content_hash"] = content_hash

        # Check existing hash in fallback or metadata
        if self._collection is not None:
            try:
                existing = self._collection.get(ids=[doc_id], include=["metadatas"])
                if existing and existing.get("metadatas") and len(existing["metadatas"]) > 0:
                    old_hash = existing["metadatas"][0].get("content_hash")
                    if old_hash == content_hash:
                        logger.debug(f"Skipping indexing for unchanged document {doc_id}")
                        return False
            except Exception as e:
                logger.debug(f"Failed to check existing hash in chromadb: {e}")

        elif doc_id in self._fallback_docs:
            old_hash = self._fallback_docs[doc_id].get("metadata", {}).get("content_hash")
            if old_hash == content_hash:
                return False

        self.add_document(doc_id=doc_id, text=text, metadata=meta)
        return True

    def query(
        self, query_text: str, n_results: int = 5, where: dict[str, Any] | None = None
    ) -> list[tuple[str, float, dict[str, Any]]]:
        if self._collection is not None:
            try:
                results = self._collection.query(query_texts=[query_text], n_results=n_results)
                matches: list[tuple[str, float, dict[str, Any]]] = []
                if results and results.get("ids") and results["ids"][0]:
                    for idx, doc_id in enumerate(results["ids"][0]):
                        distance = results["distances"][0][idx] if results.get("distances") else 0.0
                        score = float(1.0 - distance)
                        meta = results["metadatas"][0][idx] if results.get("metadatas") else {}
                        doc_text = results["documents"][0][idx] if results.get("documents") else ""
                        matches.append((doc_id, score, {"text": doc_text, "metadata": meta}))
                    return matches
            except Exception as e:
                logger.warning(f"ChromaDB query failed, falling back to TF-IDF: {e}")
        query_vector = self._get_vector(query_text)
        scored = []
        for doc_id, doc_data in self._fallback_docs.items():
            score = self._cosine_similarity(query_vector, doc_data["vector"])
            scored.append((doc_id, score, doc_data))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:n_results]

    def delete(self, doc_id: str) -> None:
        if self._collection is not None:
            try:
                self._collection.delete(ids=[doc_id])
                return
            except Exception as e:
                logger.warning(f"ChromaDB delete failed, falling back to local: {e}")
        self._fallback_docs.pop(doc_id, None)
        self._save_fallback()

    def count(self) -> int:
        if self._collection is not None:
            try:
                return self._collection.count()
            except Exception as e:
                logger.warning(f"ChromaDB count failed: {e}")
                return -1  # -1 indicates failure, 0 means empty - distinct states
        return len(self._fallback_docs)

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        if self._collection is not None:
            try:
                result = self._collection.get(ids=[doc_id])
                if result and result.get("documents"):
                    return {
                        "id": doc_id,
                        "text": result["documents"][0],
                        "metadata": (result["metadatas"][0] if result.get("metadatas") else {}),
                    }
            except Exception as e:
                logger.warning(f"ChromaDB get_document failed for {doc_id}: {e}")
        return self._fallback_docs.get(doc_id)
