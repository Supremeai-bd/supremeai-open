"""create mcp_audit_events table — tamper-evident per-agent audit chain (issue #928)

MCP Tower gap-4: append-only audit table with tenant-scoped hash chain
(prev_hash/entry_hash). Application layer (core/mcp_audit_chain.py) only ever
INSERTs; UPDATE/DELETE must be denied at the database layer too — see
docs/governance/mcp_audit_retention.md for the Supabase RLS SQL.

Revision ID: u8v9w0x1y2z3
Revises: t7u8v9w0x1y2
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "u8v9w0x1y2z3"
down_revision: str | Sequence[str] | None = "t7u8v9w0x1y2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_tables_offline_safe(bind) -> set[str]:
    """offline/online দুই মোডেই চলে — existing table নামের সেট বের করে।"""
    try:
        inspector = sa.inspect(bind)
        return set(inspector.get_table_names())
    except Exception:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    existing = _existing_tables_offline_safe(bind)
    if "mcp_audit_events" in existing:
        # Idempotent: আগেই থাকলে কিছু না করা (converge semantics)।
        return

    op.create_table(
        "mcp_audit_events",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False, server_default="unknown"),
        sa.Column("client_role", sa.String(length=64), nullable=False, server_default="agent"),
        sa.Column("provider", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column("server", sa.String(length=255), nullable=False, server_default="supremeai-mcp"),
        sa.Column("tool", sa.String(length=255), nullable=False),
        sa.Column("args_hash", sa.String(length=64), nullable=False),
        sa.Column("result_status", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("result_ref", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("hitl_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hitl_approver", sa.String(length=255), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_mcp_audit_events_tenant_ts", "mcp_audit_events", ["tenant_id", "ts"])
    op.create_index("ix_mcp_audit_events_agent_ts", "mcp_audit_events", ["agent_id", "ts"])
    # entry_hash ইউনিক — একই event দুইবার append হতে পারে না (hash collision নগণ্য)।
    op.create_unique_constraint(
        "uq_mcp_audit_events_entry_hash", "mcp_audit_events", ["entry_hash"]
    )


def downgrade() -> None:
    # Append-only চুক্তি ভাঙা ছাড়া downgrade-এর অর্থ পুরো টেবিল ফেলে দেওয়া;
    # সেটিই এখানে করা হয় (audit history হারানোর ঝুঁকি owner-দৃষ্টিতে জানানো)।
    bind = op.get_bind()
    existing = _existing_tables_offline_safe(bind)
    if "mcp_audit_events" not in existing:
        return
    op.drop_constraint("uq_mcp_audit_events_entry_hash", "mcp_audit_events", type_="unique")
    op.drop_index("ix_mcp_audit_events_agent_ts", table_name="mcp_audit_events")
    op.drop_index("ix_mcp_audit_events_tenant_ts", table_name="mcp_audit_events")
    op.drop_table("mcp_audit_events")
