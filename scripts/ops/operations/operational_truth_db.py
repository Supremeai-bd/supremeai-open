#!/usr/bin/env python3
"""SupremeAI — Operational Truth DB helper (issue #2377).

Database as Operational Truth-এর shared infrastructure:
  - ৬টি core টেবিলের idempotent DDL (Alembic migration op_truth_0001-এর সাথে
    1:1 মিল — এটা defense-in-depth: alembic না চললেও bridge/sync self-heal করবে)
  - lazy DB connection: Postgres (psycopg2, canonical Supabase) অথবা
    SQLite (local mirror / offline verification)
  - cross-flavor UPSERT helper (INSERT ... ON CONFLICT ... DO UPDATE — দুই
    flavor-ই একই syntax সাপোর্ট করে; শুধু paramstyle আলাদা)

ব্যবহার (অন্য স্ক্রিপ্ট থেকে):
    from operational_truth_db import connect, ensure_schema, upsert_rows

    conn, flavor = connect(sqlite_path="data/operational_truth.db")
    ensure_schema(conn, flavor)
    upsert_rows(conn, flavor, "agent_leases", rows, conflict_cols=["slot_id"])

CLI (self-check):
    python scripts/operations/operational_truth_db.py ensure-schema --sqlite data/operational_truth.db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]

# ── Table specs: (name, pk_cols, create-DDL) — op_truth_0001 Alembic-এর মিরর ──
# দুই flavor-ই CREATE TABLE IF NOT EXISTS সাপোর্ট করে। TIMESTAMPTZ → Postgres;
# SQLite CURRENT_TIMESTAMP-নিরপেক্ষ রাখতে TEXT-এ ISO-8601 স্ট্রিং রাখা হয়।

_TABLE_DDLS: list[tuple[str, list[str], str]] = [
    (
        "system_modules",
        ["id"],
        """
        CREATE TABLE IF NOT EXISTS system_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(255) NOT NULL UNIQUE,
            kind VARCHAR(32) NOT NULL DEFAULT 'module',
            layer VARCHAR(32) NOT NULL DEFAULT 'core',
            domain_id VARCHAR(64),
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            owner_lane VARCHAR(64),
            owning_paths JSON,
            meta JSON,
            source_doc VARCHAR(255),
            updated_at TEXT NOT NULL
        )
        """,
    ),
    (
        "capabilities",
        ["capability_id"],
        """
        CREATE TABLE IF NOT EXISTS capabilities (
            capability_id VARCHAR(32) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            category VARCHAR(64),
            status VARCHAR(32) NOT NULL DEFAULT 'PLANNED',
            tier INTEGER,
            evidence VARCHAR(255),
            canonical_path VARCHAR(255),
            preserve BOOLEAN NOT NULL DEFAULT 1,
            target_architecture VARCHAR(255),
            verification_proof TEXT,
            last_audit_at TEXT,
            source_doc VARCHAR(255),
            updated_at TEXT NOT NULL
        )
        """,
    ),
    (
        "agent_leases",
        ["slot_id"],
        """
        CREATE TABLE IF NOT EXISTS agent_leases (
            slot_id VARCHAR(64) PRIMARY KEY,
            agent_name VARCHAR(128),
            role VARCHAR(64),
            lane VARCHAR(64),
            issue_number INTEGER,
            branch_name VARCHAR(255),
            heartbeat_at TEXT,
            expires_at TEXT,
            state VARCHAR(32) NOT NULL DEFAULT 'idle',
            source VARCHAR(32) NOT NULL DEFAULT 'local',
            meta JSON,
            updated_at TEXT NOT NULL
        )
        """,
    ),
    (
        # #48 Verified Slot Architecture — the DB-side mirror of the tower's
        # credential-bound slot records (`slot_<name>` in the client registry).
        # The registry (Upstash) stays the live authorization store; this table
        # is the persistent operational projection for dashboards/forensics.
        # (provisioned_at / rotated_at / last_verified_at come from the tower
        # slot.list tool via tower_db_bridge.py sync-slots.)
        "client_slots",
        ["slot_id"],
        """
        CREATE TABLE IF NOT EXISTS client_slots (
            slot_id VARCHAR(64) PRIMARY KEY,
            slot_name VARCHAR(128) NOT NULL,
            tenant_id VARCHAR(64) NOT NULL DEFAULT 'tenant_default',
            role VARCHAR(32) NOT NULL DEFAULT 'viewer',
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            credential_id VARCHAR(32),
            provisioned_at TEXT,
            rotated_at TEXT,
            last_verified_at TEXT,
            suspended_reason TEXT,
            meta JSON,
            updated_at TEXT NOT NULL
        )
        """,
    ),
    (
        "operational_tasks",
        ["issue_number"],
        """
        CREATE TABLE IF NOT EXISTS operational_tasks (
            issue_number INTEGER PRIMARY KEY,
            title TEXT,
            group_name VARCHAR(64),
            sequence INTEGER,
            ripple_effect_score INTEGER,
            priority_tier VARCHAR(64),
            status VARCHAR(32) NOT NULL DEFAULT 'open',
            assigned_slot VARCHAR(64),
            source_doc VARCHAR(255),
            updated_at TEXT NOT NULL
        )
        """,
    ),
    (
        "secret_rotations",
        ["id"],
        """
        CREATE TABLE IF NOT EXISTS secret_rotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            secret_name VARCHAR(255) NOT NULL,
            scope VARCHAR(255) NOT NULL DEFAULT 'global',
            rotated_at TEXT,
            verified_at TEXT,
            status VARCHAR(32) NOT NULL DEFAULT 'runbook-active',
            evidence TEXT,
            notes TEXT,
            source_doc VARCHAR(255),
            updated_at TEXT NOT NULL,
            UNIQUE (secret_name, scope)
        )
        """,
    ),
    (
        "audit_queue",
        ["finding_id"],
        """
        CREATE TABLE IF NOT EXISTS audit_queue (
            finding_id VARCHAR(32) PRIMARY KEY,
            category VARCHAR(64),
            target_path VARCHAR(512),
            description TEXT,
            status VARCHAR(32) NOT NULL DEFAULT 'OPEN',
            added_date VARCHAR(32),
            resolved_at TEXT,
            source_doc VARCHAR(255),
            updated_at TEXT NOT NULL
        )
        """,
    ),
]

# Postgres variant: AUTOINCREMENT → (no), BOOLEAN DEFAULT 1 → DEFAULT TRUE,
# TEXT timestamps → TIMESTAMPTZ (canonical deployment = Supabase Postgres)।
_PG_FIXUPS = {
    "INTEGER PRIMARY KEY AUTOINCREMENT": "SERIAL PRIMARY KEY",
    "DEFAULT 1": "DEFAULT TRUE",
    "updated_at TEXT NOT NULL": "updated_at TIMESTAMPTZ NOT NULL",
    "heartbeat_at TEXT": "heartbeat_at TIMESTAMPTZ",
    "expires_at TEXT": "expires_at TIMESTAMPTZ",
    "rotated_at TEXT": "rotated_at TIMESTAMPTZ",
    "verified_at TEXT": "verified_at TIMESTAMPTZ",
    "resolved_at TEXT": "resolved_at TIMESTAMPTZ",
    "last_audit_at TEXT": "last_audit_at TIMESTAMPTZ",
    # #48 client_slots timestamps
    "provisioned_at TEXT": "provisioned_at TIMESTAMPTZ",
    "last_verified_at TEXT": "last_verified_at TIMESTAMPTZ",
}

_INDEXES = [
    ("ix_system_modules_domain", "CREATE INDEX IF NOT EXISTS ix_system_modules_domain ON system_modules (domain_id)"),
    ("ix_system_modules_status", "CREATE INDEX IF NOT EXISTS ix_system_modules_status ON system_modules (status)"),
    ("ix_system_modules_kind", "CREATE INDEX IF NOT EXISTS ix_system_modules_kind ON system_modules (kind)"),
    ("ix_capabilities_status", "CREATE INDEX IF NOT EXISTS ix_capabilities_status ON capabilities (status)"),
    ("ix_capabilities_tier", "CREATE INDEX IF NOT EXISTS ix_capabilities_tier ON capabilities (tier)"),
    ("ix_agent_leases_state", "CREATE INDEX IF NOT EXISTS ix_agent_leases_state ON agent_leases (state)"),
    ("ix_agent_leases_expires", "CREATE INDEX IF NOT EXISTS ix_agent_leases_expires ON agent_leases (expires_at)"),
    ("ix_agent_leases_issue", "CREATE INDEX IF NOT EXISTS ix_agent_leases_issue ON agent_leases (issue_number)"),
    ("ix_operational_tasks_status", "CREATE INDEX IF NOT EXISTS ix_operational_tasks_status ON operational_tasks (status)"),
    ("ix_operational_tasks_group", "CREATE INDEX IF NOT EXISTS ix_operational_tasks_group ON operational_tasks (group_name)"),
    ("ix_secret_rotations_name_scope", "CREATE INDEX IF NOT EXISTS ix_secret_rotations_name_scope ON secret_rotations (secret_name, scope)"),
    ("ix_audit_queue_status", "CREATE INDEX IF NOT EXISTS ix_audit_queue_status ON audit_queue (status)"),
    ("ix_client_slots_status", "CREATE INDEX IF NOT EXISTS ix_client_slots_status ON client_slots (status)"),
    ("ix_client_slots_tenant", "CREATE INDEX IF NOT EXISTS ix_client_slots_tenant ON client_slots (tenant_id)"),
]

TABLE_NAMES = [spec[0] for spec in _TABLE_DDLS]


def _to_flavor(ddl: str, flavor: str) -> str:
    """SQLite DDL → Postgres DDL (fixed transliteration, review-safe)।"""
    if flavor != "postgres":
        return ddl
    out = ddl
    for needle, replacement in _PG_FIXUPS.items():
        out = out.replace(needle, replacement)
    return out


def connect(
    db_url: str | None = None,
    sqlite_path: str | None = None,
) -> tuple[Any, str]:
    """Lazy connect — Postgres (canonical) অথবা SQLite (local mirror)।

    Priority: db_url > sqlite_path। দুটোই না দিলে স্পষ্ট error (fail-closed)।
    psycopg2 import শুধু দরকার পড়লেই হয় (CI/dry-run mode dependency-free)।
    """
    if db_url:
        try:
            import psycopg2  # lazy: dry-run mode-এ dependency লাগে না
        except ImportError as exc:  # pragma: no cover — env-specific
            raise RuntimeError(
                "psycopg2 নেই — Postgres mode-এর জন্য install করুন "
                "(pip install psycopg2-binary) অথবা --sqlite ব্যবহার করুন"
            ) from exc
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        return conn, "postgres"
    if sqlite_path:
        import sqlite3

        path = Path(sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(str(path)), "sqlite"
    raise RuntimeError("কোনো DB target নেই — --db-url অথবা --sqlite দিন (dry-run চাইলে কিছুই না)")


def ensure_schema(conn: Any, flavor: str) -> list[str]:
    """Create-if-missing সব operational-truth টেবিল + index (idempotent)।

    Return: যেসব object এই run-এ নতুন তৈরি হলো (observability)।
    """
    created: list[str] = []
    cur = conn.cursor()
    try:
        for name, _pks, ddl in _TABLE_DDLS:
            before = _object_exists(cur, flavor, name, "table")
            if not before:
                cur.execute(_to_flavor(ddl, flavor))
                created.append(f"table:{name}")
        for idx_name, idx_ddl in _INDEXES:
            exists = _object_exists(cur, flavor, idx_name, "index")
            if not exists:
                cur.execute(_to_flavor(idx_ddl, flavor))
                created.append(f"index:{idx_name}")
        conn.commit()
    finally:
        cur.close()
    return created


def _object_exists(cur: Any, flavor: str, name: str, kind: str) -> bool:
    """Table/index existence check (cross-flavor) — silent-false নয়, স্পষ্ট raise।"""
    if flavor == "postgres":
        if kind == "table":
            cur.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name = %s",
                (name,),
            )
        else:
            cur.execute(
                "SELECT 1 FROM pg_indexes "
                "WHERE schemaname = current_schema() AND indexname = %s",
                (name,),
            )
        return cur.fetchone() is not None
    if kind == "table":
        cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        )
    else:
        cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?", (name,)
        )
    return cur.fetchone() is not None


def _params(sql: str, flavor: str) -> str:
    """paramstyle conversion: template %s (postgres) ↔ ? (sqlite)।"""
    return sql if flavor == "postgres" else sql.replace("%s", "?")


def upsert_rows(
    conn: Any,
    flavor: str,
    table: str,
    rows: list[dict[str, Any]],
    conflict_cols: list[str],
    update_cols: list[str] | None = None,
) -> int:
    """Cross-flavor bulk UPSERT (INSERT ... ON CONFLICT ... DO UPDATE)।

    rows ফাঁকা হলে 0 return (no-op, error নয়)। update_cols None হলে
    conflict_cols বাদে বাকি সব column-ই update হবে।
    """
    if table not in TABLE_NAMES:
        raise ValueError(f"unknown operational-truth table: {table}")
    if not rows:
        return 0
    cols = list(rows[0].keys())
    # Row normalization: heterogeneous parser rows (কোনো row-এ key বাদ গেলে
    # None দিয়ে fill — INSERT সবসময় rows[0]-এর schema মেনে চলবে)
    normalized = [
        {c: row.get(c) for c in cols} for row in rows
    ]
    if update_cols is None:
        update_cols = [c for c in cols if c not in conflict_cols]
    placeholders = ", ".join(["%s"] * len(cols))
    col_list = ", ".join(cols)
    conflict_list = ", ".join(conflict_cols)
    set_list = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    sql = (
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict_list}) DO UPDATE SET {set_list}"
    )
    sql = _params(sql, flavor)
    cur = conn.cursor()
    try:
        for row in normalized:
            # JSON column-গুলো serialize করা হয় যদি dict/list পড়ে যায়
            values = [
                _json_dumps(v) if isinstance(v, (dict, list)) else v for v in row.values()
            ]
            cur.execute(sql, tuple(values))
        conn.commit()
    finally:
        cur.close()
    return len(rows)


def fetch_all(conn: Any, flavor: str, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Read helper — dict rows (report/query সুবিধার্থে)।"""
    cur = conn.cursor()
    try:
        cur.execute(_params(sql, flavor), params)
        if flavor == "postgres":
            cols = [d[0] for d in cur.description]
        else:
            cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        cur.close()


