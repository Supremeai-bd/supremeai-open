"""SupremeAI MCP Gateway Hub models (Personal MCP Gateway plan, Phase A).

Tables (docs/plans/features/personal_mcp_gateway_multitenant_hub_plan.md §3):
    - ``mcp_slugs``   vanity/alias slug → tenant routing registry
    - ``mcp_tenants`` hub tenancy record + limits for an EXISTING account tenant
    - ``mcp_clients`` per-AI-client credentials (SHA-256 hashed bearer tokens)

QUOTA-SAFETY NOTE (hard constraint, Task 7-d):
    These tables manage ROUTING and PER-CLIENT credentials under the user's
    EXISTING account/tenant. A ``McpTenant`` row is the hub's tenancy record for
    an identity that already exists in the platform (keyed by the caller's
    tenant_id from the verified JWT) — it never creates a new billable account,
    quota pool, or circumvention path. Limits (max_clients, max_tools_per_min,
    max_token_days) are enforced by ``api.routes.mcp_hub``.

SQLite/Postgres compatibility:
    - UUID primary keys use ``postgresql.UUID(as_uuid=True)`` — on SQLAlchemy 2.0
      this subclasses the generic ``Uuid`` type and transparently falls back to a
      CHAR(32) value on SQLite (same pattern as ``models.system_config`` /
      ``models.integration``, both created on SQLite by the test suite).
    - JSONB columns use ``JSON().with_variant(JSONB, "postgresql")`` (same as
      ``models.crawler`` / ``models.system_config``).
    - The Postgres-only ``slug ~* '...'`` CHECK constraint lives in the Alembic
      migration (``mcp_gw_0001``) ONLY — SQLite cannot evaluate the ``~*``
      operator, so the equivalent format is enforced in Python here via
      ``SLUG_RE`` / ``is_valid_slug()`` and by the management API.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base

# Vanity slug contract (mirrors the migration's `valid_slug_format` CHECK).
# Up to 63 chars, lowercase alphanumeric, may not start/end with a hyphen.
SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

# Slugs that would collide with platform routing/infrastructure hostnames.
RESERVED_SLUGS = frozenset(
    {"admin", "api", "app", "core", "system", "hub", "auth", "www", "mail", "root"}
)

# DDL defaults (plan §3) — kept here so lazily-created rows match the SQL schema.
DEFAULT_ALLOWED_CATEGORIES = ["github", "ai", "docs", "notify", "knowledge"]
DEFAULT_CLIENT_SCOPES = ["health:read", "system:read", "tools:execute"]

JSONType = JSON().with_variant(JSONB, "postgresql")


def is_valid_slug(slug: str) -> bool:
    """Return True when ``slug`` satisfies the vanity-slug format contract."""
    return bool(slug) and SLUG_RE.match(slug) is not None


def _utcnow() -> datetime:
    return datetime.now(UTC)


class McpSlug(Base):
    """Vanity/alias subdomain slug mapped to a hub tenant."""

    __tablename__ = "mcp_slugs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        # Partial lookup index on Postgres (only ACTIVE slugs route traffic);
        # other dialects (SQLite tests) simply materialise the full index.
        Index(
            "idx_mcp_slugs_lookup",
            "slug",
            postgresql_where=text("status = 'active'"),
        ),
    )

    def __repr__(self) -> str:
        return f"<McpSlug slug={self.slug!r} tenant={self.tenant_id!r} status={self.status!r}>"


class McpTenant(Base):
    """Hub tenancy + limits record for an EXISTING platform tenant.

    This is NOT a new account: ``id`` is the caller's existing tenant identity
    (from the verified JWT). The ``admin_token_hash`` is the SHA-256 of the
    gateway admin secret provisioned for the Node control-plane (Phase B, its
    plaintext is never exposed by this backend).
    """

    __tablename__ = "mcp_tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="customer")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    plan: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    admin_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Limits — enforced server-side by api/routes/mcp_hub.py (no circumvention).
    max_clients: Mapped[int] = mapped_column(nullable=False, default=10)
    max_tools_per_min: Mapped[int] = mapped_column(nullable=False, default=120)
    max_token_days: Mapped[int] = mapped_column(nullable=False, default=90)
    allowed_categories: Mapped[list[Any]] = mapped_column(
        JSONType, nullable=False, default=lambda: list(DEFAULT_ALLOWED_CATEGORIES)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return f"<McpTenant id={self.id!r} plan={self.plan!r} status={self.status!r}>"


class McpClient(Base):
    """Per-AI-client credential (Cursor, Claude, Gemini, VS Code, custom…).

    The bearer token is shown to the user EXACTLY ONCE at creation/rotation;
    only ``token_hash`` (SHA-256 hex, 64 chars) is persisted.
    """

    __tablename__ = "mcp_clients"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("mcp_tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="generic")
    protocol: Mapped[str] = mapped_column(String(30), nullable=False, default="streamable-http")
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="agent")
    scopes: Mapped[list[Any]] = mapped_column(
        JSONType, nullable=False, default=lambda: list(DEFAULT_CLIENT_SCOPES)
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    token_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        # Partial UNIQUE index for live-token lookups (plan §3 + Task 7-d spec).
        Index(
            "idx_mcp_clients_token_hash",
            "token_hash",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("idx_mcp_clients_tenant", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<McpClient id={self.id!r} tenant={self.tenant_id!r} status={self.status!r}>"
