"""
system_config.py — Database-Driven Configuration Model
=======================================================
SupremeAI 2.0-এর জন্য centralized key-value config টেবিল।
এখানে cache thresholds, provider metadata, rate limits, feature flags
সবকিছু DB-তে রাখা হবে — যাতে config পাল্টাতে re-deploy না লাগে।

Phase 1 — True Database-Driven Core
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class SystemConfig(Base):
    """
    Centralized key-value configuration store.

    বাংলা মন্তব্য: প্রতিটা "logic decision" যা বর্তমানে কোডে hardcode করা আছে
    (cache threshold, provider base_url, rate limits, feature flags) —
    সেগুলো এখানে DB row হিসেবে রাখা হবে। Config পাল্টাতে আর re-deploy লাগবে না।

    TTL caching layer (ConfigCache) এই টেবিলের ওপর বসবে —
    প্রতি request-এ DB hit না করে in-memory cache serve করবে,
    এবং change-event এলে cache invalidate হবে।
    """

    __tablename__ = "system_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    value: Mapped[Any] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="general")
    is_active: Mapped[bool] = mapped_column(default=True)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        return f"<SystemConfig key='{self.key}' category='{self.category}'>"
