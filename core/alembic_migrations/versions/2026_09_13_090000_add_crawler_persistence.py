"""Create crawler persistence tables (crawl_policies, crawl_history, crawl_events).

বাংলা: MASTER_PLAN Phase 1 ("Scout goes live") — আগে crawl policy/history শুধু
in-memory রাখা হতো (api/routes/crawler_admin.py-র module-level dict/list)। ফলে
service restart-এ সব governance policy আর audit trail মুছে যেত — "No Silent
Failure" ও "Memory Must Compound" constitution-এর সরাসরি লঙ্ঘন। এই migration
তিনটি tenant-scoped টেবিল তৈরি করে যাতে governed crawl-এর policy, history ও
telemetry event প্রোডাকশনে durable থাকে।

RLS নোট (Supabase): এই টেবিলগুলো শুধু service-role client (db.client) দিয়ে
লেখা/পড়া হয় এবং API লেয়ারে get_project_admin guard প্রতি-টেন্যান্ট isolation
এনফোর্স করে (crawler_admin.py router dependency)। তাই এখানে per-row RLS
policy-র বদলে API-layer authorization-ই canonical guard।
"""

import sqlalchemy as sa
from alembic import op

revision = "2026_09_13_090000"
down_revision = "2026_09_12_190000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crawl_policies",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_depth", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("max_results", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("default_rate_limit_per_min", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("request_timeout_seconds", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("cache_ttl_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("allowed_domains", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("blocked_domains", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("domain_rules", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_crawl_policies_tenant", "crawl_policies", ["tenant_id"])

    op.create_table(
        "crawl_history",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(128), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("sources_crawled", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("total_pages_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_pages_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_content_hash", sa.String(128), nullable=False, server_default=""),
        sa.Column("extractive_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("token_reduction_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_crawl_history_tenant", "crawl_history", ["tenant_id"])
    op.create_index("ix_crawl_history_task", "crawl_history", ["task_id"])

    op.create_table(
        "crawl_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("task_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("severity", sa.String(16), nullable=False, server_default="INFO"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_crawl_events_tenant", "crawl_events", ["tenant_id"])
    op.create_index("ix_crawl_events_task", "crawl_events", ["task_id"])


def downgrade() -> None:
    op.drop_table("crawl_events")
    op.drop_table("crawl_history")
    op.drop_table("crawl_policies")
