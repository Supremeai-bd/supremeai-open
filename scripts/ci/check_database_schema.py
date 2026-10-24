#!/usr/bin/env python3
"""
check_database_schema.py
=========================
Connects to the REAL database (production or whatever DATABASE_URL points
to) read-only, and diffs it against the canonical contract at
backend/database/contracts/schema_contract.yaml.

This is the permanent guardrail against the kind of silent drift found in
the 2026-08-30 audit (missing columns, missing indexes, incompatible
schemas that only surface as runtime failures).

Exit codes:
  0 -> no required (blocking) issues found (warnings are still printed)
  1 -> at least one required table/column/index is missing
  2 -> could not connect / contract file missing / other setup error

Usage:
  DATABASE_URL=postgresql://... python scripts/ci/check_database_schema.py

Writes a human-readable report to stdout and, if GITHUB_STEP_SUMMARY is
set, a Markdown summary for the Actions run summary page.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required (`pip install pyyaml`)", file=sys.stderr)
    sys.exit(2)

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: psycopg2 is required (`pip install psycopg2-binary`)", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "backend" / "database" / "contracts" / "schema_contract.yaml"


def load_contract() -> dict:
    if not CONTRACT_PATH.exists():
        print(f"ERROR: contract file not found at {CONTRACT_PATH}", file=sys.stderr)
        sys.exit(2)
    with open(CONTRACT_PATH) as f:
        return yaml.safe_load(f)


def get_db_url() -> str:
    url = (
        os.environ.get("DB_SCHEMA_CHECK_URL")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("SUPABASE_DATABASE_URL")
    )
    if not url:
        print(
            "ERROR: no database URL found. Set DB_SCHEMA_CHECK_URL "
            "(preferred, should be a read-only role) or DATABASE_URL.",
            file=sys.stderr,
        )
        sys.exit(2)
    return url


def verify_readonly_identity(conn) -> None:
    """Fail loudly (not just quietly proceed) if this connection is not what
    we expect: a genuinely read-only session, ideally under the dedicated
    ci_schema_check_ro role. This is a safety check so a misconfigured
    DB_SCHEMA_CHECK_URL secret can never accidentally point this job at a
    privileged/writable credential.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT current_user, current_setting('transaction_read_only')")
        current_user, read_only = cur.fetchone()

    print(f"Connected as: {current_user} | transaction_read_only={read_only}")

    if read_only != "on":
        print(
            "ERROR: database session is NOT read-only (transaction_read_only=off). "
            "Refusing to proceed — DB_SCHEMA_CHECK_URL must point to a read-only "
            "role/connection.",
            file=sys.stderr,
        )
        sys.exit(2)

    if current_user != "ci_schema_check_ro":
        print(
            f"WARNING: connected as '{current_user}', not the dedicated "
            "'ci_schema_check_ro' role. This still works because the session "
            "is enforced read-only, but using a dedicated least-privilege "
            "role is strongly recommended (set DB_SCHEMA_CHECK_URL)."
        )


def fetch_live_schema(conn) -> tuple[set[str], dict[str, set[str]], set[str]]:
    """Returns (tables, {table: {columns}}, indexes)."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        )
        tables = {r["table_name"] for r in cur.fetchall()}

        cur.execute(
            "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public'"
        )
        columns: dict[str, set[str]] = {}
        for r in cur.fetchall():
            columns.setdefault(r["table_name"], set()).add(r["column_name"])

        cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
        indexes = {r["indexname"] for r in cur.fetchall()}

    return tables, columns, indexes


def main() -> int:
    contract = load_contract()
    db_url = get_db_url()

    try:
        conn = psycopg2.connect(db_url, connect_timeout=10)
        conn.set_session(readonly=True, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not connect to database: {exc}", file=sys.stderr)
        if "Network is unreachable" in str(exc) and "supabase" in db_url.lower():
            print("\n⚠️ WARNING: Supabase IPv6 connection blocked by GitHub Actions.", file=sys.stderr)
            print("Skipping schema check gracefully. To enable this check, set DB_SCHEMA_CHECK_URL to an IPv4 (Supavisor Pooler) string.", file=sys.stderr)
            # Write to github step summary if available
            summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary_file:
                with open(summary_file, "a") as f:
                    f.write("\n### 🗄️ Database Schema Contract Check\n")
                    f.write("⚠️ **Skipped**: Supabase direct connection (IPv6) is not supported in GitHub Actions.\n")
                    f.write("Please update `DB_SCHEMA_CHECK_URL` secret to use the Supavisor Pooler (IPv4) connection string.\n")
            return 0
        return 2

    try:
        verify_readonly_identity(conn)
        live_tables, live_columns, live_indexes = fetch_live_schema(conn)
    finally:
        conn.close()

    errors: list[str] = []
    warnings: list[str] = []

    for table_name, table_spec in contract.get("tables", {}).items():
        table_required = table_spec.get("required", True)
        if table_name not in live_tables:
            line = f"table `{table_name}` is missing"
            if table_required:
                errors.append(line)
            else:
                warnings.append(f"{line} ({table_spec.get('note', 'non-blocking')})")
            continue

        for col_name, col_spec in (table_spec.get("columns") or {}).items():
            col_required = col_spec.get("required", True)
            if col_name not in live_columns.get(table_name, set()):
                line = f"column `{table_name}.{col_name}` is missing"
                if col_required:
                    errors.append(line)
                else:
                    warnings.append(f"{line} ({col_spec.get('note', 'non-blocking')})")

        for idx_name, idx_spec in (table_spec.get("indexes") or {}).items():
            idx_required = idx_spec.get("required", True)
            if idx_name not in live_indexes:
                line = f"index `{idx_name}` on `{table_name}` is missing"
                if idx_required:
                    errors.append(line)
                else:
                    warnings.append(f"{line} ({idx_spec.get('note', 'non-blocking')})")

    # --- Report ---
    print("=" * 70)
    print("DATABASE SCHEMA CONTRACT CHECK")
    print("=" * 70)
    print(f"Contract: {CONTRACT_PATH.relative_to(REPO_ROOT)}")
    print(f"Tables in live DB: {len(live_tables)}")
    print()

    if errors:
        print(f"❌ {len(errors)} REQUIRED issue(s) found:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("✅ No required (blocking) schema issues found.")

    if warnings:
        print(f"\n⚠️  {len(warnings)} warning(s) (known/non-blocking drift):")
        for w in warnings:
            print(f"  - {w}")

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a") as f:
            f.write("\n### 🗄️ Database Schema Contract Check\n")
            if errors:
                f.write(f"❌ **{len(errors)} blocking issue(s):**\n\n")
                for e in errors:
                    f.write(f"- {e}\n")
            else:
                f.write("✅ No required (blocking) schema issues found.\n")
            if warnings:
                f.write(f"\n⚠️ **{len(warnings)} warning(s):**\n\n")
                for w in warnings:
                    f.write(f"- {w}\n")

    if errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
