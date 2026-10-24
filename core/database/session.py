from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from core.config import settings
from core.degraded_mode import allow_db_degradation
from core.logging_config import logger


# বাংলা মন্তব্য: কানেকশন স্ট্রিংয়ে postgresql:// বা postgres:// থাকলে তা asyncpg-এর জন্য postgresql+asyncpg:// দিয়ে প্রতিস্থাপন করা হচ্ছে
def get_async_url(url: str) -> str:
    if not url or not isinstance(url, str):
        return "sqlite+aiosqlite:///:memory:"
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith(("sqlite://", "sqlite+aiosqlite://", "postgresql+asyncpg://")):
        return url
    raise ValueError(
        "Unsupported database URL scheme; refusing silent SQLite fallback. "
        "Use PostgreSQL/asyncpg or an explicit SQLite URL for local tests."
    )


# ── Lazy Engine Initialization ──────────────────────────────────────────────
# বাংলা মন্তব্য: engine ও AsyncSessionLocal এখন lazily initialize হয় — module import-এ নয়।
# এতে playwright-এর config.webServer বা অ্যাসিনক্রোনাস বুট সিকোয়েন্সে
# ডাটাবেস কানেকশন ছাড়াই সার্ভার বুট হতে পারে।
# প্রথমবার engine/AsyncSessionLocal অ্যাক্সেস করলেই কেবল create_async_engine() কল হবে।

_engine_instance: AsyncEngine | None = None
_session_maker_instance: async_sessionmaker[AsyncSession] | None = None


# বাংলা মন্তব্য (BUG FIX v2): asyncpg-এর ডিফল্ট statement-নাম জেনারেটর প্রতি Connection
# object-এ ০ থেকে sequential counter ব্যবহার করে (__asyncpg_stmt_0__, _1__, ...)। PgBouncer
# transaction pooling mode একই backend PostgreSQL সেশন একাধিক ভিন্ন asyncpg Connection-এর
# মধ্যে ভাগ করে, ফলে দুটো ভিন্ন connection স্বাধীনভাবে গণনা করে একই নাম (যেমন
# "__asyncpg_stmt_6__") তৈরি করতে পারে — pgbouncer সেগুলোকে একই backend-এ multiplex করলে
# 'DuplicatePreparedStatementError' হয়। শুধু statement_cache_size=0 এই নাম-সংঘর্ষ ঠেকায় না
# (SQLAlchemy-এর asyncpg dialect cache নির্বিশেষে সবসময় Connection.prepare() কল করে —
# sqlalchemy/discussions/10246)। প্রকৃত সমাধান: UUID-ভিত্তিক সম্পূর্ণ random নাম, যাতে দুটো
# ভিন্ন connection কখনো একই নাম জেনারেট না করে।
def _build_random_name_connection_class():
    from uuid import uuid4

    from asyncpg import Connection as _AsyncpgConnection

    class RandomNameConnection(_AsyncpgConnection):
        def _get_unique_id(self, prefix: str) -> str:
            return f"__asyncpg_{prefix}_{uuid4().hex}__"

    return RandomNameConnection


def _build_engine_kwargs(async_url: str) -> dict[str, Any]:
    """বাংলা: async_url-এর ধরণ (sqlite/postgresql) অনুসারে engine kwargs তৈরি করে।"""
    engine_kwargs: dict[str, Any] = {"echo": False}
    if async_url.startswith("sqlite"):
        engine_kwargs["poolclass"] = StaticPool
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    elif async_url.startswith("postgresql"):
        _role = settings.service_role.lower()

        # বাংলা মন্তব্য: asyncpg এর জন্য prepared statement সংক্রান্ত সেটিংস connect_args-এর ভেতরে থাকতে হবে
        from core.db_ssl import build_supabase_ssl_context

        engine_kwargs.update(
            {
                # NullPool: SQLAlchemy নিজে connection পুল না রেখে প্রতিটি অপারেশনে নতুন
                # connection নেয় ও ছাড়ে — PgBouncer-এর backend connection lifecycle-এর
                # সাথে SQLAlchemy-এর নিজস্ব pooling "double-pooling" করে স্ট্যাল
                # prepared-statement অবস্থা তৈরি করে না।
                "poolclass": NullPool,
                "pool_pre_ping": True,
                "connect_args": {
                    "command_timeout": 30,
                    "server_settings": {"application_name": f"supremeai_2_0_{_role}"},
                    "statement_cache_size": 0,
                    "connection_class": _build_random_name_connection_class(),
                    "ssl": build_supabase_ssl_context(),
                },
            }
        )
        logger.info(
            f"🔌 DB engine configured for SERVICE_ROLE='{_role}': poolclass=NullPool, "
            f"statement_cache_size=0, random prepared-statement names (PgBouncer-safe)."
        )
    return engine_kwargs


import os
import time

from sqlalchemy import event

# বাংলা মন্তব্য: স্লো কুয়েরি ডিটেকশনের থ্রেশহোল্ড (ডিফল্ট: 0.2 সেকেন্ড / 200ms)
from core.config import settings

