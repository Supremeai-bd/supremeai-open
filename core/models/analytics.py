"""SQLAlchemy models for Layer 5: Data & Analytics.

InsightMage auto-reports and ChurnProphet retention predictions.
"""

# বাংলা মন্তব্য: ডাটা এনালিটিক্স ও চুরন প্রেডিকশন সম্পর্কিত টেবিলসমূহ।

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class AutoReport(Base):
    """InsightMage generated auto-reports from Firestore analytics data."""

    # বাংলা মন্তব্য: ইনসাইট-মেজ দ্বারা জেনারেটেড রিপোর্টের ক্যাশ টেবিল
    __tablename__ = "auto_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # trend, anomaly, summary, forecast
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    data_source: Mapped[str] = mapped_column(String(100), nullable=False)  # firestore_table_name
    metrics_json: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )  # extracted metrics
    natural_language_summary: Mapped[str] = mapped_column(Text, nullable=False)
    anomaly_detected: Mapped[bool] = mapped_column(default=False, nullable=False)
    severity: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # low, medium, high, critical

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChurnPrediction(Base):
    """ChurnProphet churn risk predictions per user."""

    # বাংলা মন্তব্য: চুরন-প্রফেট ইউজার চুরন প্রেডিকশন টেবিল
    __tablename__ = "churn_predictions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    churn_risk_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0-1.0
    risk_level: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # low, medium, high, critical
    factors_json: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )  # top contributing factors
    recommended_actions: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)

    # Feedback loop: did the user actually churn?
    actual_churned: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    predicted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RetentionAction(Base):
    """Tracked retention actions taken based on ChurnProphet recommendations."""

    # বাংলা মন্তব্য: চুরন রোধে নেওয়া পদক্ষেপের ট্র্যাকিং টেবিল
    __tablename__ = "retention_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    churn_prediction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # push_notification, discount, personal_call, etc.
    action_content: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_response: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # opened, ignored, converted, churned
    effectiveness_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # calculated post-facto

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
