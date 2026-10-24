"""Model-router status + override endpoints
(GET /admin-api/model-router, POST /admin-api/model-router/override)."""

from api.routes.admin_dashboard import router
from api.routes.admin_dashboard._models import RouterOverrideRequest
from core.logging_config import logger


@router.get("/model-router")
def get_model_router():
    return {
        "current_override": None,
        "override_remaining_requests": 0,
        "ab_test_active": False,
        "ab_test_split": 50,
        "provider_order": ["openrouter", "gemini", "groq", "deepseek"],
        "cost_quality_preference": 0.7,
    }


@router.post("/model-router/override")
def set_router_override(payload: RouterOverrideRequest):
    logger.info(
        f"Router override set: {payload.provider}/{payload.model} for {payload.remaining_requests} requests"
    )
    return {
        "status": "success",
        "override": {
            "provider": payload.provider,
            "model": payload.model,
            "remaining": payload.remaining_requests,
        },
    }
