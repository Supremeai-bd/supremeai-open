"""add missing indexes

Revision ID: 2f7b3c5f620e
Revises: cb8d8501f289
Create Date: 2026-08-26 08:56:21.239577

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect


revision: str = "2f7b3c5f620e"
down_revision: str | Sequence[str] | None = "cb8d8501f289"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    """Return whether an optional table exists on the current database.

    Issue #478: offline mode (``alembic upgrade --sql``) has no live
    connection — inspection is impossible on the MockConnection. The CI
    migration gate verifies the FULL chain offline, so optional-table
    guards must degrade to ``True`` there (emitting unconditional DDL in
    the generated plan is correct: the live run still guards).
    """
    from alembic import context

    if context.is_offline_mode():
        return True
    return inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    """Add missing indexes; real creation failures must fail the migration."""
    op.create_index("idx_artifacts_user_id", "artifacts", ["user_id"], if_not_exists=True)
    print("Created index: idx_artifacts_user_id")
    op.create_index(
        "idx_artifacts_conversation_id", "artifacts", ["conversation_id"], if_not_exists=True
    )
    print("Created index: idx_artifacts_conversation_id")
    op.create_index("idx_artifacts_updated_at", "artifacts", ["updated_at"], if_not_exists=True)
    print("Created index: idx_artifacts_updated_at")
    op.create_index(
        "idx_artifacts_user_updated", "artifacts", ["user_id", "updated_at"], if_not_exists=True
    )
    print("Created index: idx_artifacts_user_updated")
    op.create_index("idx_artifacts_type", "artifacts", ["artifact_type"], if_not_exists=True)
    print("Created index: idx_artifacts_type")
    op.create_index(
        "idx_artifacts_pinned", "artifacts", ["user_id", "is_pinned"], if_not_exists=True
    )
    print("Created index: idx_artifacts_pinned")
    op.create_index("idx_conversations_user_id", "conversations", ["user_id"], if_not_exists=True)
    print("Created index: idx_conversations_user_id")
    op.create_index(
        "idx_conversations_created", "conversations", ["user_id", "created_at"], if_not_exists=True
    )
    print("Created index: idx_conversations_created")
    op.create_index(
        "idx_messages_conversation_id", "messages", ["conversation_id"], if_not_exists=True
    )
    print("Created index: idx_messages_conversation_id")
    op.create_index(
        "idx_messages_conv_created",
        "messages",
        ["conversation_id", "created_at"],
        if_not_exists=True,
    )
    print("Created index: idx_messages_conv_created")
    op.create_index("idx_users_email", "users", ["email"], unique=True, if_not_exists=True)
    print("Created index: idx_users_email (unique)")
    op.create_index("idx_users_sub", "users", ["sub"], if_not_exists=True)
    print("Created index: idx_users_sub")
    op.create_index(
        "idx_user_prefs_user_id", "user_preferences", ["user_id"], unique=True, if_not_exists=True
    )
    print("Created index: idx_user_prefs_user_id (unique)")

    if _table_exists("knowledge_base"):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_knowledge_base_user_embedding
            ON knowledge_base USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            """
        )
        print("Created index: idx_knowledge_base_user_embedding (HNSW)")
        op.create_index(
            "idx_knowledge_base_user_id", "knowledge_base", ["user_id"], if_not_exists=True
        )
        print("Created index: idx_knowledge_base_user_id")
    else:
        print("Skipped knowledge_base indexes: table does not exist")

    if _table_exists("activity_logs"):
        op.create_index(
            "idx_activity_logs_user_time",
            "activity_logs",
            ["user_id", "created_at"],
            if_not_exists=True,
        )
        print("Created index: idx_activity_logs_user_time")
    else:
        print("Skipped activity_logs index: table does not exist")

    if _table_exists("telemetry"):
        op.create_index(
            "idx_telemetry_session", "telemetry", ["session_id", "timestamp"], if_not_exists=True
        )
        print("Created index: idx_telemetry_session")
    else:
        print("Skipped telemetry index: table does not exist")

    print("Migration complete: all applicable indexes created.")


def downgrade() -> None:
    """Remove indexes created by this migration when their tables exist."""
    index_tables = {
        "artifacts": [
            "idx_artifacts_user_id",
            "idx_artifacts_conversation_id",
            "idx_artifacts_updated_at",
            "idx_artifacts_user_updated",
            "idx_artifacts_type",
            "idx_artifacts_pinned",
        ],
        "conversations": ["idx_conversations_user_id", "idx_conversations_created"],
        "messages": ["idx_messages_conversation_id", "idx_messages_conv_created"],
        "users": ["idx_users_email", "idx_users_sub"],
        "user_preferences": ["idx_user_prefs_user_id"],
        "knowledge_base": ["idx_knowledge_base_user_id", "idx_knowledge_base_user_embedding"],
        "activity_logs": ["idx_activity_logs_user_time"],
        "telemetry": ["idx_telemetry_session"],
    }
    for table_name, index_names in index_tables.items():
        if not _table_exists(table_name):
            continue
        for index_name in index_names:
            op.drop_index(index_name, table_name=table_name, if_exists=True)
            print(f"Dropped index: {index_name}")
    print("Rollback complete.")
