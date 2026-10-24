#!/usr/bin/env python3
"""Re-index ai_memory rows: replace hash-fallback embeddings with real semantic ones.

Issue #442 — Module 01 backfill step.

Usage:
    # With Render env vars loaded (or .env present):
    python scripts/maintenance/reindex_ai_memory_embeddings.py

    # Dry-run (show plan, don't write):
    REINDEX_DRY_RUN=true python scripts/maintenance/reindex_ai_memory_embeddings.py

    # Limit rows (smoke-test before full backfill):
    REINDEX_LIMIT=10 python scripts/maintenance/reindex_ai_memory_embeddings.py

Requirements:
    - SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY  (service-role bypasses RLS)
    - CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID (for semantic embeddings)
    - Run from the repo root so backend/ is importable.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Make backend importable when run from repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Optional .env loader (silent if python-dotenv is absent)
try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env", override=False)
    load_dotenv(_REPO_ROOT / ".env.local", override=False)
except ImportError:
    pass

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("reindex_ai_memory")

DRY_RUN = os.getenv("REINDEX_DRY_RUN", "false").lower() == "true"
LIMIT = int(os.getenv("REINDEX_LIMIT", "0") or "0")  # 0 = all rows
BATCH_SIZE = int(os.getenv("REINDEX_BATCH", "50") or "50")
SLEEP_BETWEEN_BATCHES = float(os.getenv("REINDEX_SLEEP", "0.5") or "0.5")


def get_supabase_client():
    """Return a service-role Supabase client (bypasses RLS)."""
    try:
        from core.config import settings
        # canonical attribute is the lowercase property (settings.SUPABASE_URL
        # raised AttributeError and was silently swallowed — the old fallback
        # always won, making the "canonical settings" routing a no-op).
        url = getattr(settings, "supabase_url", "") or os.environ.get("SUPABASE_URL", "")
    except Exception:
        url = os.environ.get("SUPABASE_URL", "")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or ""
    )
    if not url or not key:
        log.error(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required. "
            "Set them in your environment or .env file."
        )
        sys.exit(1)
    try:
        from supabase import create_client
        return create_client(url, key)
    except ImportError:
        log.error("pip install supabase is required.")
        sys.exit(1)


def fetch_rows(client, offset: int, batch: int) -> list[dict]:
    """Fetch a page of ai_memory rows (id + text, ordered by created_at)."""
    result = (
        client.table("ai_memory")
        .select("id, content, summary, user_id, session_id")
        .order("created_at")
        .range(offset, offset + batch - 1)
        .execute()
    )
    return result.data or []


def row_text(row: dict) -> str:
    """Return the embeddable text for a row.

    Issue #442 reindex gap: cascade/session/semantic-cache writers store
    ``summary`` (memory_service.save_memory, CascadeMemoryService.store_memory)
    and never ``content`` — content-only selection skipped those rows entirely.
    """
    return (row.get("content") or "").strip() or (row.get("summary") or "").strip()


def embed_content(text: str) -> tuple[list[float], str]:
    """Return (vector, provider_label) using the current provider chain."""
    from core.embeddings import (
        embed_for_pgvector,
        remote_embed_cf,
        local_embed,
        hash_vectorize,
        _PG_DIM,
    )

    loc = local_embed(text)
    if loc is not None and len(loc) == _PG_DIM:
        return loc, "local_sentence_transformer"

    cf = remote_embed_cf(text)
    if cf is not None and len(cf) == _PG_DIM:
        return cf, "cloudflare_workers_ai"

    # Hash fallback: improved stopword-filtered, sublinear-TF version
    return hash_vectorize(text, size=_PG_DIM), "hash_fallback_improved"


def main() -> None:
    log.info("=== ai_memory re-index (issue #442 backfill) ===")
    if DRY_RUN:
        log.info("DRY_RUN=true — no writes will be made.")
    if LIMIT:
        log.info("REINDEX_LIMIT=%d — will process at most %d rows.", LIMIT, LIMIT)

    client = get_supabase_client()

    total_processed = 0
    total_upgraded = 0
    total_failed = 0
    providers: dict[str, int] = {}

    offset = 0
    while True:
        batch = BATCH_SIZE
        if LIMIT and (offset + batch) > LIMIT:
            batch = LIMIT - offset
        if batch <= 0:
            break

        rows = fetch_rows(client, offset, batch)
        if not rows:
            log.info("No more rows at offset %d — done.", offset)
            break

        log.info("Processing batch offset=%d, rows=%d", offset, len(rows))
        for row in rows:
            row_id = row["id"]
            content = row_text(row)
            if not content:
                log.debug("Row %s: no content/summary, skipping.", row_id)
                total_processed += 1
                continue

            try:
                vec, provider = embed_content(content)
            except Exception as exc:
                log.error("Row %s: embedding failed: %s", row_id, exc)
                total_failed += 1
                total_processed += 1
                continue

            providers[provider] = providers.get(provider, 0) + 1
            if provider != "hash_fallback_improved":
                total_upgraded += 1

            if not DRY_RUN:
                try:
                    client.table("ai_memory").update({"embedding": vec}).eq(
                        "id", row_id
                    ).execute()
                except Exception as exc:
                    log.error("Row %s: upsert failed: %s", row_id, exc)
                    total_failed += 1
                    total_processed += 1
                    continue
            else:
                log.debug("DRY_RUN: would update row %s with %s vector.", row_id, provider)

            total_processed += 1

        offset += len(rows)
        if len(rows) < batch:
            break

        time.sleep(SLEEP_BETWEEN_BATCHES)

    log.info("=== Re-index complete ===")
    log.info("  Total processed      : %d", total_processed)
    log.info("  Upgraded to semantic : %d", total_upgraded)
    log.info("  Still hash fallback  : %d", providers.get("hash_fallback_improved", 0))
    log.info("  Failed               : %d", total_failed)
    log.info("  Provider breakdown   : %s", providers)
    if DRY_RUN:
        log.info("  (DRY RUN — no rows were modified)")


if __name__ == "__main__":
    main()
