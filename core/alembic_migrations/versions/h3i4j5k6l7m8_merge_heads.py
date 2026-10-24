"""merge heads

বাংলা মন্তব্য: g2b3c4d5e6f7 branch-টাকে মূল chain-এর সাথে মার্জ করা হচ্ছে।
আগে এই migration সরাসরি tier_s_001 এবং 2026_08_15_145220-কেও আবার merge
করছিল, কিন্তু cb8d8501f289 migration-টা আগেই (2026-08-26) সেই দুইটা branch
merge করে ফেলেছিল এবং তার উপরে 2f7b3c5f620e ও 7c4d9e1f2a3b chain হিসেবে যুক্ত
হয়েছে। ফলে একই branch দুইবার merge হওয়ায় competing/overlapping merge head
তৈরি হচ্ছিল। এখন g2b3c4d5e6f7-কে সরাসরি সেই chain-এর বর্তমান tip
(7c4d9e1f2a3b)-এর সাথে merge করা হলো যাতে single, linear head বজায় থাকে।

Revision ID: h3i4j5k6l7m8
Revises: g2b3c4d5e6f7, 7c4d9e1f2a3b
Create Date: 2026-08-30
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "h3i4j5k6l7m8"
down_revision: str | Sequence[str] | None = (
    "g2b3c4d5e6f7",
    "7c4d9e1f2a3b",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """কোনো schema পরিবর্তন নেই -- শুধু branch merge।"""
    pass


def downgrade() -> None:
    """কোনো schema পরিবর্তন নেই -- শুধু branch merge।"""
    pass
