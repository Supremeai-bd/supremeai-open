"""add api_keys.scopes column and conversation_context session_id unique index

NOTE ON DRIFT: production's recorded alembic_version was found to be
"2026_08_19_043607", which does not exist anywhere in this migration chain.
This means `alembic upgrade head` cannot safely run against production until
a baseline-reconciliation migration is authored (see audit notes). The two
DDL changes below were verified against the live production schema
(project <project-ref>) before being applied directly, and are
captured here only so the change is tracked in version control. Do NOT
run `alembic upgrade` against production with this file until the
baseline reconciliation migration exists and `alembic stamp` has been
run to align production's version pointer with this chain.

Revision ID: f1a2b3c4d5e6
Revises: 358bcbe79a4a
Create Date: 2026-08-30
"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "358bcbe79a4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE public.api_keys ADD COLUMN IF NOT EXISTS scopes TEXT[] DEFAULT '{}'::text[];"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "uq_conversation_context_session_id "
        "ON public.conversation_context(session_id);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_conversation_context_session_id;")
    op.execute("ALTER TABLE public.api_keys DROP COLUMN IF EXISTS scopes;")
