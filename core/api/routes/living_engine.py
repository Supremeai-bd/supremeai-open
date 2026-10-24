# backend/api/routes/living_engine.py
"""SupremeAI Living Engine API Endpoints.

Provides unified runtime reasoning and autonomous execution endpoints
for unpredictable demands.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.security.authentication.rbac import get_current_user_token
from services.living_engine import LivingEngineOrchestrator

router = APIRouter(
    prefix="/api/v1/engine",
    tags=["living-engine"],
    dependencies=[Depends(get_current_user_token)],
)

# Singleton engine instance
global_orchestrator = LivingEngineOrchestrator()


class SolveRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="User or admin instruction in any language")
    context: dict[str, Any] | None = Field(default=None, description="Optional execution context")
    session_id: str | None = Field(
        default="", description="Session ID for continuous memory tracking"
    )


@router.post("/solve")
async def solve_unpredictable_demand(req: SolveRequest):
    """Executes full 4-Pillar reasoning and autonomous execution pipeline."""
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    solution = await global_orchestrator.solve_unpredictable_demand(
        prompt=req.prompt,
        context=req.context,
        session_id=req.session_id or "",
    )

    if not solution.success and solution.error:
        raise HTTPException(status_code=500, detail=solution.error)

    return solution.to_dict()
