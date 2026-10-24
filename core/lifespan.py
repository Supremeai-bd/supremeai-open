"""This module serves as the central FastAPI application lifespan manager for the SupremeAI project, orchestrating the robust startup and graceful shutdown of all critical backend infrastructure. It handles the initialization of essential services such as database connection pools, Redis caches, global HTTP clients, OpenTelemetry tracing, the core AI Orchestrator, and various background agents, ensuring the application is fully prepared to serve requests. The module is designed with defensive programming principles, allowing the application to start in a degraded mode if certain non-critical services fail to initialize, thereby enhancing operational stability and resilience in a highly scalable AI ecosystem.

Key Components:
- `_ensure_api_key_tables()`: Asynchronously creates or verifies the existence of database tables required for API key management, usage tracking, and event logging.
- `app_lifespan()`: An asynchronous context manager that manages the entire lifecycle of the FastAPI application, performing comprehensive setup during startup and orderly teardown during shutdown.

Dependencies:
- `asyncio`: For managing asynchronous operations and background tasks.
- `os`: For accessing environment variables to determine runtime context.
- `contextlib`: Provides the `asynccontextmanager` decorator for lifespan management.
- `httpx`: Used for creating and managing a global asynchronous HTTP client pool.
- `loguru`: For structured and informative logging throughout the application lifecycle.
- `core.services`: Provides global service instances, including the shared HTTP client.
- `core.config`: Accesses application-wide configuration settings.
- `core.config_cache`: Manages the system's dynamic configuration cache.
- `core.messaging.event_bus`: Facilitates internal error reporting and event emission.
- `core.maintenance_pipeline`: Manages background monitoring and health checks for the system.
- `core.orchestration.orchestrator`: Initializes and manages the core AI orchestration engine.
- `database.pgbouncer_pool`: Handles the initialization and closing of PostgreSQL database connection pools.
- `core.cache.redis_manager`: Manages connections to the Redis caching service.
- `core.observability.telemetry`: Initializes OpenTelemetry for distributed tracing.
- `core.sentinel_agent`: Manages a background agent responsible for periodic system tasks.
- `database.db`: Used for bootstrapping and ensuring the integrity of the Supabase database schema.
- `tools.ai_agents.browser_agent`: Provides functionality to shut down any globally managed browser instances.
- `monitoring.metrics_collector`: Collects system metrics for observability and monitoring."""

# backend/core/lifespan.py
# ⚠️ WARNING: DO NOT MOVE THIS FILE. It is heavily integrated into the FastAPI startup lifecycle.
# Moving this file will break relative paths, imports, and core app lifespan management.
import asyncio
import time  # - Added for metrics collection
from contextlib import asynccontextmanager

import httpx

from core import services
from core.config import settings
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus
from core.orchestration.periodic_task_scheduler import Orchestrator
from core.reliability_controller import ReliabilityController
from core.startup_validator import StartupValidator
from monitoring.metrics_collector import metrics_collector
from utils.http_client import set_shared_client


