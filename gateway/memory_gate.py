"""Relevance-gated memory (ChronoFact Pillar 3 pattern) for SupremeAI gateway.

Gates semantic memory on a strict cosine threshold (default 0.72) so that
context from a previous domain cannot leak into the current task. Returns the
retained entries and reports how many were rejected as cross-domain pollution.

Stdlib only.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

DEFAULT_THRESHOLD = 0.72

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _unigrams(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _tfidf(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf = Counter(tokens)
    return {t: tf[t] * idf.get(t, 0.0) for t in tf}


def _idf(docs: list[list[str]]) -> dict[str, float]:
    n = len(docs)
    df: Counter[str] = Counter()
    for d in docs:
        for t in set(d):
            df[t] += 1
    return {t: math.log((n + 1) / (f + 1)) + 1.0 for t, f in df.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in a if k in b)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


@dataclass
class MemoryEntry:
    entry_id: str
    domain: str
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class GateResult:
    retained: list[MemoryEntry]
    rejected: list[MemoryEntry]
    threshold: float
    leak_count: int

    @property
    def leak_rate(self) -> float:
        total = len(self.retained) + len(self.rejected)
        if total == 0:
            return 0.0
        return self.leak_count / total


class MemoryGate:
    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        self.threshold = max(0.0, min(1.0, float(threshold)))

    def gate(self, query: str, entries: Iterable[MemoryEntry]) -> GateResult:
        entry_list = list(entries)
        if not entry_list:
            return GateResult([], [], self.threshold, 0)
        q_tokens = _unigrams(query)
        if not q_tokens:
            # No query signal -> reject all (fail-closed: no evidence).
            return GateResult([], list(entry_list), self.threshold, len(entry_list))
        docs = [q_tokens] + [_unigrams(e.content) for e in entry_list]
        idf = _idf(docs)
        q_vec = _tfidf(q_tokens, idf)
        retained: list[MemoryEntry] = []
        rejected: list[MemoryEntry] = []
        for entry, doc in zip(entry_list, docs[1:]):
            sim = _cosine(q_vec, _tfidf(doc, idf))
            if sim >= self.threshold:
                retained.append(entry)
            else:
                rejected.append(entry)
        return GateResult(retained, rejected, self.threshold, len(rejected))

    def is_cross_domain_leak(self, query: str, entry: MemoryEntry) -> bool:
        res = self.gate(query, [entry])
        return len(res.rejected) > 0
