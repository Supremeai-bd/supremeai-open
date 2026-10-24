"""Create MCP gateway hub tables (mcp_slugs, mcp_tenants, mcp_clients).

বাংলা: Personal MCP Gateway & Multi-Tenant Hub plan (Phase A) — docs/plans/features/
personal_mcp_gateway_multitenant_hub_plan.md §3 অনুযায়ী তিনটি relational টেবিল।

QUOTA-SAFETY NOTE (hard constraint, Task 7-d):
    The hub manages ROUTING and PER-CLIENT credentials under the user's EXISTING
    account/tenant. `mcp_tenants` rows are hub tenancy records keyed by the
    caller's existing tenant identity — they NEVER create a new billable account,
    new quota pool, or any way to circumvent per-tenant limits (max_clients,
    max_tools_per_min, max_token_days are enforced in the management API).

Postgres-only notes:
    - `mcp_slugs.valid_slug_format` uses the Postgres regex operator `~*`; the
      equivalent format is enforced in Python (`models.mcp_gateway.SLUG_RE`) so
      the ORM model stays SQLite-compatible for the test suite.
    - Partial indexes (WHERE status = 'active') are declared via
      `postgresql_where`; on other dialects alembic emits nothing for them.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "mcp_gw_0001"
down_revision = "2026_09_13_100000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. MCP Slugs Registry (vanity & alias mapping)
    op.create_table(
        "mcp_slugs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.String(63), nullable=False, unique=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False, server_default="user"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "slug ~* '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'",
            name="valid_slug_format",
        ),
    )
    # Partial lookup index — only ACTIVE slugs participate in subdomain routing.
    op.create_index(
        "idx_mcp_slugs_lookup",
        "mcp_slugs",
        ["slug"],
        unique=False,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index("idx_mcp_slugs_tenant", "mcp_slugs", ["tenant_id"])

    # 2. MCP Tenants (extended metadata and limits)
    op.create_table(
        "mcp_tenants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner_email", sa.String(255), nullable=False),
        sa.Column("type", sa.String(20), nullable=False, server_default="customer"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("plan", sa.String(20), nullable=False, server_default="free"),
        sa.Column("admin_token_hash", sa.String(64), nullable=False),
        sa.Column("max_clients", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("max_tools_per_min", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("max_token_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column(
            "allowed_categories",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text('\'["github", "ai", "docs", "notify", "knowledge"]\'::jsonb'),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # 3. MCP Clients (per-AI-client credentials)
    op.create_table(
        "mcp_clients",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("mcp_tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False, server_default="generic"),
        sa.Column("protocol", sa.String(30), nullable=False, server_default="streamable-http"),
        sa.Column("role", sa.String(20), nullable=False, server_default="agent"),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text('\'["health:read", "system:read", "tools:execute"]\'::jsonb'),
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("token_prefix", sa.String(12), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    # Partial UNIQUE index on the live-token hash (plan §3 + Task 7-d spec).
    op.create_index(
        "idx_mcp_clients_token_hash",
        "mcp_clients",
        ["token_hash"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index("idx_mcp_clients_tenant", "mcp_clients", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("idx_mcp_clients_tenant", table_name="mcp_clients")
    op.drop_index("idx_mcp_clients_token_hash", table_name="mcp_clients")
    op.drop_table("mcp_clients")
    op.drop_table("mcp_tenants")
    op.drop_index("idx_mcp_slugs_tenant", table_name="mcp_slugs")
    op.drop_index("idx_mcp_slugs_lookup", table_name="mcp_slugs")
    op.drop_table("mcp_slugs")
