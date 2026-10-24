"""
API Key Management Database Access Layer
Uses raw asyncpg via PgBouncerConnectionPool
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from database.pgbouncer_pool import get_db_pool


def now_epoch() -> int:
    return int(datetime.now(UTC).timestamp())


async def create_api_key(
    user_id: str,
    name: str,
    key_hash: str,
    key_masked: str,
    key_prefix: str,
    rate_limit_rps: int = 6,
    expires_at: int | None = None,
    scopes: list[str] | None = None,
) -> dict[str, Any] | None:
    pool = await get_db_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO api_keys (user_id, name, key_hash, key_masked, key_prefix,
                              rate_limit_rps, expires_at, created_at, updated_at, scopes)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING id, user_id, name, key_masked, key_prefix, rate_limit_rps,
                  revoked, expires_at, created_at, updated_at, scopes
        """,
        user_id,
        name,
        key_hash,
        key_masked,
        key_prefix,
        rate_limit_rps,
        expires_at,
        now_epoch(),
        now_epoch(),
        scopes or [],
    )
    return dict(row) if row else None


async def get_api_key_by_id(key_id: int) -> dict[str, Any] | None:
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT id, user_id, name, key_masked, key_prefix, rate_limit_rps, revoked, expires_at, created_at, updated_at, scopes FROM api_keys WHERE id = $1",
        key_id,
    )
    return dict(row) if row else None


async def get_api_keys_by_user(user_id: str) -> list[dict[str, Any]]:
    pool = await get_db_pool()
    rows = await pool.fetch(
        "SELECT id, user_id, name, key_masked, key_prefix, rate_limit_rps, revoked, "
        "expires_at, last_used_at, created_at, scopes FROM api_keys WHERE user_id = $1 "
        "ORDER BY created_at DESC",
        user_id,
    )
    return [dict(r) for r in rows]


async def get_api_key_by_hash(key_hash: str) -> dict[str, Any] | None:
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT id, user_id, name, key_hash, key_masked, revoked, expires_at, scopes FROM api_keys WHERE key_hash = $1",
        key_hash,
    )
    return dict(row) if row else None


async def update_api_key_last_used(key_id: int) -> None:
    pool = await get_db_pool()
    await pool.execute(
        "UPDATE api_keys SET last_used_at = $1, updated_at = $2 WHERE id = $3",
        now_epoch(),
        now_epoch(),
        key_id,
    )


async def revoke_api_key(key_id: int) -> dict[str, Any] | None:
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "UPDATE api_keys SET revoked = TRUE, updated_at = $1 WHERE id = $2 RETURNING id, name, key_masked, revoked, updated_at",
        now_epoch(),
        key_id,
    )
    return dict(row) if row else None


async def delete_api_key(key_id: int) -> bool:
    pool = await get_db_pool()
    result = await pool.execute("DELETE FROM api_keys WHERE id = $1", key_id)
    return result == "DELETE 1"


async def rotate_api_key(
    key_id: int,
    new_key_hash: str,
    new_key_masked: str,
    new_key_prefix: str,
) -> dict[str, Any] | None:
    pool = await get_db_pool()
    row = await pool.fetchrow(
        """
        UPDATE api_keys SET key_hash = $1, key_masked = $2, key_prefix = $3, updated_at = $4, revoked = FALSE
        WHERE id = $5
        RETURNING id, name, key_masked, key_prefix, revoked, created_at, updated_at
        """,
        new_key_hash,
        new_key_masked,
        new_key_prefix,
        now_epoch(),
        key_id,
    )
    return dict(row) if row else None


async def record_api_key_usage(
    key_id: int,
    endpoint: str,
    status_code: int,
    latency_ms: float,
    ip_address: str | None = None,
) -> None:
    pool = await get_db_pool()
    await pool.execute(
        """
        INSERT INTO api_key_usage (api_key_id, endpoint, status_code, latency_ms, ip_address, created_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        key_id,
        endpoint,
        status_code,
        latency_ms,
        ip_address,
        now_epoch(),
    )


async def get_api_key_usage(key_id: int, limit: int = 100) -> list[dict[str, Any]]:
    pool = await get_db_pool()
    rows = await pool.fetch(
        "SELECT id, api_key_id, endpoint, status_code, latency_ms, ip_address, created_at "
        "FROM api_key_usage WHERE api_key_id = $1 ORDER BY created_at DESC LIMIT $2",
        key_id,
        limit,
    )
    return [dict(r) for r in rows]


async def get_api_key_usage_stats(key_id: int) -> dict[str, Any]:
    pool = await get_db_pool()
    row = await pool.fetchrow(
        """
        SELECT
            COUNT(*) as total_requests,
            COUNT(*) FILTER (WHERE status_code >= 400) as error_count,
            AVG(latency_ms) as avg_latency_ms,
            MAX(latency_ms) as max_latency_ms,
            MIN(created_at) as first_request_at,
            MAX(created_at) as last_request_at
        FROM api_key_usage WHERE api_key_id = $1
        """,
        key_id,
    )
    return dict(row) if row else {}


async def record_api_key_event(
    key_id: int,
    event_type: str,
    details: str | None = None,
    ip_address: str | None = None,
) -> None:
    pool = await get_db_pool()
    await pool.execute(
        "INSERT INTO api_key_events (api_key_id, event_type, details, ip_address, created_at) VALUES ($1, $2, $3, $4, $5)",
        key_id,
        event_type,
        details,
        ip_address,
        now_epoch(),
    )


async def get_all_api_keys(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    pool = await get_db_pool()
    rows = await pool.fetch(
        "SELECT id, user_id, name, key_masked, key_prefix, rate_limit_rps, revoked, "
        "expires_at, last_used_at, created_at, scopes FROM api_keys ORDER BY created_at DESC "
        "LIMIT $1 OFFSET $2",
        limit,
        offset,
    )
    return [dict(r) for r in rows]
