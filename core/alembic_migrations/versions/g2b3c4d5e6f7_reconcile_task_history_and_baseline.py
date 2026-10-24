"""reconcile task_history schema + document production baseline drift

Applied directly to production (project <project-ref>) and mirrored
here for version control / future environments (staging, local, CI).

Background: CloudPostgresStore.save_task() INSERTs into
(task_type, prompt, result, provider, cost, latency_ms, success) but the
live task_history table only had (task, approach, result, success,
created_at). This meant every save_task() call was silently failing in
production. Fixed by adding the missing canonical columns and backfilling
from the legacy ones. Legacy columns (task, approach) are kept (not
dropped) to avoid destructive data loss for historical rows.

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-08-30
"""

from typing import Union
from collections.abc import Sequence

from alembic import op

revision: str = "g2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE public.task_history ADD COLUMN IF NOT EXISTS task_type VARCHAR(50);")
    op.execute("ALTER TABLE public.task_history ADD COLUMN IF NOT EXISTS prompt TEXT;")
    op.execute("ALTER TABLE public.task_history ADD COLUMN IF NOT EXISTS provider VARCHAR(100);")
    op.execute("ALTER TABLE public.task_history ADD COLUMN IF NOT EXISTS cost DECIMAL(10,6);")
    op.execute("ALTER TABLE public.task_history ADD COLUMN IF NOT EXISTS latency_ms INTEGER;")
    op.execute("""
        UPDATE public.task_history
        SET prompt = COALESCE(prompt, task),
            task_type = COALESCE(task_type, approach)
        WHERE prompt IS NULL OR task_type IS NULL;
    """)
    op.execute(
        "COMMENT ON COLUMN public.task_history.task IS 'DEPRECATED legacy column, superseded by prompt/task_type.';"
    )
    op.execute(
        "COMMENT ON COLUMN public.task_history.approach IS 'DEPRECATED legacy column, superseded by task_type.';"
    )


def downgrade() -> None:
    # Non-destructive forward migration; no safe automatic downgrade for
    # backfilled data. Columns are left in place intentionally.
    pass
