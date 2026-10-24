"""create decision_metadata table — agent decision provenance chain (#4052)

Roadmap v2 §3.2: records every agent decision with the 13-field metadata
schema (evidence + confidence + outcome + policy_context + verification +
supersedes). Provenance chain: superseded decisions are marked
``status='deprecated'``, NEVER deleted — the FK self-reference keeps the
chain queryable. Application layer: ``core/learning/decision_store.py``.

বাংলা: verification ফিল্ডই মূল — "সিদ্ধান্ত কাজ করেছিল কি না" শেখা হয়
সেখান থেকেই। পুরোনো সিদ্ধান্ত মুছে ফেলা হয় না (provenance preserved)।

Revision ID: d4052dec1a01
Revises: b30b7a512986
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4052dec1a01"
down_revision: str | Sequence[str] | None = "b30b7a512986"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_tables(bind) -> set[str]:
    try:
        inspector = sa.inspect(bind)
        return set(inspector.get_table_names())
    except Exception:  # pragma: no cover - offline mode
        return set()


def upgrade() -> None:
    if "decision_metadata" in _existing_tables(op.get_bind()):
        return  # idempotent — create_all-based envs may already have it

    op.create_table(
        "decision_metadata",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=True),
        sa.Column("agent_type", sa.String(50), nullable=False, index=True),
        sa.Column("task_type", sa.String(50), nullable=False, index=True),
        sa.Column("decision", sa.String(255), nullable=False),
        sa.Column("why", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=False, server_default="pending", index=True),
        sa.Column("reusability", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("policy_context", sa.JSON(), nullable=True),
        sa.Column("verification", sa.Text(), nullable=True),
        sa.Column("supersedes", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active", index=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["supersedes"], ["decision_metadata.id"]),
    )
    op.create_index("ix_decision_metadata_supersedes", "decision_metadata", ["supersedes"])


def downgrade() -> None:
    op.drop_index("ix_decision_metadata_supersedes", table_name="decision_metadata")
    op.drop_table("decision_metadata")
