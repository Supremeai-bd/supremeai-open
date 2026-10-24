"""Cold-start knowledge injection loader for SupremeAI.

Reads a curated evergreen JSON seed, enforces quality gates (dedup, confidence,
per-category caps with facet diversity), and embeds into the local ChromaDBStore
(which falls back to offline TF-IDF when ChromaDB is unavailable). Because the
gates run at ingest time, adding more curated entries is always safe: volume
cannot degrade retrieval.

The injected docs are tagged namespace="coldstart_fallback" and are meant to be
queried through the degraded/offline path (KnowledgeBaseIndexer.search_knowledge
or retrieve_fallback()), NOT through the tenant-scoped KnowledgeQAService.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from memory.chromadb_store import ChromaDBStore


@dataclass
class LoaderConfig:
    source: str
    namespace: str = "coldstart_fallback"
    db_path: str | None = None
    collection: str = "supremeai_knowledge"
    min_confidence: str = "high"
    core_categories: set[str] = field(default_factory=lambda: {
        "programming_fundamentals",
        "ai_ml_fundamentals",
        "security_principles",
        "system_design_principles",
    })
    caps: dict[str, int] = field(default_factory=lambda: {"core": 250, "support": 60})
    mins: dict[str, int] = field(default_factory=lambda: {"core": 50, "support": 15})
    allowed_facets: set[str] = field(default_factory=lambda: {
        "concept", "pattern", "fact", "glossary", "method", "reference",
    })
    excluded_prefixes: set[str] = field(default_factory=lambda: set())


def normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def question_hash(question: str) -> str:
    return hashlib.sha256(normalize(question).encode("utf-8")).hexdigest()


def tier_of(category_id: str, cfg: LoaderConfig) -> str:
    return "core" if category_id in cfg.core_categories else "support"


def facet_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in entries:
        t = e.get("type", "concept")
        counts[t] = counts.get(t, 0) + 1
    return counts


def diverse_truncate(entries: list[dict[str, Any]], cap: int) -> list[dict[str, Any]]:
    by_type: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        by_type.setdefault(e.get("type", "concept"), []).append(e)
    types = list(by_type.keys())
    idx = {t: 0 for t in types}
    selected: list[dict[str, Any]] = []

    for t in types:
        if idx[t] < len(by_type[t]):
            selected.append(by_type[t][idx[t]])
            idx[t] += 1
            if len(selected) >= cap:
                return selected

    progress = True
    while len(selected) < cap and progress:
        progress = False
        for t in types:
            if idx[t] < len(by_type[t]) and len(selected) < cap:
                selected.append(by_type[t][idx[t]])
                idx[t] += 1
                progress = True
    return selected


def apply_gates(categories: list[dict[str, Any]], cfg: LoaderConfig) -> tuple[list[tuple[str, dict[str, Any]]], dict[str, Any]]:
    seen_hashes: set[str] = set()
    accepted: list[tuple[str, dict[str, Any]]] = []
    stats = {
        "total_input": 0,
        "removed_duplicates": 0,
        "removed_low_confidence": 0,
        "removed_empty": 0,
        "by_category": {},
    }
    required = {cfg.min_confidence.lower()}

    for cat in categories:
        cid = cat.get("category_id", "unknown")
        tier = tier_of(cid, cfg)
        cap = cfg.caps[tier]
        min_target = cfg.mins[tier]
        passed: list[dict[str, Any]] = []

        for e in cat.get("entries", []):
            stats["total_input"] += 1
            q = e.get("question", "")
            a = e.get("answer", "")
            if not q or not a:
                stats["removed_empty"] += 1
                continue
            h = question_hash(q)
            if h in seen_hashes:
                stats["removed_duplicates"] += 1
                continue
            seen_hashes.add(h)
            conf = (e.get("confidence") or "").lower()
            if conf not in required:
                stats["removed_low_confidence"] += 1
                continue
            passed.append(e)

        if len(passed) > cap:
            passed = diverse_truncate(passed, cap)

        stats["by_category"][cid] = {
            "tier": tier,
            "accepted": len(passed),
            "cap": cap,
            "min_target": min_target,
            "meets_min": len(passed) >= min_target,
            "facets": facet_counts(passed),
        }
        accepted.extend((cid, e) for e in passed)

    return accepted, stats


def build_doc(category_id: str, entry: dict[str, Any], cfg: LoaderConfig) -> dict[str, Any]:
    q = entry.get("question", "")
    a = entry.get("answer", "")
    eid = entry.get("id") or question_hash(q)[:12]
    text = f"Q: {q}\nA: {a}"
    metadata = {
        "namespace": cfg.namespace,
        "source": "coldstart_seed",
        "category_id": category_id,
        "type": entry.get("type", "concept"),
        "tags": entry.get("tags", []),
        "confidence": entry.get("confidence"),
        "last_verified": entry.get("last_verified"),
        "question": q,
    }
    return {"id": f"coldstart::{category_id}::{eid}", "text": text, "metadata": metadata}


def reset_collection(store: ChromaDBStore) -> None:
    try:
        if store._collection is not None and store._client is not None:
            store._client.delete_collection(store.collection_name)
            store._init_chroma()
            return
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(f"Silenced error: {e}")
    store._fallback_docs.clear()
    store._save_fallback()


def retrieve_fallback(query: str, n: int = 5, namespace: str = "coldstart_fallback", db_path: str | None = None) -> list[tuple[str, float, dict[str, Any]]]:
    store = ChromaDBStore(db_path=db_path)
    results = store.query(query, n_results=max(n * 4, n))
    out = [r for r in results if r[2].get("metadata", {}).get("namespace") == namespace]
    return out[:n]


def run(cfg: LoaderConfig, dry_run: bool, reset: bool) -> dict[str, Any]:
    with open(cfg.source, encoding="utf-8") as f:
        raw = json.load(f)
    categories = raw.get("categories", [])
    accepted, stats = apply_gates(categories, cfg)

    if dry_run:
        stats["indexed"] = 0
        stats["mode"] = "dry-run"
        return stats

    store = ChromaDBStore(db_path=cfg.db_path, collection_name=cfg.collection)
    if reset:
        reset_collection(store)

    indexed = 0
    for cid, e in accepted:
        doc = build_doc(cid, e, cfg)
        store.add_document_incremental(doc["id"], doc["text"], doc["metadata"])
        indexed += 1

    stats["indexed"] = indexed
    stats["store_type"] = "chromadb" if store._collection is not None else "tfidf_fallback"
    stats["mode"] = "inject"
    return stats


def print_report(stats: dict[str, Any]) -> None:
    print("=" * 60)
    print(f"MODE: {stats.get('mode')}")
    print(f"Input entries: {stats.get('total_input')}")
    print(f"Removed dupes: {stats.get('removed_duplicates')} | low-conf: {stats.get('removed_low_confidence')} | empty: {stats.get('removed_empty')}")
    print(f"Indexed: {stats.get('indexed')} | store: {stats.get('store_type', 'n/a')}")
    print("-" * 60)
    for cid, s in stats["by_category"].items():
        flag = "OK" if s["meets_min"] else "BELOW-MIN"
        print(f"  {cid:28s} {s['tier']:7s} acc={s['accepted']:3d} cap={s['cap']:3d} [{flag}] facets={s['facets']}")
    print("=" * 60)


def parse_args() -> argparse.Namespace:
    default_source = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "coldstart_knowledge_seed_comprehensive.json")
    p = argparse.ArgumentParser(description="Inject curated evergreen knowledge into the local vector store.")
    p.add_argument("--source", default=default_source, help="Path to the curated JSON seed.")
    p.add_argument("--db-path", default=None, help="ChromaDB persistence path (default: backend/data/chromadb_store).")
    p.add_argument("--namespace", default="coldstart_fallback")
    p.add_argument("--min-confidence", default="high", help="Minimum confidence to ingest (e.g. high).")
    p.add_argument("--dry-run", action="store_true", help="Apply gates and report without writing.")
    p.add_argument("--reset", action="store_true", help="Clear the collection before injecting.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = LoaderConfig(
        source=args.source,
        namespace=args.namespace,
        db_path=args.db_path,
        min_confidence=args.min_confidence,
    )
    stats = run(cfg, dry_run=args.dry_run, reset=args.reset)
    print_report(stats)


if __name__ == "__main__":
    main()
