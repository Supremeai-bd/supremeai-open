"""TF-IDF tool schema pruner (ChronoFact Pillar 4 pattern, adapted for SupremeAI gateway).

Given a user query and a list of tool schemas, compute cosine similarity between
query unigrams and each tool's unigrams, and retain only tools whose similarity
meets or exceeds ``threshold``. Responses are cached by a SHA-256 key over the
(query, tool names, threshold) tuple for instant repeat hits (0 LLM token cost).

Stdlib only. No secrets. Pure function; safe for concurrent use (cache guarded
by a lock-free dict assignment; Python dict assignment is atomic under GIL).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable


@dataclass
class ToolSchema:
    name: str
    description: str
    tokens: int = 0


@dataclass
class PruneResult:
    retained: list[ToolSchema]
    pruned: list[ToolSchema]
    threshold: float
    query_tokens: int
    retained_tokens: int
    original_tokens: int

    @property
    def reduction_pct(self) -> float:
        if self.original_tokens <= 0:
            return 0.0
        return (1.0 - self.retained_tokens / self.original_tokens) * 100.0


_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _unigrams(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _idf(documents: list[list[str]]) -> dict[str, float]:
    n = len(documents)
    df: Counter[str] = Counter()
    for d in documents:
        for t in set(d):
            df[t] += 1
    idf: dict[str, float] = {}
    for term, f in df.items():
        idf[term] = math.log((n + 1) / (f + 1)) + 1.0
    return idf


def _vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf = Counter(tokens)
    return {t: tf[t] * idf.get(t, 0.0) for t in tf}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in a if k in b)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# Process-local cache: key -> retained tool names (for instant repeat hits).
_CACHE: dict[str, tuple[str, ...]] = {}


def _cache_key(query: str, tools: Iterable[ToolSchema], threshold: float) -> str:
    names = ",".join(sorted(t.name for t in tools))
    raw = f"{query}|{names}|{threshold:.6f}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def route_tools(
    query: str,
    tools: Iterable[ToolSchema],
    threshold: float = 0.45,
    use_cache: bool = True,
) -> PruneResult:
    """Prune ``tools`` to those relevant to ``query`` via TF-IDF cosine similarity.

    Tools with similarity >= ``threshold`` are retained. ``threshold`` is clamped
    to [0.0, 1.0]. An empty query retains nothing (conservative: no evidence).
    """
    tool_list = list(tools)
    threshold = max(0.0, min(1.0, float(threshold)))

    key = _cache_key(query, tool_list, threshold)
    if use_cache and key in _CACHE:
        retained_names = set(_CACHE[key])
        retained = [t for t in tool_list if t.name in retained_names]
        pruned = [t for t in tool_list if t.name not in retained_names]
        return _build_result(query, tool_list, retained, pruned, threshold)

    q_tokens = _unigrams(query)
    if not q_tokens:
        # No query signal -> retain nothing (fail-closed: no evidence).
        retained: list[ToolSchema] = []
        pruned = list(tool_list)
        if use_cache:
            _CACHE[key] = ()
        return _build_result(query, tool_list, retained, pruned, threshold)

    documents = [q_tokens] + [_unigrams(t.name + " " + t.description) for t in tool_list]
    idf = _idf(documents)
    q_vec = _vector(q_tokens, idf)

    retained = []
    pruned = []
    for tool, doc in zip(tool_list, documents[1:]):
        sim = _cosine(q_vec, _vector(doc, idf))
        if sim >= threshold:
            retained.append(tool)
        else:
            pruned.append(tool)

    if use_cache:
        _CACHE[key] = tuple(t.name for t in retained)

    return _build_result(query, tool_list, retained, pruned, threshold)


def _build_result(
    query: str,
    tool_list: list[ToolSchema],
    retained: list[ToolSchema],
    pruned: list[ToolSchema],
    threshold: float,
) -> PruneResult:
    return PruneResult(
        retained=retained,
        pruned=pruned,
        threshold=threshold,
        query_tokens=len(_unigrams(query)),
        retained_tokens=sum(t.tokens for t in retained),
        original_tokens=sum(t.tokens for t in tool_list),
    )


def clear_cache() -> None:
    _CACHE.clear()
