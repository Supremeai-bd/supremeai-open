"""merge heads

Revision ID: cb8d8501f289
Revises: 2026_08_15_145220, tier_s_001
Create Date: 2026-08-26 08:56:11.458438

"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cb8d8501f289"
down_revision: str | Sequence[str] | None = ("2026_08_15_145220", "tier_s_001")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
