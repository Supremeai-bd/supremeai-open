"""Add M2 context metadata to chat_attachments (M2-A, OSS plan §4).

বাংলা: M2 Context Engine-এর জন্য বিদ্যমান ``chat_attachments`` টেবিলেই
L0/L1/L2 summary layering + scope anchoring columns যোগ (নতুন context
database নয় — roadmap doctrine: extend existing Files surface)।

- summary_l0  TEXT  (ছোট semantic summary)
- summary_l1  JSONB (structured summary)
- content_ref TEXT  (raw source reference, L2)
- content_hash VARCHAR(64) + index (sha256; chroma convention)
- parent_id   self-FK SET NULL + index (hierarchical collections)
  2026-09-20: column type follows the LIVE prod table — `chat_attachments.id`
  is TEXT there (legacy runtime-created schema, pre-UUID model), and a UUID
  FK to a TEXT column cannot be implemented (DatatypeMismatch, run
  35496566026). TEXT keeps the FK implementable; the ORM type mismatch is
  tracked separately as pre-existing model/prod drift.
- version     INTEGER NOT NULL DEFAULT 1
- workspace_id / project_id VARCHAR(255) + index (scope chain)
- updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()

Existing raw-Supabase writers keep working (additive columns only; every new
column is nullable or server-defaulted). ORM mirror: models/chat_attachment.py.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "2026_09_15_130000"
down_revision = "2026_09_15_120000"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("chat_attachments", sa.Column("summary_l0", sa.Text(), nullable=True))
    op.add_column("chat_attachments", sa.Column("summary_l1", _JSONB, nullable=True))
    op.add_column("chat_attachments", sa.Column("content_ref", sa.Text(), nullable=True))
    op.add_column(
        "chat_attachments",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "chat_attachments",
        sa.Column(
            "parent_id",
            sa.Text(),
            sa.ForeignKey("chat_attachments.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "chat_attachments",
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column("chat_attachments", sa.Column("workspace_id", sa.String(255), nullable=True))
    op.add_column("chat_attachments", sa.Column("project_id", sa.String(255), nullable=True))
    op.add_column(
        "chat_attachments",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index("ix_chat_attachments_content_hash", "chat_attachments", ["content_hash"])
    op.create_index("ix_chat_attachments_parent_id", "chat_attachments", ["parent_id"])
    op.create_index("ix_chat_attachments_workspace_id", "chat_attachments", ["workspace_id"])
    op.create_index("ix_chat_attachments_project_id", "chat_attachments", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_attachments_project_id", table_name="chat_attachments")
    op.drop_index("ix_chat_attachments_workspace_id", table_name="chat_attachments")
    op.drop_index("ix_chat_attachments_parent_id", table_name="chat_attachments")
    op.drop_index("ix_chat_attachments_content_hash", table_name="chat_attachments")
    op.drop_column("chat_attachments", "updated_at")
    op.drop_column("chat_attachments", "project_id")
    op.drop_column("chat_attachments", "workspace_id")
    op.drop_column("chat_attachments", "version")
    op.drop_column("chat_attachments", "parent_id")
    op.drop_column("chat_attachments", "content_hash")
    op.drop_column("chat_attachments", "content_ref")
    op.drop_column("chat_attachments", "summary_l1")
    op.drop_column("chat_attachments", "summary_l0")
