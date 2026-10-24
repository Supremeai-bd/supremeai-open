"""Create mission orchestration tables (missions + mission_trace_events).

2026-09-20 (Migration Gate drift series): the canonical run tables migration
(2026_09_15_120000, M1-A) declares ``runs.mission_id -> missions.id`` FK, but
NO revision ever created ``missions`` / ``mission_trace_events`` — the tables
were expected to exist from runtime-managed create_all. On production the
missions subsystem never booted, so the tables are absent and the FK creation
fails with `UndefinedTable: relation "missions" does not exist`
(run 35496566026). This revision closes the chain hole, mirroring the ORM
models in ``backend/missions/models.py`` exactly (same columns/defaults, so
future autogenerate sees no drift).

Idempotent per repo convention (7c4d9e1f2a3b / issue #478): offline --sql
plans still emit full DDL; live runs inspect and skip existing objects.

Revision ID: 2026_09_14_120000
Revises: 6250e2a31d38
Create Date: 2026-09-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "2026_09_14_120000"
down_revision = "6250e2a31d38"
branch_labels = None
depends_on = None


def _inspect_offline_safe(bind):
    """Offline mode cannot inspect (MockConnection) — degrade to None so the
    generated SQL plan keeps the DDL; the live run guards with the real
    inspector. NOTE: ``context.is_offline_mode`` is a method — call it."""
    from alembic import context

    if context.is_offline_mode():
        return None
    return sa.inspect(bind)


def upgrade() -> None:
    bind = op.get_bind()
    insp = _inspect_offline_safe(bind)
    tables = set(insp.get_table_names()) if insp else set()

    if "missions" not in tables:
        op.create_table(
            "missions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("goal_text", sa.Text(), nullable=False),
            sa.Column("strategy", sa.String(200), nullable=True),
            sa.Column("strategy_options", JSONB(), nullable=False, server_default="[]"),
            sa.Column("phases", JSONB(), nullable=False, server_default="[]"),
            sa.Column("current_phase", sa.Integer(), nullable=False),
            sa.Column("state", sa.String(32), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False),
            sa.Column("owner_id", sa.String(255), nullable=False),
            sa.Column("agent_id", sa.String(255), nullable=True),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.Column("repair_count", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_missions_state", "missions", ["state"])
        op.create_index("ix_missions_owner_id", "missions", ["owner_id"])

    if "mission_trace_events" not in tables:
        op.create_table(
            "mission_trace_events",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "mission_id",
                UUID(as_uuid=True),
                sa.ForeignKey("missions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("phase", sa.Integer(), nullable=False),
            sa.Column("event", sa.String(64), nullable=False),
            sa.Column("detail", JSONB(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("mission_id", "seq", name="uq_mission_trace_mission_seq"),
        )
        op.create_index(
            "ix_mission_trace_events_mission_id", "mission_trace_events", ["mission_id"]
        )


def downgrade() -> None:
    op.drop_index("ix_mission_trace_events_mission_id", table_name="mission_trace_events")
    op.drop_table("mission_trace_events")
    op.drop_index("ix_missions_owner_id", table_name="missions")
    op.drop_index("ix_missions_state", table_name="missions")
    op.drop_table("missions")
