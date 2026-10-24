"""Ecosystem admin routes — Phase 9, 15 (ROADMAP §9, §13, §27, §47).

বাংলা: admin endpoints. Production-এ core.security.authentication.auth_middleware
verify_admin_session_fail_closed ব্যবহার হবে (JWT ভিত্তিক)।
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from adaptive_engine.approval_workflow import ApprovalDecision, ApprovalProposal
from adaptive_engine.learning_loop import LearningOpportunity, LearningStage
from adaptive_engine.task_engine import TaskState, get_task_engine
from api.dependencies import get_current_user_token
from ecosystem import (
    Capability,
    CapabilityLifecycleState,
    CapabilityRuntimeTier,
    CapabilityStateError,
    ProposalKind,
    ProposalPriority,
    ProposalState,
    SourceCategory,
    SourcePolicy,
    SourceState,
    get_approval_workflow,
    get_capability_registry,
    get_governance_engine,
    get_learning_loop,
    get_source_governance,
)


# বাংলা: admin auth — JWT প্রথম (module docstring-এর production intent),
# static ADMIN_TOKEN শুধু ops/service-to-service fallback.
async def _verify_admin(request: Request) -> dict:
    try:
        payload = get_current_user_token(request)
        if payload.get("role") == "admin":
            return {
                "role": "admin",
                "subject": str(payload.get("sub") or payload.get("email") or "jwt"),
            }
    except HTTPException as exc:
        logger.debug(
            "JWT admin token check failed (%s); falling through to static token fallback", exc
        )
    static_token = os.getenv("ADMIN_TOKEN", "")
    auth = request.headers.get("Authorization", "")
    if static_token and auth == f"Bearer {static_token}":
        return {"role": "admin", "subject": "static-admin-token"}
    if not payload_ok(request):
        raise HTTPException(401, "Missing or invalid admin credentials")
    raise HTTPException(403, "Admin access required")


def payload_ok(request: Request) -> bool:
    """True when a decoded user context exists (authenticated non-admin)."""
    return getattr(request.state, "user", None) is not None


router = APIRouter(
    prefix="/api/v1/ecosystem/admin",
    tags=["ecosystem-admin"],
    dependencies=[Depends(_verify_admin)],
)


class CapabilityCreateRequest(BaseModel):
    name: str
    purpose: str
    signature: str
    category: str = "general"
    version: str = "0.1.0"
    execution_method: str = "in_process"
    security_level: str = "standard"
    runtime_tier: str = "WARM"
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    owner: str = "system"
    tenant_id: str | None = None


@router.post("/capabilities")
def admin_create_capability(req: CapabilityCreateRequest) -> dict:
    try:
        rt = CapabilityRuntimeTier(req.runtime_tier)
    except ValueError:
        raise HTTPException(400, f"invalid runtime_tier: {req.runtime_tier}")
    cap = Capability(
        name=req.name,
        purpose=req.purpose,
        signature=req.signature,
        category=req.category,
        version=req.version,
        execution_method=req.execution_method,
        security_level=req.security_level,
        runtime_tier=rt,
        inputs=req.inputs,
        outputs=req.outputs,
        dependencies=req.dependencies,
        permissions=req.permissions,
        owner=req.owner,
        tenant_id=req.tenant_id,
    )
    try:
        return get_capability_registry().register(cap).model_dump()
    except Exception as e:
        raise HTTPException(409, str(e))


class LifecycleTransitionRequest(BaseModel):
    to_state: str
    actor: str = "admin"
    reason: str | None = None


class SourceDiscoverRequest(BaseModel):
    url: str
    category: str | None = None


class SourceTransitionRequest(BaseModel):
    to_state: str


class PolicyCreateRequest(BaseModel):
    """Canonical SourcePolicy fields (ROADMAP §8) — matches the engine model."""

    name: str
    scope: str = "domain"
    scope_value: str
    decision: str = "ALLOWLISTED"
    reason: str | None = None
    rate_limit_per_minute: int = 30
    crawl_budget_per_day: int = 500
    requires_approval: bool = False


class PruneLearnedRequest(BaseModel):
    older_than_days: int = 30
    min_relevance: float = 0.1


@router.post("/capabilities/{capability_id}/lifecycle")
def admin_transition_capability(capability_id: str, req: LifecycleTransitionRequest) -> dict:
    try:
        to = CapabilityLifecycleState(req.to_state)
    except ValueError:
        raise HTTPException(400, f"invalid state: {req.to_state}")
    try:
        return (
            get_capability_registry()
            .transition(capability_id, to, actor=req.actor, reason=req.reason)
            .model_dump()
        )
    except Exception as e:
        raise HTTPException(409, str(e))


@router.post("/capabilities/{capability_id}/promote")
def admin_promote_capability(capability_id: str, actor: str = "admin") -> dict:
    try:
        return get_capability_registry().promote(capability_id, actor=actor).model_dump()
    except Exception as e:
        raise HTTPException(409, str(e))


@router.post("/capabilities/{capability_id}/archive")
def admin_archive_capability(capability_id: str, actor: str = "admin") -> dict:
    try:
        return get_capability_registry().archive(capability_id, actor=actor).model_dump()
    except Exception as e:
        raise HTTPException(409, str(e))


class ProposalCreateRequest(BaseModel):
    kind: str
    title: str
    description: str
    priority: str = "MEDIUM"
    risk_level: str = "medium"
    dedup_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    cost_estimate: dict[str, Any] = Field(default_factory=dict)
    proposed_by: str = "system"
    tenant_id: str | None = None


@router.get("/proposals")
def admin_list_proposals(
    kind: str | None = None, priority: str | None = None, limit: int = Query(50, le=200)
) -> list[dict]:
    return [
        p.model_dump()
        for p in get_approval_workflow().list_pending(
            kind=ProposalKind(kind) if kind else None,
            priority=ProposalPriority(priority) if priority else None,
            limit=limit,
        )
    ]


@router.post("/proposals")
def admin_create_proposal(req: ProposalCreateRequest) -> dict:
    try:
        k = ProposalKind(req.kind)
        p = ProposalPriority(req.priority)
    except ValueError as e:
        raise HTTPException(400, str(e))
    prop = ApprovalProposal(
        kind=k,
        title=req.title,
        description=req.description,
        priority=p,
        risk_level=req.risk_level,
        dedup_key=req.dedup_key,
        payload=req.payload,
        evidence=req.evidence,
        cost_estimate=req.cost_estimate,
        proposed_by=req.proposed_by,
        tenant_id=req.tenant_id,
    )
    return get_approval_workflow().propose(prop).model_dump()


class ProposalDecisionRequest(BaseModel):
    decision: str
    resolved_by: str
    reason: str | None = None
    policy_scope: str | None = None
    policy_value: str | None = None


@router.post("/proposals/{proposal_id}/decide")
def admin_decide_proposal(proposal_id: str, req: ProposalDecisionRequest) -> dict:
    try:
        d = ProposalState(req.decision)
    except ValueError:
        raise HTTPException(400, f"invalid decision: {req.decision}")
    if d not in {ProposalState.APPROVED, ProposalState.REJECTED, ProposalState.DEFERRED}:
        raise HTTPException(400, "must be APPROVED/REJECTED/DEFERRED")
    dec = ApprovalDecision(
        proposal_id=proposal_id,
        decision=d,
        resolved_by=req.resolved_by,
        reason=req.reason,
        policy_scope=req.policy_scope,
        policy_value=req.policy_value,
    )
    try:
        return get_approval_workflow().decide(dec).model_dump()
    except Exception as e:
        raise HTTPException(409, str(e))


@router.get("/decisions")
def admin_list_decisions(dedup_key: str | None = None, limit: int = 100) -> list[dict]:
    return get_approval_workflow().list_decisions(dedup_key=dedup_key, limit=limit)


class OpportunityCreateRequest(BaseModel):
    requirement: str
    signal_id: str | None = None
    source_url: str | None = None
    usefulness: str = "unknown"
    feasibility: str = "unknown"
    risk: str = "medium"
    cost: str = "medium"
    maintenance: str = "low"


@router.get("/opportunities")
def admin_list_opportunities(
    stage: str | None = None, limit: int = Query(50, le=200)
) -> list[dict]:
    return [
        o.model_dump()
        for o in get_learning_loop().list_opportunities(
            stage=LearningStage(stage) if stage else None, limit=limit
        )
    ]


@router.post("/opportunities")
def admin_surface_opportunity(req: OpportunityCreateRequest) -> dict:
    opp = LearningOpportunity(
        requirement=req.requirement,
        signal_id=req.signal_id,
        source_url=req.source_url,
        usefulness=req.usefulness,
        feasibility=req.feasibility,
        risk=req.risk,
        cost=req.cost,
        maintenance=req.maintenance,
    )
    return get_learning_loop().surface_opportunity(opp).model_dump()


class OpportunityAdvanceRequest(BaseModel):
    to_stage: str
    note: str | None = None


@router.post("/opportunities/{opportunity_id}/advance")
def admin_advance_opportunity(opportunity_id: str, req: OpportunityAdvanceRequest) -> dict:
    try:
        s = LearningStage(req.to_stage)
    except ValueError:
        raise HTTPException(400, f"invalid stage: {req.to_stage}")
    return get_learning_loop().advance_stage(opportunity_id, s).model_dump()


# --- 2.4.3 Sources (SO1–SO4) -------------------------------------------


@router.get("/sources")
def admin_list_sources(
    state: str | None = None,
    category: str | None = None,
    limit: int = Query(200, le=500),
) -> list[dict]:
    """SO1 — list discovered sources."""
    return get_source_governance().list_sources(state=state, category=category, limit=limit)


@router.post("/sources/discover", status_code=201)
def admin_discover_source(req: SourceDiscoverRequest) -> dict:
    """SO2 — record a discovered URL; policy match auto-applies its decision."""
    cat: SourceCategory | None = None
    if req.category:
        try:
            cat = SourceCategory(req.category)
        except ValueError as e:
            raise HTTPException(400, f"invalid category: {req.category}") from e
    return get_source_governance().discover(req.url, category=cat)


@router.post("/sources/{source_id}/transition")
def admin_transition_source(source_id: str, req: SourceTransitionRequest) -> dict:
    """SO3 — transition source state along the ROADMAP §8 lifecycle."""
    try:
        to = SourceState(req.to_state)
    except ValueError as e:
        raise HTTPException(400, f"invalid state: {req.to_state}") from e
    if get_source_governance().get_source(source_id) is None:
        raise HTTPException(404, f"source not found: {source_id}")
    try:
        return get_source_governance().transition_source(source_id, to)
    except Exception as e:
        raise HTTPException(409, str(e)) from e


@router.get("/sources/{source_id}")
def admin_get_source(source_id: str) -> dict:
    """SO4 — get one source with full metadata."""
    src = get_source_governance().get_source(source_id)
    if src is None:
        raise HTTPException(404, f"source not found: {source_id}")
    return src


# --- 2.4.4 Source Policies (SP1–SP4) ------------------------------------


@router.get("/policies")
def admin_list_policies(limit: int = Query(200, le=500)) -> list[dict]:
    """SP1 — list source policies."""
    return [p.model_dump() for p in get_source_governance().list_policies(limit=limit)]


@router.post("/policies", status_code=201)
def admin_create_policy(req: PolicyCreateRequest) -> dict:
    """SP2 — create a source policy (canonical engine shape)."""
    try:
        decision = SourceState(req.decision)
    except ValueError as e:
        raise HTTPException(400, f"invalid decision state: {req.decision}") from e
    policy = SourcePolicy(
        name=req.name,
        scope=req.scope,
        scope_value=req.scope_value,
        decision=decision,
        reason=req.reason,
        rate_limit_per_minute=req.rate_limit_per_minute,
        crawl_budget_per_day=req.crawl_budget_per_day,
        requires_approval=req.requires_approval,
    )
    try:
        return get_source_governance().add_policy(policy).model_dump()
    except Exception as e:
        raise HTTPException(409, str(e)) from e


@router.delete("/policies/{policy_id}")
def admin_delete_policy(policy_id: str) -> dict:
    """SP3 — delete a source policy."""
    if not get_source_governance().delete_policy(policy_id):
        raise HTTPException(404, f"policy not found: {policy_id}")
    return {"ok": True, "policy_id": policy_id}


@router.get("/policies/match")
def admin_match_policy(url: str = Query(...)) -> dict:
    """SP4 — test-match a URL against policies (domain scope)."""
    from urllib.parse import urlparse

    gov = get_source_governance()
    netloc = urlparse(url).netloc.lower().removeprefix("www.")
    policy = gov.match_policy(domain=netloc) if netloc else None
    return {
        "url": url,
        "matched": policy is not None,
        "policy": policy.model_dump() if policy is not None else None,
    }


# --- 2.4.5 Learned Items (LE1–LE3) ---------------------------------------


@router.get("/learned")
def admin_list_learned(
    source_type: str | None = None,
    min_confidence: float = 0.0,
    min_relevance: float = 0.0,
    limit: int = Query(100, le=500),
) -> list[dict]:
    """LE1 — list learned items with provenance (ROADMAP §10)."""
    st: SourceCategory | None = None
    if source_type:
        try:
            st = SourceCategory(source_type)
        except ValueError as e:
            raise HTTPException(400, f"invalid source_type: {source_type}") from e
    items = get_source_governance().list_learned(
        min_confidence=min_confidence,
        min_relevance=min_relevance,
        source_type=st,
        limit=limit,
    )
    return [i.model_dump() for i in items]


@router.post("/learned/prune")
def admin_prune_learned(req: PruneLearnedRequest) -> dict:
    """LE2 — prune low-value learned items (ROADMAP §56)."""
    n = get_source_governance().prune_low_value(
        older_than_days=req.older_than_days,
        min_relevance=req.min_relevance,
    )
    return {"pruned_count": n}


@router.delete("/learned/{item_id}")
def admin_delete_learned(item_id: str) -> dict:
    """LE3 — hard-delete a learned item."""
    if not get_source_governance().delete_learned(item_id):
        raise HTTPException(404, f"learned item not found: {item_id}")
    return {"ok": True, "item_id": item_id}


# --- 2.4.6 Proposal decision history (PR4) -------------------------------


@router.get("/proposals/{proposal_id}/decisions")
def admin_list_proposal_decisions(proposal_id: str) -> list[dict]:
    """PR4 — decision memory rows for one proposal."""
    return get_approval_workflow().list_decisions(proposal_id=proposal_id)


# --- 2.4.7 Governance (GO1–GO2) ------------------------------------------


@router.get("/governance/decisions")
def admin_governance_decisions(
    action: str | None = None, limit: int = Query(100, le=500)
) -> list[dict]:
    """GO1 — recent authz decisions (newest first)."""
    return get_governance_engine().list_decisions(action=action, limit=limit)


@router.get("/governance/budgets")
def admin_governance_budgets() -> list[dict]:
    """GO2 — current budget state per BudgetKind."""
    return get_governance_engine().budget_summary()


# --- 2.4.8 Capability delete (C5) -----------------------------------------


@router.delete("/capabilities/{capability_id}")
def admin_delete_capability(capability_id: str) -> dict:
    """C5 — hard-delete an ARCHIVED capability (honest lifecycle contract)."""
    try:
        ok = get_capability_registry().delete(capability_id)
    except CapabilityStateError as e:
        raise HTTPException(409, str(e)) from e
    if not ok:
        raise HTTPException(404, f"capability not found: {capability_id}")
    return {"ok": True, "capability_id": capability_id}


@router.get("/overview")
def admin_overview() -> dict:
    caps = get_capability_registry().list(limit=500)
    pending = get_approval_workflow().list_pending(limit=50)
    opps = get_learning_loop().list_opportunities(limit=50)
    escalated = get_task_engine().list(state=TaskState.ESCALATED, limit=20)
    return {
        "capabilities": {
            "total": len(caps),
            "active": sum(1 for c in caps if c.lifecycle_state == CapabilityLifecycleState.ACTIVE),
            "archived": sum(
                1 for c in caps if c.lifecycle_state == CapabilityLifecycleState.ARCHIVED
            ),
        },
        "approvals_pending": len(pending),
        "learning_opportunities": {
            "total": len(opps),
            "awaiting_approval": sum(1 for o in opps if o.stage == LearningStage.AWAITING_APPROVAL),
        },
        "escalated_tasks": len(escalated),
    }


__all__ = ["router"]
