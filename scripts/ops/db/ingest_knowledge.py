#!/usr/bin/env python3
"""
SupremeAI Knowledge Injection Pipeline
=======================================
load -> validate schema -> merge batch header -> embed -> upsert (dedupe on id)

Usage:
  python ingest_knowledge.py --init-db                          # create table (once)
  python ingest_knowledge.py --dir knowledge/ --dry-run         # validate only, no DB/API
  python ingest_knowledge.py --dir knowledge/                   # full inject
  python ingest_knowledge.py --approve t1-price-001 t2-faq-en-014
  python ingest_knowledge.py --deactivate-stale --repo-version <new_hash>

Requires: pip install psycopg2-binary httpx
Env:      DATABASE_URL (or --dsn), OPENAI_API_KEY (or --openai-base-url for self-hosted)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    sys.exit("Missing dependency: pip install psycopg2-binary")

try:
    import httpx
except ImportError:
    httpx = None  # only needed for the 'openai' embedder

LANGUAGES = {"en", "bn", "hi", "ar", "es", "zh"}

SCHEMAS = {
    "doc":                 {"required": ["title", "content"],                "optional": ["source_file"]},
    "domain":              {"required": ["title", "content"],                "optional": ["domain", "source_file"]},
    "faq":                 {"required": ["question", "answer"],              "optional": ["question_variants", "translation_group"]},
    "error_pattern":       {"required": ["title", "symptoms", "remediation"],"optional": ["error_code", "causes", "severity"]},
    "conversational_seed": {"required": ["intent", "patterns", "responses"], "optional": []},
    "glossary":            {"required": ["term", "definition"],              "optional": ["term_variants"]},
}

BATCH_FIELDS = {
    "tier": int, "priority": str, "repo_version": str, "injected_at": str,
    "default_language": str, "default_license": str,
    "default_confidence": float, "default_needs_review": bool,
}

# ---------------------------------------------------------------- embed text

def build_embed_text(rec: dict) -> str:
    """Manifest embedding_rules: one canonical text per record type."""
    t = rec["type"]
    clean = lambda items: [i for i in items if i and not str(i).startswith("*")]  # drop sentinel patterns

    if t == "faq":
        parts = [rec.get("question", ""), *clean(rec.get("question_variants", [])), rec.get("answer", "")]
    elif t in ("doc", "domain"):
        parts = [rec.get("title", ""), rec.get("content", "")]
    elif t == "error_pattern":
        parts = [rec.get("title", ""), rec.get("error_code", ""),
                 *clean(rec.get("symptoms", [])), *clean(rec.get("causes", []))]
    elif t == "conversational_seed":
        parts = [rec.get("intent", ""), *clean(rec.get("patterns", []))]
    elif t == "glossary":
        parts = [rec.get("term", ""), *clean(rec.get("term_variants", [])), rec.get("definition", "")]
    else:
        parts = [rec.get("title", ""), rec.get("content", "")]

    return " | ".join(p.strip() for p in parts if p and p.strip())

# ---------------------------------------------------------------- embedders

class TransientError(Exception):
    pass

class HashEmbedder:
    """Deterministic mock for pipeline smoke tests / CI. NOT for production retrieval."""
    name = "hash-mock"
    def __init__(self, dim: int = 1536):
        self.dim = dim
    def embed(self, texts):
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            v = [((h[i % len(h)] * (i + 7)) % 251 - 125) / 125.0 for i in range(self.dim)]
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out

class OpenAICompatibleEmbedder:
    """Any OpenAI-compatible /embeddings endpoint (OpenAI, vLLM, Ollama, LM Studio, gateway...).
    >>> To use backend/core/embeddings.py instead: subclass and override .embed()."""
    def __init__(self, base_url, api_key, model, batch_size=64, max_retries=6):
        if httpx is None:
            raise RuntimeError("httpx required for the openai embedder: pip install httpx")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.client = httpx.Client(timeout=120.0)

    @property
    def name(self):
        return self.model

    def embed(self, texts):
        vecs = []
        for i in range(0, len(texts), self.batch_size):
            vecs.extend(self._embed_batch(texts[i:i + self.batch_size]))
        return vecs

    def _embed_batch(self, batch):
        delay = 1.5
        for attempt in range(1, self.max_retries + 1):
            try:
                r = self.client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
                    json={"model": self.model, "input": batch},
                )
                if r.status_code == 429 or r.status_code >= 500:
                    raise TransientError(f"HTTP {r.status_code}")
                r.raise_for_status()  # 4xx fails fast (auth errors shouldn't retry)
                data = sorted(r.json()["data"], key=lambda d: d["index"])
                return [d["embedding"] for d in data]
            except (TransientError, httpx.TransportError) as e:
                if attempt == self.max_retries:
                    raise
                sleep_for = delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                print(f"    embed retry {attempt}/{self.max_retries} ({e}) — sleeping {sleep_for:.1f}s")
                time.sleep(sleep_for)

# ---------------------------------------------------------------- store

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id              TEXT PRIMARY KEY,
    record_type     TEXT NOT NULL,
    tier            INTEGER NOT NULL,
    title           TEXT,
    content         TEXT,
    language        TEXT,
    domain_tags     TEXT[] NOT NULL DEFAULT '{{}}',
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'draft', 'archived')),
    confidence      REAL,
    needs_review    BOOLEAN NOT NULL DEFAULT FALSE,
    priority        TEXT,
    repo_version    TEXT,
    source_file     TEXT,
    license         TEXT,
    injected_at     TIMESTAMPTZ,
    embed_text      TEXT,
    content_hash    TEXT,
    embedding_model TEXT,
    embedding       vector({dim}),
    payload         JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kc_embedding ON knowledge_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_kc_status    ON knowledge_chunks (status, record_type);
CREATE INDEX IF NOT EXISTS idx_kc_tags      ON knowledge_chunks USING gin (domain_tags);
CREATE INDEX IF NOT EXISTS idx_kc_payload   ON knowledge_chunks USING gin (payload jsonb_path_ops);
"""

