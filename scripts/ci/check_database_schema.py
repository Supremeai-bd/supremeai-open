#!/usr/bin/env python3
"""
check_database_schema.py
=========================
Connects to the REAL database (production or whatever DATABASE_URL points
to) read-only, and diffs it against the canonical contract at
core/database/contracts/schema_contract.yaml.

This is the permanent guardrail against the kind of silent drift found in
the 2026-08-30 audit (missing columns, missing indexes, incompatible
schemas that only surface as runtime failures).

Layout-rename lesson (#3699, 2026-10-31): this script pointed at the
pre-rename `backend/` tree for its whole life, so it exited 2 ("contract
file not found") on every invocation and the guardrail silently never
guarded. The path now resolves against BOTH the current `core/` tree and
the legacy `backend/` tree and fails closed naming both candidates, so a
future rename breaks loudly, not silently.

Exit codes:
  0 -> no required (blocking) issues found (warnings are still printed)
  1 -> at least one required table/column/index/function is missing
  2 -> could not connect / contract file missing / other setup error

Usage:
  DATABASE_URL=postgresql://... python scripts/ci/check_database_schema.py
  python scripts/ci/check_database_schema.py --self-test   # no DB needed

Writes a human-readable report to stdout and, if GITHUB_STEP_SUMMARY is
set, a Markdown summary for the Actions run summary page.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # only needed for the live-diff path; --self-test stays zero-dep
    yaml = None

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # only needed for the live-diff path; --self-test stays zero-dep
    psycopg2 = None
    RealDictCursor = None

REPO_ROOT = Path(__file__).resolve().parents[2]
# Candidate layouts, newest first. `backend/` is the pre-rename tree kept
# only so the failure mode of a future rename is a loud, named exit — never
# a silent "file not found" every run (the #3699 lesson).
CONTRACT_CANDIDATES = (
    REPO_ROOT / "core" / "database" / "contracts" / "schema_contract.yaml",
    REPO_ROOT / "backend" / "database" / "contracts" / "schema_contract.yaml",
)


def resolve_contract_path() -> Path:
    """Return the first existing contract path; exit 2 naming ALL candidates."""
    for candidate in CONTRACT_CANDIDATES:
        if candidate.exists():
            return candidate
    listing = "\n  ".join(str(c) for c in CONTRACT_CANDIDATES)
    print(
        "ERROR: contract file not found at any known location:\n  "
        f"{listing}\n"
        "If the layout was renamed again, add the new path to CONTRACT_CANDIDATES "
        "and delete the stale one — never let this guard point at a ghost.",
        file=sys.stderr,
    )
    sys.exit(2)


def load_contract() -> dict:
    if yaml is None:
        print("ERROR: PyYAML is required (`pip install pyyaml`)", file=sys.stderr)
        sys.exit(2)
    contract_path = resolve_contract_path()
    with open(contract_path) as f:
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


def fetch_live_schema(
    conn,
) -> tuple[set[str], dict[str, set[str]], set[str], set[str]]:
    """Returns (tables, {table: {columns}}, indexes, functions)."""
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

        # RPC functions the code calls via .rpc("name", ...) — e.g. exec_sql.
        # information_schema.routines only lists routines the current role can
        # see, which is exactly the visibility the caller needs.
        cur.execute(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema='public'"
        )
        functions = {r["routine_name"] for r in cur.fetchall()}

    return tables, columns, indexes, functions


def diff_contract(
    contract: dict,
    live_tables: set[str],
    live_columns: dict[str, set[str]],
    live_indexes: set[str],
    live_functions: set[str],
) -> tuple[list[str], list[str]]:
    """Pure diff of the contract against live introspection snapshots.

    Returns (errors, warnings). Required gaps -> errors; required:false
    gaps -> warnings. Kept pure so --self-test can pin the semantics with
    no database involved.
    """
    errors: list[str] = []
    warnings: list[str] = []

    for table_name, table_spec in (contract.get("tables") or {}).items():
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

    for fn_name, fn_spec in (contract.get("functions") or {}).items():
        fn_required = fn_spec.get("required", True)
        if fn_name not in live_functions:
            line = f"function `{fn_name}` is missing"
            if fn_required:
                errors.append(line)
            else:
                warnings.append(f"{line} ({fn_spec.get('note', 'non-blocking')})")

    return errors, warnings


def _self_test() -> int:
    """Pin the diff_contract + path-resolution semantics with no database.

    Born from the #3699 root cause: this guard was dead from birth (ghost
    `backend/` path) and its contract could not even express the function
    class of drift it was built to catch. These checks make both failure
    modes loud if they ever regress.
    """
    failures: list[str] = []

    # 1. Contract path must resolve inside the CURRENT tree, not a ghost.
    if not resolve_contract_path().exists():
        failures.append("resolved contract path does not exist")
    if "backend" in str(resolve_contract_path()):
        failures.append("resolved contract path points at the legacy backend/ tree")

    live_cols = {"t1": {"a", "b"}}

    # 2. Required table gap -> error (blocking).
    errs, warns = diff_contract(
        {"tables": {"gone": {"required": True, "columns": {}}}},
        set(), {}, set(), set(),
    )
    if errs != ["table `gone` is missing"] or warns:
        failures.append(f"required table gap mis-routed: {errs} / {warns}")

    # 3. required:false column gap -> warning (non-blocking, #3544 born-red lesson).
    errs, warns = diff_contract(
        {"tables": {"t1": {"required": True, "columns": {"c": {"required": False, "note": "n"}}}}},
        {"t1"}, live_cols, set(), set(),
    )
    if errs or not warns:
        failures.append(f"optional column gap must warn, not error: {errs} / {warns}")

    # 4. Function section: missing required function -> error; optional -> warning.
    errs, warns = diff_contract(
        {"functions": {
            "must_exist": {"required": True},
            "maybe_later": {"required": False, "note": "pending migration"},
        }},
        set(), {}, set(), {"maybe_later"},
    )
    if errs != ["function `must_exist` is missing"] or warns:
        failures.append(f"function diff semantics wrong: {errs} / {warns}")

    # 5. Empty/absent sections must not crash (old code assumed keys exist).
    errs, warns = diff_contract({}, set(), {}, set(), set())
    if errs or warns:
        failures.append(f"empty contract must diff clean: {errs} / {warns}")

    if failures:
        print(f"SELF-TEST FAIL ({len(failures)}):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("SELF-TEST PASS (5 checks)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return _self_test()

    if psycopg2 is None:
        print(
            "ERROR: psycopg2 is required for the live check "
            "(`pip install psycopg2-binary`)",
            file=sys.stderr,
        )
        sys.exit(2)

    contract = load_contract()
    db_url = get_db_url()

    try:
        conn = psycopg2.connect(db_url, connect_timeout=10)
        conn.set_session(readonly=True, autocommit=True)
    except Exception as exc:
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
        live_tables, live_columns, live_indexes, live_functions = fetch_live_schema(conn)
    finally:
        conn.close()

    errors, warnings = diff_contract(
        contract, live_tables, live_columns, live_indexes, live_functions
    )

    # --- Report ---
    print("=" * 70)
    print("DATABASE SCHEMA CONTRACT CHECK")
    print("=" * 70)
    print(f"Contract: {resolve_contract_path().relative_to(REPO_ROOT)}")
    print(f"Tables in live DB: {len(live_tables)} | functions visible: {len(live_functions)}")
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
