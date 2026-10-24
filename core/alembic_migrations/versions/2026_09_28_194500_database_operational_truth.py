"""database as operational truth — 6 core tables (issue #2377)

SupremeAI-র মূল দর্শন: DATABASE = live operational truth, GIT = architectural
blueprint, VECTOR DB = deep knowledge/RAG। এই migration সেই দর্শনের প্রথম
concrete স্তর — ৬টি core টেবিল যা Markdown registries-কে ধীরে ধীরে
DB-driven truth-এ রূপান্তর করবে (no dumping ground — শুধু live-state টেবিল):

  1. system_modules   — ডোমেইন/মডিউল/নোড/DB-model/resource-এর লাইভ স্ট্যাটাস
                        (source: ECOSYSTEM_GRAPH_REGISTRY.yaml #2399 + tower
                        resource.status sync via tower_db_bridge.py)
  2. capabilities     — capability lifecycle tracker
                        (source: CAPABILITY_LEDGER.md — 6-state taxonomy)
  3. agent_leases     — slot/lease management + tower heartbeat mirror
                        (source: AGENT_SLOT_REGISTRY.yaml + MCP Tower
                        agent_status/agent_heartbeat via tower_db_bridge.py)
  4. operational_tasks— priority/roadmap queue
                        (source: ACTIVE_ISSUES_AND_PRIORITY_ROADMAP.md)
  5. secret_rotations — rotation history (source: TOKEN_ROTATION_VERIFICATION.md)
  6. audit_queue      — live audit findings window (source: ACTIVE_AUDIT_QUEUE.md)

Canonical spec: docs/architecture/DATABASE_OPERATIONAL_TRUTH.md (issue #2377)

Revision ID: op_truth_0001
Revises: merge_learn_0001
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "op_truth_0001"
down_revision: str | Sequence[str] | None = "merge_learn_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "system_modules",
    "capabilities",
    "agent_leases",
    "operational_tasks",
    "secret_rotations",
    "audit_queue",
)


def _existing_tables_offline_safe(bind) -> set[str]:
    """offline/online দুই মোডেই চলে — existing table নামের সেট বের করে।"""
    try:
        inspector = sa.inspect(bind)
        return set(inspector.get_table_names())
    except Exception:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    existing = _existing_tables_offline_safe(bind)

    # ── 1. system_modules — ডোমেইন/মডিউল/নোড/DB-model/infra-resource লাইভ স্ট্যাটাস ──
    if "system_modules" not in existing:
        op.create_table(
            "system_modules",
            sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False, unique=True),
            # kind: domain | module | node | db-model | resource
            sa.Column("kind", sa.String(length=32), nullable=False, server_default="module"),
            # layer: core | api | infra | agent | domain (graph registry অনুযায়ী)
            sa.Column("layer", sa.String(length=32), nullable=False, server_default="core"),
            sa.Column("domain_id", sa.String(length=64), nullable=True),
            # status: active | deprecated | migrating | decision-required | offline
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("owner_lane", sa.String(length=64), nullable=True),
            sa.Column("owning_paths", sa.JSON(), nullable=True),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.Column("source_doc", sa.String(length=255), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_system_modules_domain", "system_modules", ["domain_id"])
        op.create_index("ix_system_modules_status", "system_modules", ["status"])
        op.create_index("ix_system_modules_kind", "system_modules", ["kind"])

    # ── 2. capabilities — capability lifecycle (CAPABILITY_LEDGER 6-state) ──
    if "capabilities" not in existing:
        op.create_table(
            "capabilities",
            # CAP-AI-01 স্টাইল stable id (ledger-এর সাথে 1:1)
            sa.Column("capability_id", sa.String(length=32), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("category", sa.String(length=64), nullable=True),
            # VERIFIED | PARTIAL | IN_PROGRESS | PLANNED | PROPOSED | DEPRECATED
            sa.Column("status", sa.String(length=32), nullable=False, server_default="PLANNED"),
            # 1-4 — evidence-hierarchy derivation (sync script ডকুমেন্ট দেখুন)
            sa.Column("tier", sa.Integer(), nullable=True),
            sa.Column("evidence", sa.String(length=255), nullable=True),
            sa.Column("canonical_path", sa.String(length=255), nullable=True),
            sa.Column("preserve", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("target_architecture", sa.String(length=255), nullable=True),
            sa.Column("verification_proof", sa.Text(), nullable=True),
            sa.Column("last_audit_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source_doc", sa.String(length=255), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_capabilities_status", "capabilities", ["status"])
        op.create_index("ix_capabilities_tier", "capabilities", ["tier"])

    # ── 3. agent_leases — slot/lease + tower heartbeat mirror ──
    if "agent_leases" not in existing:
        op.create_table(
            "agent_leases",
            # slot_id: agent-3, z.ai-1, coder-2 ... (tower validateSlot format)
            # অথবা pool template: "pool:coder"
            sa.Column("slot_id", sa.String(length=64), primary_key=True),
            sa.Column("agent_name", sa.String(length=128), nullable=True),
            sa.Column("role", sa.String(length=64), nullable=True),
            sa.Column("lane", sa.String(length=64), nullable=True),
            sa.Column("issue_number", sa.Integer(), nullable=True),
            sa.Column("branch_name", sa.String(length=255), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            # state: online | stale | expired | pool-template | idle
            sa.Column("state", sa.String(length=32), nullable=False, server_default="idle"),
            # source: mcp-tower | slot-registry | local
            sa.Column("source", sa.String(length=32), nullable=False, server_default="local"),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_agent_leases_state", "agent_leases", ["state"])
        op.create_index("ix_agent_leases_expires", "agent_leases", ["expires_at"])
        op.create_index("ix_agent_leases_issue", "agent_leases", ["issue_number"])

    # ── 4. operational_tasks — priority/roadmap queue (roadmap sync) ──
    if "operational_tasks" not in existing:
        op.create_table(
            "operational_tasks",
            sa.Column("issue_number", sa.Integer(), primary_key=True),
            sa.Column("title", sa.Text(), nullable=True),
            sa.Column("group_name", sa.String(length=64), nullable=True),
            sa.Column("sequence", sa.Integer(), nullable=True),
            # Auditors Ripple Effect Rule — কতগুলো downstream কাজ সহজ হবে
            sa.Column("ripple_effect_score", sa.Integer(), nullable=True),
            sa.Column("priority_tier", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
            sa.Column("assigned_slot", sa.String(length=64), nullable=True),
            sa.Column("source_doc", sa.String(length=255), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_operational_tasks_status", "operational_tasks", ["status"])
        op.create_index("ix_operational_tasks_group", "operational_tasks", ["group_name"])

    # ── 5. secret_rotations — rotation history ──
    if "secret_rotations" not in existing:
        op.create_table(
            "secret_rotations",
            sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column("secret_name", sa.String(length=255), nullable=False),
            sa.Column("scope", sa.String(length=255), nullable=True),
            sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            # status: runbook-active | rotated | verified | pending-owner
            sa.Column(
                "status", sa.String(length=32), nullable=False, server_default="runbook-active"
            ),
            sa.Column("evidence", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("source_doc", sa.String(length=255), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        # (secret_name, scope) = natural key — upsert conflict target
        op.create_unique_constraint(
            "uq_secret_rotations_name_scope", "secret_rotations", ["secret_name", "scope"]
        )
        op.create_index(
            "ix_secret_rotations_name_scope", "secret_rotations", ["secret_name", "scope"]
        )

    # ── 6. audit_queue — live audit findings window (50-item sliding) ──
    if "audit_queue" not in existing:
        op.create_table(
            "audit_queue",
            # GAP-001 স্টাইল stable finding id
            sa.Column("finding_id", sa.String(length=32), primary_key=True),
            sa.Column("category", sa.String(length=64), nullable=True),
            sa.Column("target_path", sa.String(length=512), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            # OPEN | RESOLVED | BLOCKED:OWNER | IN_PROGRESS
            sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
            sa.Column("added_date", sa.String(length=32), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source_doc", sa.String(length=255), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_audit_queue_status", "audit_queue", ["status"])


def downgrade() -> None:
    """৬টি টেবিলই operational mirror — downgrade মানে truth-layer ফেলে দেওয়া।

    seed data আবার sync script দিয়ে আসবে, তাই ক্ষতি নেই; তবে owner-কে জানানো থাকল।
    """
    bind = op.get_bind()
    existing = _existing_tables_offline_safe(bind)
    for table in reversed(_TABLES):
        if table in existing:
            op.drop_table(table)
