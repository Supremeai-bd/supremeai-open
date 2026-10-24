"""SupremeAI AI Memory Model — pgvector-backed long-term memory (Phase C).

Canonical schema: ``backend/database/supabase/ai_memory_phase_c.sql`` (Task 7-b)
and Alembic revision ``2026_09_13_100000``. The embedding contract is
**vector(384)** — enforced database-side by the column typmod and Python-side by
``core.embeddings._PG_DIM`` (see docs/database/AI_MEMORY_SCHEMA_AUDIT.md §2).

History (audit 2026-09-14, Task 7-b): this model previously described a
never-deployed shape (``content_type`` column, 1536-dim vectors, ``users`` FK)
and crashed on import — a positional string had been passed to
``mapped_column()`` (interpreted as the column *name*), leaving ``list[float]``
unresolvable, and it declared a relationship to a non-existent ``User`` mapper.
No module imported it, so the breakage stayed latent. It has been re-aligned to
the live schema; it is still **not** registered in ``models/__init__.py``
because ``create_all`` cannot express the pgvector type on SQLite test
databases — the table is owned by Alembic + the Supabase SQL companion file.

Usage note: ``similarity_search``/``cosine_distance`` require the optional
``pgvector`` package (and a real Postgres connection). Without it the model is
still importable and a placeholder type still renders ``vector(384)`` in DDL;
vector *operations* raise a clear runtime error instead of an AttributeError.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base

# Canonical embedding dimension — MUST equal the `vector(N)` typmod in
# backend/database/supabase/ai_memory_phase_c.sql (contract-locked by
# backend/tests/models/test_ai_memory_schema_contract.py).
EMBEDDING_DIMENSIONS = 384

try:  # optional dependency: needed only for vector operations, not for import
    from pgvector.sqlalchemy import Vector

    _EMBEDDING_TYPE: Any = Vector(EMBEDDING_DIMENSIONS)
    HAS_PGVECTOR_TYPE = True
except ModuleNotFoundError:  # pragma: no cover - exercised only in slim envs
    from sqlalchemy.types import UserDefinedType

    class _VectorPlaceholder(UserDefinedType):
        """DDL-compatible stand-in that still renders ``vector(384)`` on Postgres.

        Keeps the model importable (and honest about the column spec) in
        environments without the optional ``pgvector`` package; Python-side
        bind/result coercion stays a plain list.
        """

        cache_ok = True

        def get_col_spec(self, **kw: Any) -> str:  # noqa: ARG002 - SA signature
            return f"vector({EMBEDDING_DIMENSIONS})"

    _EMBEDDING_TYPE = _VectorPlaceholder()
    HAS_PGVECTOR_TYPE = False


class AIMemory(Base):
    """AI Memory entries with vector embeddings for semantic search."""

    __tablename__ = "ai_memory"

    # Primary key (server-side default matches Alembic gen_random_uuid())
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # Owner reference — Supabase auth.uid() rendered as text (JWT `sub`).
    # Nullable: system/anonymous rows exist (core/memory/auto_rag_injector.py).
    # Deliberately NOT a ForeignKey: no users ORM table exists; see audit §3.
    user_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    session_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(64), nullable=False, default="main")
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, default="general")

    # Content
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Experience-writer columns (adaptive_engine/supabase_vector_backend.py)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    memory_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    importance_score: Mapped[float | None] = mapped_column(nullable=True)

    # Vector embedding — vector(384) typmod enforces the dimension contract
    embedding: Mapped[list[float] | None] = mapped_column(_EMBEDDING_TYPE, nullable=True)

    # Flexible metadata (attribute is `metadata_` — `metadata` is reserved)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # INDEXES — mirror of ai_memory_phase_c.sql (HNSW created only when no ANN
    # index exists; see SQL Part 5 for the conditional DO-block)
    # -------------------------------------------------------------------------
    __table_args__ = (
        Index(
            "ix_ai_memory_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_ai_memory_user_created",
            "user_id",
            text("created_at DESC"),
        ),
    )

    def __repr__(self) -> str:
        return f"<AIMemory(id={self.id!s}, session={self.session_id!r})>"

    @classmethod
    async def similarity_search(
        cls,
        session,
        query_embedding: list[float],
        user_id: str | None = None,
        limit: int = 10,
        threshold: float = 0.7,
    ) -> list[AIMemory]:
        """Vector similarity search (requires the optional pgvector package).

        Args:
            session: Async DB session
            query_embedding: Query vector (must be 384-dim per the contract)
            user_id: Optional owner filter (auth.uid()::text)
            limit: Max results fetched before threshold post-filter
            threshold: Minimum cosine similarity (0-1)

        Returns:
            List of AIMemory ordered by similarity, threshold-filtered.
        """
        from sqlalchemy import select

        if not HAS_PGVECTOR_TYPE:
            raise RuntimeError(
                "AIMemory.similarity_search requires the optional 'pgvector' package"
            )

        query = select(cls).order_by(cls.embedding.cosine_distance(query_embedding)).limit(limit)

        if user_id is not None:
            query = query.where(cls.user_id == user_id)

        result = await session.execute(query)
        memories = result.scalars().all()

        # Post-filter by threshold (keeps parity with the RPC similarity metric
        # `1 - (embedding <=> query)` without importing numpy at module scope).
        filtered = []
        for mem in memories:
            if mem.embedding:
                similarity = _cosine_similarity(query_embedding, list(mem.embedding))
                if similarity >= threshold:
                    filtered.append(mem)

        return filtered

    @classmethod
    async def store_memory(
        cls,
        session,
        *,
        user_id: str | None,
        session_id: str,
        summary: str,
        content: str | None = None,
        embedding: list[float] | None = None,
        agent_type: str = "main",
        task_type: str = "general",
        metadata: dict[str, Any] | None = None,
    ) -> AIMemory:
        """Store a new memory entry (column set mirrors the canonical SQL)."""
        memory = cls(
            user_id=user_id,
            session_id=session_id,
            summary=summary,
            content=content,
            embedding=embedding,
            agent_type=agent_type,
            task_type=task_type,
            metadata_=metadata or {},
        )
        session.add(memory)
        await session.flush()
        return memory


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Pure-Python cosine similarity (zero-dependency; matches core.embeddings)."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2, strict=True))
    norm1 = sum(a * a for a in v1) ** 0.5
    norm2 = sum(b * b for b in v2) ** 0.5
    if norm1 <= 0.0 or norm2 <= 0.0:
        return 0.0
    return dot / (norm1 * norm2)
