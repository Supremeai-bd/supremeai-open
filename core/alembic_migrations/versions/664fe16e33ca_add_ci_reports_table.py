"""add_ci_reports_table

Revision ID: 664fe16e33ca
Revises:
Create Date: 2026-06-29 02:10:12.661696

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "664fe16e33ca"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # বাংলা মন্তব্য: গিটহাব রানার থেকে লগ পুশ করার পরিবর্তে ডেটাবেসে লগ রাখার জন্য ci_reports টেবিল তৈরি করা হলো
    op.execute("""
        CREATE TABLE IF NOT EXISTS ci_reports (
            id SERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL UNIQUE,
            run_number INTEGER,
            event_name VARCHAR(50),
            actor VARCHAR(100),
            workflow_name VARCHAR(150),
            status VARCHAR(50) NOT NULL,
            runtime_seconds INTEGER,
            commit_sha VARCHAR(100),
            branch VARCHAR(100),
            jobs_summary JSONB,
            error_logs TEXT,
            created_at INTEGER NOT NULL
        )
        """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_ci_reports_run_id ON ci_reports(run_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ci_reports_created ON ci_reports(created_at DESC)")


def downgrade() -> None:
    """Downgrade schema."""
    # বাংলা মন্তব্য: ci_reports টেবিল ড্রপ করা হচ্ছে
    op.execute("DROP TABLE IF EXISTS ci_reports")
