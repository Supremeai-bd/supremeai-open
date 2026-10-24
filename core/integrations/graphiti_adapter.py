"""Graphiti-inspired temporal knowledge-graph memory adapter for SupremeAI.
STATUS: orphaned — see docs/operations/MODULE_STATUS_REGISTRY.md (#449).

Graphiti (real-time knowledge graphs for agents) থেকে নেওয়া মূল ধারণা: memory-তে
**time-aware** entity→relation→entity ট্রিপল সংরক্ষণ করা, যাতে প্রশ্নের সাথে
প্রাসঙ্গিক ও সাম্প্রতিক সম্পর্ক রিকল করা যায় — শুধু সমান্তরাল ভেক্টর না, বরং গতিপ্রকৃতি
(temporal abstraction / causal) বুঝে কাজ করা যায়।

এখানে Graphiti-কে optional dependency হিসেবে ব্যবহার করা হয় (Flag on + dependency
থাকলে upstream-এর সাথে কাজ করে)। না থাকলে একটি zero-cost fallback (timestamped
episode triples + recency/keyword ranking) ব্যবহার হয়।
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

from core.logging_config import logger
from integrations._flags import flag, import_available

_ENABLED_FLAG = "SUPREMEAI_GRAPHITI_ENABLED"


def _words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[a-z0-9\u0980-\u09FF]+", text) if len(w) > 1}


def _asyncio_run(coro: Any) -> Any:
    """Run an async coroutine from a sync context safely (no nested loop)."""
    try:
        loop = asyncio.get_running_loop()
        # If we are already in an event loop, we can't block with asyncio.run.
        # So we spawn a task that will run in the background.
        return loop.create_task(coro)
    except RuntimeError:
        return asyncio.run(coro)


class GraphitiMemoryAdapter:
    """Temporal knowledge-graph memory bridging optional Graphiti with zero-cost fallback."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        data_dir: str = "data",
    ) -> None:
        self.enabled_flag = _ENABLED_FLAG
        self._graphiti = None
        self._triples: list[dict[str, Any]] = []

        # Determine fallback storage path
        self.data_dir = Path(__file__).resolve().parent.parent.parent / data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._fallback_path = self.data_dir / "graphiti_fallback.json"

        self._load_fallback()

        if flag(_ENABLED_FLAG) and import_available("graphiti_core") and uri:
            try:
                from graphiti_core import Graphiti  # type: ignore[import-not-found]

                # NOTE: embedder placeholder — upstream full wiring আমাদের llm_router দিয়ে করা যায়
                self._graphiti = Graphiti(uri=uri, user=user or "", password=password or "")
                logger.info("GraphitiMemoryAdapter: using upstream temporal graph memory.")
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    f"GraphitiMemoryAdapter: upstream init failed, using fallback: {exc}"
                )
                self._graphiti = None
        else:
            logger.info(
                "GraphitiMemoryAdapter: upstream disabled/absent, using zero-cost fallback "
                f"(flag={flag(_ENABLED_FLAG)}, dep={import_available('graphiti_core')}, uri={bool(uri)})."
            )

    @property
    def active(self) -> bool:
        return self._graphiti is not None

    def _load_fallback(self) -> None:
        if self._fallback_path.exists():
            try:
                with open(self._fallback_path, encoding="utf-8") as f:
                    data = json.load(f)
                    # Convert 'words' list back to set
                    for t in data:
                        if isinstance(t.get("words"), list):
                            t["words"] = set(t["words"])
                    self._triples = data
            except Exception as e:
                logger.warning(f"GraphitiMemoryAdapter: failed to load fallback data: {e}")
                self._triples = []

    def _save_fallback(self) -> None:
        try:
            # Convert sets to lists for JSON serialization
            data_to_save = []
            for t in self._triples:
                t_copy = t.copy()
                if isinstance(t_copy.get("words"), set):
                    t_copy["words"] = list(t_copy["words"])
                data_to_save.append(t_copy)

            with open(self._fallback_path, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"GraphitiMemoryAdapter: failed to save fallback data: {e}")

    def add_episode(self, text: str) -> None:
        """Record a temporally-stamped memory episode."""
        text = (text or "").strip()
        if not text:
            return
        if self.active:
            _asyncio_run(self._graphiti.build_episode(text))  # type: ignore[union-attr]
            return
        self._triples.append({"text": text, "ts": time.time(), "words": _words(text)})
        self._save_fallback()

    def search(self, query: str, top_k: int = 3, recency_weight: float = 0.0) -> list[str]:
        """Return top-k temporally relevant memories (recency + keyword)."""
        if self.active:
            return [t["text"] for t in self._triples[:top_k]]  # upstream path (rare, sync-limited)

        q = _words(query)
        ranked: list[tuple[float, str]] = []
        for t in self._triples:
            overlap = len(q & t["words"])
            recency = max(0.0, 1.0 - (time.time() - t["ts"]) / 86400.0)  # 1-day half-life
            ranked.append((overlap + recency_weight * recency, t["text"]))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [text for score, text in ranked[:top_k] if score > 0.0]
