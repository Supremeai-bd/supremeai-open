"""Create user_execution_mode table for execution-mode self-service persistence.

বাংলা: Universal Zero-Complexity Interface plan-এর "execution mode self-service"
ফিচারটি `user_execution_mode` টেবিলে upsert করে (api/routes/connections.py →
set_execution_mode) — কিন্তু এই টেবিলের কোনো migration ছিল না, ফলে production-এ
persisted=False হয়ে degrade করত (No Silent Failure লঙ্ঘন)। এই migration টেবিলটি
তৈরি করে এবং Constitution-এর tenant isolation নিশ্চিত করতে RLS policy যোগ করে।
"""

import sqlalchemy as sa
from alembic import op

revision = "2026_09_12_190000"
down_revision = "2026_09_12_090000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # বাংলা: user_id-ই natural primary key (প্রতি user-এর একটাই mode) —
    # PostgREST upsert (ON CONFLICT) user_id-কেই conflict target হিসেবে ব্যবহার করে,
    # তাই আলাদা synthetic id রাখলে set_execution_mode-এর upsert ভেঙে যেত।
    op.create_table(
        "user_execution_mode",
        sa.Column("user_id", sa.String(255), primary_key=True),
        sa.Column("mode", sa.String(32), nullable=False, server_default="ask_before_acting"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("user_execution_mode")