SLOW_QUERY_THRESHOLD_SECONDS = settings.db_slow_query_threshold


def _attach_query_listeners(async_engine: AsyncEngine) -> None:
    """বাংলা: স্লো কুয়েরি মনিটরিং এবং কোডবেস প্রোফাইলিংয়ের জন্য ইভেন্ট লিসেনার।"""
    sync_engine = async_engine.sync_engine

    @event.listens_for(sync_engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("_query_start_times", []).append(time.monotonic())

    @event.listens_for(sync_engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        start_times = conn.info.get("_query_start_times")
        if start_times:
            duration = time.monotonic() - start_times.pop()
            if duration > SLOW_QUERY_THRESHOLD_SECONDS:
                clean_stmt = " ".join(statement.split())[:300]
                logger.warning(
                    f"🐢 [SLOW DB QUERY] {duration:.3f}s (> {SLOW_QUERY_THRESHOLD_SECONDS}s) | Query: {clean_stmt}"
                )


def init_engine() -> None:
    """বাংলা: engine ও AsyncSessionLocal একবার lazily initialize করে।

    import-এর সময় নয় — প্রথমবার engine/AsyncSessionLocal অ্যাক্সেসের সময় কল হয়।
    Safe to call multiple times — second call is a no-op.
    """
    global _engine_instance, _session_maker_instance
    if _engine_instance is not None:
        return

    DATABASE_URL = settings.supabase_database_url
    # Master audit 2026-09-02: env-gated production degradation.
    # Default behaviour is UNCHANGED (fail-fast in production). When
    # SUPABASE_ALLOW_DB_DEGRADATION=true is explicitly set (free-tier
    # deployments where the DB pooler password is not provisioned yet), the
    # server boots and serves all Supabase-REST-based features; raw
    # SQLAlchemy/asyncpg routes fail per-request instead of killing the whole
    # node in a crash loop. Set SUPABASE_DATABASE_URL_POOLER to re-enable the
    # strict path — no code change needed, just remove/rename the opt-in var.
    # P0 (Task 9-c): the flag is now resolved via core.degraded_mode, the
    # single source of truth shared by every subsystem SQLite-fallback gate.
    _ALLOW_DB_DEGRADATION = allow_db_degradation()
    if not DATABASE_URL:
        # বাংলা: production-এ missing DB URL = fail-fast। test/CI-এ SQLite fallback।
        current_env = (getattr(settings, "env", "") or "").lower()
        if current_env in ("production", "prod"):
            if _ALLOW_DB_DEGRADATION:
                logger.critical(
                    "DEGRADED BOOT (opt-in): SUPABASE_DATABASE_URL_POOLER missing in "
                    "PRODUCTION — booting WITHOUT the SQLAlchemy engine "
                    "(SUPABASE_ALLOW_DB_DEGRADATION=true). REST-based features work; "
                    "SQL-dependent routes will error per-request until the pooler URL is set."
                )
                return
            else:
                logger.critical(
                    "FATAL: SUPABASE_DATABASE_URL_POOLER missing in PRODUCTION. "
                    "Refusing to boot with SQLite fallback (data loss risk). "
                    "Set SUPABASE_ALLOW_DB_DEGRADATION=true to boot in degraded REST-only mode."
                )
                raise RuntimeError("Production environment requires SUPABASE_DATABASE_URL_POOLER")
        else:
            logger.warning(
                "SUPABASE_DATABASE_URL_POOLER is missing. Falling back to SQLite in-memory (test/dev only)."
            )

    _async_url = get_async_url(DATABASE_URL or "")
    engine_kwargs = _build_engine_kwargs(_async_url)

    try:
        _engine_instance = create_async_engine(_async_url, **engine_kwargs)
        _attach_query_listeners(_engine_instance)
        _session_maker_instance = async_sessionmaker(
            bind=_engine_instance,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    except Exception as exc:
        # বাংলা: production-ে ফেইল-ফাস্ট, test/staging-এ SQLite fallback।
        current_env = (getattr(settings, "env", "") or "").lower()
        if current_env in ("production", "prod") and not _ALLOW_DB_DEGRADATION:
            logger.critical(f"FATAL: Failed to create DB engine in PRODUCTION: {exc}")
            raise RuntimeError(f"Production DB engine creation failed: {exc}") from exc
        if current_env in ("production", "prod") and _ALLOW_DB_DEGRADATION:
            logger.critical(
                f"DEGRADED BOOT (opt-in): DB engine creation failed in PRODUCTION: {exc}. "
                "Booting WITHOUT the SQLAlchemy engine."
            )
            return
        logger.error(
            f"Failed to create DB engine for '{_async_url}': {exc}. Falling back to SQLite in-memory."
        )
        fallback_url = "sqlite+aiosqlite:///:memory:"
        _engine_instance = create_async_engine(
            fallback_url,
            echo=False,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        _attach_query_listeners(_engine_instance)
        _session_maker_instance = async_sessionmaker(
            bind=_engine_instance,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )


# ── Internal accessor (resolves lazy init for intra-module use) ──────────────
def _get_session_maker() -> async_sessionmaker[AsyncSession]:
    """বাংলা: get_db_session_context()-এর ভিতরে AsyncSessionLocal-এর জন্য internal accessor।"""
    init_engine()
    if _session_maker_instance is None:
        raise RuntimeError(
            "Database engine is not initialized (running in degraded REST-only mode). "
            "Set SUPABASE_DATABASE_URL_POOLER to enable SQL access."
        )
    return _session_maker_instance


# ── Import-safe placeholder for degraded REST-only mode ────────────────────
# বাংলা মন্তব্য (PROD OUTAGE FIX 2026-09-02): P0 fail-closed fix-এর পর degraded
# REST-only mode-এ module-level `from database.session import AsyncSessionLocal`
# import-ই startup crash করাচ্ছিল — __getattr__ সাথে সাথে RuntimeError raise করত,
# ফলে FastAPI lifespan fail → port bind fail → Render port-scan timeout →
# update_failed loop (primary + scraper উভয় node প্রভাবিত)। এই placeholder
# import-safe: ব্যবহার করার সময় (call/attribute) তবেই RuntimeError হয়, এবং engine
# পরে initialize হলে (init_engine() প্রতি access-এ retry করে) স্বয়ংক্রিয়ভাবে
# real session maker-এ delegate করে — কোনো stale binding ভাঙে না।
class _UninitializedSessionMaker:
    """Stands in for AsyncSessionLocal while the engine is unavailable.

    Import-safe: importing it never raises. Any real USE (calling it to create a
    session or touching an attribute) retries init_engine() and then either
    delegates to the real session maker or raises the same helpful RuntimeError
    as _get_session_maker() (degraded REST-only mode) — per-request, never at
    import time, so a missing SUPABASE_DATABASE_URL_POOLER can no longer kill
    application startup.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> AsyncSession:
        return _get_session_maker()(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        # Attribute access also defers to the real maker or raises RuntimeError
        # while degraded — never returns a fake object (fail-closed preserved).
        return getattr(_get_session_maker(), name)

    def __repr__(self) -> str:
        return "<AsyncSessionLocal (uninitialized — degraded REST-only mode)>"


# ── Module-level __getattr__ for lazy backward-compatible access ─────────────
# বাংলা মন্তব্য: hundreds of files use `from database.session import engine, AsyncSessionLocal`.
# __getattr__ ensures those imports still work — engine is initialized on first real access.
def __getattr__(name: str):
    if name == "engine":
        init_engine()
        return _engine_instance
    if name == "AsyncSessionLocal":
        init_engine()
        if _session_maker_instance is not None:
            return _session_maker_instance
        return _UninitializedSessionMaker()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """বাংলা: dir()-এ engine ও AsyncSessionLocal দেখানোর জন্য।"""
    return [*list(globals().keys()), "engine", "AsyncSessionLocal"]


@asynccontextmanager
async def get_db_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for backend tasks or non-FastAPI usages.

    বাংলা: FastAPI-এর বাইরে বা ব্যাকগ্রাউন্ড টাস্কে ডাটাবেস সেশন ব্যবহারের জন্য।
    """
    from fastapi import HTTPException
    from sqlalchemy.exc import TimeoutError as SATimeoutError

    try:
        session_maker = _get_session_maker()
    except RuntimeError as e:
        logger.error(f"Database session requested but DB is degraded: {e}")
        raise HTTPException(
            status_code=503,
            detail="Database service unavailable (running in degraded REST-only mode).",
        ) from e

    try:
        async with session_maker() as session:
            try:
                yield session
            except Exception as e:
                await session.rollback()
                logger.error(f"Database transaction rolled back due to error: {e}")
                raise
    except (TimeoutError, SATimeoutError) as e:
        logger.error(f"Database pool exhausted: {e}")
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable due to high load (DB pool exhausted).",
        ) from e


# FastAPI Dependency Injection (with safe rollback)
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency for database sessions.

    বাংলা: FastAPI রুটগুলোর জন্য ডাটাবেস ডিপেন্ডেন্সি।
    """
    async with get_db_session_context() as session:
        yield session


async def check_engine_health() -> bool:
    """Check if database engine is reachable and responsive.

    বাংলা: ডাটাবেস ইঞ্জিন সচল ও সংযোগযোগ্য কিনা যাচাই করে।
    """
    from sqlalchemy import text

    try:
        init_engine()
        engine = _engine_instance
        if engine is None:
            logger.info("Database engine not initialized (degraded mode) — reporting unhealthy")
            return False
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning(f"Database health check probe failed: {e}")
        return False


async def dispose_engine() -> None:
    """Dispose all engine pools cleanly. Call during graceful shutdown.

    বাংলা: শাটডাউনের সময় সমস্ত ডাটাবেস কানেকশন পুল ক্লোজ করে।
    """
    global _engine_instance, _session_maker_instance
    if _engine_instance is not None:
        logger.info("Disposing database engine pools...")
        await _engine_instance.dispose()
        _engine_instance = None
        _session_maker_instance = None
