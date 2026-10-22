"""SupremeAI Gateway — lightweight in-memory semantic memory sidecar (P4).

Backend-neutral store/search used by /v1/memory/* endpoints. Designed as a
swap-in seam for Qdrant/Chroma: replace MemoryStore with a vector-backed
implementation without changing the HTTP contract. Scoring is honest
(keyword-overlap, no fabricated embeddings) — production should inject a
real embedding model via the store's score() hook.
"""

from __future__ import annotations

import logging
import re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)



@dataclass
class MemoryItem:
    id: str
    namespace: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created: float = field(default_factory=time.time)


class MemoryStore:
    def __init__(self) -> None:
        self._items: list[MemoryItem] = []

    def store(
        self,
        *,
        text: str,
        namespace: str = "default",
        item_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        iid = item_id or ("mem-" + uuid.uuid4().hex[:12])
        # upsert by id
        self._items = [
            x for x in self._items if not (x.id == iid and x.namespace == namespace)
        ]
        item = MemoryItem(
            id=iid, namespace=namespace, text=text, metadata=metadata or {}
        )
        self._items.append(item)
        return item

    def _score(self, query: str, text: str) -> float:
        q_tokens = set(re.findall(r"\w+", query.lower()))
        t_tokens = set(re.findall(r"\w+", text.lower()))
        if not q_tokens or not t_tokens:
            return 0.0
        inter = len(q_tokens & t_tokens)
        union = len(q_tokens | t_tokens)
        return inter / union if union else 0.0

    def search(
        self,
        *,
        query: str,
        top_k: int = 5,
        namespace: str | None = None,
        threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        cands = self._items
        if namespace:
            cands = [x for x in cands if x.namespace == namespace]
        scored = []
        for x in cands:
            s = self._score(query, x.text)
            if s >= threshold:
                scored.append((s, x))
        scored.sort(key=lambda p: p[0], reverse=True)
        out = []
        for s, x in scored[:top_k]:
            out.append(
                {
                    "id": x.id,
                    "score": round(s, 4),
                    "text": x.text,
                    "namespace": x.namespace,
                    "metadata": x.metadata,
                    "created": x.created,
                }
            )
        return out

    def clear(self, namespace: str | None = None) -> int:
        before = len(self._items)
        if namespace:
            self._items = [x for x in self._items if x.namespace != namespace]
        else:
            self._items = []
        return before - len(self._items)

    def count(self, namespace: str | None = None) -> int:
        if namespace:
            return sum(1 for x in self._items if x.namespace == namespace)
        return len(self._items)


class QdrantMemoryStore(MemoryStore):
    """Vector-backed memory store connecting to Qdrant REST API.

    Maintains full compatibility with MemoryStore interface while forwarding
    upserts and searches to Qdrant. Degrades gracefully to in-memory fallback
    if Qdrant is unreachable.
    """

    def __init__(
        self,
        qdrant_url: str,
        api_key: str | None = None,
        collection: str = "supremeai_memory",
        vector_size: int = 128,
        timeout_s: float = 5.0,
    ) -> None:
        super().__init__()
        self.qdrant_url = qdrant_url.rstrip("/")
        self.api_key = api_key
        self.collection = collection
        self.vector_size = vector_size
        self.timeout_s = timeout_s
        self._collection_ensured = False
        self._qdrant_ok = True
        self._last_error: str | None = None

    @property
    def degraded(self) -> bool:
        return not self._qdrant_ok or not self._collection_ensured

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["api-key"] = self.api_key
        return h

    def _ensure_collection(self) -> None:
        if self._collection_ensured:
            return
        import json
        import urllib.request

        payload = json.dumps(
            {"vectors": {"size": self.vector_size, "distance": "Cosine"}}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.qdrant_url}/collections/{self.collection}",
            data=payload,
            headers=self._headers(),
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                if resp.status in (200, 201, 409):
                    self._collection_ensured = True
                    self._qdrant_ok = True
                    self._last_error = None
                    return
                self._last_error = f"unexpected status {resp.status}"
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                self._collection_ensured = True
                self._qdrant_ok = True
                self._last_error = None
                return
            self._last_error = f"HTTP {exc.code}: {exc.reason}"
            logger.warning("Qdrant collection ensure failed: %s", self._last_error)
        except Exception as exc:  # noqa: BLE001 - degraded fallback
            self._last_error = str(exc)[:200]
            logger.warning("Qdrant collection ensure failed: %s", self._last_error)
        self._qdrant_ok = False

    def _embed(self, text: str) -> list[float]:
        """Deterministic embedding vector (dimension vector_size)."""
        import hashlib
        import math

        vec = [0.0] * self.vector_size
        for word in re.findall(r"\w+", text.lower()):
            idx = (
                int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
                % self.vector_size
            )
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm > 0 else vec

    def store(
        self,
        *,
        text: str,
        namespace: str = "default",
        item_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        item = super().store(
            text=text, namespace=namespace, item_id=item_id, metadata=metadata
        )
        import json

        self._ensure_collection()
        point_id = item.id.replace("mem-", "")
        if not re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            point_id,
            re.IGNORECASE,
        ):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, item.id))

        point = {
            "id": point_id,
            "vector": self._embed(text),
            "payload": {
                "id": item.id,
                "namespace": namespace,
                "text": text,
                "metadata": item.metadata,
                "created": item.created,
            },
        }
        payload = json.dumps({"points": [point]}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.qdrant_url}/collections/{self.collection}/points?wait=true",
            data=payload,
            headers=self._headers(),
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                if resp.status not in (200, 201, 202):
                    raise RuntimeError(f"unexpected status {resp.status}")
            self._qdrant_ok = True
            self._last_error = None
        except Exception as exc:  # noqa: BLE001 - degraded fallback
            self._qdrant_ok = False
            self._last_error = str(exc)[:200]
            logger.warning("Qdrant memory store failed: %s", self._last_error)
        return item

    def search(
        self,
        *,
        query: str,
        top_k: int = 5,
        namespace: str | None = None,
        threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        import json

        search_filter = None
        if namespace:
            search_filter = {
                "must": [{"key": "namespace", "match": {"value": namespace}}]
            }
        body: dict[str, Any] = {
            "vector": self._embed(query),
            "limit": top_k,
            "with_payload": True,
        }
        if search_filter:
            body["filter"] = search_filter
        if threshold > 0.0:
            body["score_threshold"] = threshold

        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.qdrant_url}/collections/{self.collection}/points/search",
            data=payload,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = []
                for hit in data.get("result", []):
                    p = hit.get("payload", {})
                    results.append(
                        {
                            "id": p.get("id", str(hit.get("id"))),
                            "score": round(float(hit.get("score", 0.0)), 4),
                            "text": p.get("text", ""),
                            "namespace": p.get("namespace", "default"),
                            "metadata": p.get("metadata", {}),
                            "created": p.get("created", 0.0),
                        }
                    )
                return results
        except (urllib.error.URLError, OSError, ValueError):
            self._qdrant_ok = False
            self._last_error = "qdrant search failed"
            logger.warning("Qdrant memory search failed; using in-memory fallback")
            return super().search(
                query=query, top_k=top_k, namespace=namespace, threshold=threshold
            )
