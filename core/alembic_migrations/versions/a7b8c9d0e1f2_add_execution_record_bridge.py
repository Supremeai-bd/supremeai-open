"""add_execution_record_bridge_columns

Revision ID: a7b8c9d0e1f2
Revises: b30b7a512986, k1l2m3n4o5p6
Create Date: 2026-09-04 12:00:00.000000

Merge of the two existing migration heads plus the durable ExecutionRecord
bridge columns on automation_executions (correlation_id, tenant_id, ... ).

Gap closure: canonical orchestration ExecutionRecord rows were process-local;
this migration gives the orchestrator a durable landing zone for every governed
dispatch (policy decision, evidence, actor/tenant/project/conversation links).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = ("b30b7a512986", "k1l2m3n4o5p6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        ALTER TABLE automation_executions
            ADD COLUMN IF NOT EXISTS correlation_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS project_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS conversation_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS capability VARCHAR(100),
            ADD COLUMN IF NOT EXISTS evidence JSONB,
            ADD COLUMN IF NOT EXISTS policy JSONB
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_executions_correlation_id "
        "ON automation_executions(correlation_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_executions_tenant_id "
        "ON automation_executions(tenant_id)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        ALTER TABLE automation_executions
            DROP COLUMN IF EXISTS correlation_id,
            DROP COLUMN IF EXISTS tenant_id,
            DROP COLUMN IF EXISTS project_id,
            DROP COLUMN IF EXISTS conversation_id,
            DROP COLUMN IF EXISTS capability,
            DROP COLUMN IF EXISTS evidence,
            DROP COLUMN IF EXISTS policy
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_automation_executions_correlation_id")
    op.execute("DROP INDEX IF EXISTS idx_automation_executions_tenant_id")
