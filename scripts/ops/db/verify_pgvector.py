#!/usr/bin/env python3
"""
Verify pgvector extension and vector tables on the target PostgreSQL / Supabase instance.

Usage:
    python scripts/db/verify_pgvector.py [--dsn DATABASE_URL]
"""

from __future__ import annotations

import argparse
import os
import sys

try:
    import psycopg2
except ImportError:
    try:
        from psycopg import connect
    except ImportError:
        sys.exit("Missing dependency: psycopg2-binary or psycopg required.")


def get_connection(dsn: str):
    return psycopg2.connect(dsn, connect_timeout=5)


def verify_pgvector(dsn: str) -> bool:
    print("[INFO] Connecting to database to verify pgvector...")
    try:
        conn = get_connection(dsn)
    except Exception as e:
        print(f"[ERROR] Failed to connect to database: {e}")
        return False

    all_ok = True
    with conn.cursor() as cur:
        # 1. Check vector extension
        cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")
        ext = cur.fetchone()
        if ext:
            print(f"[OK] pgvector extension is installed: version {ext[1]}")
        else:
            print("[FAIL] pgvector extension is NOT installed in pg_extension!")
            all_ok = False

        # 2. Check vector tables
        vector_tables = ["ai_memory", "knowledge_base", "knowledge_chunks"]
        for table in vector_tables:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                );
                """,
                (table,),
            )
            exists = cur.fetchone()[0]
            if exists:
                print(f"[OK] Table '{table}' exists.")
                # Check embedding column type
                cur.execute(
                    """
                    SELECT column_name, udt_name 
                    FROM information_schema.columns 
                    WHERE table_name = %s AND column_name = 'embedding';
                    """,
                    (table,),
                )
                col = cur.fetchone()
                if col:
                    print(f"     -> Column 'embedding' type: {col[1]}")
                else:
                    print(f"     [WARN] Table '{table}' does not have an 'embedding' column.")
            else:
                print(f"[INFO] Table '{table}' does not exist (optional/not yet migrated).")

        # 3. Check HNSW / IVFFLAT indexes
        cur.execute(
            """
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE indexdef ILIKE '%hnsw%' OR indexdef ILIKE '%ivfflat%';
            """
        )
        indexes = cur.fetchall()
        if indexes:
            print(f"[OK] Found {len(indexes)} vector index(es):")
            for idx in indexes:
                print(f"     -> {idx[0]}")
        else:
            print("[INFO] No HNSW or IVFFLAT vector indexes found.")

    conn.close()
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Verify pgvector on Postgres/Supabase")
    parser.add_argument("--dsn", default=None, help="Postgres connection DSN")
    args = parser.parse_args()

    dsn = args.dsn
    if not dsn:
        try:
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
            from core.config import settings

            dsn = (
                getattr(settings, "supabase_database_url_writer", None)
                or getattr(settings, "supabase_database_url", None)
            )
        except Exception:
            dsn = os.getenv("SUPABASE_DATABASE_URL_WRITER")

    if not dsn:
        print("[WARN] No database URL available. Skipping live check (exit 0).")
        sys.exit(0)

    ok = verify_pgvector(dsn)
    if not ok:
        sys.exit(1)
    print("[SUCCESS] pgvector verification completed successfully.")


if __name__ == "__main__":
    main()
