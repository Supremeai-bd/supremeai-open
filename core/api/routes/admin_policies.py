"""Admin API route for Policy Engine (#4049).

বাংলা: policy rules manage করার জন্য admin endpoint।
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_current_admin
from governance.policy_engine import enforce_policies, evaluate_policies
from governance.policy_rules import DEFAULT_POLICY_RULES, get_active_rules

router = APIRouter(prefix="/admin-api/policies", tags=["policy-engine"])


class PolicyEvaluateRequest(BaseModel):
    """Request body for evaluating policies."""

    agent_role: str = Field(..., description="Agent role (coder, ci, auditor, etc.)")
    provider: str = Field(..., description="Provider name (groq, openai, cerebras)")
    task_type: str = Field("default", description="Task type")
    cost_per_call_usd: float = Field(0.0, description="Estimated cost per call")
    health_status: str = Field("healthy", description="Provider health status")
    security_clearance: str = Field("low", description="Security clearance level")


@router.post("/evaluate")
async def evaluate_policies_endpoint(
    request: PolicyEvaluateRequest,
    _admin: Any = Depends(get_current_admin),
) -> dict[str, Any]:
    """Evaluate a request against all policy rules.

    বাংলা: একটি provider call request-কে সব policy rules-এর বিরুদ্ধে evaluate করে।
    """
    try:
        evaluation = evaluate_policies(
            agent_role=request.agent_role,
            provider=request.provider,
            task_type=request.task_type,
            cost_per_call_usd=request.cost_per_call_usd,
            health_status=request.health_status,
            security_clearance=request.security_clearance,
        )
        return {
            "status": "ok",
            "evaluation": evaluation.to_dict(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Policy evaluation failed: {e}") from e


@router.post("/enforce")
async def enforce_policies_endpoint(
    request: PolicyEvaluateRequest,
    _admin: Any = Depends(get_current_admin),
) -> dict[str, Any]:
    """Enforce policy rules. Returns allowed=true/false.

    বাংলা: policy enforce করে। denied হলে allowed=false।
    """
    try:
        allowed = enforce_policies(
            agent_role=request.agent_role,
            provider=request.provider,
            task_type=request.task_type,
            cost_per_call_usd=request.cost_per_call_usd,
            health_status=request.health_status,
            security_clearance=request.security_clearance,
        )
        return {
            "status": "ok",
            "allowed": allowed,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Policy enforcement failed: {e}") from e


@router.get("/rules")
async def list_rules_endpoint(
    _admin: Any = Depends(get_current_admin),
) -> dict[str, Any]:
    """List all policy rules (active + inactive).

    বাংলা: সব policy rules-এর তালিকা।
    """
    return {
        "rules": [r.to_dict() for r in DEFAULT_POLICY_RULES],
        "total": len(DEFAULT_POLICY_RULES),
        "active_count": len(get_active_rules(DEFAULT_POLICY_RULES)),
    }


@router.get("/rules/active")
async def list_active_rules_endpoint(
    _admin: Any = Depends(get_current_admin),
) -> dict[str, Any]:
    """List active policy rules (sorted by priority).

    বাংলা: শুধু enabled rules, priority অনুযায়ী sorted।
    """
    active = get_active_rules(DEFAULT_POLICY_RULES)
    return {
        "rules": [r.to_dict() for r in active],
        "total": len(active),
    }
