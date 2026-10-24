"""SQLAlchemy models for Layer 4: Localization & UX.

BhashaBot translation cache and VoiceDidi voice processing records.
"""

# বাংলা মন্তব্য: ল্যারালাইজেশন ও ভয়েস সেশন ডেটা সংরক্ষণের জন্য টেবিল ও স্কিমা।

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class TranslationCache(Base):
    """Stores BhashaBot translation results for performance and cost optimization."""

    # বাংলা মন্তব্য: ভাষা-বট অনুবাদের ক্যাশ ডেটা স্টোরেজ
    __tablename__ = "translation_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_text: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    source_lang: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    target_lang: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    translated_text: Mapped[str] = mapped_column(Text, nullable=False)
    context_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )  # SHA-256 of context metadata
    quality_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )  # 0.0-1.0, user feedback or BLEU
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class VoiceSession(Base):
    """VoiceDidi voice command session records for analytics and improvement."""

    # বাংলা মন্তব্য: ভয়েস-দিদি ভয়েস সেশন ট্র্যাকিং এবং এনালিটিক্স টেবিল
    __tablename__ = "voice_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    audio_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recognized_text_bn: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    intent_detected: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action_taken: Mapped[str | None] = mapped_column(String(255), nullable=True)
    success: Mapped[bool] = mapped_column(default=True, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # JSONB for flexible metadata: device info, noise level, regional accent, etc.
    metadata_json: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
