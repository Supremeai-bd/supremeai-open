"""Admin API route for Learning Loop (#4054).

বাংলা: learning loop চালানোর জন্য admin endpoint।
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_current_admin
from learning.learning_loop import run_learning_loop

router = APIRouter(prefix="/admin-api/learning", tags=["learning-loop"])


class LearningLoopRequest(BaseModel):
    """Request body for running the learning loop."""

    decisions: list[dict[str, Any]] = Field(
        ..., description="List of DecisionMetadata dicts (from #4052)"
    )
    min_occurrences: int = Field(3, description="Minimum count to be considered a pattern")
    skills_dir: str = Field("knowledge/skills", description="Output dir for skill templates")
    guards_dir: str = Field(
        "knowledge/regression_guards", description="Output dir for regression guards"
    )


@router.post("/run")
async def run_learning_loop_endpoint(
    request: LearningLoopRequest,
    _admin: Any = Depends(get_current_admin),
) -> dict[str, Any]:
    """Run the learning loop — mine patterns + write skill templates + regression guards.

    বাংলা: সম্পূর্ণ learning loop চালায়। decisions থেকে patterns mine →
    skill templates + regression guards।
    """
    try:
        result = run_learning_loop(
            decisions=request.decisions,
            min_occurrences=request.min_occurrences,
            skills_dir=request.skills_dir,
            guards_dir=request.guards_dir,
        )
        return {
            "status": "ok",
            "result": result.to_dict(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Learning loop failed: {e}") from e


@router.get("/status")
async def learning_status_endpoint(
    _admin: Any = Depends(get_current_admin),
) -> dict[str, Any]:
    """Get learning loop status — how many skill templates + guards exist.

    বাংলা: বর্তমানে কতগুলো skill template + regression guard আছে তা দেখায়।
    """
    from pathlib import Path

    skills = (
        list(Path("knowledge/skills").glob("*.yaml")) if Path("knowledge/skills").exists() else []
    )
    guards = (
        list(Path("knowledge/regression_guards").glob("*.yaml"))
        if Path("knowledge/regression_guards").exists()
        else []
    )

    return {
        "skill_templates": len(skills),
        "regression_guards": len(guards),
        "skill_template_files": [f.name for f in skills],
        "regression_guard_files": [f.name for f in guards],
    }
