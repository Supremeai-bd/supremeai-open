import asyncio
import os
import sys
from pathlib import Path

from core import services
from core.agent_supervisor import agent_supervisor
from core.logging_config import logger


def _build_orchestrator_tick_loop(orchestrator):
    """Build the periodic tick loop for the core Orchestrator (issue #1817).

    Contract:
    - Runs ``orchestrator.tick()`` immediately, then every ``interval`` seconds
      (the Orchestrator's own cadence drives fitness scoring, the self-evolution
      tick, and the budget-guardian subprocess).
    - A budget-guardian HALT (RuntimeError containing "Halting orchestrator")
      returns CLEANLY — the supervisor treats a normal return as a permanent
      stop, so fail-closed financial-bleed protection is never defeated by an
      auto-restart into the same halt.
    - Any other exception propagates so the supervisor's exponential-backoff
      restart can self-heal transient failures (Redis/DB blips, cold starts).
    - ``_running`` mirrors the loop lifecycle so ``GET /orchestrator/status``
      (and the supervisor health map) reflect reality.
    """

    async def _orchestrator_tick_loop() -> None:
        orchestrator._running = True
        try:
            while True:
                try:
                    await orchestrator.tick()
                except RuntimeError as exc:
                    if "Halting orchestrator" in str(exc):
                        logger.critical(
                            f"🛑 Orchestrator tick loop HALTED (fail-closed): {exc} "
                            "Restart the process to re-enable after remediation."
                        )
                        return
                    raise
                await asyncio.sleep(orchestrator.interval)
        finally:
            orchestrator._running = False

    return _orchestrator_tick_loop


