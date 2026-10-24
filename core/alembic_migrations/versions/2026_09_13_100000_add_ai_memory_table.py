"""Create canonical ai_memory table with pgvector support (Phase C).

বাংলা: CHECKPOINT.md-তে থাকা দীর্ঘদিনের বকেয়া "Supabase ai_memory table setup (Phase C)"
টাস্কটি এতদিন শুধু ম্যানুয়াল docs/api-database/migrations/ai_memory_migration.sql হিসেবে ছিল।
সংবিধানের "Production Parity" ও "Single Source of Truth" নীতি অনুযায়ী সমস্ত ডাটাবেজ
স্কিমা Alembic-এর মাধ্যমে পরিচালিত হতে হবে (Manual SQL Runner নিষিদ্ধ)।
এই মাইগ্রেশনটি canonical `ai_memory` টেবিল তৈরি করে, semantic search-এর জন্য pgvector
এবং HNSW/IVFFlat ইনডেক্সিং এবং match_ai_memory RPC সাপোর্ট যুক্ত করে।
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "2026_09_13_100000"
down_revision = "2026_09_13_090000"
branch_labels = None
depends_on = None


def _inspect_offline_safe(bind):
    """Issue #478 convention (see 7c4d9e1f2a3b): offline mode cannot inspect
    (MockConnection) — degrade to None so the generated SQL plan keeps the
    DDL; the live run guards with the real inspector.

    2026-09-20: the live DB already contains `ai_memory` (runtime-managed
    create_all before the Migration Gate existed) — un-guarded re-create hit
    `DuplicateTable: relation "ai_memory" already exists` once the deploy
    chain (always() gate, PR #811) started running this job.
    """
    from alembic import context

    if context.is_offline_mode():
        return None
    return sa.inspect(bind)


def upgrade() -> None:
    bind = op.get_bind()
    insp = _inspect_offline_safe(bind)
    tables = set(insp.get_table_names()) if insp else set()

    # 1. Ensure pgvector extension exists
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Create canonical ai_memory table
    if "ai_memory" not in tables:
        op.create_table(
            "ai_memory",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("user_id", sa.String(255), nullable=True, index=True),
            sa.Column("session_id", sa.String(255), nullable=False, index=True),
            sa.Column("agent_type", sa.String(64), nullable=False, server_default="main"),
            sa.Column("task_type", sa.String(64), nullable=False, server_default="general"),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column(
                "metadata",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    # 3. Add vector column (384 dims for all-MiniLM-L6-v2, extensible)
    op.execute("ALTER TABLE ai_memory ADD COLUMN IF NOT EXISTS embedding vector(384);")

    # 4. Indexes for filtering and semantic lookup (partial-drift guarded)
    existing_indexes = (
        {ix["name"] for ix in insp.get_indexes("ai_memory")}
        if insp and "ai_memory" in tables
        else set()
    )
    if "ix_ai_memory_user_task" not in existing_indexes:
        op.create_index("ix_ai_memory_user_task", "ai_memory", ["user_id", "task_type"])
    if "ix_ai_memory_created_at_desc" not in existing_indexes:
        op.create_index("ix_ai_memory_created_at_desc", "ai_memory", [sa.text("created_at DESC")])

    # Try creating vector index if memory allows, fallback gracefully
    op.execute("""
        DO $$
        BEGIN
            CREATE INDEX IF NOT EXISTS ix_ai_memory_embedding_ivfflat
                ON ai_memory
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
        EXCEPTION
            WHEN OTHERS THEN
                RAISE NOTICE 'Vector index creation deferred or handled by Supabase: %', SQLERRM;
        END $$;
    """)

    # 5. Create match_ai_memory RPC function for Supabase/PostgREST
    op.execute("""
        CREATE OR REPLACE FUNCTION match_ai_memory(
            query_embedding VECTOR(384),
            match_threshold FLOAT DEFAULT 0.55,
            match_count     INT DEFAULT 5,
            p_user_id     TEXT DEFAULT NULL
        )
        RETURNS TABLE (
            id          UUID,
            session_id  TEXT,
            agent_type  TEXT,
            task_type   TEXT,
            summary     TEXT,
            metadata    JSONB,
            created_at  TIMESTAMPTZ,
            similarity  FLOAT
        )
        LANGUAGE SQL STABLE
        AS $$
            SELECT
                id,
                session_id,
                agent_type,
                task_type,
                summary,
                metadata,
                created_at,
                1 - (embedding <=> query_embedding) AS similarity
            FROM ai_memory
            WHERE (p_user_id IS NULL OR user_id = p_user_id)
              AND 1 - (embedding <=> query_embedding) >= match_threshold
            ORDER BY embedding <=> query_embedding
            LIMIT match_count;
        $$;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS match_ai_memory(VECTOR, FLOAT, INT, TEXT);")
    op.drop_table("ai_memory")
