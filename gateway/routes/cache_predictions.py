from fastapi import APIRouter

from core.cache.predictive_cache_engine import get_predictive_engine

router = APIRouter(prefix="/cache/predictions", tags=["cache"])


@router.get("/{user_id}")
async def get_predictions(user_id: str, current_key: str = ""):
    engine = get_predictive_engine()
    preds = engine.predict(user_id=user_id, current_key=current_key)
    return {
        "predictions": [
            {"key": p.key, "confidence": p.confidence, "description": p.description} for p in preds
        ]
    }
