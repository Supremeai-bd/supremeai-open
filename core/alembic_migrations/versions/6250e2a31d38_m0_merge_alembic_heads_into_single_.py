"""m0: merge alembic heads into single lineage

Revision ID: 6250e2a31d38
Revises: mcp_gw_0001, a7b8c9d0e1f2, k5l6m7n8o9p0
Create Date: 2026-09-14 20:46:30.127699

"""

from collections.abc import Sequence


# revision identifiers, used by Alembic.
revision: str = "6250e2a31d38"
down_revision: str | Sequence[str] | None = ("mcp_gw_0001", "a7b8c9d0e1f2", "k5l6m7n8o9p0")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