UPSERT_SQL = """
INSERT INTO knowledge_chunks
    (id, record_type, tier, title, content, language, domain_tags, status, confidence,
     needs_review, priority, repo_version, source_file, license, injected_at,
     embed_text, content_hash, embedding_model, embedding, payload)
VALUES %s
ON CONFLICT (id) DO UPDATE SET
    record_type = EXCLUDED.record_type, tier = EXCLUDED.tier, title = EXCLUDED.title,
    content = EXCLUDED.content, language = EXCLUDED.language, domain_tags = EXCLUDED.domain_tags,
    status = EXCLUDED.status, confidence = EXCLUDED.confidence, needs_review = EXCLUDED.needs_review,
    priority = EXCLUDED.priority, repo_version = EXCLUDED.repo_version, source_file = EXCLUDED.source_file,
    license = EXCLUDED.license, injected_at = EXCLUDED.injected_at, embed_text = EXCLUDED.embed_text,
    content_hash = EXCLUDED.content_hash, embedding_model = EXCLUDED.embedding_model,
    embedding = EXCLUDED.embedding, payload = EXCLUDED.payload, updated_at = now()
"""
UPSERT_TEMPLATE = "(%s,%s,%s,%s,%s,%s,%s::text[],%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector,%s)"

class PgVectorStore:
    def __init__(self, dsn: str):
        self.conn = psycopg2.connect(dsn)

    def init_db(self, dim: int):
        with self.conn.cursor() as cur:
            cur.execute(DDL.format(dim=dim))
        self.conn.commit()

    def existing_states(self, ids):
        with self.conn.cursor() as cur:
            cur.execute("SELECT id, content_hash, status FROM knowledge_chunks WHERE id = ANY(%s)", (ids,))
            return {r[0]: (r[1], r[2]) for r in cur.fetchall()}

    def upsert(self, rows):
        with self.conn.cursor() as cur:
            execute_values(cur, UPSERT_SQL, rows, template=UPSERT_TEMPLATE, page_size=200)
        self.conn.commit()

    def deactivate_stale(self, repo_version: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute("UPDATE knowledge_chunks SET status='archived', updated_at=now() "
                        "WHERE repo_version IS DISTINCT FROM %s AND status <> 'archived'", (repo_version,))
            n = cur.rowcount
        self.conn.commit()
        return n

    def approve(self, ids) -> int:
        with self.conn.cursor() as cur:
            cur.execute("UPDATE knowledge_chunks SET status='active', needs_review=FALSE, updated_at=now() "
                        "WHERE id = ANY(%s) AND status='draft'", (ids,))
            n = cur.rowcount
        self.conn.commit()
        return n

# ---------------------------------------------------------------- validation

def validate_batch(batch, src, errors):
    if not isinstance(batch, dict):
        errors.append(f"{src}: 'batch' must be an object")
        return
    for f, typ in BATCH_FIELDS.items():
        v = batch.get(f)
        if v is None:
            errors.append(f"{src}: batch missing '{f}'"); continue
        if typ is bool and not isinstance(v, bool): errors.append(f"{src}: batch '{f}' must be boolean")
        elif typ is int and not isinstance(v, int): errors.append(f"{src}: batch '{f}' must be int")
        elif typ is float and not isinstance(v, (int, float)): errors.append(f"{src}: batch '{f}' must be number")
        elif typ is str and not isinstance(v, str): errors.append(f"{src}: batch '{f}' must be string")
    c = batch.get("default_confidence")
    if isinstance(c, (int, float)) and not 0 <= c <= 1:
        errors.append(f"{src}: batch default_confidence out of [0,1]")

def validate_record(rec, src, idx, seen, errors, warnings, allow_overwrite):
    """Returns record id if the record is valid (warnings allowed), else None."""
    where = f"{src}#record[{idx}]"
    if not isinstance(rec, dict):
        errors.append(f"{where}: record must be an object"); return None
    rid = rec.get("id")
    if not rid or not isinstance(rid, str):
        errors.append(f"{where}: missing or invalid 'id'"); return None
    where = f"{src}:{rid}"

    errs = []
    if rid in seen:
        msg = f"{where}: duplicate id (first seen in {seen[rid]})"
        warnings.append(msg) if allow_overwrite else errs.append(msg)
    else:
        seen[rid] = src

    rtype = rec.get("type")
    if rtype not in SCHEMAS:
        errs.append(f"unknown type '{rtype}' (expected one of {sorted(SCHEMAS)})")
    else:
        for f in SCHEMAS[rtype]["required"]:
            v = rec.get(f)
            if v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, (list, dict)) and not v):
                errs.append(f"missing or empty required field '{f}'")

    if rec.get("language") and rec["language"] not in LANGUAGES:
        warnings.append(f"{where}: language '{rec['language']}' not in {sorted(LANGUAGES)}")
    conf = rec.get("confidence")
    if conf is not None and not (isinstance(conf, (int, float)) and 0 <= conf <= 1):
        errs.append("confidence must be a number in [0,1]")
    tags = rec.get("domain_tags")
    if tags is not None and (not isinstance(tags, list) or not all(isinstance(t, str) for t in tags)):
        errs.append("domain_tags must be a list of strings")

    errors.extend(f"{where}: {e}" for e in errs)
    return rid if not errs else None

