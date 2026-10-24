"""Add ecosystem tables

Revision ID: b30b7a512986
Revises:
Create Date: 2026-09-02 00:29:20.912345

"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b30b7a512986"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ecosystem_proposals
    op.create_table(
        "ecosystem_proposals",
        sa.Column("proposal_id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("priority", sa.String(), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("context", sa.String(), nullable=False, server_default="{}"),
        sa.Column("proposed_by", sa.String(), nullable=False, server_default="system"),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("resolved_at", sa.String(), nullable=True),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.Column("resolution_reason", sa.String(), nullable=True),
    )

    # ecosystem_decision_memory
    op.create_table(
        "ecosystem_decision_memory",
        sa.Column("memory_id", sa.String(), primary_key=True),
        sa.Column("proposal_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("dedup_key", sa.String(), nullable=True),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("time", sa.String(), nullable=False),
    )
    op.create_index(
        "idx_ecosystem_decision_memory_dedup", "ecosystem_decision_memory", ["dedup_key"]
    )

    # ecosystem_capabilities
    op.create_table(
        "ecosystem_capabilities",
        sa.Column("capability_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False, server_default="0.1.0"),
        sa.Column("signature", sa.String(), nullable=False, unique=True),
        sa.Column("category", sa.String(), nullable=False, server_default="general"),
        sa.Column("inputs", sa.String(), nullable=False, server_default="[]"),
        sa.Column("outputs", sa.String(), nullable=False, server_default="[]"),
        sa.Column("health_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("success_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("lifecycle_state", sa.String(), nullable=False, server_default="IDEA"),
        sa.Column("runtime_tier", sa.String(), nullable=False, server_default="WARM"),
        sa.Column("source", sa.String(), nullable=False, server_default="internal"),
        sa.Column("provenance", sa.String(), nullable=False, server_default="{}"),
        sa.Column("owner", sa.String(), nullable=False, server_default="system"),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("activation_metadata", sa.String(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("promoted_at", sa.String(), nullable=True),
        sa.Column("archived_at", sa.String(), nullable=True),
    )

    # ecosystem_deployments
    op.create_table(
        "ecosystem_deployments",
        sa.Column("deployment_id", sa.String(), primary_key=True),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("repository", sa.String(), nullable=False),
        sa.Column("commit_sha", sa.String(), nullable=True),
        sa.Column("image_digest", sa.String(), nullable=True),
        sa.Column("environment", sa.String(), nullable=False, server_default="production"),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("health_after_deploy", sa.String(), nullable=True),
        sa.Column("rollback_status", sa.String(), nullable=True),
        sa.Column("triggered_by", sa.String(), nullable=False, server_default="system"),
        sa.Column("correlation", sa.String(), nullable=False, server_default="{}"),
        sa.Column("artifacts", sa.String(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("completed_at", sa.String(), nullable=True),
    )

    # ecosystem_health_snapshots
    op.create_table(
        "ecosystem_health_snapshots",
        sa.Column("snapshot_id", sa.String(), primary_key=True),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("availability", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("error_rate", sa.Float(), nullable=True),
        sa.Column("cpu_percent", sa.Float(), nullable=True),
        sa.Column("memory_current_mb", sa.Float(), nullable=True),
        sa.Column("memory_peak_mb", sa.Float(), nullable=True),
        sa.Column("memory_limit_mb", sa.Float(), nullable=True),
        sa.Column("memory_percent", sa.Float(), nullable=True),
        sa.Column("memory_trend", sa.String(), nullable=True),
        sa.Column("startup_memory_mb", sa.Float(), nullable=True),
        sa.Column("idle_memory_mb", sa.Float(), nullable=True),
        sa.Column("version", sa.String(), nullable=True),
        sa.Column("dependency_health", sa.String(), nullable=False, server_default="{}"),
        sa.Column("captured_at", sa.String(), nullable=False),
        sa.Column("metadata", sa.String(), nullable=False, server_default="{}"),
    )

    # ecosystem_evolution_signals
    op.create_table(
        "ecosystem_evolution_signals",
        sa.Column("signal_id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("evidence", sa.String(), nullable=False, server_default="[]"),
        sa.Column("capability_hint", sa.String(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("priority", sa.String(), nullable=False, server_default="MEDIUM"),
        sa.Column("detected_at", sa.String(), nullable=False),
        sa.Column("proposed_capability_id", sa.String(), nullable=True),
    )

    # ecosystem_learning_opportunities
    op.create_table(
        "ecosystem_learning_opportunities",
        sa.Column("opportunity_id", sa.String(), primary_key=True),
        sa.Column("requirement", sa.String(), nullable=False),
        sa.Column("signal_id", sa.String(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("usefulness", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("feasibility", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("risk", sa.String(), nullable=False, server_default="medium"),
        sa.Column("cost", sa.String(), nullable=False, server_default="medium"),
        sa.Column("maintenance", sa.String(), nullable=False, server_default="low"),
        sa.Column("reuse_existing_id", sa.String(), nullable=True),
        sa.Column("proposal_id", sa.String(), nullable=True),
        sa.Column("stage", sa.String(), nullable=False, server_default="GAP_SIGNAL"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index(
        "idx_ecosystem_learning_opportunities_stage", "ecosystem_learning_opportunities", ["stage"]
    )

    # ecosystem_resources
    op.create_table(
        "ecosystem_resources",
        sa.Column("resource_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False, server_default="web_service"),
        sa.Column("environment", sa.String(), nullable=False, server_default="production"),
        sa.Column("repository", sa.String(), nullable=True),
        sa.Column("deployment_id", sa.String(), nullable=True),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("state", sa.String(), nullable=False, server_default="REGISTERED"),
        sa.Column("dependencies", sa.String(), nullable=False, server_default="[]"),
        sa.Column("capabilities", sa.String(), nullable=False, server_default="[]"),
        sa.Column("metadata", sa.String(), nullable=False, server_default="{}"),
        sa.Column("provider_config_ref", sa.String(), nullable=True),
        sa.Column("owner", sa.String(), nullable=False, server_default="system"),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )

    # ecosystem_sources
    op.create_table(
        "ecosystem_sources",
        sa.Column("source_id", sa.String(), primary_key=True),
        sa.Column("url", sa.String(), nullable=False, unique=True),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False, server_default="UNKNOWN"),
        sa.Column("category", sa.String(), nullable=False, server_default="UNKNOWN"),
        sa.Column("trust_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("risk_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("cost_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("first_seen_at", sa.String(), nullable=False),
        sa.Column("last_seen_at", sa.String(), nullable=False),
        sa.Column("metadata", sa.String(), nullable=False, server_default="{}"),
        sa.Column("owner", sa.String(), nullable=False, server_default="system"),
        sa.Column("tenant_id", sa.String(), nullable=True),
    )

    # ecosystem_source_policies
    op.create_table(
        "ecosystem_source_policies",
        sa.Column("policy_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("scope_value", sa.String(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("crawl_budget_per_day", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("requires_approval", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("auto_policies_generated", sa.String(), nullable=False, server_default="[]"),
        sa.Column("created_by", sa.String(), nullable=False, server_default="admin"),
        sa.Column("created_at", sa.String(), nullable=False),
    )

    # ecosystem_learned_items
    op.create_table(
        "ecosystem_learned_items",
        sa.Column("item_id", sa.String(), primary_key=True),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False, server_default="UNKNOWN"),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("retrieved_at", sa.String(), nullable=False),
        sa.Column("source_version", sa.String(), nullable=True),
        sa.Column("provenance", sa.String(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("cross_check_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("policy_decision", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("capabilities_affected", sa.String(), nullable=False, server_default="[]"),
        sa.Column("relevance", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("freshness", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_of", sa.String(), nullable=True),
        sa.Column("raw_blob_ref", sa.String(), nullable=True),
    )
    op.create_index("idx_ecosystem_learned_items_source", "ecosystem_learned_items", ["source_url"])
    op.create_index("idx_ecosystem_learned_items_conf", "ecosystem_learned_items", ["confidence"])

    # ecosystem_tasks
    op.create_table(
        "ecosystem_tasks",
        sa.Column("task_id", sa.String(), primary_key=True),
        sa.Column("goal", sa.String(), nullable=False),
        sa.Column("owner", sa.String(), nullable=False, server_default="USER"),
        sa.Column("scope", sa.String(), nullable=False, server_default="USER_WORKSPACE"),
        sa.Column("state", sa.String(), nullable=False, server_default="RECEIVED"),
        sa.Column("plan", sa.String(), nullable=False, server_default="[]"),
        sa.Column("capability_requirements", sa.String(), nullable=False, server_default="[]"),
        sa.Column("resource_id", sa.String(), nullable=True),
        sa.Column("capability_id", sa.String(), nullable=True),
        sa.Column("artifacts", sa.String(), nullable=False, server_default="[]"),
        sa.Column("result", sa.String(), nullable=False, server_default="{}"),
        sa.Column("success_criteria", sa.String(), nullable=False, server_default="{}"),
        sa.Column("verification_result", sa.String(), nullable=False, server_default="{}"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_limit", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("time_limit_seconds", sa.Integer(), nullable=False, server_default="1800"),
        sa.Column("risk_level", sa.String(), nullable=False, server_default="medium"),
        sa.Column("correlation", sa.String(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(), nullable=False, server_default="system"),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("audit_id", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("started_at", sa.String(), nullable=True),
        sa.Column("completed_at", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ecosystem_tasks")
    op.drop_table("ecosystem_learned_items")
    op.drop_table("ecosystem_source_policies")
    op.drop_table("ecosystem_sources")
    op.drop_table("ecosystem_resources")
    op.drop_table("ecosystem_learning_opportunities")
    op.drop_table("ecosystem_evolution_signals")
    op.drop_table("ecosystem_health_snapshots")
    op.drop_table("ecosystem_deployments")
    op.drop_table("ecosystem_capabilities")
    op.drop_table("ecosystem_decision_memory")
    op.drop_table("ecosystem_proposals")
