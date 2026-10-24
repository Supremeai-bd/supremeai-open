import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class UserPluginInstallation(Base):
    __tablename__ = "user_plugin_installations"
    __table_args__ = (Index("idx_user_plugins_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    plugin_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("plugin_manifests.id"), nullable=False
    )
    integration_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integrations.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="installed"
    )  # installed | pending_auth | error
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    granted_capabilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    installed_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")
    config_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1")

    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    health_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="healthy"
    )  # healthy | degraded | broken
