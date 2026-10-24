# backend/core/factory.py
"""SupremeAI Factory & Master Wiring Layer.

Connects and orchestrates ALL phases and modules:
- Centralized Structured Logging & Global Exception Handling
- SupremeAIIntegrator (Phases 1, 2, 3)
- Canonical Task Runtime & TaskContract State Machine
- Deterministic Verifier Engine
- IntelligentRateLimiter (4-Provider Fallback Chain: Gemini -> Groq -> OpenRouter -> Ollama)
- SelfBenchmarkEngine & AdaptiveOptimizer
- PerformanceMonitor & Background Self-Evolution
- Graceful Shutdown & Comprehensive Health Check
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Structured logging setup
from core.adaptive_optimizer import AdaptiveOptimizer, get_optimizer
from core.config import Settings, settings
from core.integration_layer import SupremeAIIntegrator
from core.logging_config import logger
from core.provider_rate_limiter import IntelligentRateLimiter, get_provider_rate_limiter
from core.self_benchmark import SelfBenchmarkEngine
from core.task_contract import RiskLevel, TaskBudget, TaskContract, VerificationPolicy
from evolution.performance_monitor import PerformanceMonitor
from runtime.task_context import TaskContext
from runtime.task_runtime import TaskRuntime, get_task_runtime
from verification.verifier import VerifierEngine, get_verifier


class SupremeAIFactory:
    """Factory pattern for creating fully pre-wired production SupremeAI instances."""

    def __init__(self) -> None:
        self._limiter: IntelligentRateLimiter | None = None
        self._integrator: SupremeAIIntegrator | None = None
        self._benchmarker: SelfBenchmarkEngine | None = None
        self._optimizer: AdaptiveOptimizer | None = None
        self._monitor: PerformanceMonitor | None = None
        self._runtime: TaskRuntime | None = None
        self._verifier: VerifierEngine | None = None
        self._settings: Settings | None = None
        self._start_time: datetime | None = None

    async def create_production_instance(self) -> SupremeAIIntegrator:
        """Create and wire all system components for production execution."""
        logger.info("🏭 Creating PRODUCTION-WIRED SupremeAI instance...")
        self._start_time = datetime.now()

        self._settings = settings

        # 2. Initialize integrator (Phase 1, 2, 3)
        self._integrator = SupremeAIIntegrator(
            {
                "engine": {
                    "max_depth": getattr(getattr(self._settings, "api", None), "workers", 4)
                    if self._settings
                    else 4
                },
                "reasoning": {"parallel": True},
                "memory": {
                    "max_episodic": (
                        getattr(
                            getattr(self._settings, "memory", None), "max_episodic_memory", 1000
                        )
                        if self._settings
                        else 1000
                    )
                },
                "auto_evolution": {"enabled": True, "check_interval": 300},
                "monitoring": {"retention_hours": 24},
            }
        )
        await self._integrator.initialize()

        # 3. Wire rate limiter & provider fallback chain
        self._limiter = get_provider_rate_limiter(
            {
                "max_queue_size": (
                    getattr(getattr(self._settings, "api", None), "rate_limit_per_minute", 60) * 2
                    if self._settings
                    else 120
                ),
                "circuit_breaker_threshold": 3,
                "max_retries": 3,
            }
        )
        self._integrator.rate_limiter = self._limiter

        # 4. Initialize benchmark engine
        self._benchmarker = SelfBenchmarkEngine(
            ai_system=self._integrator,
            config={"test_duration_ms": 5000},
        )
        self._integrator.benchmarker = self._benchmarker

        # 5. Initialize adaptive optimizer
        self._optimizer = get_optimizer(
            benchmarker=self._benchmarker,
            ai_system=self._integrator,
            config={"auto_optimize": True, "max_risk": "medium"},
        )
        self._integrator.optimizer = self._optimizer

        # 6. Performance monitor
        self._monitor = self._integrator.performance_monitor or PerformanceMonitor()
        self._integrator.monitor = self._monitor

        # 7. Wire Verifier & Canonical Task Runtime
        self._verifier = get_verifier()
        self._runtime = get_task_runtime(ai_system=self._integrator)
        self._integrator.runtime = self._runtime
        self._integrator.verifier = self._verifier

        # 8. Start background processes
        await self._integrator.start_background_processes()

        logger.info("🎉 PRODUCTION SUPREMEAI WIRED & READY (Canonical Task Runtime Active)!")
        return self._integrator

    async def safe_process(
        self, query: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Safe processing wrapper routing through Canonical TaskContract and TaskRuntime."""
        if not self._integrator:
            await self.create_production_instance()

        if not self._runtime:
            self._runtime = get_task_runtime(ai_system=self._integrator)

        ctx_dict = context or {}
        policy_str = ctx_dict.get("verification_policy", "standard")
        policy = (
            VerificationPolicy(policy_str)
            if policy_str in [p.value for p in VerificationPolicy]
            else VerificationPolicy.STANDARD
        )

        # Create Canonical TaskContract
        task = TaskContract(
            goal=query,
            context=ctx_dict,
            risk_level=RiskLevel(ctx_dict.get("risk_level", "medium")),
            budget=TaskBudget(
                max_cost_usd=float(ctx_dict.get("max_cost_usd", 0.50)),
                max_execution_seconds=float(ctx_dict.get("timeout_seconds", 60.0)),
            ),
            verification_policy=policy,
            required_capabilities=ctx_dict.get("required_capabilities", []),
            success_criteria=ctx_dict.get("success_criteria", []),
        )

        task_ctx = TaskContext(
            tenant_id=ctx_dict.get("tenant_id"),
            session_id=ctx_dict.get("session_id"),
        )

        # Execute through authoritative control plane
        task_res = await self._runtime.execute_task(task, task_ctx)

        return {
            "success": task_res.success,
            "answer": task_res.answer,
            "confidence": task_res.confidence,
            "provider_used": task_res.provider_used,
            "latency_ms": task_res.execution_time_ms,
            "verified": getattr(getattr(task_res, "verification", None), "verified", None),
            "components_used": task_res.components_used,
            "task_id": task_res.task_id,
            "rate_limited": False
            if task_res.success
            else ("rate limit" in str(task_res.error).lower()),
            "error": task_res.error,
        }

    async def graceful_shutdown(self) -> None:
        """Clean shutdown - saves state, closes background tasks."""
        logger.info("🛑 Initiating graceful shutdown...")
        if self._integrator:
            await self._integrator.shutdown()
        logger.info("✅ Shutdown complete")

    def health_check(self) -> dict[str, Any]:
        """Comprehensive health check across all wired components."""
        is_init = getattr(self._integrator, "initialized", True) if self._integrator else False
        return {
            "status": "healthy" if is_init else "degraded",
            "components": {
                "integrator": self._integrator is not None,
                "runtime": self._runtime is not None,
                "verifier": self._verifier is not None,
                "rate_limiter": self._limiter is not None,
                "benchmark": self._benchmarker is not None,
                "optimizer": self._optimizer is not None,
            },
            "uptime": str(datetime.now() - self._start_time) if self._start_time else "N/A",
        }


# Singleton factory instance
_factory_instance: SupremeAIFactory | None = None


def get_factory() -> SupremeAIFactory:
    global _factory_instance
    if _factory_instance is None:
        _factory_instance = SupremeAIFactory()
    return _factory_instance


async def get_ai() -> SupremeAIIntegrator:
    factory = get_factory()
    if factory._integrator is None:
        await factory.create_production_instance()
    return factory._integrator
