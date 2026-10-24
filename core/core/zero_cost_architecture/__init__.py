# ============================================================================
# Zero-Cost Architecture Module
# ============================================================================
# বাংলা: SupremeAI-এর জন্য শূন্য-খরচের আর্কিটেকচার মডিউল।
#
# This module provides production-ready infrastructure at $0/month:
# - In-Process Async Queue (replaces Celery/RQ)
# - Upstash Redis Integration (free tier optimized)
# - Self-Healing Circuit Breakers
# - Performance Learning Engine
#
# QUICK START:
# --------------
# from core.zero_cost_architecture import (
#     ZeroCostOrchestrator,
#     get_orchestrator,
#     lifespan_manager,
#     resilient_execute,
#     TaskPriority,
# )
#
# # In your FastAPI app:
# app.router.lifespan_context = lifespan_manager
#
# # Use in endpoints:
# @resilient_execute(circuit_breaker="llm_api", priority=TaskPriority.HIGH)
# async def my_task():
#     ...
#
# COST BREAKDOWN:
# ---------------
# Render Free Tier:      $0/month (1 instance, 512MB RAM)
# Upstash Redis Free:    $0/month (10K requests/day)
# Total:                 $0/month ✅
#
# Author: SuperAI Transformation Engine
# Version: 2.0.0-zero-cost
# ============================================================================

from .zero_cost_patch_phase1_4 import (
    # Phase 3: Adaptive Circuit Breaker
    AdaptiveCircuitBreaker,
    AdaptiveCircuitBreakerState,
    BreakerMetrics,
    CircuitBreakerOpenError,
    # Phase 1: In-Process Async Queue
    InProcessAsyncQueue,
    LearnedParameter,
    # Phase 4: Learning Engine
    PerformanceLearningEngine,
    QueuedTask,
    QueueFullError,
    TaskCancelledError,
    TaskFailedError,
    TaskPriority,
    TaskStatus,
    TaskTimeoutError,
    # Phase 2: Upstash Redis
    UpstashRedisClient,
    # Configuration
    ZeroCostConfig,
    # Integration Layer
    ZeroCostOrchestrator,
    # Utilities
    generate_correlation_id,
    get_orchestrator,
    get_zero_cost_config,
    lifespan_manager,
    measure_coroutine_performance,
    resilient_execute,
    sanitize_for_logging,
)

__all__ = [
    "ZeroCostConfig",
    "get_zero_cost_config",
    "InProcessAsyncQueue",
    "TaskPriority",
    "TaskStatus",
    "QueuedTask",
    "QueueFullError",
    "TaskTimeoutError",
    "TaskFailedError",
    "TaskCancelledError",
    "UpstashRedisClient",
    "AdaptiveCircuitBreaker",
    "AdaptiveCircuitBreakerState",
    "BreakerMetrics",
    "PerformanceLearningEngine",
    "LearnedParameter",
    "ZeroCostOrchestrator",
    "get_orchestrator",
    "lifespan_manager",
    "resilient_execute",
    "generate_correlation_id",
    "sanitize_for_logging",
    "measure_coroutine_performance",
    "CircuitBreakerOpenError",
]

__version__ = "2.0.0-zero-cost"
