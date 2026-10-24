"""Add centralized SupremeAI capability connection tables."""

import sqlalchemy as sa
from alembic import op

revision = "2026_09_12_090000"
down_revision = "2026_09_06_120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supremeai_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("connection_type", sa.String(32), nullable=False, server_default="mcp"),
        sa.Column("permission_level", sa.String(32), nullable=False, server_default="user"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("tool_permissions", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "url", name="uq_supremeai_connections_tenant_url"),
    )
    op.create_index("ix_supremeai_connections_tenant", "supremeai_connections", ["tenant_id"])
    op.create_index("ix_supremeai_connections_status", "supremeai_connections", ["status"])

    op.create_table(
        "supremeai_connection_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_supremeai_connection_audit_tenant", "supremeai_connection_audit", ["tenant_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_supremeai_connection_audit_tenant", table_name="supremeai_connection_audit")
    op.drop_table("supremeai_connection_audit")
    op.drop_index("ix_supremeai_connections_status", table_name="supremeai_connections")
    op.drop_index("ix_supremeai_connections_tenant", table_name="supremeai_connections")
    op.drop_table("supremeai_connections")
