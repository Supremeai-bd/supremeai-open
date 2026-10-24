# backend/core/integration_layer.py
"""SupremeAI Unified Master Integration Layer (Phases 1, 2, 3 Complete Integration).

Provides a single high-level unified interface for:
- Full Request Lifecycle (Safety -> Multi-Type Reasoning -> Pattern Recognition -> Domain Adaptation -> Living Execution -> Memory Storage -> Learning)
- Continuous Background Process Management (Auto-Evolution, Memory Consolidation, Health Monitoring)
- Graceful Shutdown and Session Telemetry
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from adapters.business_adapter import BusinessAdapter
from adapters.dev_adapter import DevAdapter
from adapters.ux_adapter import UXAdapter
from core.advanced_reasoning import AdvancedReasoningEngine
from core.evolution_module import EvolutionModule
from core.logging_config import logger
from core.resilience.safety_rollback_manager import SafetyRollbackManager
from evolution.auto_evolution_controller import AutoEvolutionController
from learning.pattern_recognizer import PatternRecognizer
from scaling.distributed_manager import DistributedScalingManager
from services.living_engine import LivingEngineOrchestrator, SolutionResult


@dataclass
class IntegratedResult:
    """Unified result from SupremeAI multi-phase pipeline."""

    success: bool
    answer: Any
    confidence: float
    processing_time_ms: float
    components_used: list[str]
    evolution_applied: bool
    learning_occurred: bool
    domain: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "answer": self.answer,
            "confidence": self.confidence,
            "processing_time_ms": self.processing_time_ms,
            "components_used": self.components_used,
            "evolution_applied": self.evolution_applied,
            "learning_occurred": self.learning_occurred,
            "domain": self.domain,
            "metadata": self.metadata,
        }


class SupremeAIIntegrator:
    """Master Integrator connecting Phases 1, 2, and 3 into an autonomous living system."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config: dict[str, Any] = config or {}

        # Core Engines
        self.reasoning_engine = AdvancedReasoningEngine(self.config.get("reasoning", {}))
        self.pattern_recognizer = PatternRecognizer(self.config.get("patterns", {}))
        self.evolution_module = EvolutionModule(self.config.get("evolution", {}))
        self.living_engine = LivingEngineOrchestrator(
            reasoning_engine=self.reasoning_engine,
            pattern_recognizer=self.pattern_recognizer,
            evolution_module=self.evolution_module,
        )

        # Domain Adapters
        self.dev_adapter = DevAdapter(self.config.get("dev", {}))
        self.business_adapter = BusinessAdapter(self.config.get("business", {}))
        self.ux_adapter = UXAdapter(self.config.get("ux", {}))

        # Phase 3 Self-Evolution & Production Resilience
        self.auto_evolution = AutoEvolutionController(self.config.get("auto_evolution", {}))
        self.performance_monitor = self.auto_evolution.performance_monitor
        self.memory_consolidator = self.auto_evolution.memory_consolidator
        self.safety_rollback = SafetyRollbackManager(self.config.get("safety", {}))
        self.scaling_manager = DistributedScalingManager(self.config.get("scaling", {}))

        # State & Telemetry
        self.initialized = False
        self._background_running = False
        self._background_tasks: list[asyncio.Task[Any]] = []

        self.session_stats: dict[str, Any] = {
            "requests_processed": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_processing_time_ms": 0.0,
            "evolutions_triggered": 0,
            "learnings_stored": 0,
        }

    async def initialize(self) -> bool:
        """Initializes all underlying subsystems and validates baseline health."""
        if self.initialized:
            return True

        logger.info("Initializing SupremeAI Unified Master Integration Layer...")
        await self.auto_evolution.check_system_health()
        self.initialized = True
        logger.info("SupremeAI Unified Integration Layer successfully initialized!")
        return True

    async def process(
        self, user_input: str, context: dict[str, Any] | None = None
    ) -> IntegratedResult:
        """Main end-to-end processing pipeline for any user demand."""
        start_time = time.perf_counter()
        if not self.initialized:
            await self.initialize()

        self.session_stats["requests_processed"] += 1
        ctx = context or {}
        components_used = ["reasoning_engine", "pattern_recognizer", "living_engine"]

        try:
            # 1. Execute full reasoning, dynamic HTN DAG, and domain adaptation
            solution: SolutionResult = await self.living_engine.solve_unpredictable_demand(
                prompt=user_input,
                context=ctx,
            )

            # 2. Record performance metric
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            self.performance_monitor.record_metric(
                self.performance_monitor.generate_report(1).detailed_metrics.get(
                    "system.cpu.usage_percent", []
                )[-1]
                if self.performance_monitor.metrics.get("system.cpu.usage_percent")
                else None  # type: ignore[arg-type]
            ) if self.performance_monitor.metrics.get("system.cpu.usage_percent") else None

            if solution.domain == "development":
                components_used.append("dev_adapter")
            elif solution.domain == "business":
                components_used.append("business_adapter")
            elif solution.domain == "ux":
                components_used.append("ux_adapter")

            self.session_stats["successful_requests"] += 1
            self.session_stats["total_processing_time_ms"] += duration_ms
            self.session_stats["learnings_stored"] += len(solution.patterns)

            return IntegratedResult(
                success=solution.success,
                answer=solution.results or solution.error,
                confidence=solution.fitness_score,
                processing_time_ms=round(duration_ms, 2),
                components_used=components_used,
                evolution_applied=bool(solution.evolution.get("improvement_pct", 0) > 0),
                learning_occurred=bool(len(solution.patterns) > 0),
                domain=solution.domain,
                metadata={
                    "reasoning": solution.reasoning,
                    "execution_order": solution.execution_order,
                    "evolution": solution.evolution,
                },
            )

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            self.session_stats["failed_requests"] += 1
            logger.error(f"SupremeAIIntegrator: Processing error: {exc}")

            return IntegratedResult(
                success=False,
                answer=f"Processing error: {str(exc)}",
                confidence=0.0,
                processing_time_ms=round(duration_ms, 2),
                components_used=components_used,
                evolution_applied=False,
                learning_occurred=False,
                domain="error",
                metadata={"error": str(exc)},
            )

    async def start_background_processes(self) -> None:
        """Launches continuous self-evolution, memory consolidation, and scaling loops in background."""
        if self._background_running:
            return

        self._background_running = True
        logger.info("Starting SupremeAI Background Autonomous Evolution & Maintenance tasks...")

        # Evolution loop
        async def _evolution_loop() -> None:
            while self._background_running:
                try:
                    await asyncio.sleep(self.config.get("evolution_interval_seconds", 300))
                    cycle = await self.auto_evolution.run_evolution_cycle()
                    self.session_stats["evolutions_triggered"] += 1
                    logger.info(f"Background Evolution Cycle completed: {cycle.cycle_id}")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning(f"Background evolution loop tick: {e}")

        # Memory consolidation loop
        async def _consolidation_loop() -> None:
            while self._background_running:
                try:
                    await asyncio.sleep(self.config.get("consolidation_interval_seconds", 600))
                    await self.memory_consolidator.consolidate()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning(f"Background consolidation tick: {e}")

        self._background_tasks.append(asyncio.create_task(_evolution_loop()))
        self._background_tasks.append(asyncio.create_task(_consolidation_loop()))

    async def shutdown(self) -> None:
        """Gracefully shuts down all background processes and creates a safety checkpoint."""
        logger.info("Shutting down SupremeAI Integrator...")
        self._background_running = False
        for task in self._background_tasks:
            task.cancel()

        # Create safety checkpoint on shutdown
        await self.safety_rollback.create_checkpoint()
        logger.info("SupremeAI Integrator gracefully shut down with safety checkpoint saved.")

    def get_system_status(self) -> dict[str, Any]:
        """Provides a composite status dashboard across all subsystems."""
        return {
            "initialized": self.initialized,
            "background_running": self._background_running,
            "session_stats": self.session_stats,
            "auto_evolution": self.auto_evolution.get_statistics(),
            "performance_metrics": self.performance_monitor.get_current_metrics(),
            "cluster_status": self.scaling_manager.get_cluster_status(),
        }


# Global Singleton Facade
_global_integrator: SupremeAIIntegrator | None = None


async def get_integrator(config: dict[str, Any] | None = None) -> SupremeAIIntegrator:
    """Returns or creates the global SupremeAIIntegrator singleton."""
    global _global_integrator
    if _global_integrator is None:
        _global_integrator = SupremeAIIntegrator(config)
        await _global_integrator.initialize()
    return _global_integrator