def _json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    ensure_p = sub.add_parser("ensure-schema", help="Create all operational-truth tables (idempotent)")
    ensure_p.add_argument("--db-url", default=None, help="Postgres URL (Supabase writer)")
    ensure_p.add_argument("--sqlite", default=None, help="SQLite path (local mirror)")

    sub.add_parser("tables", help="List managed table names")
    sub.add_parser("specs", help="Print DDL specs (flavor-agnostic review)")

    args = parser.parse_args()

    if args.cmd == "tables":
        for name in TABLE_NAMES:
            print(name)
        return 0
    if args.cmd == "specs":
        for name, pks, ddl in _TABLE_DDLS:
            print(f"-- {name} (pk: {', '.join(pks)})")
            print(ddl.strip())
        return 0

    try:
        conn, flavor = connect(db_url=args.db_url, sqlite_path=args.sqlite)
    except RuntimeError as exc:
        print(f"[ensure-schema] ✗ {exc}", file=sys.stderr)
        return 2
    try:
        created = ensure_schema(conn, flavor)
    finally:
        conn.close()
    if created:
        print(f"[ensure-schema] ✅ {flavor}: নতুন তৈরি → {', '.join(created)}")
    else:
        print(f"[ensure-schema] ✅ {flavor}: সব টেবিল/ইনডেক্স আগেই আছে (no-op)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
