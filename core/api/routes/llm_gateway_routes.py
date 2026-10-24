"""LLM Gateway API routes with health monitoring."""

# বাংলা মন্তব্য: REGRESSION FIX — কমিট 985ed35 ভুলভাবে `from core.auth import get_current_user`
# import করেছিল যা কোডবেসে কখনোই ছিল না। প্রতিটি অন্য রাউটারের মতো
# `from api.dependencies import get_current_user_token` ব্যবহার করা হচ্ছে।

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.dependencies import get_current_user_token
from core.llm.free_tier_tracker import get_tracker
from core.llm.llm_gateway import get_llm_gateway
from core.resilience.circuit_breaker_manager import get_circuit_breaker_manager

router = APIRouter(prefix="/llm-gateway", tags=["llm-gateway"])


@router.get("/health")
async def llm_gateway_health(current_user: dict = Depends(get_current_user_token)):
    """Health check for LLM Gateway with circuit breaker and tracker status."""
    gateway = get_llm_gateway()

    # Get circuit breaker states
    cb_manager = get_circuit_breaker_manager()
    circuit_breaker_states = cb_manager.get_all_states()

    # Get free tier tracker status
    tracker = get_tracker()
    tracker_status = tracker.get_status()

    return {
        "status": "healthy",
        "gateway_initialized": gateway is not None,
        "circuit_breakers": circuit_breaker_states,
        "free_tier_trackers": tracker_status,
        "providers_configured": True,
    }


@router.get("/admin/gateway/state")
async def get_gateway_state(current_user: dict = Depends(get_current_user_token)):
    """Get detailed state information for all gateways."""
    gateway = get_llm_gateway()

    # Get circuit breaker states
    cb_manager = get_circuit_breaker_manager()
    circuit_breaker_states = cb_manager.get_all_states()

    # Get free tier tracker status
    tracker = get_tracker()
    tracker_status = tracker.get_status()

    return {
        "llm_gateway": {
            "initialized": gateway is not None,
            "request_count": getattr(gateway, "_request_count", 0),
            "error_count": getattr(gateway, "_error_count", 0),
        },
        "circuit_breakers": circuit_breaker_states,
        "free_tier_trackers": tracker_status,
    }


@router.post("/admin/circuit-breaker/reset/{name}")
async def reset_circuit_breaker(name: str, current_user: dict = Depends(get_current_user_token)):
    """Reset a specific circuit breaker."""
    cb_manager = get_circuit_breaker_manager()
    success = cb_manager.reset_breaker(name)

    if success:
        return {"message": f"Circuit breaker {name} reset successfully"}
    else:
        return JSONResponse(status_code=404, content={"error": f"Circuit breaker {name} not found"})


@router.get("/admin/providers/fallback-chain")
async def get_fallback_chain(
    task_type: str = "chat",
    model: str | None = None,
    provider: str | None = None,
    current_user: dict = Depends(get_current_user_token),
):
    """Get the current fallback chain for a given task type."""
    gateway = get_llm_gateway()
    call_chain = gateway._build_call_chain(model, provider, task_type)

    return {"task_type": task_type, "fallback_chain": call_chain, "chain_length": len(call_chain)}