@asynccontextmanager
async def app_lifespan(app):
    """
    SupremeAI 2.0 Core Lifespan Manager.
    Handles high-concurrency initialization and defensive teardowns.
    """
    logger.info("🌐 Core Infrastructure Bootstrapping Active...")

    # Initialize Intelligent Silent Catcher for real-time observability
    from core.intelligent_silent_catcher import setup_silent_catcher

    setup_silent_catcher()

    # Issue #451: capture the main loop (sync store callers bridge through
    # it) and hydrate every durable state store from Redis before serving.
    import asyncio as _asyncio

    from core import state_store as _state_store

    _state_store.set_main_loop(_asyncio.get_running_loop())
    try:
        hydrated = await _state_store.hydrate_all()
        logger.info("Durable state stores hydrated: %d record(s)", hydrated)
        # Feature-level hydrations that read the mirror into live objects.
        try:
            from core.social_growth import social_growth_circle

            social_growth_circle.hydrate()
        except Exception as sg_err:
            logger.warning("social_growth hydrate skipped: %s", sg_err)
        try:
            from tools.learning.style_learner import _learner as style_learner_singleton

            style_learner_singleton.hydrate()
        except Exception as sl_err:
            logger.debug("style_learner hydrate skipped: %s", sl_err)
        # বাংলা (#2259 D1): unified_learning KnowledgeNode hydration হুক বাদ —
        # ইঞ্জিন retired; learned_knowledge durable-state-এর কোনো reader ছিল না।
        _state_store.log_banner()
    except Exception as ss_err:
        logger.warning("Durable state store hydration failed (mirror-only mode): %s", ss_err)

    # Record system startup
    await metrics_collector.set_gauge("system_startup_time", time.time())

    # বাংলা মন্তব্ব্য: স্টার্টআপ ভ্যালিডেশন এবং নির্ভরযোগ্যতা নিয়ন্ত্রণ প্যানেল বুটস্ট্র্যাপ করা।
    # Safety-net: wrap startup validation in try/except so boot continues in degraded mode.
    try:
        await StartupValidator.validate()
    except Exception as e:
        logger.error(f"StartupValidator failed (continuing in degraded mode): {e}")
        error_event_bus.emit(
            ErrorEvent(
                module="lifespan",
                error_type="STARTUP_VALIDATOR_FAILED",
                message=str(e)[:200],
                severity="WARNING",
                structured_context=ErrorContext(module="auto_fixed"),
                context={"component": "startup_validator"},
            )
        )
    try:
        await ReliabilityController.initialize()
    except Exception as e:
        logger.error(f"ReliabilityController init failed (continuing in degraded mode): {e}")
        error_event_bus.emit(
            ErrorEvent(
                module="lifespan",
                error_type="RELIABILITY_CTRL_INIT_FAILED",
                message=str(e)[:200],
                severity="WARNING",
                structured_context=ErrorContext(module="auto_fixed"),
                context={"component": "reliability_controller"},
            )
        )
    app.state.subsystem_status = {"db": "up", "redis": "up", "config": "up"}

    # Update metrics with subsystem status
    await metrics_collector.set_gauge(
        "subsystem_db_status",
        1 if app.state.subsystem_status["db"] == "up" else 0,
        {"subsystem": "db"},
    )
    await metrics_collector.set_gauge(
        "subsystem_redis_status",
        1 if app.state.subsystem_status["redis"] == "up" else 0,
        {"subsystem": "redis"},
    )
    await metrics_collector.set_gauge(
        "subsystem_config_status",
        1 if app.state.subsystem_status["config"] == "up" else 0,
        {"subsystem": "config"},
    )

    # ── Parallelized Startup Phase 1: Independent services ──────────────────
    # বাংলা মন্তব্ব্য: P2 Fix — startup latency এবং cold start freeze এড়াতে
    # স্বাধীন সার্ভিসগুলো asyncio.gather() দিয়ে সমান্তরালে চালানো হচ্ছে।
    # Sequential dependency: HTTP client must be initialized first (others depend on it).

    # Global HTTP client initialization (sequential — dependency for others)
    services.global_http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_keepalive_connections=50, max_connections=200),
        timeout=httpx.Timeout(30.0),
        headers={"User-Agent": "SupremeAI-Orchestrator/2.0"},
    )
    app.state.http_client = services.global_http_client
    set_shared_client(services.global_http_client)
    services.model_router._http_client = services.global_http_client
    logger.info("✅ Global HTTP Connection Pool initialized [Max Cons: 200].")

    # Parallel Phase: DB pool, Config cache, Redis, Tracing, CostGuard
    # Phase 1: independent infrastructure initialization.
    from core.startup.services import initialize_independent_services

    try:
        await initialize_independent_services(app)
    except Exception as e:
        # Issue #513 (BE-07): init handlers swallow everything they can degrade
        # internally — only failures they deliberately let escape (e.g. the
        # production-critical "Redis is required for production" RuntimeError)
        # reach this point. In production those must BLOCK boot (fail-fast),
        # not be downgraded to a log line; outside production keep the
        # degraded-mode convenience.
        if settings.env == "production":
            logger.critical(
                f"🔥 initialize_independent_services failed in production — aborting boot: {e}"
            )
            raise
        logger.error(f"initialize_independent_services failed (continuing in degraded mode): {e}")
        error_event_bus.emit(
            ErrorEvent(
                module="lifespan",
                error_type="INDEPENDENT_SERVICES_INIT_FAILED",
                message=str(e)[:200],
                severity="WARNING",
                structured_context=ErrorContext(module="auto_fixed"),
                context={"component": "independent_services"},
            )
        )

    # ── Sequential Phase 2: Services that depend on Phase 1 ───────��─────────
    # Orchestrator initialization (depends on HTTP client + DB)
    try:
        orch_inst = Orchestrator()
        app.state.orchestrator = orch_inst
        logger.info("⚙️ Orchestrator background tasks initialized successfully.")
        await metrics_collector.increment_counter("orchestrator_init_success_total")
    except Exception as e:
        logger.error(f"Failed to initialize Orchestrator: {e}")
        await metrics_collector.increment_counter("orchestrator_init_failure_total")
        error_event_bus.emit(
            ErrorEvent(
                module="lifespan",
                error_type="ORCHESTRATOR_INIT_FAILED",
                message=str(e)[:200],
                severity="WARNING",
                structured_context=ErrorContext(module="auto_fixed"),
                context={"component": "orchestrator"},
            )
        )
        app.state.orchestrator = None

    # Supabase schema bootstrap (depends on DB pool)
    import os

    timeout_val = float(os.getenv("DB_BOOTSTRAP_TIMEOUT", "30.0"))
    try:
        from database import db as supabase_db

        if settings.supabase_database_url:
            await asyncio.wait_for(
                asyncio.to_thread(supabase_db.bootstrap_schema), timeout=timeout_val
            )
            logger.info("Supabase schema bootstrap complete")
    except asyncio.CancelledError:
        logger.info("Supabase schema bootstrap cancelled during shutdown")
        raise
    except TimeoutError:
        # Issue #478: a skipped migration/bootstrap must never count as silent
        # success in production — make it CRITICAL-visible (crash remains off
        # the table: the readiness schema gate owns the fail-closed decision).
        if str(getattr(settings, "env", "") or os.getenv("ENV", "")).lower() in {
            "production",
            "prod",
        }:
            logger.critical(
                f"Supabase schema bootstrap timed out after {timeout_val}s in PRODUCTION "
                "— schema drift possible; readiness schema gate will report missing tables. "
                "Set SUPABASE_DATABASE_URL_WRITER (MANUAL_STEPS 7.9)."
            )
        else:
            logger.warning(
                f"Supabase schema bootstrap timed out after {timeout_val}s — continuing without full schema init."
            )
    except Exception as exc:
        if str(getattr(settings, "env", "") or os.getenv("ENV", "")).lower() in {
            "production",
            "prod",
        }:
            logger.critical(
                "Supabase bootstrap failed on startup in PRODUCTION: "
                f"{type(exc).__name__} (details suppressed) — readiness schema gate will verify tables."
            )
        else:
            logger.warning(
                f"Supabase bootstrap failed on startup: {exc}. Continuing without schema bootstrap."
            )
        error_event_bus.emit(
            ErrorEvent(
                module="lifespan",
                error_type="SUPABASE_BOOTSTRAP_FAILED",
                message=str(exc)[:200],
                severity="WARNING",
                structured_context=ErrorContext(module="auto_fixed"),
                context={"component": "supabase"},
            )
        )

    # Zero-Cost Architecture subsystem (issue #1830): adaptive circuit
    # breakers + learning engine + in-process queue (2k+ lines, heavily
    # unit-tested) shipped DARK — lifespan_manager() was never referenced by
    # this module, so /api/v1/zero-cost/health reported "initializing" forever
    # and the learning engine never received a single metric. Mirrors the
    # documented usage (lifespan_manager docstring): initialize() before
    # yield, shutdown() after. Fail-soft: a broken zero-cost subsystem must
    # not block boot (house degraded-mode pattern).
    try:
        from core.zero_cost_architecture.zero_cost_patch_phase1_4 import get_orchestrator

        zc_orchestrator = get_orchestrator()
        await zc_orchestrator.initialize()
        app.state.zero_cost_orchestrator = zc_orchestrator
        logger.info("✅ Zero-Cost Architecture initialized (queue + learning engine live).")
    except Exception as e:
        logger.error(f"Zero-Cost Architecture init failed (continuing in degraded mode): {e}")
        error_event_bus.emit(
            ErrorEvent(
                module="lifespan",
                error_type="ZERO_COST_INIT_FAILED",
                message=str(e)[:200],
                severity="WARNING",
                structured_context=ErrorContext(module="auto_fixed"),
                context={"component": "zero_cost_orchestrator"},
            )
        )

    # Background maintenance and agents are kept in a dedicated startup module.
    from core.startup.agents import start_background_services

    try:
        await start_background_services(app)
    except Exception as e:
        logger.error(f"start_background_services failed (continuing in degraded mode): {e}")
        error_event_bus.emit(
            ErrorEvent(
                module="lifespan",
                error_type="BACKGROUND_SERVICES_START_FAILED",
                message=str(e)[:200],
                severity="WARNING",
                structured_context=ErrorContext(module="auto_fixed"),
                context={"component": "background_services"},
            )
        )

    yield  # এখানে অ্যাপ্লিকেশন ট্রাফিক রিসিভ করবে

    # Zero-Cost Architecture shutdown (issue #1830): stop queue worker +
    # learning engine gracefully. Fail-soft — shutdown must always continue.
    try:
        from core.zero_cost_architecture.zero_cost_patch_phase1_4 import get_orchestrator

        await get_orchestrator().shutdown()
        logger.info("🛑 Zero-Cost Architecture shut down.")
    except Exception as e:
        logger.warning(f"Zero-Cost Architecture shutdown skipped: {e}")

    from core.shutdown import shutdown_services

    await shutdown_services(app)
