"""Admin API routes for managing crawl policies, rules, and inspecting crawl history.

SECURITY FIX (AUDIT-SEC-6, HIGH): আগে এই admin router-এ কোনো auth guard ছিল না —
রেজিস্ট্রির is_admin=True শুধু get_current_user_token যোগ করত, অর্থাৎ যেকোনো
সাধারণ ইউজার সব টেন্যান্টের crawl policy তৈরি/বদলাতে পারত। এখন router-level
get_current_admin guard বাধ্যতামূলক।

MASTER_PLAN Phase 1 ("Scout goes live"): আগে policy/history ছিল in-memory —
restart মানেই সব governance state হারানো এবং GET /events ছিল hardcoded placeholder
(stub)। এখন সব state scout/persistence.py দিয়ে durable থাকে (DB-first,
memory-fallback = Graceful Degradation), এবং সম্পূর্ণ CRUD surface যোগ হয়েছে
(specs/002 contracts/crawler-admin-api.yaml অনুযায়ী):
  PATCH /policies/{id}            — partial update
  POST  /policies/{id}/enable     — is_active=true (governed crawl-এর পূর্বশর্ত)
  POST  /policies/{id}/disable    — fail-closed toggle
  DELETE /policies/{id}           — policy মুছে ফেলা
  GET   /events                   — সত্যিকারের telemetry (আর placeholder নয়)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.dependencies import get_project_admin
from core.logging_config import logger
from scout import persistence
from scout.models import CrawlHistoryRecord, CrawlPolicy, DomainRule, TrustLevel

router = APIRouter(
    prefix="/api/v1/admin/crawler",
    tags=["crawler-admin"],
    dependencies=[Depends(get_project_admin)],
)


class PolicyCreatePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    is_active: bool = True
    max_depth: int = Field(default=2, ge=1, le=5)
    max_results: int = Field(default=10, ge=1, le=50)
    default_rate_limit_per_min: int = Field(default=30, ge=1, le=600)
    allowed_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    domain_rules: list[DomainRule] = Field(default_factory=list)


class PolicyUpdatePayload(BaseModel):
    """Partial update — শুধু পাঠানো ফিল্ড বদলায় (None = unchanged)।"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
    max_depth: int | None = Field(default=None, ge=1, le=5)
    max_results: int | None = Field(default=None, ge=1, le=50)
    default_rate_limit_per_min: int | None = Field(default=None, ge=1, le=600)
    allowed_domains: list[str] | None = None
    blocked_domains: list[str] | None = None
    domain_rules: list[DomainRule] | None = None


def _apply_update(policy: CrawlPolicy, payload: PolicyUpdatePayload) -> CrawlPolicy:
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in data.items():
        setattr(policy, key, value)
    return policy


@router.get("/policies", response_model=list[CrawlPolicy])
async def list_policies(user: dict = Depends(get_project_admin)) -> list[CrawlPolicy]:
    """Lists all crawl policies for the tenant (durable; DB-first)."""
    tenant_id = user["tenant_id"]
    policies = await persistence.list_policies(tenant_id)
    if not policies:
        # বাংলা: প্রথমবার এলে ডিফল্ট policy seed করে রাখা হয় — পরের বার থেকে
        # টেন্যান্ট নিজের policy সম্পূর্ণভাবে CRUD করতে পারে।
        default_pol = CrawlPolicy(tenant_id=tenant_id, name="Default Policy")
        try:
            await persistence.upsert_policy(default_pol)
        except Exception:
            # Seed failure stays non-fatal (next create retries), but it must
            # be observable — the old bare `except: pass` swallowed DB outages
            # silently, so a broken persistence layer looked like a fresh
            # tenant on every request.
            logger.warning(
                "Crawl policy seed failed for tenant %s; returning in-memory "
                "default. Will retry on next create.",
                tenant_id,
                exc_info=True,
            )
        policies = [default_pol]
    return policies


@router.post("/policies", response_model=CrawlPolicy, status_code=status.HTTP_201_CREATED)
async def create_or_update_policy(
    payload: PolicyCreatePayload, user: dict = Depends(get_project_admin)
) -> CrawlPolicy:
    """Creates a new crawl policy (durable, tenant-scoped)."""
    tenant_id = user["tenant_id"]
    existing = await persistence.list_policies(tenant_id)
    if len(existing) >= 50:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Policy limit reached for tenant; delete old policies first",
        )
    new_policy = CrawlPolicy(
        tenant_id=tenant_id,
        name=payload.name,
        is_active=payload.is_active,
        max_depth=payload.max_depth,
        max_results=payload.max_results,
        default_rate_limit_per_min=payload.default_rate_limit_per_min,
        allowed_domains=payload.allowed_domains,
        blocked_domains=payload.blocked_domains,
        domain_rules=payload.domain_rules,
    )
    try:
        await persistence.upsert_policy(new_policy)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    return new_policy


@router.patch("/policies/{policy_id}", response_model=CrawlPolicy)
async def update_policy(
    policy_id: str,
    payload: PolicyUpdatePayload,
    user: dict = Depends(get_project_admin),
) -> CrawlPolicy:
    """Partial update of a crawl policy (name, limits, domain rules, active flag)."""
    tenant_id = user["tenant_id"]
    policy = await persistence.get_policy(policy_id, tenant_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    updated = _apply_update(policy, payload)
    try:
        await persistence.upsert_policy(updated)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    return updated


@router.post("/policies/{policy_id}/enable", response_model=CrawlPolicy)
async def enable_policy(policy_id: str, user: dict = Depends(get_project_admin)) -> CrawlPolicy:
    """Activates a policy — governed scout crawl এই policy-ই follow করবে।"""
    return await _set_policy_active(policy_id, user, True)


@router.post("/policies/{policy_id}/disable", response_model=CrawlPolicy)
async def disable_policy(policy_id: str, user: dict = Depends(get_project_admin)) -> CrawlPolicy:
    """Deactivates a policy — fail-closed: inactive policy কিছুই authorize করে না।"""
    return await _set_policy_active(policy_id, user, False)


async def _set_policy_active(policy_id: str, user: dict, active: bool) -> CrawlPolicy:
    tenant_id = user["tenant_id"]
    policy = await persistence.get_policy(policy_id, tenant_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    policy.is_active = active
    await persistence.upsert_policy(policy)
    return policy


@router.delete("/policies/{policy_id}", status_code=status.HTTP_200_OK)
async def delete_policy(policy_id: str, user: dict = Depends(get_project_admin)) -> dict[str, Any]:
    """Deletes a crawl policy (tenant-scoped, hard delete)."""
    tenant_id = user["tenant_id"]
    deleted = await persistence.delete_policy(policy_id, tenant_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return {"status": "deleted", "policy_id": policy_id, "tenant_id": tenant_id}


@router.get("/history", response_model=list[CrawlHistoryRecord])
async def get_crawl_history(
    task_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_project_admin),
) -> list[CrawlHistoryRecord]:
    """Retrieves durable crawl execution records (real data recorded by scout runs)."""
    tenant_id = user["tenant_id"]
    return await persistence.list_history(tenant_id, task_id=task_id, limit=limit)


@router.get("/events")
async def get_crawl_events(
    task_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(get_project_admin),
) -> list[dict[str, Any]]:
    """Retrieves real crawl telemetry events (previously a hardcoded stub)."""
    tenant_id = user["tenant_id"]
    return await persistence.list_events(
        tenant_id, task_id=task_id, event_type=event_type, limit=limit
    )
