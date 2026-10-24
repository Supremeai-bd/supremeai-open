"""Create canonical run tables: runs + run_events (M1-A).

বাংলা: M1 Canonical Run fabric-এর ভিত্তি — এক execution contract (Mission /
Agent / Tool / MCP / Browser / Code সব Run হিসেবে observe হবে, feature
rewrite ছাড়া)। ``runs`` হলো execution boundary row (lifecycle status,
budgets, consumed counters, retry classification, artifacts) আর
``run_events`` হলো per-run sequenced immutable audit stream।

Extend-not-replace: ``runs.mission_id`` existing Mission core-এর সাথে
canonical anchor করে (SET NULL — mission cleanup হলেও run audit trail
টিকে থাকে); ``source_type``/``source_ref`` evidence row-গুলোর (যেমন
automation_executions) দিকে নির্দেশ করে, duplicate subsystem নয়।
``parent_run_id`` self-FK M2 Context Engine-এর RUN/STEP scope-এর ভিত্তি।

Style: sa.Column-based upgrade/downgrade (ai_memory migration house style);
JSON uses JSONB on PostgreSQL; the models side (``runs/models.py``) carries
the JSON().with_variant(JSONB) sqlite-testable mirror. NOTE: indexes are
created via explicit ``op.create_index`` (``index=True`` inside
``op.create_table`` is a no-op in Alembic); single-column index names follow
the SQLAlchemy ``create_all`` convention (``ix_<table>_<column>``) so
test-metadata and production schema agree.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "2026_09_15_120000"
down_revision = "2026_09_14_120000"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", _UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        # identity
        sa.Column("run_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="requested"),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("workspace_id", sa.String(255), nullable=True),
        sa.Column("chat_id", sa.String(255), nullable=True),
        # extend-not-replace anchoring
        sa.Column(
            "mission_id",
            _UUID,
            sa.ForeignKey("missions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "parent_run_id",
            _UUID,
            sa.ForeignKey("runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_type", sa.String(32), nullable=True),
        sa.Column("source_ref", sa.String(255), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("trace_id", sa.String(100), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        # budgets
        sa.Column("max_wall_clock_ms", sa.Integer(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("max_tool_calls", sa.Integer(), nullable=True),
        sa.Column("max_retries", sa.Integer(), nullable=True),
        # consumed counters
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_calls_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retries_used", sa.Integer(), nullable=False, server_default="0"),
        # failure + artifacts
        sa.Column("retry_class", sa.String(32), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("artifacts", _JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        # lifecycle timestamps
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        # audit timestamps
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_runs_idempotency_key"),
    )

    op.create_table(
        "run_events",
        sa.Column("id", _UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "run_id",
            _UUID,
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("detail", _JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("run_id", "seq", name="uq_run_events_run_seq"),
    )

    # --- single-column indexes (create_all-convention names) ---------------
    for column in (
        "run_type",
        "status",
        "user_id",
        "workspace_id",
        "chat_id",
        "mission_id",
        "parent_run_id",
        "source_type",
        "source_ref",
        "idempotency_key",
        "trace_id",
        "correlation_id",
    ):
        op.create_index(f"ix_runs_{column}", "runs", [column])
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])

    # --- hot-path composite indexes ----------------------------------------
    op.create_index("ix_runs_status_created", "runs", ["status", "created_at"])
    op.create_index("ix_runs_user_created", "runs", ["user_id", "created_at"])
    op.create_index("ix_runs_workspace_created", "runs", ["workspace_id", "created_at"])
    op.create_index("ix_runs_source", "runs", ["source_type", "source_ref"])
    op.create_index("ix_run_events_run_seq", "run_events", ["run_id", "seq"])


def downgrade() -> None:
    op.drop_index("ix_run_events_run_seq", table_name="run_events")
    op.drop_index("ix_runs_source", table_name="runs")
    op.drop_index("ix_runs_workspace_created", table_name="runs")
    op.drop_index("ix_runs_user_created", table_name="runs")
    op.drop_index("ix_runs_status_created", table_name="runs")
    op.drop_index("ix_run_events_run_id", table_name="run_events")
    for column in (
        "correlation_id",
        "trace_id",
        "idempotency_key",
        "source_ref",
        "source_type",
        "parent_run_id",
        "mission_id",
        "chat_id",
        "workspace_id",
        "user_id",
        "status",
        "run_type",
    ):
        op.drop_index(f"ix_runs_{column}", table_name="runs")
    op.drop_table("run_events")
    op.drop_table("runs")
