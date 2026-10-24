"""merge_learning_reports — every main-merge saved as a learning report

Founder directive (issue #1929): PR helper records WHY each merge was allowed as
an improvement, WHAT it did, and its held/mistake history — SupremeAI learns from
every change. Chains from head u8v9w0x1y2z3 (single-head guard must stay green).

Revision ID: merge_learn_0001
Revises: u8v9w0x1y2z3
Create Date: 2026-09-27
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "merge_learn_0001"
down_revision: str | Sequence[str] | None = "u8v9w0x1y2z3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # বাংলা মন্তব্য: প্রতিটি main-merge এর লার্নিং রিপোর্ট টেবিল — কেন improvement হিসেবে
    # allow হলো, কী করল, আর কোন কোন ভুলে/আটকে থাকার ইতিহাস (held_history) সেভ হবে।
    op.execute("""
        CREATE TABLE IF NOT EXISTS merge_learning_reports (
            id SERIAL PRIMARY KEY,
            pr_number INTEGER NOT NULL UNIQUE,
            title TEXT NOT NULL,
            author VARCHAR(100) NOT NULL,
            merged_by VARCHAR(100),
            lane VARCHAR(50),
            branch VARCHAR(200) NOT NULL,
            merge_sha VARCHAR(100),
            merged_at BIGINT NOT NULL,
            risk_class VARCHAR(30),
            gate_status VARCHAR(30),
            why_allowed TEXT,
            what_it_did TEXT,
            held_history JSONB,
            linked_issues JSONB,
            files JSONB,
            additions INTEGER DEFAULT 0,
            deletions INTEGER DEFAULT 0,
            lessons_ref TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_merge_learning_pr ON merge_learning_reports(pr_number)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_merge_learning_merged_at ON merge_learning_reports(merged_at DESC)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_merge_learning_lane ON merge_learning_reports(lane)")


def downgrade() -> None:
    """Downgrade schema."""
    # বাংলা মন্তব্য: merge_learning_reports টেবিল ড্রপ
    op.execute("DROP TABLE IF EXISTS merge_learning_reports")
