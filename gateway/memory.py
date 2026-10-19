"""SupremeAI Gateway — lightweight in-memory semantic memory sidecar (P4).

Backend-neutral store/search used by /v1/memory/* endpoints. Designed as a
swap-in seam for Qdrant/Chroma: replace MemoryStore with a vector-backed
implementation without changing the HTTP contract. Scoring is honest
(keyword-overlap, no fabricated embeddings) — production should inject a
real embedding model via the store's score() hook.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


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
