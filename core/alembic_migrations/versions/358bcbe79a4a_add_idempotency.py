"""add idempotency

Revision ID: 358bcbe79a4a
Revises: 2f7b3c5f620e
Create Date: 2026-08-28 19:42:24.563678

"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "358bcbe79a4a"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add idempotency_key to automation_executions
    op.add_column(
        "automation_executions", sa.Column("idempotency_key", sa.String(length=100), nullable=True)
    )
    op.create_index(
        op.f("ix_automation_executions_idempotency_key"),
        "automation_executions",
        ["idempotency_key"],
        unique=False,
    )

    # Create unique constraint
    op.create_unique_constraint(
        "uq_automation_workflow_idempotency",
        "automation_executions",
        ["workflow_key", "idempotency_key"],
    )

    # Create automation_execution_attempts table
    op.create_table(
        "automation_execution_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["execution_id"], ["automation_executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_automation_execution_attempts_execution_id"),
        "automation_execution_attempts",
        ["execution_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_automation_execution_attempts_execution_id"),
        table_name="automation_execution_attempts",
    )
    op.drop_table("automation_execution_attempts")
    op.drop_constraint(
        "uq_automation_workflow_idempotency", "automation_executions", type_="unique"
    )
    op.drop_index(
        op.f("ix_automation_executions_idempotency_key"), table_name="automation_executions"
    )
    op.drop_column("automation_executions", "idempotency_key")
