"""Recreate live performance_metrics table — neutralize k5l6m7n8o9p0 drop (issue #1177)

R9-এর "zero writers/readers" দাবিটি পুরনো: `core/self_evolution/performance_oracle.py`
`PerformanceMetric`-এ INSERT (record_metric) ও SELECT (get_agent_stats /
identify_weakest_links) করে, আর `api/routes/agent_breeding.py`-এর লাইভ admin
routes (`POST /metrics`, `GET /metrics/{agent}`, `/weakest-links`,
`/top-performers`) সরাসরি ওরাকলটি ব্যবহার করে।

k5l6m7n8o9p0 (already merged) drops this table on `alembic upgrade head` →
উপরের route-গুলো 500 করবে। History rewrite ঝুঁকিপূর্ণ বলে এই forward migration
টেবিলটি absent হলে হুবহু j9k0l1m2n3o4-এর DDL-এ পুনরায় তৈরি করে:
  * k5l6 applied থাকলে → টেবিল ফেরত আসে (idempotent recreate);
  * k5l6 না-applied থাকলে → টেবিল already আছে → no-op।

Issue #1177; roadmap item 1.10 revision.

Revision ID: t7u8v9w0x1y2
Revises: task_records_0001
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Any

from alembic import context as _alembic_context
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "t7u8v9w0x1y2"
down_revision: str | tuple[str, ...] = "task_records_0001"
branch_labels: Any = None
depends_on: str | tuple[str, ...] = None


def _existing_tables() -> list[str]:
    """Offline mode-এ reflect করা যায় না (MockConnection) — k5l6-এর স্থাপিত
    কনভেনশন অনুসরণ করে খালি তালিকা দেওয়া হয়, ফলে offline plan-এ CREATE
    emission নিশ্চিত হয় (নতুন env-এ টেবিল তৈরি হয়)।"""
    if _alembic_context.is_offline_mode():
        return []
    return sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    """Recreate performance_metrics verbatim from j9k0l1m2n3o4 if absent."""
    if "performance_metrics" in _existing_tables():
        return
    op.create_table(
        "performance_metrics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("agent_name", sa.String(length=255), nullable=False),
        sa.Column("metric_type", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column(
            "context",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Mirror of k5l6m7n8o9p0.upgrade() — drop the table if it exists."""
    if "performance_metrics" not in _existing_tables():
        return
    op.drop_table("performance_metrics")
