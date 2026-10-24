import asyncio
import os

from core.cache.redis_manager import redis_manager
from core.config import settings
from core.config_cache import config_cache
from core.logging_config import logger
from core.maintenance_pipeline import maintenance_pipeline
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus
from core.reliability_controller import ReliabilityController
from core.startup.api_key_tables import ensure_api_key_tables as _ensure_api_key_tables
from database.pgbouncer_pool import PgBouncerConnectionPool, get_db_pool, init_db_pool


async def initialize_independent_services(app):
    async def _init_tracing() -> None:
        """Initialize OpenTelemetry tracing in a thread to avoid blocking."""
        try:
            from core.observability.telemetry import setup_tracing

            await asyncio.to_thread(setup_tracing)
            logger.info("✅ OpenTelemetry tracing provider successfully initialized.")
        except Exception as exc:
            logger.warning(f"Failed to initialize tracing provider: {exc}")
            error_event_bus.emit(
                ErrorEvent(
                    module="lifespan",
                    error_type="TRACING_INIT_FAILED",
                    message=str(exc)[:200],
                    severity="WARNING",
                    structured_context=ErrorContext(module="auto_fixed"),
                    context={"component": "opentelemetry"},
                )
            )

    async def _init_db_pool() -> None:
        """Initialize database connection pool and API key tables with unified connection management."""
        _db_url = settings.supabase_database_url
        try:
            if "sqlite" in _db_url:
                logger.info(
                    "💾 SQLite Memory Database Detected for Agent Telemetry. Skipping PostgreSQL asyncpg pool initialization."
                )
                app.state.db_pool = None
            else:
                # Helper function to initialize and health check a specific DB pool
                async def _try_connect_and_check(db_url: str) -> PgBouncerConnectionPool | None:
                    await init_db_pool(db_url)
                    pool = await get_db_pool()
                    if pool:
                        try:
                            conn = await pool.acquire()
                            try:
                                await conn.fetchval("SELECT 1")
                            finally:
                                await pool.release(conn)
                        except Exception as health_exc:
                            raise health_exc from health_exc
                    return pool

                # 1. Attempt Primary DB (Supabase)
                try:
                    pool = await _try_connect_and_check(_db_url)
                    logger.info(
                        "✅ Database connection pool health check passed. Connected to Primary DB (Supabase)."
                    )
                except Exception as primary_exc:
                    logger.error(f"❌ Primary DB (Supabase) failed: {primary_exc}.")
                    raise Exception(
                        f"Primary DB connection failed. Error: {primary_exc}"
                    ) from primary_exc

                logger.info("⚡ PgBouncer connection pool successfully initialized at startup.")
                await _ensure_api_key_tables()

                # Apply Alembic migrations before serving requests. Disabling this in
                # production would allow the live schema to drift from the application.
                if os.getenv("AUTO_MIGRATE", "true").lower() == "true":
                    try:
                        from scripts.db.auto_migrate import run_migrations

                        logger.info("🔄 Running automatic Alembic migrations on startup...")
                        await asyncio.to_thread(run_migrations)
                        logger.info("✅ Automatic Alembic migrations completed.")
                    except Exception as mig_err:
                        if settings.env == "production":
                            logger.critical("❌ Production database migration failed: %s", mig_err)
                            raise
                        logger.warning("⚠️ Automatic migration notice: %s", mig_err)

                # Optimize queries with connection pooling best practices
                app.state.db_pool = pool
        except Exception as exc:
            logger.error(f"❌ Failed to initialize DB Pool: {exc}")
            app.state.db_pool = None
            is_db_critical = settings.env == "production"
            app.state.subsystem_status["db"] = "down" if is_db_critical else "optional_offline"
            error_event_bus.emit(
                ErrorEvent(
                    module="lifespan",
                    error_type="DB_POOL_INIT_FAILED",
                    message=str(exc)[:200],
                    severity="CRITICAL" if settings.env == "production" else "WARNING",
                    structured_context=ErrorContext(module="auto_fixed"),
                    context={
                        "env": settings.env,
                    },
                )
            )
            if settings.env == "production":
                logger.critical(
                    "🔥 PRODUCTION DB UNAVAILABLE — running in degraded mode. DB-dependent endpoints will return 503."
                )

    async def _init_config_cache() -> None:
        """Initialize system configuration cache."""
        try:
            await config_cache.refresh_async()
            logger.info("✅ System configuration cache successfully initialized.")
        except Exception as exc:
            logger.warning(
                f"⚠️ Async config load failed, falling back to local DEFAULT_CONFIGS: {exc}"
            )
            app.state.subsystem_status["config"] = "fallback"
            error_event_bus.emit(
                ErrorEvent(
                    module="lifespan",
                    error_type="CONFIG_CACHE_INIT_FAILED",
                    message=str(exc)[:200],
                    severity="WARNING",
                    structured_context=ErrorContext(module="auto_fixed"),
                    context={"fallback": "DEFAULT_CONFIGS"},
                )
            )
            from core.config_cache import DEFAULT_CONFIGS

            config_cache._cache = dict(DEFAULT_CONFIGS)

    async def _init_redis() -> None:
        """Verify Redis connection and restore reliability state."""
        try:
            # Always call get_client_async() to trigger lazy init first
            client = await redis_manager.get_client_async()
            if client:
                try:
                    await client.ping()
                except Exception as ping_err:
                    # Federation failover at boot (issue #460 Pillar 2): the
                    # canonical primary can be quota-exhausted while a sibling
                    # account is healthy. report_failure() rotates the pool;
                    # retry ONCE before the fail-fast policy blocks startup.
                    # Non-quota errors leave the pool untouched → re-raise as
                    # before (policy intent preserved).
                    redis_manager.report_failure(ping_err)
                    client = await redis_manager.get_client_async()
                    if not client:
                        raise ping_err
                    await client.ping()
                logger.info("[OK] Redis connection verified successfully.")
                await ReliabilityController.restore_from_persistence()
            else:
                raise ConnectionError("Redis client is None — check REDIS_URL env var.")
        except Exception as e:
            logger.error(f"Failed to initialize Redis Manager: {e}")

            is_critical = (
                getattr(settings, "redis_required_for_production", False)
                and settings.env == "production"
            )

            app.state.subsystem_status["redis"] = "down" if is_critical else "optional_offline"
            error_event_bus.emit(
                ErrorEvent(
                    module="lifespan",
                    error_type="REDIS_INIT_FAILED",
                    message=str(e)[:200],
                    severity="CRITICAL" if is_critical else "WARNING",
                    structured_context=ErrorContext(module="auto_fixed"),
                    context={
                        "env": settings.env,
                        "redis_required": getattr(settings, "redis_required_for_production", False),
                    },
                )
            )
            if is_critical:
                logger.critical("🚨 PRODUCTION REDIS UNAVAILABLE - blocking startup!")
                raise RuntimeError("Redis is required for production but unavailable.") from e
            else:
                logger.warning(
                    "⚠️ Redis is unavailable but marked as optional. Running safely without Redis."
                )

    async def _init_cost_guard() -> None:
        """Initialize CostGuard for distributed budget tracking."""
        try:
            from core.cost_guard import cost_guard

            await cost_guard.connect()
            logger.info("✅ CostGuard Redis connection initialized for budget tracking.")
        except Exception as e:
            logger.warning(f"CostGuard initialization failed (non-critical): {e}")
            error_event_bus.emit(
                ErrorEvent(
                    module="lifespan",
                    error_type="COST_GUARD_INIT_FAILED",
                    message=str(e)[:200],
                    severity="WARNING",
                    structured_context=ErrorContext(module="auto_fixed"),
                    context={"component": "cost_guard"},
                )
            )

    # BE-12 (issue #544): batch-load all vault secrets off the event-loop
    # thread BEFORE any component reads a secret-backed property
    # (supabase_database_url, redis_url, jwt_secret, ...). Without this, the
    # first property access (below, inside _init_db_pool/_init_redis) runs the
    # sync Infisical fetch + time.sleep retry backoff on the loop thread,
    # freezing every concurrent request and the liveness probe on timeouts.
    try:
        await settings.apreload_secrets()
        logger.info("✅ Core secrets preloaded off the event loop (BE-12).")
    except Exception as exc:
        logger.warning(f"Secret preload failed (continuing with lazy loads): {exc}")

    # Run all independent initializations in parallel
    init_results = await asyncio.gather(
        _init_tracing(),
        _init_db_pool(),
        _init_config_cache(),
        _init_redis(),
        _init_cost_guard(),
        return_exceptions=True,
    )

    for idx, result in enumerate(init_results):
        if isinstance(result, BaseException):
            logger.error(f"Startup initialization failed for component {idx}: {result}")
            if isinstance(result, RuntimeError):
                raise result

    # Sync DB-backed Model Registries after DB is initialized
    if app.state.subsystem_status.get("db") != "down":
        try:
            from brain.economic_optimizer import get_economic_optimizer
            from brain.model_registry import ModelRegistry
            from core.health.health_monitor import get_health_monitor
            from core.middleware.health_aware_middleware import (
                sync_from_db as sync_health_middleware,
            )
            from core.resilience.circuit_breaker import sync_from_db as sync_circuit_breaker
            from database.session import get_db_session_context
            from utils.branding import sync_from_db as sync_branding

            async with get_db_session_context() as db:
                economic_opt = await get_economic_optimizer()
                health_monitor = get_health_monitor()
                # বাংলা মন্তব্য (BUG FIX): একই AsyncSession (db) দিয়ে asyncio.gather()
                # ব্যবহার করে 6টা coroutine সমান্তরালে চালানো হচ্ছিল — কিন্তু SQLAlchemy
                # AsyncSession একইসাথে একাধিক concurrent operation সাপোর্ট করে না
                # ("This session is provisioning a new connection; concurrent
                # operations are not permitted"), ফলে config sync বারবার fail করে
                # silently default value-তে fallback করত। একই session sequentially
                # await করে ঠিক করা হলো — গতি সামান্য কমলেও এটাই সঠিক ও নিরাপদ পদ্ধতি।
                await ModelRegistry.sync_from_db(db)
                await economic_opt.sync_from_db(db)
                await sync_branding(db)
                await sync_circuit_breaker(db)
                await health_monitor.sync_from_db(db)
                await sync_health_middleware(db)
                logger.info(
                    "✅ Core model registries and system thresholds synchronized from DB successfully."
                )
        except Exception as e:
            logger.error(f"❌ Failed to sync model registries from DB: {e}")

    # Start SupremeAI Immune System zero-cost background probing
    maintenance_pipeline.start_monitoring()
