import asyncio
import os
import time  # - Added for metrics collection

from core import services
from core.agent_supervisor import agent_supervisor
from core.cache.redis_manager import redis_manager
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus
from core.persistence import pooled_pg
from core.persistence.write_behind import flush_all as flush_write_behind_batchers
from database.pgbouncer_pool import get_db_pool
from monitoring.metrics_collector import metrics_collector
from utils.http_client import set_shared_client


async def shutdown_services(app):
    logger.critical(
        "🚨 Graceful Shutdown Sequence triggered (Render + Uvicorn lifespan)."
    )  # AUD-1.6: wording drift fix (was "Cloud Run Orchestrator")

    # Shutdown Tier-8 Meta-Self Agents
    try:
        from core.tier8.tier8_integration import shutdown_tier8

        await shutdown_tier8()
        logger.info("✅ Tier-8 Meta-Self subsystem shutdown completed.")
    except Exception as exc:
        logger.warning(f"⚠️ Tier-8 shutdown failed: {exc}")

    # Orchestrator cleanup
    try:
        orch = getattr(app.state, "orchestrator", None)
        if orch and hasattr(orch, "stop"):
            await orch.stop()
    except Exception as e:
        logger.error(f"Error during orchestrator shutdown: {e}")
        error_event_bus.emit(
            ErrorEvent(
                module="lifespan",
                error_type="SHUTDOWN_ORCHESTRATOR_FAILED",
                message=str(e)[:200],
                severity="WARNING",
                structured_context=ErrorContext(module="auto_fixed"),
                context={"phase": "shutdown"},
            )
        )

    # Shutdown all background agents via centralized supervisor
    # বাংলা মন্তব্ব্য: AgentSupervisor graceful shutdown — পূর্বের ম্যানুয়াল task management প্রতিস্থাপন করে।
    try:
        timeout_val = float(os.getenv("SHUTDOWN_TIMEOUT", "30"))
        await agent_supervisor.shutdown_all(timeout=timeout_val)
        logger.info("✅ All background agents shut down via centralized supervisor.")
    except (Exception, asyncio.CancelledError) as e:
        logger.error(f"Error during agent supervisor shutdown: {e}")
        error_event_bus.emit(
            ErrorEvent(
                module="lifespan",
                error_type="SHUTDOWN_AGENT_SUPERVISOR_FAILED",
                message=str(e)[:200],
                severity="WARNING",
                structured_context=ErrorContext(module="auto_fixed"),
                context={"phase": "shutdown"},
            )
        )

    # Sprint 3 (learning loop): final durable-telemetry flush so buffered
    # learning_events land in Postgres before the HTTP clients are torn down.
    try:
        from core.learning import get_learning_store

        await get_learning_store().stop()
        logger.info("✅ LearningStore flushed and stopped.")
    except (Exception, asyncio.CancelledError) as e:
        logger.warning(f"LearningStore shutdown skipped: {e}")

    # Flush write-behind batchers (audit_logger, checkpoint_manager) so any
    # buffered-but-not-yet-flushed rows land before we tear down connections.
    # This is the graceful-shutdown half of the write-behind tradeoff: a hard
    # crash still loses at most one flush_interval window, but a normal
    # deploy/restart (this path) loses nothing.
    try:
        await asyncio.to_thread(flush_write_behind_batchers)
        logger.info("✅ Write-behind persistence batchers flushed successfully.")
    except Exception as exc:
        logger.error(f"Error flushing write-behind batchers: {exc}")
        error_event_bus.emit(
            ErrorEvent(
                module="lifespan",
                error_type="WRITE_BEHIND_FLUSH_FAILED",
                message=str(exc)[:200],
                severity="WARNING",
                structured_context=ErrorContext(module="auto_fixed"),
                context={"phase": "shutdown"},
            )
        )

    # Database pool cleanup — single close with proper state tracking
    try:
        from database.pgbouncer_pool import dispose_db_pool

        await dispose_db_pool()
    except Exception as e:
        logger.error(f"Error closing DB pool: {e}")
        error_event_bus.emit(
            ErrorEvent(
                module="lifespan",
                error_type="SHUTDOWN_DB_POOL_FAILED",
                message=str(e)[:200],
                severity="WARNING",
                structured_context=ErrorContext(module="auto_fixed"),
                context={"phase": "shutdown"},
            )
        )
    # Synchronous pgbouncer pool — only close if it was initialized
    try:
        if hasattr(pooled_pg, "_pool") and pooled_pg._pool is not None:
            await asyncio.to_thread(pooled_pg.close_pool)
            logger.info("✅ Synchronous pgbouncer pool closed successfully.")
    except Exception as e:
        logger.error(f"Error closing sync pgbouncer pool: {e}")

    # Redis cleanup
    try:
        await redis_manager.close()
        logger.info("✅ Redis Manager connection closed.")
    except Exception as e:
        logger.error(f"Error closing Redis Manager: {e}")
        error_event_bus.emit(
            ErrorEvent(
                module="lifespan",
                error_type="SHUTDOWN_REDIS_FAILED",
                message=str(e)[:200],
                severity="WARNING",
                structured_context=ErrorContext(module="auto_fixed"),
                context={"phase": "shutdown"},
            )
        )

    # HTTP client cleanup
    try:
        if services.global_http_client:
            await services.global_http_client.aclose()
        set_shared_client(None)
        services.global_http_client = None
        logger.info("✅ Global HTTP connection pool closed successfully.")
    except Exception as e:
        logger.error(f"Error during HTTP connection pool drainage: {e!s}")
        error_event_bus.emit(
            ErrorEvent(
                module="lifespan",
                error_type="SHUTDOWN_HTTP_CLIENT_FAILED",
                message=str(e)[:200],
                severity="WARNING",
                structured_context=ErrorContext(module="auto_fixed"),
                context={"phase": "shutdown"},
            )
        )

    # Browser cleanup
    try:
        from core.playwright_manager import shutdown_global_browser

        await shutdown_global_browser()
    except Exception as e:
        logger.error(f"Failed to shutdown global browser: {e}")
        error_event_bus.emit(
            ErrorEvent(
                module="lifespan",
                error_type="SHUTDOWN_BROWSER_FAILED",
                message=str(e)[:200],
                severity="WARNING",
                structured_context=ErrorContext(module="auto_fixed"),
                context={"phase": "shutdown"},
            )
        )
    logger.info(
        "💀 Graceful shutdown sequence successfully finalized."
    )  # AUD-1.6: wording drift fix (was "Serverless runtime environment")
    # Record system shutdown
    await metrics_collector.set_gauge("system_shutdown_time", time.time())
