"""This module implements the `MaintenancePipeline`, acting as the "Immune System" for the SupremeAI ecosystem. It is responsible for continuously monitoring the health and performance of critical backend components such as databases, Redis, and external AI APIs. The pipeline proactively listens for system-wide error events, performs routine health checks, detects potential performance regressions, and attempts automated self-healing remediation actions like switching LLM providers or re-initializing services to ensure the overall stability and resilience of the AI platform.

Key Components:
- `MaintenancePipeline`: A class that orchestrates continuous health monitoring, processes error events, detects performance issues, and triggers automated remediation strategies to maintain system integrity.
- `maintenance_pipeline`: A global singleton instance of the `MaintenancePipeline` class, providing a centralized point of control for system health management.

Dependencies:
- `asyncio`: For managing asynchronous operations and background monitoring tasks.
- `logging`: For structured logging of health status, warnings, and critical events.
- `time`: For timestamping health checks and implementing cooldown periods for remediation.
- `core.messaging.event_bus`: For registering listeners to and emitting system-wide `ErrorEvent`s.
- `core.health.health_probes`: Provides specific functions to probe the health of internal and external services (e.g., database, Redis, external APIs).
- `core.cache.redis_manager`: Utilized within remediation logic to interact with Redis, such as updating configuration or re-initializing connections."""

import asyncio
import os
import random
import time

from core.health.health_probes import probe_database, probe_external_api, probe_redis
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus


