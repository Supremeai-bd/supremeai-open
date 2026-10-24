"""Adapters from existing retrieval surfaces into the canonical ContextEngine.

বাংলা: নতুন কোনো memory store তৈরি না করে বিদ্যমান memory_service-এর recall
API-কে Context Engine-এর RawCandidate contract-এ রূপান্তর করা হয়।
"""

from __future__ import annotations

import hashlib
from typing import Any

from context.engine import RawCandidate
from context.items import ItemKind
from context.scopes import Scope
from services.memory_service import recall_memories


def _memory_text(row: dict[str, Any]) -> str:
    return str(row.get("summary") or row.get("content") or "").strip()


async def memory_source(scope: Scope, query: str) -> list[RawCandidate]:
    """Return tenant-scoped semantic memories for the canonical engine."""
    if not scope.user_id or not query.strip():
        return []

    rows = await recall_memories(task_description=query, user_id=scope.user_id, limit=20)
    candidates: list[RawCandidate] = []
    for index, row in enumerate(rows):
        text = _memory_text(row)
        if not text:
            continue
        memory_id = str(row.get("id") or row.get("memory_id") or f"row-{index}")
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        candidates.append(
            RawCandidate(
                content=text,
                source_type="ai_memory",
                source_ref=f"ai_memory:{memory_id}",
                user_id=str(row.get("user_id") or scope.user_id),
                layer=str(metadata.get("summary_level") or "l1"),
                item_scope=str(metadata.get("scope_level") or "user"),
                kind=ItemKind.memory,
                base_score=float(row.get("score") or row.get("similarity") or 0.0),
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return candidates


def build_context_engine():
    """Construct the canonical engine with the currently available memory adapter."""
    from context.engine import ContextEngine

    return ContextEngine(memory_source=memory_source)


__all__ = ["build_context_engine", "memory_source"]


# বাংলা: `build_context_engine()`-ই integration entrypoint; সরাসরি নতুন
# memory database বা parallel context pipeline ব্যবহার করা যাবে না।
# TODO M2-C: একই contract-এ file, RAG এবং conversation adapters যুক্ত হবে।
