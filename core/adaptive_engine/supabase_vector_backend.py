"""Supabase pgvector backend for ExperienceDatabase.

FREE-TIER SOLUTION — no Render disk needed.

Render free tier does NOT support persistent disks/volumes. Without this backend,
ChromaDB and Qdrant lose all learned experiences on every container cold-start
(Render free-tier sleeps after 15 min idle).

This backend uses Supabase pgvector (already provisioned via `ai_memory` table
in alembic_migrations/versions/001_initial_schema.sql:301 + match_experiences
RPC). Supabase free tier (500MB) handles ~300K vectors at 1536 dims.

Architecture:
    record_experience() → _embed() → SupabaseVectorBackend.upsert()
        ↓
    ai_memory table (Supabase, persistent across restarts)
        ↓
    find_similar() → match_experiences RPC → cosine similarity (<=> operator)

Env vars:
- USE_SUPABASE_VECTOR=true  → use this backend (default true on Render free-tier)
- USE_SUPABASE_VECTOR=false → use ChromaDB/Qdrant (requires local disk)
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from core.logging_config import logger


class SupabaseVectorBackend:
    """Use Supabase pgvector instead of ChromaDB/Qdrant.

    This is the PREFERRED backend on Render free-tier because:
    - No local disk needed (Supabase is remote + persistent)
    - Already provisioned (ai_memory table + ivfflat index)
    - 500MB free tier is plenty for ~300K vectors at 1536 dims
    - Survives Render container restarts (data is in Supabase, not local FS)
    """

    COLLECTION_NAME = "experience"

    def __init__(self) -> None:
        # Lazy import to avoid circular deps
        from database.supabase_client import db as supabase_db

        self.supabase_db = supabase_db
        self._available: bool | None = None  # cached availability check

    @property
    def is_available(self) -> bool:
        """Check if Supabase client + pgvector are available (cached)."""
        if self._available is not None:
            return self._available
        try:
            client = getattr(self.supabase_db, "client", None)
            self._available = bool(client)
            if not self._available:
                logger.warning(
                    "[SupabaseVectorBackend] Supabase client not configured — "
                    "set SUPABASE_URL and SUPABASE_KEY env vars. "
                    "Vector search will be disabled."
                )
            return self._available
        except Exception as exc:
            logger.debug(f"[SupabaseVectorBackend] availability check failed: {exc}")
            self._available = False
            return False

    def upsert(
        self,
        exp_id: int | str,
        text: str,
        embedding: list[float],
        result: str,
        response_text: str = "",
        user_id: str = "",
    ) -> bool:
        """Insert/update an experience in Supabase ai_memory table.

        Returns True on success, False on failure (caller should fall back).
        """
        if not self.is_available:
            return False
        try:
            client = self.supabase_db.client
            # Use ai_memory table (already has VECTOR(1536) column)
            # memory_type='procedural' because experiences are procedural knowledge
            row_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"exp-{exp_id}"))
            payload = {
                "id": row_id,
                "agent_id": "00000000-0000-0000-0000-000000000000",  # placeholder (no agent FK)
                "memory_type": "procedural",
                "content": text[:8000],  # truncate to fit TEXT column
                "embedding": embedding,
                "metadata": {
                    "collection": self.COLLECTION_NAME,
                    "exp_id": str(exp_id),
                    "result": result,
                    "response": response_text[:1000],
                    "user_id": user_id,
                },
                "importance_score": 1.0 if result == "success" else 0.3,
            }
            # Upsert handles both insert (new) and update (same exp_id)
            client.table("ai_memory").upsert(payload).execute()
            return True
        except Exception as exc:
            logger.debug(f"[SupabaseVectorBackend] upsert failed: {exc}")
            return False

    def query(
        self,
        query_embedding: list[float],
        limit: int = 5,
        threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Find similar experiences using Supabase match_experiences RPC.

        Returns list of dicts: {id, content, metadata, similarity}
        """
        if not self.is_available:
            return []
        try:
            client = self.supabase_db.client
            # Use the match_experiences RPC (defined in migration 16_add_match_experiences_rpc.sql)
            response = client.rpc(
                "match_experiences",
                {
                    "query_embedding": query_embedding,
                    "match_count": limit,
                    "match_threshold": threshold,
                    "filter_collection": self.COLLECTION_NAME,
                },
            ).execute()
            if not response.data:
                return []
            # Normalize: each row → {id, content, metadata, similarity}
            results = []
            for row in response.data:
                metadata = row.get("metadata", {})
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except Exception:
                        metadata = {}
                results.append(
                    {
                        "id": row.get("id"),
                        "content": row.get("content", ""),
                        "metadata": metadata,
                        "similarity": float(row.get("similarity", 0.0)),
                        "source": "supabase_pgvector",
                    }
                )
            return results
        except Exception as exc:
            # OBSERVABLE degradation, not silent (#2257): the historical
            # failure mode here was match_experiences typed VECTOR(1536)
            # while every caller passes the canonical 384-dim embeddings —
            # pgvector rejects at execution and experience recall died
            # silently at debug level. Surface it at WARNING with the fix
            # pointer; re-type the RPC via
            # backend/database/migrations/17_retype_match_experiences_384.sql
            # (match_experiences must be vector(384), the canonical
            # ai_memory embedding contract — see
            # docs/database/AI_MEMORY_SCHEMA_AUDIT.md §2).
            logger.warning(
                "[SupabaseVectorBackend] experience query failed: "
                f"{exc} — returning []. If this mentions dimension mismatch, "
                "apply backend/database/migrations/"
                "17_retype_match_experiences_384.sql (RPC must be "
                "vector(384))."
            )
            return []


__all__ = ["SupabaseVectorBackend"]
