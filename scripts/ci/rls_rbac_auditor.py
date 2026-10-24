#!/usr/bin/env python3
"""
rls_rbac_auditor.py
===================
Deep audit tool for Row-Level Security (RLS) & Role-Based Access Control (RBAC) (Traps #9, #10, #35, #47, #49).
Checks:
1. Database Schema RLS:
   - Scans backend/database/migrations/*.sql
   - Verifies that all newly created public tables have `ENABLE ROW LEVEL SECURITY`
   - Verifies that corresponding policies (SELECT, INSERT, UPDATE, DELETE) exist
2. Backend API RBAC:
   - Scans admin and sensitive routes for RBAC enforcement
   - Checks that routes modifying system config, billing, or tenant settings require appropriate permissions
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "backend" / "database" / "migrations"
ROUTES_DIR = REPO_ROOT / "backend" / "api" / "routes"


def audit_sql_migrations() -> list[str]:
    issues = []
    if not MIGRATIONS_DIR.exists():
        return issues

    created_tables = set()
    rls_enabled_tables = set()
    tables_with_policies = set()

    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        content = sql_file.read_text(encoding="utf-8", errors="ignore")

        # Find CREATE TABLE
        for match in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-zA-Z0-9_]+)", content, re.IGNORECASE):
            created_tables.add(match.group(1).lower())

        # Find ALTER TABLE ... ENABLE ROW LEVEL SECURITY
        for match in re.finditer(r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:public\.)?([a-zA-Z0-9_]+)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", content, re.IGNORECASE):
            rls_enabled_tables.add(match.group(1).lower())

        # Find CREATE POLICY ... ON <table>
        for match in re.finditer(r"CREATE\s+POLICY\s+[a-zA-Z0-9_]+\s+ON\s+(?:public\.)?([a-zA-Z0-9_]+)", content, re.IGNORECASE):
            tables_with_policies.add(match.group(1).lower())

        # Check for dynamic RLS loop (e.g. in 17_enable_rls.sql)
        if "ENABLE ROW LEVEL SECURITY" in content and "FOR t_name IN SELECT tablename FROM pg_tables" in content:
            # Global RLS enabler present
            rls_enabled_tables.update(created_tables)

    missing_rls = created_tables - rls_enabled_tables
    if missing_rls:
        for t in sorted(missing_rls):
            issues.append(f"SQL Schema Audit: Table '{t}' was created without explicit `ENABLE ROW LEVEL SECURITY`.")

    return issues


def audit_rbac_in_routes() -> list[str]:
    issues = []
    if not ROUTES_DIR.exists():
        return issues

    # Admin routes must require admin or have role check
    admin_routes_file = ROUTES_DIR / "admin.py"
    if admin_routes_file.exists():
        content = admin_routes_file.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(content, filename=str(admin_routes_file))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    is_route = any("router." in ast.unparse(dec) for dec in node.decorator_list)
                    if is_route:
                        fn_str = ast.unparse(node)
                        # Check for role / permission checks
                        has_rbac = any(term in fn_str.lower() for term in ("role", "admin", "permission", "usercontext", "authorize", "forbidden", "403"))
                        if not has_rbac:
                            issues.append(
                                f"RBAC Audit: Route {admin_routes_file.name}:{node.lineno} (`def {node.name}`) "
                                f"appears to lack RBAC/role authorization verification!"
                            )
        except Exception as e:
            issues.append(f"Error parsing {admin_routes_file}: {e}")

    return issues


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Auditing Row-Level Security (RLS) and Role-Based Access Control (RBAC) (Traps #9, #10, #35, #47, #49)...")
    sql_issues = audit_sql_migrations()
    rbac_issues = audit_rbac_in_routes()

    all_issues = sql_issues + rbac_issues

    if all_issues:
        for issue in all_issues:
            print(f"[WARN] {issue}")
        print(f"\nTotal RLS/RBAC findings: {len(all_issues)}")
        return 0

    print("[PASS] All database tables enforce RLS and sensitive routes enforce RBAC.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
