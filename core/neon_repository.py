from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any
from uuid import UUID

import asyncpg

from core.config import settings

_pool: asyncpg.Pool | None = None


def _asyncpg_dsn(database_url: str) -> str:
    """asyncpg শুধু plain postgresql:// scheme বোঝে; SQLAlchemy-style
    'postgresql+asyncpg://' (test_settings/DATABASE_URL-এ ব্যবহৃত) দিলে
    asyncpg.create_pool() DSN parse করতে ব্যর্থ হয় — তাই ড্রাইভার সাফিক্স
    বাদ দেওয়া হচ্ছে।"""
    if "+" in database_url.split("://", 1)[0]:
        scheme, rest = database_url.split("://", 1)
        scheme = scheme.split("+", 1)[0]
        return f"{scheme}://{rest}"
    return database_url


async def get_neon_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        database_url = getattr(settings, "database_url", "") or getattr(
            settings, "supabase_database_url", ""
        )
        if not database_url:
            raise RuntimeError("DATABASE_URL is required for Neon persistence")
        _pool = await asyncpg.create_pool(dsn=_asyncpg_dsn(database_url), min_size=1, max_size=10)
    return _pool


async def close_neon_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _json(value: Mapping[str, Any] | None) -> str:
    return json.dumps(dict(value or {}), separators=(",", ":"))


def _decode_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _normalize_policy(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    for key in ("rules", "features", "actions", "limits"):
        normalized[key] = _decode_json(normalized.get(key)) or {}
    return normalized


async def load_policy(tenant_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    pool = await get_neon_pool()
    row = await pool.fetchrow(
        """
        SELECT tenant_id, user_id, rules, features, actions, limits, version, updated_by,
               created_at, updated_at
        FROM supremeai_policy_configs
        WHERE tenant_id = $1 AND user_id IS NOT DISTINCT FROM $2
        ORDER BY user_id NULLS FIRST, version DESC
        LIMIT 1
        """,
        tenant_id,
        user_id,
    )
    return _normalize_policy(row) if row else None


async def save_policy(
    tenant_id: str,
    updated_by: str,
    *,
    user_id: str | None = None,
    rules: Mapping[str, Any] | None = None,
    features: Mapping[str, Any] | None = None,
    actions: Mapping[str, Any] | None = None,
    limits: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    pool = await get_neon_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            existing = await connection.fetchrow(
                """
                SELECT id, rules, features, actions, limits, version
                FROM supremeai_policy_configs
                WHERE tenant_id = $1 AND user_id IS NOT DISTINCT FROM $2
                FOR UPDATE
                """,
                tenant_id,
                user_id,
            )
            if existing:
                row = await connection.fetchrow(
                    """
                    UPDATE supremeai_policy_configs
                    SET rules = rules || $2::jsonb,
                        features = features || $3::jsonb,
                        actions = actions || $4::jsonb,
                        limits = limits || $5::jsonb,
                        version = version + 1,
                        updated_by = $6,
                        updated_at = NOW()
                    WHERE id = $1
                    RETURNING tenant_id, user_id, rules, features, actions, limits, version, updated_by,
                              created_at, updated_at
                    """,
                    existing["id"],
                    _json(rules),
                    _json(features),
                    _json(actions),
                    _json(limits),
                    updated_by,
                )
            else:
                row = await connection.fetchrow(
                    """
                    INSERT INTO supremeai_policy_configs
                      (tenant_id, user_id, rules, features, actions, limits, version, updated_by)
                    VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb, 1, $7)
                    RETURNING tenant_id, user_id, rules, features, actions, limits, version, updated_by,
                              created_at, updated_at
                    """,
                    tenant_id,
                    user_id,
                    _json(rules),
                    _json(features),
                    _json(actions),
                    _json(limits),
                    updated_by,
                )
    return _normalize_policy(row)


async def create_task(
    *,
    task_id: UUID,
    tenant_id: str,
    user_id: str,
    url: str | None,
    goal: str,
    status: str,
    plan: Any = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    pool = await get_neon_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            if idempotency_key:
                existing = await connection.fetchrow(
                    """
                    SELECT id, tenant_id, user_id, url, goal, status, plan, approval, evidence,
                           idempotency_key, error, created_at, updated_at
                    FROM supremeai_browser_tasks
                    WHERE tenant_id = $1 AND user_id = $2 AND idempotency_key = $3
                    FOR UPDATE
                    """,
                    tenant_id,
                    user_id,
                    idempotency_key,
                )
                if existing:
                    return dict(existing)
            row = await connection.fetchrow(
                """
                INSERT INTO supremeai_browser_tasks
                  (id, tenant_id, user_id, url, goal, status, plan, idempotency_key)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
                RETURNING id, tenant_id, user_id, url, goal, status, plan, approval, evidence,
                          idempotency_key, error, created_at, updated_at
                """,
                task_id,
                tenant_id,
                user_id,
                url,
                goal,
                status,
                json.dumps(plan or []),
                idempotency_key,
            )
    return dict(row)


async def update_task_status(
    *, task_id: UUID, tenant_id: str, user_id: str, status: str
) -> dict[str, Any] | None:
    pool = await get_neon_pool()
    row = await pool.fetchrow(
        """
        UPDATE supremeai_browser_tasks
        SET status = $1, updated_at = NOW()
        WHERE id = $2 AND tenant_id = $3 AND user_id = $4
        RETURNING id, status, updated_at
        """,
        status,
        task_id,
        tenant_id,
        user_id,
    )
    return dict(row) if row else None


async def delete_task(*, task_id: UUID, tenant_id: str, user_id: str) -> bool:
    pool = await get_neon_pool()
    result = await pool.execute(
        "DELETE FROM supremeai_browser_tasks WHERE id = $1 AND tenant_id = $2 AND user_id = $3",
        task_id,
        tenant_id,
        user_id,
    )
    return result.endswith("1")


async def list_tasks(tenant_id: str, user_id: str) -> list[dict[str, Any]]:
    pool = await get_neon_pool()
    rows = await pool.fetch(
        """
        SELECT id, tenant_id, user_id, url, goal, status, plan, approval, evidence,
               idempotency_key, error, created_at, updated_at
        FROM supremeai_browser_tasks
        WHERE tenant_id = $1 AND user_id = $2
        ORDER BY created_at DESC
        """,
        tenant_id,
        user_id,
    )
    return [dict(row) for row in rows]


async def append_audit_event(
    *,
    tenant_id: str,
    user_id: str | None,
    event_type: str,
    resource_type: str,
    resource_id: str | None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    pool = await get_neon_pool()
    await pool.execute(
        """
        INSERT INTO supremeai_audit_events
          (tenant_id, user_id, event_type, resource_type, resource_id, metadata)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
        tenant_id,
        user_id,
        event_type,
        resource_type,
        resource_id,
        _json(metadata),
    )


__all__ = [
    "get_neon_pool",
    "close_neon_pool",
    "load_policy",
    "save_policy",
    "create_task",
    "update_task_status",
    "delete_task",
    "list_tasks",
    "append_audit_event",
]
