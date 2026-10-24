"""ChatAttachment ORM model + M2 context metadata (ecosystem Ph2 / M2-A).

বাংলা: M2 Context Engine-এর ভিত্তি — ``chat_attachments`` টেবিলটিই repo-র
একমাত্র general files-metadata surface (tier_s_features migration)। OSS plan
§4 অনুযায়ী এতে L0/L1/L2 summary layering + context anchoring columns যোগ করা
হলো (Alembic ``2026_09_15_130000``):

- ``summary_l0``  — ছোট semantic summary (এক-দুই বাক্য; budgeter-এর প্রথম পছন্দ)
- ``summary_l1``  — structured summary (JSON: sections/entities/keywords)
- ``content_ref`` — raw source-এর রেফারেন্স (L2; ref:// semantics M7-এ formalize)
- ``content_hash``— sha256 (chromadb_store-এর content_hash convention)
- ``parent_id``   — self-FK (hierarchical file collections / folder nesting)
- ``version``     — integer versioning (artifact ``version`` precedent)
- ``workspace_id``/``project_id`` — scope-chain anchoring (GLOBAL→USER→
  WORKSPACE→PROJECT→CHAT→RUN→STEP-এর WORKSPACE/PROJECT ধাপ)

ORM মডেলটি ইচ্ছাকৃতভাবে ``models.base.Base``-এ (canonical DeclarativeBase —
missions/runs প্যাটার্ন) যাতে alembic env metadata + sqlite test create_all
world-এ যোগ দেয়; ``JSON().with_variant(JSONB)`` sqlite-testable রাখে।
বিদ্যমান raw-Supabase writer (chat_upload) অক্ষত — extend, not replace;
মডেলটি পড়ার পথ দেয় (M2-B Context Engine) এবং নতুন লেখকদের ক্যানোনিকাল
ORM পথ দেয়।
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin

# JSON that compiles to ``json`` on SQLite (tests) and ``jsonb`` on PostgreSQL
# (production) — repo-wide pattern (models/system_config.py, runs/models.py).
JSON_VARIANT = JSON().with_variant(JSONB, "postgresql")


def _utcnow() -> datetime:
    """Client-side UTC timestamp factory (MissingGreenlet rule)."""
    return datetime.now(UTC)


class ChatAttachment(Base, TimestampMixin):
    """A user-uploaded file attached to a chat message — now the canonical
    files-metadata surface for the M2 Context Engine (L0/L1/L2 layering)."""

    # Client-side defaults (see _utcnow docstring / missions + runs pattern).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __tablename__ = "chat_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # --- legacy columns (tier_s_features migration; kept verbatim) ---------
    user_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)

    # --- M2-A context metadata (L0/L1/L2 + anchoring) ----------------------
    # L0: one-to-two sentence semantic summary (the budgeter's first pick).
    summary_l0: Mapped[str | None] = mapped_column(Text, nullable=True)
    # L1: structured summary ({"sections": [...], "entities": [...], ...}).
    summary_l1: Mapped[dict[str, Any] | None] = mapped_column(JSON_VARIANT, nullable=True)
    # L2 pointer: reference to the raw source (ref:// semantics formalize in M7;
    # file_path remains the storage-local path).
    content_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Integrity: sha256 hex (chromadb content_hash convention).
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Hierarchical collections (folder/file nesting, dedup groups).
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_attachments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Optimistic versioning (artifact ``version`` precedent).
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # Scope-chain anchors (WORKSPACE / PROJECT levels).
    workspace_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    def __repr__(self) -> str:
        return (
            f"<ChatAttachment(id={self.id!s}, file_name={self.file_name!r}, "
            f"version={self.version})>"
        )
