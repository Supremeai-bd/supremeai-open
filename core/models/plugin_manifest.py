from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class PluginManifest(Base):
    __tablename__ = "plugin_manifests"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)  # e.g., 'github', 'notion'
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    icon_url: Mapped[str] = mapped_column(String, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Semantic separation
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # official | mcp | community
    auth_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # oauth | api_key | bearer | none | mcp_url
    execution_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # native_adapter | remote_http | mcp
    trust_level: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # official | verified | community

    tools_provided: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    auth_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    permission_schema: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    install_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")
    manifest_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1")
    minimum_engine_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
