"""tier_s_features

Revision ID: tier_s_001
Revises: ed9761fee64f
Create Date: 2026-08-20 00:00:00.000000

Add all tables and columns required for Tier-S features:
- shared_conversations
- artifacts
- chat_attachments
- prompt_templates
- scheduled_tasks
- scheduled_task_executions
- research_sessions
- conversations.parent_conversation_id (FK)
- messages.parent_message_id (FK)
"""

from collections.abc import Sequence

# ruff: noqa: I001
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "tier_s_001"
down_revision: str | Sequence[str] | None = "ed9761fee64f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. shared_conversations
    # ------------------------------------------------------------------
    op.create_table(
        "shared_conversations",
        sa.Column("share_id", sa.Text(), nullable=False),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("share_id"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_shared_conversations_conversation_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_shared_conversations_conversation_id",
        "shared_conversations",
        ["conversation_id"],
    )
    op.create_index(
        "ix_shared_conversations_user_id",
        "shared_conversations",
        ["user_id"],
    )

    # ------------------------------------------------------------------
    # 2. artifacts
    # ------------------------------------------------------------------
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_artifacts_conversation_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_artifacts_conversation_id",
        "artifacts",
        ["conversation_id"],
    )
    op.create_index(
        "ix_artifacts_user_id",
        "artifacts",
        ["user_id"],
    )
    op.create_index(
        "ix_artifacts_artifact_type",
        "artifacts",
        ["artifact_type"],
    )

    # ------------------------------------------------------------------
    # 3. chat_attachments
    # ------------------------------------------------------------------
    op.create_table(
        "chat_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_attachments_user_id",
        "chat_attachments",
        ["user_id"],
    )
    op.create_index(
        "ix_chat_attachments_conversation_id",
        "chat_attachments",
        ["conversation_id"],
    )
    op.create_index(
        "ix_chat_attachments_message_id",
        "chat_attachments",
        ["message_id"],
    )

    # ------------------------------------------------------------------
    # 4. prompt_templates
    # ------------------------------------------------------------------
    op.create_table(
        "prompt_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "is_builtin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "usage_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_prompt_templates_user_id",
        "prompt_templates",
        ["user_id"],
    )
    op.create_index(
        "ix_prompt_templates_category",
        "prompt_templates",
        ["category"],
    )

    # ------------------------------------------------------------------
    # 5. scheduled_tasks
    # ------------------------------------------------------------------
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("schedule_type", sa.Text(), nullable=False),
        sa.Column("scheduled_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cron_expression", sa.Text(), nullable=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_scheduled_tasks_conversation_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_scheduled_tasks_user_id",
        "scheduled_tasks",
        ["user_id"],
    )
    op.create_index(
        "ix_scheduled_tasks_is_active",
        "scheduled_tasks",
        ["is_active"],
    )

    # ------------------------------------------------------------------
    # 6. scheduled_task_executions
    # ------------------------------------------------------------------
    op.create_table(
        "scheduled_task_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["scheduled_tasks.id"],
            name="fk_scheduled_task_executions_task_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_scheduled_task_executions_task_id",
        "scheduled_task_executions",
        ["task_id"],
    )
    op.create_index(
        "ix_scheduled_task_executions_status",
        "scheduled_task_executions",
        ["status"],
    )

    # ------------------------------------------------------------------
    # 7. research_sessions
    # ------------------------------------------------------------------
    op.create_table(
        "research_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "steps_completed",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_sources",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_sessions_user_id",
        "research_sessions",
        ["user_id"],
    )
    op.create_index(
        "ix_research_sessions_status",
        "research_sessions",
        ["status"],
    )

    # ------------------------------------------------------------------
    # 8. Add parent_conversation_id to conversations
    # ------------------------------------------------------------------
    op.add_column(
        "conversations",
        sa.Column(
            "parent_conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_conversations_parent_conversation_id",
        "conversations",
        "conversations",
        ["parent_conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_conversations_parent_conversation_id",
        "conversations",
        ["parent_conversation_id"],
    )

    # ------------------------------------------------------------------
    # 9. Add parent_message_id to messages
    # ------------------------------------------------------------------
    op.add_column(
        "messages",
        sa.Column(
            "parent_message_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_messages_parent_message_id",
        "messages",
        "messages",
        ["parent_message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_messages_parent_message_id",
        "messages",
        ["parent_message_id"],
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 9. Remove parent_message_id from messages
    # ------------------------------------------------------------------
    op.drop_index("ix_messages_parent_message_id", table_name="messages")
    op.drop_constraint(
        "fk_messages_parent_message_id",
        "messages",
        type_="foreignkey",
    )
    op.drop_column("messages", "parent_message_id")

    # ------------------------------------------------------------------
    # 8. Remove parent_conversation_id from conversations
    # ------------------------------------------------------------------
    op.drop_index("ix_conversations_parent_conversation_id", table_name="conversations")
    op.drop_constraint(
        "fk_conversations_parent_conversation_id",
        "conversations",
        type_="foreignkey",
    )
    op.drop_column("conversations", "parent_conversation_id")

    # ------------------------------------------------------------------
    # 7. research_sessions
    # ------------------------------------------------------------------
    op.drop_index("ix_research_sessions_status", table_name="research_sessions")
    op.drop_index("ix_research_sessions_user_id", table_name="research_sessions")
    op.drop_table("research_sessions")

    # ------------------------------------------------------------------
    # 6. scheduled_task_executions
    # ------------------------------------------------------------------
    op.drop_index("ix_scheduled_task_executions_status", table_name="scheduled_task_executions")
    op.drop_index("ix_scheduled_task_executions_task_id", table_name="scheduled_task_executions")
    op.drop_table("scheduled_task_executions")

    # ------------------------------------------------------------------
    # 5. scheduled_tasks
    # ------------------------------------------------------------------
    op.drop_index("ix_scheduled_tasks_is_active", table_name="scheduled_tasks")
    op.drop_index("ix_scheduled_tasks_user_id", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")

    # ------------------------------------------------------------------
    # 4. prompt_templates
    # ------------------------------------------------------------------
    op.drop_index("ix_prompt_templates_category", table_name="prompt_templates")
    op.drop_index("ix_prompt_templates_user_id", table_name="prompt_templates")
    op.drop_table("prompt_templates")

    # ------------------------------------------------------------------
    # 3. chat_attachments
    # ------------------------------------------------------------------
    op.drop_index("ix_chat_attachments_message_id", table_name="chat_attachments")
    op.drop_index("ix_chat_attachments_conversation_id", table_name="chat_attachments")
    op.drop_index("ix_chat_attachments_user_id", table_name="chat_attachments")
    op.drop_table("chat_attachments")

    # ------------------------------------------------------------------
    # 2. artifacts
    # ------------------------------------------------------------------
    op.drop_index("ix_artifacts_artifact_type", table_name="artifacts")
    op.drop_index("ix_artifacts_user_id", table_name="artifacts")
    op.drop_index("ix_artifacts_conversation_id", table_name="artifacts")
    op.drop_table("artifacts")

    # ------------------------------------------------------------------
    # 1. shared_conversations
    # ------------------------------------------------------------------
    op.drop_index("ix_shared_conversations_user_id", table_name="shared_conversations")
    op.drop_index("ix_shared_conversations_conversation_id", table_name="shared_conversations")
    op.drop_table("shared_conversations")
