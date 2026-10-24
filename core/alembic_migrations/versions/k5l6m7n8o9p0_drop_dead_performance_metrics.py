"""Drop dead performance_metrics table (R9 reconciliation)

SUPERSEDED (issue #1177, 2026-09-25): the R9 "zero writers/readers" finding
was stale — core/self_evolution/performance_oracle.py INSERTs and SELECTs
this table, and live admin routes in api/routes/agent_breeding.py
(POST /metrics, GET /metrics/{agent}, /weakest-links, /top-performers) call
the oracle directly. The subsequent migration t7u8v9w0x1y2 recreates the
table idempotently, so applying both in order is safe (drop → recreate).
This file is kept unmodified for chain integrity — do not apply standalone
against a database that still needs the table.

The performance_metrics table (created by j9k0l1m2n3o4) has zero writers
and zero readers in production. Live code writes to learning_events instead.
This migration removes the dead schema.

IGNORE_SAFETY_WARNING: Table is completely unused in production (0 writers, 0 readers).
Dropping is an intentional dead-code cleanup per R9 architecture reconciliation.

See: docs/architecture/PROJECT_STATUS_RECONCILIATION_2026-09-13.md R9

Revision ID: k5l6m7n8o9p0
Revises: j9k0l1m2n3o4
Create Date: 2026-09-13
"""

from __future__ import annotations

from typing import Any

from alembic import context as _alembic_context
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "k5l6m7n8o9p0"
down_revision: str | tuple[str, ...] = "j9k0l1m2n3o4"
branch_labels: Any = None
depends_on: str | tuple[str, ...] = None


def upgrade() -> None:
    """Drop the dead performance_metrics table if it exists."""
    bind = op.get_bind()
    # Issue #478: offline mode cannot reflect a MockConnection — treat the
    # table as absent in the generated plan; the live run still reflects.
    if _alembic_context.is_offline_mode():
        existing_tables: list[str] = []
    else:
        existing_tables = sa.inspect(bind).get_table_names()

    if "performance_metrics" in existing_tables:
        op.drop_table("performance_metrics")


def downgrade() -> None:
    """Recreate performance_metrics (for rollback only — not used in prod)."""
    op.create_table(
        "performance_metrics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("agent_name", sa.String(length=255), nullable=False),
        sa.Column("metric_type", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column(
            "context",
            sa.JSON().with_variant(
                sa.dialects.postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
