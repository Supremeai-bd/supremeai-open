"""add persistent Render account state and preflight audit events"""

import sqlalchemy as sa
from alembic import op

revision = "2026_09_06_120000"
down_revision = "h3i4j5k6l7m8"
branch_labels = None
depends_on = None


def _inspect_offline_safe(bind):
    """Issue #478 convention (see 7c4d9e1f2a3b): offline mode cannot inspect
    (MockConnection) — degrade to None so the generated SQL plan keeps the
    DDL; the live run guards with the real inspector.

    2026-09-20: the live DB already contains both tables (runtime-managed
    create_all before the Migration Gate existed). Un-guarded re-create hit
    `psycopg2.errors.DuplicateTable: relation "render_account_states" already
    exists` once the deploy chain (always() gate, PR #811) started running
    this job. Guard mirrors the repo's idempotent-migration convention.
    """
    from alembic import context

    if context.is_offline_mode():
        return None
    return sa.inspect(bind)


def upgrade() -> None:
    bind = op.get_bind()
    insp = _inspect_offline_safe(bind)
    tables = set(insp.get_table_names()) if insp else set()

    if "render_account_states" not in tables:
        op.create_table(
            "render_account_states",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("account_key", sa.String(120), nullable=False, unique=True),
            sa.Column("role", sa.String(80), nullable=False),
            sa.Column("plan", sa.String(40), nullable=False, server_default="unknown"),
            sa.Column("status", sa.String(32), nullable=False, server_default="unknown"),
            sa.Column("reason", sa.String(120), nullable=True),
            sa.Column("usage_minutes", sa.Float(), nullable=True),
            sa.Column("usage_period_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("recheck_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata", sa.JSON(), nullable=True),
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
    # Partial-drift guard: table may exist without its index.
    existing_indexes = (
        {ix["name"] for ix in insp.get_indexes("render_account_states")}
        if insp and "render_account_states" in tables
        else set()
    )
    if "ix_render_account_states_status_recheck" not in existing_indexes:
        op.create_index(
            "ix_render_account_states_status_recheck",
            "render_account_states",
            ["status", "recheck_at"],
        )

    if "render_preflight_events" not in tables:
        op.create_table(
            "render_preflight_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("account_key", sa.String(120), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("reason", sa.String(120), nullable=True),
            sa.Column("usage_minutes", sa.Float(), nullable=True),
            sa.Column(
                "observed_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("metadata", sa.JSON(), nullable=True),
        )
        # Index belongs to the table that this migration just created.
        op.create_index(
            "ix_render_preflight_events_account_observed",
            "render_preflight_events",
            ["account_key", "observed_at"],
        )


def downgrade() -> None:
    op.drop_index(
        "ix_render_preflight_events_account_observed", table_name="render_preflight_events"
    )
    op.drop_table("render_preflight_events")
    op.drop_index("ix_render_account_states_status_recheck", table_name="render_account_states")
    op.drop_table("render_account_states")
