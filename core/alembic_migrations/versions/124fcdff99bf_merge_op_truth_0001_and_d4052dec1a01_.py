"""merge op_truth_0001 and d4052dec1a01 lineages (#4136)

Revision ID: 124fcdff99bf
Revises: op_truth_0001, d4052dec1a01
Create Date: 2026-10-06 16:20:15.039403

"""

from typing import Sequence, Union  # noqa: UP035, UP007 — alembic template style pinned by graph-unification file

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "124fcdff99bf"
down_revision: str | Sequence[str] | None = ("op_truth_0001", "d4052dec1a01")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