class MaintenancePipeline:
    def __init__(self):
        self.health_score = 100
        self._monitor_task = None
        # বাংলা মন্তব্য (RUF006 fix): নিচে emergency evolution tick-এর জন্য
        # create_task() করা হয়, সেটার strong reference ধরে রাখার জন্য।
        self._evolution_tick_task = None
        self.last_recovery_time = 0  # Cooldown tracker
        self.last_cleanup_time = 0
        # Register to listen to error events
        error_event_bus.register_listener("*", self._handle_error_event)

    def start_monitoring(self, interval: int | None = None):
        """Starts the background probing task with configurable interval."""
        if interval is None:
            interval = int(os.getenv("MAINTENANCE_INTERVAL") or "120")
        self._monitor_interval = interval
        if self._monitor_task is None:
            self._monitor_task = asyncio.create_task(self._monitoring_loop())

    async def _monitoring_loop(self):
        """Background loop that runs zero-cost health probes with configurable interval + jitter."""
        logger.info(
            f"🛡️ Immune System: Background monitoring started (interval={self._monitor_interval}s)."
        )
        while True:
            # Add random jitter (±10%) to prevent thundering herd
            jitter = random.uniform(0.9, 1.1)
            actual_interval = int(self._monitor_interval * jitter)
            await asyncio.sleep(actual_interval)

            await self.run_health_check()

            # Run cleanup once every 24 hours
            current_time = time.time()
            if current_time - self.last_cleanup_time > 86400:
                await self.cleanup_automation_executions()
                self.last_cleanup_time = current_time

    async def _handle_error_event(self, event):
        logger.warning(
            f"🛡️ Immune System received error event: {event.error_type} in {event.module}"
        )
        if event.severity in ("ERROR", "CRITICAL"):
            self.health_score = max(0, self.health_score - 5)
            await self.auto_remediate(event)

    async def run_health_check(self):
        # logger.info("🛡️ Immune System: Running routine health check...")

        results = {
            "redis": await probe_redis(),
            "database": await probe_database(),
            "api_gemini": await probe_external_api("https://generativelanguage.googleapis.com"),
            "api_openrouter": await probe_external_api("https://openrouter.ai/api/v1/auth/key"),
            "timestamp": time.time(),
        }

        # Calculate Degradation
        penalty = 0
        from core.config import settings

        if results["redis"]["status"] == "down":
            if (
                getattr(settings, "redis_required_for_production", False)
                or settings.env != "production"
            ):
                penalty += 50
        if results["database"]["status"] == "down":
            penalty += 50
        if results["api_gemini"]["status"] == "down":
            penalty += 20
        if results["api_openrouter"]["status"] == "down":
            penalty += 20

        # Adjust score safely
        self.health_score = max(0, 100 - penalty)

        # Trigger circuit breaker event if degraded significantly
        if self.health_score < 70:
            logger.warning(
                f"🛡️ Immune System: Health degraded (Score: {self.health_score}). Triggering circuit breaker event."
            )
            error_event_bus.emit(
                ErrorEvent(
                    module="maintenance_pipeline",
                    error_type="system.health.degraded",
                    message="System health score dropped below safe threshold.",
                    severity="CRITICAL",
                    structured_context=ErrorContext(module="auto_fixed"),
                    context={"results": results, "score": self.health_score},
                )
            )

        status = (
            "HEALTHY"
            if self.health_score > 80
            else ("DEGRADED" if self.health_score > 50 else "CRITICAL")
        )
        results["status"] = status
        results["health_score"] = self.health_score
        return results

    async def detect_performance_regression(self):
        """
        Monitors key performance indicators (KPIs) like p95 latency.
        If latency exceeds a predefined threshold after a new deployment,
        it can trigger a rollback action via GitHub Actions.
        """
        logger.info("🛡️ Immune System: Running performance regression detection...")
        try:
            from api.routes.metrics import metrics_engine

            history = metrics_engine.latency_history
            if not history:
                logger.info("🛡️ Immune System: Latency logs empty. Skipping regression check.")
                return

            # বাংলা মন্তব্য: P95 ল্যাটেন্সি গণনা করা।
            # হিস্ট্রি সর্ট করে ৯৫তম পার্সেন্টাইল ভ্যালু বের করা হচ্ছে।
            sorted_history = sorted(history)
            idx = int(len(sorted_history) * 0.95)
            # duration-টি সেকেন্ডে থাকে, তাই ms-এ রূপান্তর করছি
            p95_latency = sorted_history[min(idx, len(sorted_history) - 1)] * 1000.0

            LATENCY_THRESHOLD_MS = 500.0  # Dev default threshold 500ms

            logger.info(f"🛡️ Immune System: Current real P95 Latency = {p95_latency:.2f}ms")
            if p95_latency > LATENCY_THRESHOLD_MS:
                logger.critical(
                    f"🚨 Performance Regression Detected! p95 latency ({p95_latency:.2f}ms) exceeds threshold ({LATENCY_THRESHOLD_MS}ms)."
                )
                # In a real scenario, this would trigger a GitHub Actions workflow to rollback the deployment.

        except Exception as e:
            logger.error(f"Failed to run performance regression check: {e}")

    async def cleanup_automation_executions(self):
        """
        Cleans up old automation executions and attempts to prevent unbounded DB growth.
        Retains data for the last 30 days.
        """
        logger.info("🛡️ Immune System: Running automation execution retention cleanup...")
        try:
            from sqlalchemy import text

            from core.app import app
            from core.db import get_session_factory

            if app.state.subsystem_status.get("db") == "down":
                logger.warning("🛡️ Immune System: Skipping automation cleanup, DB is down.")
                return

            factory = get_session_factory()
            async with factory() as session:
                # Do not turn an expected schema drift into a recurring ERROR.
                # The table is created by the Alembic migration
                # a1b2c3d4e5f6 and extended by 358bcbe79a4a. Old/stale
                # environments may legitimately not have it yet.
                table_exists = await session.scalar(
                    text("SELECT to_regclass('public.automation_executions')")
                )
                if table_exists is None:
                    logger.warning(
                        "🛡️ Immune System: automation_executions table is absent; "
                        "skipping retention cleanup until migrations are applied."
                    )
                    return

                # Delete executions older than 30 days (attempts will cascade delete)
                result = await session.execute(
                    text(
                        "DELETE FROM automation_executions WHERE created_at < NOW() - INTERVAL '30 days'"
                    )
                )
                await session.commit()
                deleted_count = result.rowcount
            if deleted_count > 0:
                logger.info(
                    f"🛡️ Immune System: Cleaned up {deleted_count} old automation executions."
                )
        except Exception as e:
            # বাংলা মন্তব্য: "automation_executions" টেবিলটা মূল migration chain-এ
            # কখনো CREATE হয়নি (শুধু ALTER/reference করা হতো) — এখন
            # a1b2c3d4e5f6 migration দিয়ে সেটা ঠিক করা হয়েছে। তবু কোনো পুরনো/
            # আংশিক-migrated environment-এ table এখনো না থাকলে যেন প্রতি cleanup
            # cycle-এ ERROR log স্প্যাম না হয়, তাই সেই নির্দিষ্ট ক্ষেত্রে WARNING-এ নামানো হলো।
            if "does not exist" in str(e) and "automation_executions" in str(e):
                logger.warning(
                    f"🛡️ Immune System: automation_executions table not found (run migrations "
                    f"— see a1b2c3d4e5f6_add_automation_executions_table.py): {e}"
                )
            else:
                logger.error(f"Failed to cleanup automation executions: {e}")

    async def auto_remediate(self, event=None):
        logger.warning("🚑 Immune System: Triggering self-healing remediation...")

        # Cooldown Period (2 minutes) to prevent Flapping
        current_time = time.time()
        if current_time - self.last_recovery_time < 120:
            logger.info("⏳ Auto-Recovery skipped: System is in cooldown period.")
            return

        if event:
            logger.info(f"Attempting to heal module {event.module} for error {event.error_type}")
            from core.cache.redis_manager import redis_manager

            # Simulated checks based on the event payload or type
            # In a real scenario, the event type might be exactly 'llm_provider_down' or 'redis_connection_lost'

            if (
                "gemini" in str(event.context).lower()
                or event.error_type == "system.health.degraded"
            ):
                logger.info(
                    "🚑 Auto-Recovery: LLM Provider degraded. Switching active provider to OpenRouter."
                )
                # Set active_provider in Redis (if redis is up)
                if redis_manager.client:
                    try:
                        await redis_manager.client.set("active_provider", "openrouter")
                        error_event_bus.emit(
                            ErrorEvent(
                                module="auto_remediation",
                                error_type="system.routing.updated",
                                message="Switched to OpenRouter successfully.",
                                severity="INFO",
                                structured_context=ErrorContext(module="auto_fixed"),
                            )
                        )
                        self.last_recovery_time = current_time
                        self.health_score = min(100, self.health_score + 30)
                    except Exception as e:
                        logger.error(f"Failed to switch provider: {e}")

            if "redis" in str(event.context).lower() or event.error_type == "redis_connection_lost":
                logger.info("🚑 Auto-Recovery: Redis degraded. Attempting to re-initialize pool.")
                try:
                    await redis_manager.close()
                    # Re-init would happen here depending on the manager implementation
                    # e.g., await redis_manager.connect()
                    self.last_recovery_time = current_time
                    self.health_score = min(100, self.health_score + 20)
                except Exception as e:
                    logger.error(f"Failed to recover Redis: {e}")

        # বাংলা মন্তব্য: Health critical threshold-এ পৌঁছালে SelfEvolutionAgent-কে
        # জরুরি evolution cycle চালাতে signal দেওয়া হচ্ছে।
        # এটাই সেই bridge যেটা self-healing → self-evolution loop বন্ধ করে।
        if self.health_score < 50:
            from core.config import settings

            if settings.env == "production":
                logger.warning(
                    f"🛡️ Health critical (score={self.health_score}). "
                    "Skipping SelfEvolutionAgent trigger in production to prevent aggressive mutations."
                )
            else:
                try:
                    import asyncio as _asyncio

                    from core.self_evolution.self_evolution_agent import (
                        SelfEvolutionAgent,
                    )
                except ImportError as e:
                    logger.error(f"Cannot import SelfEvolutionAgent: {e}")
                    return

                # FIX: original used SelfEvolutionAgent.__new__(SelfEvolutionAgent)
                # which skips __init__ → self.fitness_engine, self.auto_skill_creator
                # are never set → _tick() crashes immediately with AttributeError,
                # caught by outer try/except → silently skipped.
                # Now: try app.state.evo_agent first (properly initialized in startup);
                # fall back to a real __init__() call if app.state not available.
                _evo = None
                try:
                    # Access the already-initialized singleton from app state
                    from core.app import app

                    _evo = getattr(app.state, "evo_agent", None)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).exception(f"Silenced error: {e}")

                if _evo is None:
                    # No app.state.evo_agent — instantiate properly (with shared FitnessEngine)
                    # SELF-EVOLVE FIX (real): pass shared FitnessEngine singleton so
                    # the emergency tick() reads the SAME metrics as the regular loop.
                    try:
                        from api.deps import get_fitness_engine

                        _evo = SelfEvolutionAgent(
                            fitness_engine=get_fitness_engine(),
                            interval_seconds=300,
                        )
                    except Exception as init_exc:
                        logger.debug(
                            f"SelfEvolutionAgent init failed (FitnessEngine missing?): {init_exc!r}"
                        )
                        _evo = None

                # শুধু tick() চালাই, পুরো loop নয় — non-blocking
                if _evo is not None and hasattr(_evo, "_tick"):
                    try:
                        self._evolution_tick_task = _asyncio.create_task(_evo._tick())
                        logger.warning(
                            f"🛡️→🧬 Health critical (score={self.health_score}), "
                            "triggered emergency evolution tick."
                        )
                    except Exception as evo_exc:
                        logger.debug(f"Evolution trigger skipped: {evo_exc!r}")

        logger.info("🚑 Remediation cycle completed.")


# Global instance for easy import and singleton usage
maintenance_pipeline = MaintenancePipeline()
