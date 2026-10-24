"""Persist Core API task gateway records."""

import sqlalchemy as sa
from alembic import op

revision = "task_records_0001"
down_revision = "2026_09_15_130000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_records",
        sa.Column("task_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_task_records_tenant", "task_records", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("idx_task_records_tenant", table_name="task_records")
    op.drop_table("task_records")
