#!/usr/bin/env python3
"""SupremeAI — ingest_plans_to_rag.py (issue #2377, Deliverable 4).

Category C documents (~310টি) → RAG vector memory-তে semantic-search করা যায়
এমনভাবে ইনজেস্ট — এজেন্টের context window ভারী না করে ("Documents as Context"):

  docs/plans/        (161) — অতীত ফিচার প্ল্যান
  docs/archive/      (98)  — archived docs
  docs/plan-network/ (52)  — plan network artifacts

Ingestion engine: backend/memory/rag_pipeline.py (RAGPipeline.ingest_document —
MCP tool `ingest_document_rag`-এর একই pipeline, ChromaDB vector store)।

Resumable: content-hash manifest (data/rag_ingest_manifest.json) — আগে
ইনজেস্ট হওয়া ফাইল (content unchanged) আর ছুঁয়ে না হয়।

Usage:
    # Dry-run — কী ইনজেস্ট হবে দেখুন (কোনো vector store লাগে না):
    python scripts/operations/ingest_plans_to_rag.py --dry-run

    # Live ingest (local ChromaDB):
    python scripts/operations/ingest_plans_to_rag.py

    # নির্দিষ্ট ক্যাটাগরি + limit:
    python scripts/operations/ingest_plans_to_rag.py --category plans --limit 20
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
MANIFEST_PATH = REPO_ROOT / "data" / "rag_ingest_manifest.json"

CATEGORY_DIRS: dict[str, Path] = {
    "plans": REPO_ROOT / "docs" / "plans",
    "archive": REPO_ROOT / "docs" / "archive",
    "plan-network": REPO_ROOT / "docs" / "plan-network",
}

MAX_FILE_BYTES = 2_000_000  # 2MB — এর বড় ফাইল skip (dumping-ground প্রতিরোধ)
SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".yaml", ".yml", ".json"}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def collect_files(categories: list[str]) -> list[dict[str, Any]]:
    """ক্যাটাগরি ফোল্ডার scan → file records (path, category, sha, size)।"""
    records: list[dict[str, Any]] = []
    for cat in categories:
        folder = CATEGORY_DIRS[cat]
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            records.append(
                {
                    "path": path,
                    "rel_path": str(path.relative_to(REPO_ROOT)),
                    "category": cat,
                    "sha256": _sha256(content),
                    "size": len(content),
                    "content": content,
                }
            )
    return records


def load_manifest() -> dict[str, Any]:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"files": {}}
    return {"files": {}}


def save_manifest(manifest: dict[str, Any]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_rag_pipeline(collection: str):
    """backend RAG pipeline lazy-load (dry-run mode-এ dependency লাগে না)।

    ChromaDBStore-এর silent TF-IDF fallback ধরা পড়লে fail-closed —
    persistent vector index ছাড়া "ingested" দাবি করা মিথ্যা সত্য হবে।
    """
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from memory.chromadb_store import ChromaDBStore
    from memory.rag_pipeline import RAGPipeline

    store = ChromaDBStore(collection_name=collection)
    if getattr(store, "_collection", None) is None:
        raise RuntimeError(
            "ChromaDB persistent collection available নয় (fallback TF-IDF mode "
            "detect করা হয়েছে) — chromadb install করুন অথবা --dry-run চালান। "
            "Silent in-memory ingest manifest-এ মিথ্যা 'ingested' লিখত, তাই বাতিল।"
        )
    return RAGPipeline(vector_store=store)


def ingest(
    categories: list[str],
    limit: int | None = None,
    dry_run: bool = False,
    reingest: bool = False,
    collection: str = "supremeai_plans_rag",
    chunk_size: int = 500,
    overlap: int = 100,
) -> dict[str, Any]:
    manifest = load_manifest()
    files = collect_files(categories)
    if limit is not None:
        files = files[:limit]

    pending: list[dict[str, Any]] = []
    skipped: list[str] = []
    for rec in files:
        prev = manifest["files"].get(rec["rel_path"])
        if prev and prev.get("sha256") == rec["sha256"] and not reingest:
            skipped.append(rec["rel_path"])
        else:
            pending.append(rec)

    report = {
        "mode": "dry-run" if dry_run else "ingest",
        "started_at": _now_iso(),
        "categories": categories,
        "discovered": len(files),
        "pending": len(pending),
        "skipped_unchanged": len(skipped),
        "ingested": 0,
        "failed": [],
    }

    rag = None
    if not dry_run and pending:
        try:
            rag = build_rag_pipeline(collection)
        except Exception as exc:  # chromadb/dependency unavailable
            report["failed"].append(f"rag-init: {exc}")
            return report

    for rec in pending:
        doc_id = f"docrag::{rec['category']}::{rec['sha256'][:12]}"
        metadata = {
            "source": rec["rel_path"],
            "category": rec["category"],
            "sha256": rec["sha256"],
            "size_bytes": rec["size"],
            "ingested_at": _now_iso(),
        }
        try:
            if rag is not None:
                # RAGPipeline.ingest_document — MCP tool ingest_document_rag-এর
                # একই engine (chunk + embed + index)
                chunks = rag.chunk_text(rec["content"], chunk_size=chunk_size, overlap=overlap)
                for idx, chunk in enumerate(chunks):
                    chunk_id = f"{doc_id}_chunk_{idx}"
                    rag.vector_store.add_document(
                        chunk_id, chunk, {**metadata, "chunk_index": idx, "document_id": doc_id}
                    )
            manifest["files"][rec["rel_path"]] = {
                "sha256": rec["sha256"],
                "doc_id": doc_id,
                "category": rec["category"],
                "ingested_at": metadata["ingested_at"],
            }
            report["ingested"] += 1
        except Exception as exc:
            report["failed"].append(f"{rec['rel_path']}: {exc}")

    if not dry_run and (pending or reingest):
        save_manifest(manifest)
    report["finished_at"] = _now_iso()
    return report


def _cli() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--category",
        default="plans,archive,plan-network",
        help="Comma-separated: plans,archive,plan-network",
    )
    p.add_argument("--limit", type=int, default=None, help="Max files this run")
    p.add_argument("--dry-run", action="store_true", help="List only, no ingest")
    p.add_argument("--reingest", action="store_true", help="Force re-ingest changed+unchanged")
    p.add_argument("--collection", default="supremeai_plans_rag")
    p.add_argument("--chunk-size", type=int, default=500)
    p.add_argument("--overlap", type=int, default=100)
    args = p.parse_args()

    categories = [c.strip() for c in args.category.split(",") if c.strip()]
    for c in categories:
        if c not in CATEGORY_DIRS:
            print(f"unknown category: {c} (valid: {', '.join(CATEGORY_DIRS)})", file=sys.stderr)
            return 2

    report = ingest(
        categories=categories,
        limit=args.limit,
        dry_run=args.dry_run,
        reingest=args.reingest,
        collection=args.collection,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )

    print(
        f"[rag-ingest] {report['mode']} @ {report['started_at']} | "
        f"discovered={report['discovered']} pending={report['pending']} "
        f"skipped={report['skipped_unchanged']} ingested={report['ingested']}"
    )
    if args.dry_run and report["pending"]:
        for rec in collect_files(categories)[: args.limit or 10]:
            print(f"  [dry-run] {rec['rel_path']} ({rec['size']} bytes)")
    if report["failed"]:
        for f in report["failed"][:20]:
            print(f"  ✗ {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
