from fastapi import APIRouter, Depends

from api.deps import get_current_user_token
from core.zero_cost_architecture.zero_cost_patch_phase1_4 import (
    get_orchestrator,
    get_zero_cost_config,
)

# AUDIT-FIX (#1704 P0): আগে router-এ কোনো auth dependency ছিল না — ফলে
# /zero-cost/health, /metrics, /recommendations-এর মাধ্যমে যে কেউ
# queue metrics, circuit breaker state ও learning metrics দেখতে পারত।
# এই endpoint গুলো system internals প্রকাশ করে — admin/operator-only।
router = APIRouter(
    prefix="/zero-cost",
    tags=["Zero-Cost Architecture"],
    dependencies=[Depends(get_current_user_token)],
)


@router.get("/health")
async def zero_cost_health():
    orchestrator = get_orchestrator()
    return {
        "status": "healthy",
        "queue": orchestrator.queue.get_metrics(),
        "redis_connected": orchestrator.redis.is_connected,
        "config": {
            # Issue #1830: these read the real config fields — the endpoint
            # previously used the ENV-VAR names (ZERO_COST_MAX_CONCURRENT /
            # ZERO_COST_TASK_TIMEOUT) as pydantic attribute names, which do
            # not exist on ZeroCostConfig → AttributeError → 500 on every
            # health poll.
            "max_concurrent": get_zero_cost_config().QUEUE_MAX_CONCURRENT_TASKS,
            "timeout": get_zero_cost_config().QUEUE_TASK_TIMEOUT_SECONDS,
            "self_healing": get_zero_cost_config().SELF_HEALING_ENABLED,
        },
    }


@router.get("/metrics")
async def zero_cost_metrics():
    orchestrator = get_orchestrator()
    cb_metrics = {name: cb.get_metrics() for name, cb in orchestrator.circuit_breakers.items()}
    return {
        "queue_metrics": orchestrator.queue.get_metrics(),
        "circuit_breakers": cb_metrics,
        "learning_metrics": orchestrator.learning_engine.get_learning_metrics(),
    }


@router.get("/recommendations")
async def zero_cost_recommendations():
    orchestrator = get_orchestrator()
    metrics = orchestrator.learning_engine.get_learning_metrics()

    recommendations = []
    for op, param in metrics.items():
        # Issue #1830: the config field is QUEUE_TASK_TIMEOUT_SECONDS — the
        # env-var name (ZERO_COST_TASK_TIMEOUT) is not a pydantic attribute.
        if param.get("p95_duration", 0) > get_zero_cost_config().QUEUE_TASK_TIMEOUT_SECONDS * 0.8:
            recommendations.append(
                f"Timeout for {op} is approaching P95 duration. Consider increasing it."
            )
        if param.get("error_rate", 0) > 0.1:
            recommendations.append(
                f"High error rate ({param['error_rate'] * 100:.1f}%) observed for {op}."
            )

    if not recommendations:
        recommendations.append("System is running optimally within Zero-Cost constraints.")

    return {"recommendations": recommendations}
