"""Project Space ORM model (ERR-B01, canonical defect register 2026-09-15).

বাংলা: ERR-B01 অনুযায়ী `/projects` (WorkspaceModulePage) ছিল সম্পূর্ণ স্ট্যাটিক —
"Create a project space" ক্লিক কিছুই করত না, কোনো প্রজেক্ট লিস্টিং/রিনেম/ডিলিট ছিল না।
এই মডেলটি সেই ফাঁক পূরণ করে — canonical `models.base.Base` (missions/runs প্যাটার্ন)-এ
বসে যাতে alembic env metadata + sqlite test create_all world-এ স্বয়ংক্রিয়ভাবে যোগ দেয়।

`ChatAttachment.project_id` (tier_s_features migration) already carries the
``project_id`` scope anchor — this table is the anchor target, so uploaded files
can be scoped to a project space without any further schema drift.
"""

from __future__ import annotations

import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class Project(Base, TimestampMixin):
    """A user-owned Project Space: the durable container that groups
    conversations, files, and decisions so work compounds instead of
    disappearing (WorkspaceModulePage 'projects' module contract)."""

    __tablename__ = "projects"

    # UUID primary key as string — sqlite-testable while staying UUID-typed on
    # PostgreSQL (repo-wide pattern for user-facing resource ids).
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    owner_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # active | archived — mirrors github_repos.status semantics
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Project id={self.id} name={self.name!r} owner={self.owner_id}>"