async def start_background_services(app):
    # ── Start background agents via centralized Supervisor ────────────────────
    from core.cache.multi_layer_cache import start_swarm_cache_invalidator
    from core.sentinel_agent import sentinel

    # Agent 0: Orchestrator Tick (issue #1817) — the ONE trigger path that
    # drives fitness scoring, the self-evolution tick, and the budget guardian
    # subprocess on a fixed cadence. Before #1817 the Orchestrator was built at
    # boot (core/lifespan.py) but `tick()` had zero callers in any deployed
    # environment — the intended `POST /orchestrator/tick` webhook router was
    # never registered, so the entire core loop was inert.
    #
    # Fail-closed contract (financial-bleed protection): when the budget
    # guardian halts (RuntimeError "Halting orchestrator..."), the loop returns
    # CLEANLY so the supervisor stops it permanently instead of restarting it
    # into the same halt. Transient (non-halt) errors still propagate so the
    # supervisor's exponential-backoff restart can self-heal them.
    # Zero LLM cost: fitness scoring + evolution tick are in-process reads,
    # the budget guardian is a local subprocess. Kill switch:
    # ENABLE_ORCHESTRATOR_TICK=false.
    try:
        import os

        if os.getenv("ENABLE_ORCHESTRATOR_TICK", "true").lower() == "true":
            orchestrator = getattr(app.state, "orchestrator", None)
            if orchestrator is not None:
                _tick_loop = _build_orchestrator_tick_loop(orchestrator)
                await agent_supervisor.start_agent(
                    "orchestrator-tick",
                    _tick_loop,
                    health_check_interval=300,
                    max_restarts=5,
                    restart_delay=10.0,
                )
                logger.info(
                    f"✅ Orchestrator tick loop started "
                    f"(interval={getattr(orchestrator, 'interval', '?')}s; "
                    "drives fitness scoring + self-evolution + budget guardian)."
                )
            else:
                logger.warning(
                    "⚠️ Orchestrator not initialized at boot — tick loop NOT started "
                    "(check ORCHESTRATOR_INIT_FAILED entries in boot logs)."
                )
        else:
            logger.info("ℹ️ Orchestrator tick loop disabled via environment variable.")
    except Exception as exc:
        logger.warning(f"⚠️ Orchestrator tick agent failed to start: {exc}")

    # Agent 1: Sentinel Agent (periodic endpoint monitoring & dependency audit)
    try:
        import os

        if os.getenv("ENABLE_SENTINEL_AGENT", "false").lower() == "true":
            await agent_supervisor.start_agent(
                "sentinel",
                lambda: sentinel.run_periodic_loop(),
                health_check_interval=60,
                max_restarts=10,
                restart_delay=1.0,
            )
            logger.info("✅ Sentinel Agent background loop started.")
        else:
            logger.info("ℹ️ Sentinel Agent disabled via environment variable.")
    except Exception as exc:
        logger.warning(f"⚠️ Sentinel Agent failed to start: {exc}")

    # Agent 2: Swarm Cache Invalidator (multi-layer cache maintenance)
    await agent_supervisor.start_agent(
        "swarm-cache",
        start_swarm_cache_invalidator,
        health_check_interval=60,
        max_restarts=5,
        restart_delay=5.0,
    )

    # Agent 3: Task Queue Worker
    try:
        # R2-03 FIX: the worker is now LAZY — it auto-starts on the first
        # enqueue() and stops after 5 idle minutes. An eager `BLPOP` loop
        # burned ~17k Upstash commands/day (> entire free-tier quota) even
        # with zero tasks. On boot we only register handlers.
        from core.queue.task_queue import redis_configured, task_queue

        if redis_configured():
            logger.info(
                "ℹ️ Task Queue Worker will start lazily on first enqueue (Upstash quota-safe)."
            )
        else:
            logger.info(
                "ℹ️ Task Queue disabled — no real REDIS_URL configured "
                "(enqueue() fails soft; set REDIS_URL to enable background tasks)."
            )
    except Exception as exc:
        logger.warning(f"⚠️ Task Queue Worker failed to start: {exc}")

    try:
        import os

        if os.getenv("ENABLE_SYSTEM_TELEMETRY", "false").lower() == "true":
            from core.telemetry.system_telemetry import run_system_telemetry_loop

            await agent_supervisor.start_agent(
                "system-telemetry",
                run_system_telemetry_loop,
                health_check_interval=60,
                max_restarts=5,
                restart_delay=2.0,
            )
            logger.info("✅ System Telemetry Broadcaster background loop started.")
        else:
            logger.info("ℹ️ System Telemetry Broadcaster disabled via environment variable.")
    except Exception as exc:
        logger.warning(f"⚠️ System Telemetry Broadcaster failed to start: {exc}")

    # Agent 4: Bug Prophet Anomaly Detector
    # FIX (incident #11, ERROR_COMPENDIUM register): the module used to live at
    # repo-root `scripts/devops/` which is NOT importable from the backend
    # process (backend/ is the runtime root), so the import always failed and
    # the whole agent stayed commented out. It now lives in
    # `backend/scripts/devops/bug_prophet.py`. Enabled behind ENABLE_BUG_PROPHET
    # (default off) — consistent with Sentinel/System-Telemetry gating.
    try:
        import os

        if os.getenv("ENABLE_BUG_PROPHET", "false").lower() == "true":
            from scripts.devops.bug_prophet import run_anomaly_detector_loop

            await agent_supervisor.start_agent(
                "bug-prophet-anomaly-detector",
                run_anomaly_detector_loop,
                health_check_interval=60,
                max_restarts=5,
                restart_delay=5.0,
            )
            logger.info("✅ BugProphet Anomaly Detector started.")
        else:
            logger.info("ℹ️ BugProphet Anomaly Detector disabled via environment variable.")
    except Exception as exc:
        logger.warning(f"⚠️ BugProphet Anomaly Detector failed to start: {exc}")

    # Agent 5: Self-Heartbeat (agent-10 slot, issue #1402) — SupremeAI pings
    # the shared agent-heartbeat Redis key so the /api/agents dashboard shows
    # agent-10 as 🟢 online while the backend is running (previously only
    # agent-11's dashboard pinged, every other slot showed "no heartbeat").
    # Zero-LLM-cost, ~1.9k Redis commands/day (0.4% Upstash budget) — default
    # ON with a kill switch, per LEARNING_LOOP/SYNAPTIC_DREAM precedent.
    try:
        import os

        if os.getenv("ENABLE_AGENT_HEARTBEAT", "true").lower() == "true":
            from core.agent_heartbeat import (
                redis_configured_for_heartbeat,
                run_agent_heartbeat_loop,
            )

            if redis_configured_for_heartbeat():
                await agent_supervisor.start_agent(
                    "agent-10-heartbeat",
                    run_agent_heartbeat_loop,
                    health_check_interval=300,
                    max_restarts=5,
                    restart_delay=10.0,
                )
                logger.info("✅ Agent-10 self-heartbeat loop started (45s cadence, TTL 300s).")
            else:
                logger.info(
                    "ℹ️ Agent-10 self-heartbeat disabled — no real REDIS_URL configured "
                    "(dashboard will show agent-10 as 'assigned · no heartbeat')."
                )
        else:
            logger.info("ℹ️ Agent-10 self-heartbeat disabled via ENABLE_AGENT_HEARTBEAT.")
    except Exception as exc:
        logger.warning(f"⚠️ Agent-10 self-heartbeat failed to start: {exc}")

    import os

    # Start Tier-8 Meta-Self Agents
    try:
        if os.getenv("ENABLE_TIER8", "false").lower() == "true":
            from core.tier8.tier8_integration import init_tier8

            await init_tier8(services.registry)
            logger.info("✅ Tier-8 Meta-Self subsystem initialized successfully.")
        else:
            logger.info("ℹ️ Tier-8 Meta-Self subsystem disabled via environment variable.")
    except Exception as exc:
        logger.warning(f"⚠️ Tier-8 initialization failed: {exc}")

    # বাংলা মন্তব্ব্য: SelfEvolutionAgent শুরু করা — এখন AgentSupervisor-এর অধীনে চলবে।
    try:
        if os.getenv("ENABLE_EVOLUTION", "false").lower() == "true":
            # SELF-EVOLVE FIX (real): pass the SHARED FitnessEngine singleton so
            # SelfEvolutionAgent._tick() reads the SAME metrics that
            # EvolutionEngine.learn_from_success() writes to via track_execution.
            # Previously SelfEvolutionAgent(interval_seconds=300) was called with
            # no fitness_engine arg → it created its OWN private FitnessEngine()
            # with empty metrics → _tick() never triggered refactors.
            # Now both use the same instance from api.deps.get_fitness_engine().
            from api.deps import get_fitness_engine
            from core.self_evolution.self_evolution_agent import SelfEvolutionAgent

            _evo_agent = SelfEvolutionAgent(
                fitness_engine=get_fitness_engine(),
                interval_seconds=300,
            )
            await _evo_agent.start()
            app.state.evo_agent = _evo_agent
            logger.info("✅ SelfEvolutionAgent background loop started (5-min evolution cycle).")
        else:
            app.state.evo_agent = None
            logger.info("ℹ️ SelfEvolutionAgent disabled via environment variable.")
    except Exception as exc:
        logger.warning(f"⚠️ SelfEvolutionAgent failed to start: {exc}")
        app.state.evo_agent = None

    # বাংলা মন্তব্ব্য: DailyLearner শুরু করা — এখন AgentSupervisor-এর অধীনে চলবে।
    try:
        if os.getenv("ENABLE_DAILY_LEARNER", "false").lower() == "true":
            from core.self_evolution.daily_learner import DailyLearner

            _daily_learner = DailyLearner()

            async def _daily_learner_loop() -> None:
                # Runs 24/7 by design, but only actually executes a learning
                # cycle when memory headroom is good. If memory is high when
                # a cycle is due, retry sooner (30 min) instead of skipping
                # the whole day — this keeps the "runs continuously, works
                # when memory is good" behavior without losing a full cycle.
                from core.memory_manager import get_memory_manager

                RETRY_DELAY_SECONDS = 1800  # 30 min
                FULL_CYCLE_SECONDS = 86400  # 24h

                while True:
                    if get_memory_manager().is_safe_for_heavy_task():
                        try:
                            await _daily_learner.learn_and_plan(
                                "Improve SupremeAI agent reasoning, error recovery, and free-tier efficiency"
                            )
                        except Exception as _exc:
                            logger.warning(f"⚠️ DailyLearner cycle failed: {_exc}")
                        await asyncio.sleep(FULL_CYCLE_SECONDS)
                    else:
                        logger.info(
                            "ℹ️ DailyLearner cycle deferred — memory usage too high, "
                            f"retrying in {RETRY_DELAY_SECONDS // 60} min."
                        )
                        await asyncio.sleep(RETRY_DELAY_SECONDS)

            await agent_supervisor.start_agent(
                "daily-learner",
                lambda: _daily_learner_loop(),
                health_check_interval=3600,  # Check hourly (runs every 24h)
                max_restarts=5,
                restart_delay=60.0,
            )
            logger.info("✅ DailyLearner background task started (24h research scan cycle).")
        else:
            logger.info("ℹ️ DailyLearner disabled via environment variable.")
    except Exception as exc:
        logger.warning(f"⚠️ DailyLearner failed to start: {exc}")

    # ── #1828: Quota Enforcer supervisor — scheduled hard-quota enforcement ──
    # বাংলা: quota_enforcer.py CLI আগে শুধু মানুষ মনে রাখলে চলত — ফলে over-quota
    # tenant কখনো suspend হতো না। এখন supervisor agent হিসেবে নির্ধারিত ব্যবধানে
    # (ডিফল্ট 24 ঘণ্টা) --enforce-all চালায়, সরাসরি CLI subprocess হিসেবে (হুবহু
    # যেভাবে মানুষ চালাত) — report + alert সব CLI-র নিজস্ব পাইপলাইনে।
    # Suspend করা একটি destructive কাজ, তাই ডিফল্ট off — prod-এ
    # ENABLE_QUOTA_ENFORCER=true দিয়ে চালু করা হয় (DailyLearner প্যাটার্ন)।
    try:
        if os.getenv("ENABLE_QUOTA_ENFORCER", "false").lower() == "true":

            async def _quota_enforcer_loop() -> None:
                script_path = (
                    Path(__file__).resolve().parents[2]
                    / "scripts"
                    / "billing"
                    / "quota_enforcer.py"
                )
                interval_seconds = (
                    max(1, int(os.getenv("QUOTA_ENFORCE_INTERVAL_HOURS", "24"))) * 3600
                )
                grace_hours = os.getenv("QUOTA_ENFORCE_GRACE_HOURS", "0")
                dry_run = os.getenv("QUOTA_ENFORCE_DRY_RUN", "false").lower() == "true"
                notify = os.getenv("QUOTA_ENFORCE_NOTIFY", "true").lower() == "true"

                while True:
                    try:
                        cmd = [sys.executable, str(script_path), "--enforce-all"]
                        if grace_hours:
                            cmd += ["--grace-hours", str(int(grace_hours))]
                        if dry_run:
                            cmd.append("--dry-run")
                        if notify:
                            cmd.append("--notify")
                        proc = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        _, stderr = await proc.communicate()
                        if proc.returncode == 0:
                            logger.info("✅ Quota enforcement pass completed (scheduled).")
                        elif proc.returncode == 1:
                            # CLI convention: exit 1 = tenants over quota (alert already sent)
                            logger.warning(
                                "⚠️ Quota enforcement pass: tenants over quota (alerts sent)."
                            )
                        else:
                            logger.error(
                                "❌ Quota enforcement pass failed "
                                f"(exit {proc.returncode}): {stderr[-500:] if stderr else 'no stderr'}"
                            )
                    except Exception as exc:
                        logger.warning(f"⚠️ Quota enforcement pass failed: {exc}")
                    await asyncio.sleep(interval_seconds)

            await agent_supervisor.start_agent(
                "quota-enforcer",
                lambda: _quota_enforcer_loop(),
                health_check_interval=3600,  # Check hourly (runs every 24h)
                max_restarts=5,
                restart_delay=60.0,
            )
            logger.info(
                "✅ QuotaEnforcer background task started (scheduled --enforce-all passes)."
            )
        else:
            logger.info(
                "ℹ️ QuotaEnforcer disabled via environment variable (ENABLE_QUOTA_ENFORCER)."
            )
    except Exception as exc:
        logger.warning(f"⚠️ QuotaEnforcer failed to start: {exc}")

    # ── #1827: Usage Metrics Aggregator — daily pipeline writer ─────────────
    # বাংলা: usage_metrics টেবিলে কেউ লিখত না — Usage dashboard স্থায়ী খালি।
    # এই agent দৈনিক in-process collector + CostGuard aggregates থেকে delta
    # snapshot লেখে (বিদ্যমান db.upsert_usage_metric ব্যবহার করে)। অ-ধ্বংসাত্মক
    # (নিজের DB-তে metrics লেখা) — তাই ডিফল্ট চালু (LearningLoop প্যাটার্ন)।
    try:
        if os.getenv("ENABLE_USAGE_METRICS_AGGREGATOR", "true").lower() == "true":

            async def _usage_metrics_loop() -> None:
                from core.startup.usage_metrics_aggregator import run_usage_metrics_loop

                interval = max(1, int(os.getenv("USAGE_METRICS_INTERVAL_HOURS", "24")))
                await run_usage_metrics_loop(interval_hours=interval)

            await agent_supervisor.start_agent(
                "usage-metrics-aggregator",
                lambda: _usage_metrics_loop(),
                health_check_interval=3600,  # Check hourly (writes every 24h)
                max_restarts=5,
                restart_delay=60.0,
            )
            logger.info("✅ UsageMetricsAggregator background task started (daily usage rows).")
        else:
            logger.info("ℹ️ UsageMetricsAggregator disabled via environment variable.")
    except Exception as exc:
        logger.warning(f"⚠️ UsageMetricsAggregator failed to start: {exc}")

    # ── Sprint 3/4 (Self-Evolution Zero-Cost plan): Learning Loop ────────────
    # Observe layer: start the LearningStore flush task ALWAYS (it is the
    # durable-telemetry pipeline; buffering is harmless, zero LLM cost, and
    # degrades to an in-process bounded buffer when the DB is unavailable).
    try:
        from core.learning import get_learning_store

        await get_learning_store().flush()  # drain anything recorded before boot
        get_learning_store().start()
        logger.info("✅ LearningStore flush loop started (durable learning_events pipeline).")
    except Exception as exc:
        logger.warning(f"⚠️ LearningStore failed to start: {exc}")

    # Analyze layer: periodic aggregate→snapshot→propose agent.
    # Proposals are NEVER auto-applied (plan §10.3) — HITL/admin review only.
    # বাংলা (M05 P-A, issue #453 Wave-3): সুরক্ষিত ডিফল্ট-উল্টো — "সেলফ-লার্নিং
    # প্ল্যাটফর্ম" দাবির সাথে বাস্তবতা মেলাতে ডিফল্ট এখন true। লুপটি শূন্য-খরচ
    # (নিজস্ব docstring: pure reads/aggregates, কোনো LLM কল নেই) এবং proposal
    # কখনো auto-apply হয় না, তাই ডিফল্ট-চালুতে খরচ/ঝুঁকি নেই।
    try:
        if os.getenv("ENABLE_LEARNING_LOOP", "true").lower() == "true":
            from core.learning.loop import get_learning_loop_agent

            _learning_agent = get_learning_loop_agent()
            await agent_supervisor.start_agent(
                "learning-loop",
                _learning_agent.start,
                health_check_interval=300,
                max_restarts=5,
                restart_delay=30.0,
            )
            logger.info(
                "✅ LearningLoopAgent registered with supervisor (5-min observe→propose cycle)."
            )
        else:
            logger.info(
                "ℹ️ LearningLoopAgent disabled via environment variable (ENABLE_LEARNING_LOOP)."
            )
    except Exception as exc:
        logger.warning(f"⚠️ LearningLoopAgent failed to start: {exc}")

    # বাংলা মন্তব্ব্য: AutoHealerService শুরু করা — DB/Redis স্বয়ংক্রিয়ভাবে ঠিক করে।
    try:
        if os.getenv("ENABLE_AUTO_HEALER", "false").lower() == "true":
            # FIX: original import was 'from core.errors.auto_healer import auto_healer_service'
            # but core/errors/auto_healer.py does NOT exist. The real module is
            # services/auto_healer.py and exports get_healer() returning AutoHealer.
            from services.auto_healer import get_healer

            auto_healer_service = get_healer()
            # BUG FIX #1 (CRITICAL): start_monitoring() is 'while True: await asyncio.sleep(30)'
            # — calling it with `await` BLOCKS the lifespan forever (ASGI never serves HTTP).
            # Fix: wrap with asyncio.create_task so it runs in background.
            import asyncio as _asyncio

            app.state.auto_healer = auto_healer_service
            app.state.auto_healer_task = _asyncio.create_task(
                auto_healer_service.start_monitoring(interval_seconds=300.0)
            )
            logger.info(
                "✅ AutoHealerService started in background (DB/Redis healing active, 300s check interval)."
            )
        else:
            logger.info("ℹ️ AutoHealerService disabled via environment variable.")
    except Exception as exc:
        logger.warning(f"⚠️ AutoHealerService failed to start: {exc}")

    # বাংলা মন্তব্ব্য: SelfHealer error listener এক্সপ্লিসিটলি রেজিস্টার করা হচ্ছে।
    try:
        from core.health.self_healer import register_self_healer_listener

        register_self_healer_listener()
        logger.info("✅ SelfHealer error listener registered in lifespan.")
    except Exception as exc:
        logger.warning(f"⚠️ SelfHealer listener registration failed: {exc}")

    # ── SupremeAI 2.0 Infrastructure Agents ──────────────────────────────────
    # বাংলা: ৪টা futuristic infrastructure agent — autonomous/self-healing/free-tier
    # vision-এর কোর। সব default "false" যাতে user opt-in করে enable করে (prior pattern:
    # Tier8/Evolution/DailyLearner সব default false)। প্রতিটা try/except-এ wrapped যাতে
    # একটা fail করলে অন্যগুলো চালু থাকে।

    # Agent: AutoScalingAgent — autonomous resource scaling (CPU/mem/response-time thresholds)
    try:
        if os.getenv("ENABLE_AUTOSCALING_AGENT", "false").lower() == "true":
            from agents.infrastructure.auto_scaling_agent import auto_scaling_agent

            async def _autoscaling_loop() -> None:
                await auto_scaling_agent.initialize_policies()
                while True:
                    try:
                        metrics = await auto_scaling_agent.collect_current_metrics()
                        rec = await auto_scaling_agent.analyze_scaling_need(metrics)
                        if rec and getattr(rec, "confidence", 0) > 0.6:
                            await auto_scaling_agent.execute_scaling_action(rec)
                    except Exception as _e:
                        logger.warning(f"⚠️ auto-scaling cycle failed: {_e}")
                    await asyncio.sleep(300)  # 5-min cycle

            await agent_supervisor.start_agent(
                "auto-scaling",
                lambda: _autoscaling_loop(),
                health_check_interval=60,
                max_restarts=5,
                restart_delay=10.0,
            )
            logger.info("✅ AutoScalingAgent started (5-min autonomous scaling cycle).")
        else:
            logger.info("ℹ️ AutoScalingAgent disabled (set ENABLE_AUTOSCALING_AGENT=true).")
    except Exception as exc:
        logger.warning(f"⚠️ AutoScalingAgent failed to start: {exc}")

    # Agent: PerformanceTuningAgent — continuous optimization with auto-apply
    try:
        if os.getenv("ENABLE_PERFORMANCE_TUNING_AGENT", "false").lower() == "true":
            from agents.infrastructure.performance_tuning_agent import performance_tuning_agent

            await agent_supervisor.start_agent(
                "performance-tuning",
                lambda: performance_tuning_agent.run_continuous_tuning(interval_minutes=15),
                health_check_interval=300,  # 5-min (loop runs 15-min cycles)
                max_restarts=5,
                restart_delay=30.0,
            )
            logger.info("✅ PerformanceTuningAgent started (15-min continuous tuning cycle).")
        else:
            logger.info(
                "ℹ️ PerformanceTuningAgent disabled (set ENABLE_PERFORMANCE_TUNING_AGENT=true)."
            )
    except Exception as exc:
        logger.warning(f"⚠️ PerformanceTuningAgent failed to start: {exc}")

    # Agent: CostOptimizationAgent — strategic cost tracking + opportunity identification
    try:
        if os.getenv("ENABLE_COST_OPTIMIZATION_AGENT", "false").lower() == "true":
            from agents.infrastructure.cost_optimization_agent import cost_optimization_agent

            async def _cost_opt_loop() -> None:
                await cost_optimization_agent.initialize_budget_config()
                while True:
                    try:
                        await cost_optimization_agent.track_cost_metrics()
                        await cost_optimization_agent.identify_optimization_opportunities()
                    except Exception as _e:
                        logger.warning(f"⚠️ cost-optimization cycle failed: {_e}")
                    await asyncio.sleep(3600)  # 1-hour cycle

            await agent_supervisor.start_agent(
                "cost-optimization",
                lambda: _cost_opt_loop(),
                health_check_interval=600,  # 10-min
                max_restarts=5,
                restart_delay=60.0,
            )
            logger.info("✅ CostOptimizationAgent started (1-hour cost-tracking cycle).")
        else:
            logger.info(
                "ℹ️ CostOptimizationAgent disabled (set ENABLE_COST_OPTIMIZATION_AGENT=true)."
            )
    except Exception as exc:
        logger.warning(f"⚠️ CostOptimizationAgent failed to start: {exc}")

    # Agent: DisasterRecoveryAgent — periodic incremental backups + integrity verification
    try:
        if os.getenv("ENABLE_DISASTER_RECOVERY_AGENT", "false").lower() == "true":
            from agents.infrastructure.disaster_recovery_agent import disaster_recovery_agent

            async def _disaster_recovery_loop() -> None:
                await disaster_recovery_agent.initialize_recovery_plans()
                while True:
                    try:
                        await disaster_recovery_agent.create_backup(backup_type="incremental")
                    except Exception as _e:
                        logger.warning(f"⚠️ disaster-recovery backup cycle failed: {_e}")
                    await asyncio.sleep(21600)  # 6-hour cycle

            await agent_supervisor.start_agent(
                "disaster-recovery",
                lambda: _disaster_recovery_loop(),
                health_check_interval=1800,  # 30-min
                max_restarts=3,
                restart_delay=120.0,
            )
            logger.info("✅ DisasterRecoveryAgent started (6-hour incremental backup cycle).")
        else:
            logger.info(
                "ℹ️ DisasterRecoveryAgent disabled (set ENABLE_DISASTER_RECOVERY_AGENT=true)."
            )
    except Exception as exc:
        logger.warning(f"⚠️ DisasterRecoveryAgent failed to start: {exc}")

    # Agent: ai_memory Retention — periodic decay/cleanup of the canonical
    # ai_memory table via the Supabase RPC fn_ai_memory_retention_cleanup.
    # M0.6 checkpoint (roadmap M0.6 / PR #303 §10): the Phase C SQL ships the
    # function and the retention indexes, but nothing invoked it on a schedule
    # until now. Env-gated like every other infrastructure agent.
    try:
        if os.getenv("ENABLE_AI_MEMORY_RETENTION", "false").lower() == "true":

            async def _ai_memory_retention_loop() -> None:
                interval = int(os.getenv("AI_MEMORY_RETENTION_INTERVAL_SECONDS", "86400"))
                while True:
                    try:
                        from services.memory_service import _get_supabase

                        client = _get_supabase()

                        def _run_retention_rpc(client=client):
                            return client.rpc("fn_ai_memory_retention_cleanup", {}).execute()

                        result = await asyncio.to_thread(_run_retention_rpc)
                        logger.info(f"✅ ai_memory retention cleanup executed: {result.data}")
                    except Exception as _e:
                        logger.warning(f"⚠️ ai_memory retention cycle failed (non-fatal): {_e}")
                    await asyncio.sleep(interval)

            await agent_supervisor.start_agent(
                "ai-memory-retention",
                lambda: _ai_memory_retention_loop(),
                health_check_interval=3600,
                max_restarts=5,
                restart_delay=60.0,
            )
            logger.info("✅ ai_memory retention agent started (daily decay/cleanup cycle).")
        else:
            logger.info(
                "ℹ️ ai_memory retention agent disabled (set ENABLE_AI_MEMORY_RETENTION=true)."
            )
    except Exception as exc:
        logger.warning(f"⚠️ ai_memory retention agent failed to start: {exc}")

    # Agent: Scheduled-task sweep (M22 P-A, issue #453 Wave 1) — S10-store-এর
    # জমানো due টাস্ক বাস্তবে চালানোর executor-লুপ।
    # বাংলা: S11 Scheduled Tasks ব্যবহারকারী-মুখী ফিচার — ব্যবহারকারী "টাস্ক চলবেই"
    # বোঝেন; তাই এটি env-gated নয় (env-gate = ভুয়া ফিচার-প্রতিশ্রুতি)। DB অনুপস্থিতে
    # লুপ সৎভাবে idle থাকে (throttled সতর্কতা), বাকি agent-দের ব্যর্থ করে না।
    try:
        from core.scheduled_task_sweep import run_due_task_sweep_loop

        await agent_supervisor.start_agent(
            "scheduled-task-sweep",
            run_due_task_sweep_loop,
            health_check_interval=300,
            max_restarts=5,
            restart_delay=10.0,
        )
        logger.info("✅ Scheduled-task sweep agent started (due-task execution loop).")
    except Exception as exc:
        logger.warning(f"⚠️ Scheduled-task sweep failed to start: {exc}")

    # Agent: Synaptic Dream — memory consolidation/prune স্পন্দন (M01 P-C,
    # issue #453 Wave 4)। বাংলা: worker-টি নির্মিত ছিল কিন্তু কোনো scheduler-এ
    # wired নয় — plan-এর "scheduled consolidation নেই" অনুপস্থিতি এখানে নিরাময়।
    # শূন্য-খরচ লুপ (দিনে একবার বাউন্ডেড Supabase প্রুন) তাই M05 P-A প্যাটার্নে
    # ডিফল্ট true + kill-switch (ENABLE_SYNAPTIC_DREAM=false = আজকের আচরণ)।
    # store-অনুপস্থিতে লুপ সৎভাবে idle থাকে (throttled সতর্কতা), বাকি agent
    # ব্যর্থ করে না। ai-memory-retention RPC-র সাথে overlap নয় — সেটি SQL-পার্শ্ব
    # fn_ai_memory_retention_cleanup, এটি Python-পার্শ্ব সৎ-কাউন্ট dream চক্র।
    try:
        if os.getenv("ENABLE_SYNAPTIC_DREAM", "true").lower() == "true":
            from workers.synaptic_dream import run_synaptic_dream_loop

            await agent_supervisor.start_agent(
                "synaptic-dream",
                run_synaptic_dream_loop,
                health_check_interval=3600,
                max_restarts=5,
                restart_delay=60.0,
            )
            logger.info("✅ Synaptic Dream agent started (memory consolidation cycle).")
        else:
            logger.info("ℹ️ Synaptic Dream agent disabled (set ENABLE_SYNAPTIC_DREAM=true).")
    except Exception as exc:
        logger.warning(f"⚠️ Synaptic Dream agent failed to start: {exc}")

    # Start the agent health monitor
    await agent_supervisor.start_monitor(check_interval=30)
