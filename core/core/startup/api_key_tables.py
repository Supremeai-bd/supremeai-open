"""Startup database initialization helpers for SupremeAI."""

from __future__ import annotations

import time

from core.logging_config import logger
from database.pgbouncer_pool import get_db_pool
from monitoring.metrics_collector import record_db_operation


async def ensure_api_key_tables() -> None:
    """Ensure API key database tables exist."""
    pool = await get_db_pool()
    # Record the database operation
    start_time = time.time()
    success = True

    # বাংলা মন্তব্ব্য: PgBouncerConnectionPool.acquire() একটি coroutine হওয়ায় সরাসরি async context manager হিসেবে ব্যবহার করা যায় না।
    # তাই এটিকে প্রথমে await করে কানেকশনটি তুলে আনা হচ্ছে এবং finally ব্লকে রিলিজ করা হচ্ছে।
    conn = await pool.acquire()
    try:
        async with conn.transaction():
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    key_masked TEXT NOT NULL,
                    key_prefix TEXT NOT NULL,
                    rate_limit_rps INTEGER DEFAULT 6,
                    rate_limit_window INTEGER DEFAULT 60,
                    revoked BOOLEAN DEFAULT FALSE,
                    expires_at INTEGER,
                    last_used_at INTEGER,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            await conn.execute(
                """
                ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS scopes TEXT[];
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_key_usage (
                    id SERIAL PRIMARY KEY,
                    api_key_id INTEGER NOT NULL REFERENCES api_keys(id),
                    endpoint TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
                    ip_address TEXT,
                    created_at INTEGER NOT NULL
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_key_events (
                    id SERIAL PRIMARY KEY,
                    api_key_id INTEGER NOT NULL REFERENCES api_keys(id),
                    event_type TEXT NOT NULL,
                    details TEXT,
                    ip_address TEXT,
                    created_at INTEGER NOT NULL
                )
                """
            )
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)")
            await conn.execute(
                "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS rate_limit_window INTEGER DEFAULT 60"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_api_key_usage_key ON api_key_usage(api_key_id, created_at DESC)"
            )
    except Exception:
        success = False
        raise
    finally:
        await pool.release(conn)
        duration = time.time() - start_time
        await record_db_operation("ensure_api_key_tables", duration, success)

    logger.info("✅ API key tables ensured")
