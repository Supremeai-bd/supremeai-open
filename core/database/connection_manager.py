"""
Unified Database Connection Manager for SupremeAI 2.0

This module provides a single, unified interface for accessing all database
connection pools in the system. It wraps the three existing pool implementations:

1. SQLAlchemy Async Engine (database/session.py) - ORM-based access
2. asyncpg Connection Pool (core/pgbouncer_pool.py) - Raw SQL, high performance
3. psycopg2 Threaded Pool (core/persistence/pooled_pg.py) - Sync legacy access

This is an ADDITIVE module — it does not modify any existing pool implementations.
It provides a convenience layer for new code to access the appropriate pool
without needing to know which pool to use.

Usage:
    from core.database.connection_manager import connection_manager

    # Get async ORM session
    async for session in connection_manager.orm_sessions():
        ...

    # Get asyncpg pool for raw SQL
    pool = await connection_manager.raw_pool()
    rows = await pool.fetch("SELECT * FROM users")

    # Get sync connection for legacy code
    with connection_manager.sync_connection() as conn:
        ...
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from core.logging_config import logger

# Lazy imports to avoid circular dependencies
# These are imported on-demand in the methods below


class ConnectionManager:
    """
    Unified database connection manager.

    Provides a single interface for accessing all three database connection pools:
    - SQLAlchemy async engine (ORM)
    - asyncpg connection pool (raw SQL)
    - psycopg2 threaded pool (sync legacy)

    All pools are lazily initialized on first access.
    """

    _instance: ConnectionManager | None = None
    _init_lock: asyncio.Lock | None = None

    def __new__(cls) -> ConnectionManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._orm_engine = None
        self._orm_session_maker = None
        self._raw_pool = None
        self._sync_pool = None
        logger.debug("ConnectionManager initialized (lazy pools)")

    @classmethod
    def get_instance(cls) -> ConnectionManager:
        """Get the singleton ConnectionManager instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── SQLAlchemy ORM (Async) ────────────────────────────────────────────────

    @asynccontextmanager
    async def orm_session(self) -> AsyncGenerator[Any, None]:
        """Get an async ORM session from the SQLAlchemy engine.

        Yields:
            An AsyncSession for ORM operations.

        Example:
            async with connection_manager.orm_session() as session:
                result = await session.execute(select(User))
        """
        from database.session import get_async_session

        async for session in get_async_session():
            yield session

    # ── asyncpg Raw SQL Pool (Async) ─────────────────────────────────────────

    async def raw_pool(self) -> Any:
        """Get the asyncpg connection pool for raw SQL queries.

        Returns:
            The asyncpg Pool instance.

        Raises:
            RuntimeError: If the pool hasn't been initialized during startup.

        Example:
            pool = await connection_manager.raw_pool()
            rows = await pool.fetch("SELECT * FROM users WHERE id = $1", user_id)
        """
        from database.pgbouncer_pool import get_db_pool

        if self._raw_pool is None:
            self._raw_pool = await get_db_pool()
        return self._raw_pool

    async def raw_pool_with_retry(self, max_retries: int = 3, initial_delay: float = 1.0) -> Any:
        """Get the asyncpg pool with exponential backoff retry.

        Args:
            max_retries: Maximum number of retry attempts.
            initial_delay: Initial delay in seconds (doubles each retry).

        Returns:
            The asyncpg Pool instance.
        """
        from database.pgbouncer_pool import get_db_pool_with_retry

        if self._raw_pool is None:
            self._raw_pool = await get_db_pool_with_retry(
                max_retries=max_retries, initial_delay=initial_delay
            )
        return self._raw_pool

    # ── psycopg2 Sync Pool ───────────────────────────────────────────────────

    @contextmanager
    def sync_connection(self) -> Any:
        """Get a synchronous database connection from the psycopg2 pool.

        Yields:
            A psycopg2 connection for sync operations.

        Example:
            with connection_manager.sync_connection() as conn:
                conn.execute("INSERT INTO checkpoints ...")
        """
        from core.persistence.pooled_pg import get_sync_connection

        with get_sync_connection() as conn:
            yield conn

    # ── Health Check ─────────────────────────────────────────────────────────

    async def health_check(self) -> dict[str, bool]:
        """Check the health of all connection pools.

        Returns:
            A dictionary mapping pool names to their health status.
        """
        health: dict[str, bool] = {
            "orm_engine": False,
            "raw_pool": False,
            "sync_pool": False,
        }

        # Check ORM engine
        try:
            from database.session import get_async_session

            async for session in get_async_session():
                await session.execute(__import__("sqlalchemy").text("SELECT 1"))
                health["orm_engine"] = True
                break
        except Exception as e:
            logger.warning(f"ORM engine health check failed: {e}")

        # Check raw pool
        try:
            pool = await self.raw_pool()
            await pool.fetchval("SELECT 1")
            health["raw_pool"] = True
        except Exception as e:
            logger.warning(f"Raw pool health check failed: {e}")

        # Check sync pool
        try:
            with self.sync_connection() as conn:
                conn.execute("SELECT 1")
                health["sync_pool"] = True
        except Exception as e:
            logger.warning(f"Sync pool health check failed: {e}")

        return health


# Singleton instance for convenience
connection_manager = ConnectionManager()
