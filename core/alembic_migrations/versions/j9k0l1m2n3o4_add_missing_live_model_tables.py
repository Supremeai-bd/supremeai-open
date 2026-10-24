"""add missing tables for live models (meta_ai, evolution, execution_policy, selector_healing, patch_telemetry, plugin, integrations, user_plugin_installations, agent_sessions, automation_execution_attempts, execution_logs)

বাংলা মন্তব্য: db_model_drift_checker.py রিপোর্ট করা "missing_table" ইস্যুর
মধ্যে যেগুলো models/__init__.py-তে রেজিস্টার্ড অথবা api/routes বা core/ কোড
থেকে সরাসরি import করে ব্যবহার হচ্ছে (অর্থাৎ genuinely live feature, dead
model না) -- সেগুলোর জন্য এই migration। বাকি ৭টা model (auto_reports,
churn_predictions, handoff_events, retention_actions,
target_platform_credentials, translation_cache, voice_sessions) কোথাও
import/ব্যবহার হয় না বলে এই migration-এ রাখা হয়নি -- এগুলো ভবিষ্যতের
ফিচারের জন্য রাখা মডেল কিনা তা যাচাই করে আলাদাভাবে সিদ্ধান্ত নিতে হবে।

Revision ID: j9k0l1m2n3o4
Revises: h3i4j5k6l7m8
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from alembic import context as _alembic_context
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "j9k0l1m2n3o4"
down_revision: str | Sequence[str] | None = "h3i4j5k6l7m8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_tables_offline_safe(conn):
    # Issue #478: offline mode cannot inspect (MockConnection) — degrade to an
    # empty set so the generated SQL plan contains the full DDL; the live run
    # still guards with the real inspector.
    from alembic import context

    if _alembic_context.is_offline_mode():
        return set()
    inspector = (
        Inspector.from_engine(conn.engine)
        if hasattr(conn, "engine")
        else Inspector.from_engine(conn)
    )
    return inspector.get_table_names()


def upgrade():
    conn = op.get_bind()
    existing_tables = _existing_tables_offline_safe(conn)
    for enum_name, enum_values in [
        (
            "agent_session_state",
            "('Idle', 'Scanning_Target_DOM', 'Executing_Workflows', 'Circuit_Breaker_Open', 'Self_Healing_Retries', 'Awaiting_Human_Input', 'Success', 'Failed')",
        ),
        ("control_mode", "('agent', 'pending_handoff', 'human')"),
        (
            "log_type_enum",
            "('shell_cmd', 'shell_stdout', 'shell_stderr', 'file_write', 'file_delete', 'dom_action', 'reasoning_token')",
        ),
        ("policy_scope_enum", "('global_scope', 'per_platform', 'per_action')"),
    ]:
        # Issue #478: offline mode has no live connection — pg_type cannot be
        # probed (execute() returns None). Treat the enum as absent so the
        # generated SQL plan contains the CREATE TYPE; the live run still
        # probes pg_type for real.
        if _alembic_context.is_offline_mode():
            exists = False
        else:
            exists = bool(
                conn.execute(
                    sa.text(f"SELECT 1 FROM pg_type WHERE typname = '{enum_name}'")
                ).scalar()
            )
        if not exists:
            op.execute(f"CREATE TYPE {enum_name} AS ENUM {enum_values}")

    if "agent_genomes" not in existing_tables:
        op.create_table(
            "agent_genomes",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("agent_name", sa.String(length=255), nullable=False),
            sa.Column(
                "chromosome",
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                nullable=False,
            ),
            sa.Column("fitness_score", sa.Float(), nullable=False),
            sa.Column("generation", sa.Integer(), nullable=False),
            sa.Column("parent_a_id", sa.UUID(), nullable=True),
            sa.Column("parent_b_id", sa.UUID(), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column(
                "lineage",
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                nullable=False,
            ),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["parent_a_id"],
                ["agent_genomes.id"],
            ),
            sa.ForeignKeyConstraint(
                ["parent_b_id"],
                ["agent_genomes.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if "agent_offspring" not in existing_tables:
        op.create_table(
            "agent_offspring",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("offspring_name", sa.String(length=255), nullable=False),
            sa.Column("parent_a_id", sa.UUID(), nullable=False),
            sa.Column("parent_b_id", sa.UUID(), nullable=False),
            sa.Column(
                "chromosome",
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                nullable=False,
            ),
            sa.Column("crossover_method", sa.String(length=50), nullable=False),
            sa.Column("mutation_rate", sa.Float(), nullable=False),
            sa.Column("evaluation_status", sa.String(length=50), nullable=False),
            sa.Column("fitness_score", sa.Float(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["parent_a_id"],
                ["agent_genomes.id"],
            ),
            sa.ForeignKeyConstraint(
                ["parent_b_id"],
                ["agent_genomes.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if "agent_performance_logs" not in existing_tables:
        op.create_table(
            "agent_performance_logs",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("agent_name", sa.String(length=255), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("response_time_ms", sa.Float(), nullable=False),
            sa.Column("accuracy_score", sa.Float(), nullable=False),
            sa.Column("cost_usd", sa.Float(), nullable=False),
            sa.Column("tokens_input", sa.Integer(), nullable=False),
            sa.Column("tokens_output", sa.Integer(), nullable=False),
            sa.Column("throughput_per_minute", sa.Float(), nullable=True),
            sa.Column("error_rate", sa.Float(), nullable=True),
            sa.Column("user_satisfaction", sa.Float(), nullable=True),
            sa.Column("endpoint", sa.String(length=255), nullable=True),
            sa.Column("model_used", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if "agent_sessions" not in existing_tables:
        op.create_table(
            "agent_sessions",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column(
                "current_state",
                postgresql.ENUM(
                    "Idle",
                    "Scanning_Target_DOM",
                    "Executing_Workflows",
                    "Circuit_Breaker_Open",
                    "Self_Healing_Retries",
                    "Awaiting_Human_Input",
                    "Success",
                    "Failed",
                    name="agent_session_state",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column(
                "control_mode",
                postgresql.ENUM(
                    "agent", "pending_handoff", "human", name="control_mode", create_type=False
                ),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if "automation_execution_attempts" not in existing_tables:
        op.create_table(
            "automation_execution_attempts",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("execution_id", sa.String(length=36), nullable=False),
            sa.Column("attempt", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("http_status", sa.Integer(), nullable=True),
            sa.Column("error_code", sa.String(length=100), nullable=True),
            sa.Column("error_message", sa.String(length=1024), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            # sa.ForeignKeyConstraint(
            #     ["execution_id"], ["automation_executions.id"], ondelete="CASCADE"
            # ),
            sa.PrimaryKeyConstraint("id"),
        )

    if "breeding_pools" not in existing_tables:
        op.create_table(
            "breeding_pools",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("pool_name", sa.String(length=255), nullable=False),
            sa.Column(
                "agent_names",
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                nullable=False,
            ),
            sa.Column("min_fitness_threshold", sa.Float(), nullable=False),
            sa.Column("max_pool_size", sa.Integer(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("pool_name"),
        )

    if "execution_logs" not in existing_tables:
        op.create_table(
            "execution_logs",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("session_id", sa.UUID(), nullable=False),
            sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "log_type",
                postgresql.ENUM(
                    "shell_cmd",
                    "shell_stdout",
                    "shell_stderr",
                    "file_write",
                    "file_delete",
                    "dom_action",
                    "reasoning_token",
                    name="log_type_enum",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column(
                "payload",
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                nullable=False,
            ),
            sa.Column("exit_code", sa.Integer(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", "ts"),
            postgresql_partition_by="RANGE (ts)",
        )

    if "execution_policies" not in existing_tables:
        op.create_table(
            "execution_policies",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column(
                "scope",
                postgresql.ENUM(
                    "global_scope",
                    "per_platform",
                    "per_action",
                    name="policy_scope_enum",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("scope_ref_id", sa.UUID(), nullable=True),
            sa.Column("max_timeout_seconds", sa.Integer(), nullable=False),
            sa.Column("max_retries", sa.Integer(), nullable=False),
            sa.Column(
                "max_serverless_compute_budget_usd",
                sa.Numeric(precision=6, scale=4),
                nullable=False,
            ),
            sa.Column("max_concurrent_sandboxes", sa.Integer(), nullable=False),
            sa.Column("circuit_breaker_failure_threshold", sa.Integer(), nullable=False),
            sa.Column("circuit_breaker_cooldown_seconds", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if "integrations" not in existing_tables:
        op.create_table(
            "integrations",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("encrypted_access_token", sa.String(), nullable=False),
            sa.Column("repo_url", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if "patch_telemetry" not in existing_tables:
        op.create_table(
            "patch_telemetry",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("error_id", sa.String(length=255), nullable=False),
            sa.Column("patch_id", sa.String(length=255), nullable=False),
            sa.Column("file_path", sa.String(length=1024), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("similarity_score", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if "performance_alerts" not in existing_tables:
        op.create_table(
            "performance_alerts",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("agent_name", sa.String(length=255), nullable=False),
            sa.Column("alert_type", sa.String(length=50), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False),
            sa.Column("metric_value", sa.Float(), nullable=False),
            sa.Column("threshold_value", sa.Float(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("recommended_action", sa.Text(), nullable=False),
            sa.Column("acknowledged_by", sa.String(length=255), nullable=True),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if "performance_metrics" not in existing_tables:
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

    if "plugin_manifests" not in existing_tables:
        op.create_table(
            "plugin_manifests",
            sa.Column("id", sa.String(length=100), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column("icon_url", sa.String(), nullable=False),
            sa.Column("category", sa.String(length=50), nullable=False),
            sa.Column("source", sa.String(length=50), nullable=False),
            sa.Column("auth_type", sa.String(length=50), nullable=False),
            sa.Column("execution_type", sa.String(length=50), nullable=False),
            sa.Column("trust_level", sa.String(length=50), nullable=False),
            sa.Column("tools_provided", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("auth_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("permission_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("install_count", sa.Integer(), nullable=False),
            sa.Column("usage_count", sa.Integer(), nullable=False),
            sa.Column("version", sa.String(length=50), nullable=False),
            sa.Column("manifest_version", sa.String(length=50), nullable=False),
            sa.Column("minimum_engine_version", sa.String(length=50), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if "selector_healing_events" not in existing_tables:
        op.create_table(
            "selector_healing_events",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("action_id", sa.UUID(), nullable=False),
            sa.Column("old_selector", sa.String(length=500), nullable=False),
            sa.Column("new_selector", sa.String(length=500), nullable=False),
            sa.Column("confidence_score", sa.Numeric(precision=3, scale=2), nullable=False),
            sa.Column("auto_applied", sa.Boolean(), nullable=False),
            sa.Column("screenshot_before_url", sa.String(length=1000), nullable=True),
            sa.Column("screenshot_after_url", sa.String(length=1000), nullable=True),
            sa.Column("reviewed_by_user_id", sa.UUID(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if "system_alerts" not in existing_tables:
        op.create_table(
            "system_alerts",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("level", sa.String(length=20), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("resolved", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if "user_plugin_installations" not in existing_tables:
        op.create_table(
            "user_plugin_installations",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("plugin_id", sa.String(length=100), nullable=False),
            sa.Column("integration_id", sa.UUID(), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), nullable=False),
            sa.Column(
                "granted_capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False
            ),
            sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("installed_version", sa.String(length=50), nullable=False),
            sa.Column("config_version", sa.String(length=50), nullable=False),
            sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("usage_count", sa.Integer(), nullable=False),
            sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.String(), nullable=True),
            sa.Column("health_status", sa.String(length=50), nullable=False),
            sa.ForeignKeyConstraint(
                ["integration_id"],
                ["integrations.id"],
            ),
            sa.ForeignKeyConstraint(
                ["plugin_id"],
                ["plugin_manifests.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if "weakest_link_reports" not in existing_tables:
        op.create_table(
            "weakest_link_reports",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("agent_name", sa.String(length=255), nullable=False),
            sa.Column("composite_score", sa.Float(), nullable=False),
            sa.Column("response_time_percentile", sa.Float(), nullable=False),
            sa.Column("accuracy_percentile", sa.Float(), nullable=False),
            sa.Column("cost_percentile", sa.Float(), nullable=False),
            sa.Column("error_rate_percentile", sa.Float(), nullable=False),
            sa.Column("suggestion", sa.String(length=50), nullable=False),
            sa.Column("reasoning", sa.Text(), nullable=False),
            sa.Column("is_acknowledged", sa.Boolean(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade():
    op.drop_table("weakest_link_reports")
    op.drop_table("user_plugin_installations")
    op.drop_table("system_alerts")
    op.drop_table("selector_healing_events")
    op.drop_table("plugin_manifests")
    op.drop_table("performance_metrics")
    op.drop_table("performance_alerts")
    op.drop_table("patch_telemetry")
    op.drop_table("integrations")
    op.drop_table("execution_policies")
    op.drop_table("execution_logs")
    op.drop_table("breeding_pools")
    op.drop_table("automation_execution_attempts")
    op.drop_table("agent_sessions")
    op.drop_table("agent_performance_logs")
    op.drop_table("agent_offspring")
    op.drop_table("agent_genomes")