def merge_batch(rec, batch, source_file):
    m = dict(rec)
    m.update({
        "tier": batch["tier"], "priority": batch["priority"],
        "repo_version": batch["repo_version"], "injected_at": batch["injected_at"],
        "language": rec.get("language", batch["default_language"]),
        "license": rec.get("license", batch["default_license"]),
        "confidence": rec.get("confidence", batch["default_confidence"]),
        "needs_review": rec.get("needs_review", batch["default_needs_review"]),
        "domain_tags": rec.get("domain_tags", []),
        "source_file": rec.get("source_file", source_file),
    })
    m["status"] = "draft" if m["needs_review"] else "active"
    return m

def display_fields(rec):
    t = rec["type"]
    title = rec.get("title") or rec.get("question") or rec.get("term") or rec.get("intent") or rec["id"]
    content = {"faq": rec.get("answer", ""), "glossary": rec.get("definition", ""),
               "conversational_seed": "\n".join(rec.get("responses", [])),
               "error_pattern": rec.get("title", "")}.get(t, rec.get("content", ""))
    return title, content

# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--files", nargs="+", help="tier*.json files to ingest")
    ap.add_argument("--dir", help="directory with manifest.json (or tier*.json glob)")
    ap.add_argument("--dsn", help="postgres DSN (default: $DATABASE_URL)")
    ap.add_argument("--embedder", choices=["openai", "hash"], default="openai")
    ap.add_argument("--openai-base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    ap.add_argument("--openai-model", default="text-embedding-3-small")
    ap.add_argument("--embed-dim", type=int, default=1536, help="must match table column (init-db)")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--max-embed-chars", type=int, default=8000)
    ap.add_argument("--dry-run", action="store_true", help="validate only — no DB, no embedding API")
    ap.add_argument("--no-strict", action="store_true", help="skip invalid records instead of aborting")
    ap.add_argument("--allow-id-overwrite", action="store_true", help="duplicate ids across files warn instead of error")
    ap.add_argument("--init-db", action="store_true")
    ap.add_argument("--approve", nargs="+", metavar="ID", help="flip draft records to active")
    ap.add_argument("--deactivate-stale", action="store_true", help="archive records from other repo_versions")
    ap.add_argument("--repo-version", help="used by --deactivate-stale")
    ap.add_argument("--report", default="ingestion_report.json")
    args = ap.parse_args()

    # ---- resolve files
    files = list(args.files or [])
    if args.dir:
        d = Path(args.dir)
        manifest = d / "manifest.json"
        if manifest.exists():
            m = json.loads(manifest.read_text(encoding="utf-8"))
            entries = m.get("files", []) + m.get("files_v2", [])
            files += [str(d / e["file"]) for e in entries if isinstance(e, dict) and e.get("file")]
        else:
            files += sorted(str(p) for p in d.glob("tier*.json"))
    files = sorted(dict.fromkeys(files))  # dedupe, keep order

    dsn = args.dsn or os.environ.get("SUPREMEAI_KNOWLEDGE_DSN") or os.environ.get("DATABASE_URL")
    store = None
    if not args.dry_run:
        if not dsn:
            sys.exit("No DSN: pass --dsn or set DATABASE_URL")
        store = PgVectorStore(dsn)
        if args.init_db:
            store.init_db(args.embed_dim)
            print(f"[init] knowledge_chunks table ready (vector dim={args.embed_dim})")
            if not files and not args.approve and not args.deactivate_stale:
                return

    # ---- utility modes that don't need files
    if args.approve:
        n = store.approve(args.approve)
        print(f"[approve] {n} record(s) draft -> active")
        if not files:
            return
    if args.deactivate_stale:
        if not args.repo_version:
            sys.exit("--deactivate-stale requires --repo-version (the NEW current version)")
        n = store.deactivate_stale(args.repo_version)
        print(f"[stale] archived {n} record(s) from other repo_versions")
        if not files:
            return

    if not files:
        sys.exit("Nothing to do: pass --files/--dir (or --approve/--deactivate-stale/--init-db alone).")

    # ---- load + validate
    print(f"[load] {len(files)} file(s)")
    seen, errors, warnings, merged, per_file = {}, [], [], [], []
    for path in files:
        src = Path(path).name
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"{src}: cannot parse JSON ({e})")
            per_file.append({"file": src, "records": 0, "valid": 0}); continue
        batch, records = data.get("batch"), data.get("records")
        if not isinstance(records, list) or not isinstance(batch, dict):
            errors.append(f"{src}: file must contain 'batch' (object) and 'records' (list)")
            per_file.append({"file": src, "records": 0, "valid": 0}); continue
        validate_batch(batch, src, errors)
        ok = 0
        for i, rec in enumerate(records):
            rid = validate_record(rec, src, i, seen, errors, warnings, args.allow_id_overwrite)
            if rid:
                merged.append(merge_batch(rec, batch, src)); ok += 1
        per_file.append({"file": src, "records": len(records), "valid": ok})
        print(f"  {src}: {ok}/{len(records)} valid")

    if errors:
        print(f"\n[validate] {len(errors)} ERROR(S):")
        for e in errors: print(f"  ✗ {e}")
        if not args.no_strict:
            sys.exit("Aborted (strict mode). Fix errors or rerun with --no-strict to skip bad records.")
    for w in warnings:
        print(f"  ⚠ {w}")

    # reject records whose embed text is empty (nothing to retrieve by)
    embed_texts = [build_embed_text(r)[:args.max_embed_chars] for r in merged]
    bad = [m["id"] for m, t in zip(merged, embed_texts) if not t.strip()]
    if bad:
        print(f"\n[validate] empty embed text for: {bad}")
        keep = [(m, t) for m, t in zip(merged, embed_texts) if t.strip()]
        merged, embed_texts = [x[0] for x in keep], [x[1] for x in keep]

    drafts = sum(1 for m in merged if m["status"] == "draft")
    print(f"\n[validate] {len(merged)} records ready "
          f"({drafts} draft/needs_review, {len(merged) - drafts} active)")

    if args.dry_run:
        print("[dry-run] sample embed texts:")
        for m, t in list(zip(merged, embed_texts))[:3]:
            print(f"  {m['id']}: {t[:120]}...")
        json.dump({"files": per_file, "records": len(merged), "drafts": drafts,
                   "errors": errors, "warnings": warnings},
                  open(args.report, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"[dry-run] OK — report written to {args.report}")
        return

    # ---- embed
    if args.embedder == "hash":
        embedder = HashEmbedder(args.embed_dim)
        print("[embed] WARNING: hash-mock embedder — output is NOT production-usable")
    else:
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            print("[embed] WARNING: OPENAI_API_KEY not set (fine for local vLLM/Ollama)")
        embedder = OpenAICompatibleEmbedder(args.openai_base_url, key, args.openai_model, args.batch_size)

    print(f"[embed] {len(embed_texts)} chunks via {embedder.name} ...")
    t0 = time.time()
    vectors = embedder.embed(embed_texts)
    print(f"[embed] done in {time.time() - t0:.1f}s")

    # ---- build rows
    rows = []
    for rec, text, vec in zip(merged, embed_texts, vectors):
        title, content = display_fields(rec)
        chash = hashlib.sha256(f"{embedder.name}::{text}".encode()).hexdigest()
        rows.append((
            rec["id"], rec["type"], rec["tier"], title, content, rec["language"],
            rec["domain_tags"], rec["status"], rec["confidence"], rec["needs_review"],
            rec["priority"], rec["repo_version"], rec["source_file"], rec["license"],
            rec["injected_at"], text, chash, embedder.name,
            "[" + ",".join(map(str, vec)) + "]",
            json.dumps(rec, ensure_ascii=False),
        ))

    # ---- upsert with change-detection (true idempotency: identical rows are not rewritten)
    existing = store.existing_states([r[0] for r in rows])
    to_write, unchanged = [], 0
    for r in rows:
        prev = existing.get(r[0])
        if prev and prev[0] == r[16] and prev[1] == r[7]:  # same content_hash & status
            unchanged += 1
        else:
            to_write.append(r)

    written = 0
    for i in range(0, len(to_write), 500):
        chunk = to_write[i:i + 500]
        store.upsert(chunk)
        written += len(chunk)
        print(f"[upsert] {written}/{len(to_write)}")

    print(f"\n[done] wrote {written}, unchanged (skipped) {unchanged}, "
          f"drafts {drafts}, total in DB-run {len(rows)}")

    json.dump({"files": per_file, "records": len(rows), "written": written,
               "unchanged": unchanged, "drafts": drafts, "errors": errors,
               "warnings": warnings, "embedding_model": embedder.name},
              open(args.report, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"[done] report -> {args.report}")

if __name__ == "__main__":
    main()
