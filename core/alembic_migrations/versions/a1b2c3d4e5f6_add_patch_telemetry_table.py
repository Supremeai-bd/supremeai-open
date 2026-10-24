"""add_patch_telemetry_table

Revision ID: a1b2c3d4e5f6
Revises: cfe7c95dbee2
Create Date: 2026-07-20 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "cfe7c95dbee2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # বাংলা মন্তব্য: Self-Healing ফিডব্যাক লুপের জন্য patch_telemetry টেবিল —
    # আগে এই ডেটা শুধু logger.info() দিয়ে লগ হতো, DB তে কখনো সেভ হতো না (silent data loss)।
    op.execute("""
        CREATE TABLE IF NOT EXISTS patch_telemetry (
            id UUID PRIMARY KEY,
            error_id VARCHAR(255) NOT NULL,
            patch_id VARCHAR(255) NOT NULL,
            file_path VARCHAR(1024) NOT NULL,
            status VARCHAR(32) NOT NULL,
            similarity_score FLOAT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_patch_telemetry_error_id ON patch_telemetry (error_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_patch_telemetry_patch_id ON patch_telemetry (patch_id)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS patch_telemetry")
