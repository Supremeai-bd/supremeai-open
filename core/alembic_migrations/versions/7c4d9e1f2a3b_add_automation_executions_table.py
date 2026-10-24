"""add missing automation_executions table

Root cause: models/automation_execution.py has defined the AutomationExecution
ORM model (__tablename__ = "automation_executions") for a long time, and later
migrations (358bcbe79a4a_add_idempotency, j9k0l1m2n3o4_add_missing_live_model_tables)
both ALTER/reference this table assuming it already exists — but no migration
ever actually CREATE TABLE'd it. In production this caused
`relation "automation_executions" does not exist` whenever
core/maintenance_pipeline.py's retention-cleanup job ran its DELETE.
This migration creates the table (idempotently, matching the ORM model), so
the chain becomes internally consistent again.

Revision ID: a1b2c3d4e5f6
Revises: 2f7b3c5f620e
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c4d9e1f2a3b"
down_revision: str | Sequence[str] | None = "2f7b3c5f620e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_tables_offline_safe(bind) -> set[str]:
    """Issue #478: offline mode cannot inspect (MockConnection) — degrade to
    empty set so the generated SQL plan unconditionally contains the DDL;
    the live run still guards with the real inspector."""
    from alembic import context

    if context.is_offline_mode():
        return set()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = _existing_tables_offline_safe(bind)

    if "automation_executions" not in existing_tables:
        op.create_table(
            "automation_executions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("event_id", sa.String(length=36), nullable=False),
            sa.Column("workflow_key", sa.String(length=100), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=50), server_default="PENDING"),
            sa.Column("attempt", sa.Integer(), server_default="1"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("http_status", sa.Integer(), nullable=True),
            sa.Column("external_execution_id", sa.String(length=100), nullable=True),
            sa.Column("trace_id", sa.String(length=100), nullable=True),
            sa.Column("error_code", sa.String(length=100), nullable=True),
            sa.Column("error_message", sa.String(length=1024), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            op.f("ix_automation_executions_event_id"),
            "automation_executions",
            ["event_id"],
        )
        op.create_index(
            op.f("ix_automation_executions_workflow_key"),
            "automation_executions",
            ["workflow_key"],
        )
        op.create_index(
            op.f("ix_automation_executions_status"),
            "automation_executions",
            ["status"],
        )
        op.create_index(
            op.f("ix_automation_executions_trace_id"),
            "automation_executions",
            ["trace_id"],
        )
        op.create_index(
            op.f("ix_automation_executions_created_at"),
            "automation_executions",
            ["created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "automation_executions" in inspector.get_table_names():
        op.drop_table("automation_executions")
