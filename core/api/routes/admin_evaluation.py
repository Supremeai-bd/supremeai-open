"""Admin API route for Capability Evaluation Engine (#4047).

বাংলা: admin endpoint-গুলো evaluation scores query করার জন্য। Router +
Policy Engine এই scores ব্যবহার করে routing decisions নেয়।
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_current_admin
from evaluation.capability_evaluator import evaluate_provider
from evaluation.models import ProviderScore

router = APIRouter(prefix="/admin-api/evaluation", tags=["capability-evaluation"])


class EvaluationRequest(BaseModel):
    """Request body for evaluating a provider."""

    provider: str = Field(..., description="Provider name (e.g., groq, openai, cerebras)")
    task_type: str = Field(
        "default",
        description="Task type (ci_fix, code_review, research, browser_automation, default)",
    )
    measurements: dict[str, Any] = Field(
        default_factory=dict, description="Measurement values for each scorer"
    )
    benchmark_run_id: str | None = Field(
        None, description="Optional run ID (auto-generated if None)"
    )
    previous_run_id: str = Field("", description="Previous run ID for regression comparison")


@router.post("/scores")
async def evaluate_provider_endpoint(
    request: EvaluationRequest,
    _admin: Any = Depends(get_current_admin),
) -> dict[str, Any]:
    """Evaluate a provider for a task-type. Returns ProviderScore JSON.

    বাংলা: একটি provider-এর জন্য ৭-dimension evaluation score তৈরি করে।
    Router + Policy Engine এই score ব্যবহার করে routing decisions নেয়।
    """
    try:
        score: ProviderScore = evaluate_provider(
            provider=request.provider,
            task_type=request.task_type,
            measurements=request.measurements,
            benchmark_run_id=request.benchmark_run_id,
            previous_run_id=request.previous_run_id,
        )
        return {
            "status": "ok",
            "score": score.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Validation error: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {e}") from e


@router.get("/weights/{task_type}")
async def get_weights_endpoint(
    task_type: str,
    _admin: Any = Depends(get_current_admin),
) -> dict[str, Any]:
    """Get dimension weights for a task-type.

    বাংলা: task-type অনুযায়ী dimension weights দেখায়। admin-configurable
    (future: Policy Engine will manage weight overrides)।
    """
    from evaluation.models import DEFAULT_TASK_WEIGHTS, get_weights

    weights = get_weights(task_type)
    return {
        "task_type": task_type,
        "weights": weights,
        "available_task_types": list(DEFAULT_TASK_WEIGHTS.keys()),
    }


@router.get("/dimensions")
async def list_dimensions_endpoint(
    _admin: Any = Depends(get_current_admin),
) -> dict[str, Any]:
    """List all 7 evaluation dimensions with descriptions.

    বাংলা: ৭টি evaluation dimension-এর তালিকা — correctness, latency, cost,
    reliability, security, tool_use, regression।
    """
    from evaluation.models import ScoreDimension

    descriptions = {
        "correctness": "Does output solve the task? (LLM-judge + test-suite pass rate)",
        "latency": "Response time p50/p95/p99 (lower = better)",
        "cost": "Dollar cost per call + per task (lower = better)",
        "reliability": "Uptime % + error rate from service_topology health check",
        "security": "Data exposure risk + hardening flags (PII redaction, sandbox, egress)",
        "tool_use": "Percentage of tool calls that succeed (MCP tools, browser, etc.)",
        "regression": "Quality delta vs last benchmark run (degradation > 10% → alert)",
    }
    return {
        "dimensions": [
            {
                "name": d.value,
                "description": descriptions.get(d.value, ""),
                "score_range": "0.0-1.0 (higher = better)",
            }
            for d in ScoreDimension
        ],
        "total": len(ScoreDimension),
    }
