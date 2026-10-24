"""add client_slots — verified slot architecture DB mirror (issue #48)

Verified Slot Architecture (#48)-এর persistent operational projection।
MCP Tower-এর client registry (Upstash) লাইভ authorization store থাকে; এই
টেবিল credential-bound slot রেকর্ডগুলোর DB-side mirror — dashboard ও
forensics-এর জন্য (provision → approve → suspend/rotate lifecycle সহ)।

মিরর source: tower `slot.list` tool via scripts/operations/tower_db_bridge.py
sync-slots (operational_truth_db.py-র client_slots DDL-এর সাথে 1:1 মিল)।

Revision ID: slot_arch_0001
Revises: 124fcdff99bf
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "slot_arch_0001"
down_revision: str | Sequence[str] | None = "124fcdff99bf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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

    # ── client_slots — credential-bound slot mirror (#48) ──
    if "client_slots" not in existing:
        op.create_table(
            "client_slots",
            # slot_id: `slot_<name>` — the registry id of the credential-bound slot
            sa.Column("slot_id", sa.String(length=64), primary_key=True),
            sa.Column("slot_name", sa.String(length=128), nullable=False),
            sa.Column(
                "tenant_id", sa.String(length=64), nullable=False, server_default="tenant_default"
            ),
            # role: viewer | restricted_viewer | repo_viewer | agent | admin | supremeadmin
            sa.Column("role", sa.String(length=32), nullable=False, server_default="viewer"),
            # status: pending | active | suspended | revoked | expired (fail-closed revocation)
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            # 12-hex fingerprint of the sha256 credential digest — NEVER the raw credential
            sa.Column("credential_id", sa.String(length=32), nullable=True),
            sa.Column("provisioned_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("suspended_reason", sa.Text(), nullable=True),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_client_slots_status", "client_slots", ["status"])
        op.create_index("ix_client_slots_tenant", "client_slots", ["tenant_id"])


def downgrade() -> None:
    """client_slots একটি operational mirror — drop করলেও truth-layer নষ্ট হয় না।

    seed data আবার `tower_db_bridge.py sync-slots` দিয়ে আসবে; তবে owner-কে
    জানানো থাকল।
    """
    bind = op.get_bind()
    existing = _existing_tables_offline_safe(bind)
    if "client_slots" in existing:
        op.drop_index("ix_client_slots_tenant", table_name="client_slots")
        op.drop_index("ix_client_slots_status", table_name="client_slots")
        op.drop_table("client_slots")
