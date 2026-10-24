"""Standalone ecosystem API server — 47 endpoints, multi-user, stdlib-only auth.

বাংলা: এই ফাইলটি গোটা ecosystem surface এক জায়গায় নিয়ে আসে।
- Auth (7 endpoints): register / login / me / logout / refresh / list-users / set-role.
- Public ecosystem (11 endpoints): health, capabilities, tasks (optional-auth scoping),
  resources, ecosystem-health, deployments, deployment trace, mcp manifest.
- User-authenticated (4 endpoints): submit task, cancel task, SSE task events, MCP call.
- Admin (25 endpoints): capabilities CRUD + lifecycle, proposals + decisions,
  sources + source policies + learned items + opportunities + governance + overview.

All signatures match the ACTUAL module APIs (not the buggy `api/routes/ecosystem*.py`).
Bugs B1–B12 from `ecosystem_plan.md` §1.3 are fixed inline.

Auth is stdlib-only (PBKDF2 + HMAC-SHA256 JWT). No bcrypt / PyJWT dependency.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure backend/ is on sys.path so ``import ecosystem`` works regardless of CWD.
_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from adaptive_engine._store import ensure_columns, get_conn, jdump, jload
from adaptive_engine.approval_workflow import ApprovalDecision
from adaptive_engine.governance import BudgetKind
from ecosystem import (
    ApprovalProposal,
    Capability,
    CapabilityLifecycleState,
    CapabilityRuntimeTier,
    DeploymentStatus,
    LearningOpportunity,
    LearningStage,
    MCPOperationCategory,
    ProposalKind,
    ProposalPriority,
    ProposalState,
    ProviderKind,
    ResourceRecord,
    ResourceState,
    SourceCategory,
    SourcePolicy,
    SourceState,
    TaskOwner,
    TaskRecord,
    TaskState,
    get_approval_workflow,
    get_capability_registry,
    get_deployment_tracker,
    get_governance_engine,
    get_health_aggregator,
    get_learning_loop,
    get_mcp_skeleton,
    get_resource_registry,
    get_source_governance,
    get_task_engine,
)
from ecosystem.users import (
    User,
    UserExistsError,
    UserNotFoundError,
    UserRole,
    get_session_store,
    get_user_store,
)

# ---------------------------------------------------------------------------
# Constants + env knobs
# ---------------------------------------------------------------------------

_START_TIME = time.time()
_VERSION = "1.0.0"

_REQUIRE_AUTH = os.getenv("ECOSYSTEM_REQUIRE_AUTH", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_ALLOW_DELETE = os.getenv("ECOSYSTEM_ALLOW_DELETE", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_ALLOW_SIGNUP = os.getenv("ECOSYSTEM_ALLOW_SIGNUP", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


# ---------------------------------------------------------------------------
# Lifespan — initialize engines + ensure schemas + seed
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Initialize all engine singletons (idempotent CREATE TABLE).
    get_task_engine()
    get_capability_registry()
    get_resource_registry()
    get_approval_workflow()
    get_governance_engine()
    get_health_aggregator()
    get_deployment_tracker()
    get_learning_loop()
    get_source_governance()
    get_mcp_skeleton()

    # Add user_id / user_email columns to ecosystem_tasks (idempotent — §3.3).
    with get_conn() as conn:
        ensure_columns(
            conn,
            "ecosystem_tasks",
            {
                "user_id": "ALTER TABLE ecosystem_tasks ADD COLUMN user_id TEXT",
                "user_email": "ALTER TABLE ecosystem_tasks ADD COLUMN user_email TEXT",
            },
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ecosystem_tasks_user ON ecosystem_tasks(user_id)"
        )
        conn.commit()

    # Multi-user auth tables.
    from ecosystem.users import ensure_users_schema

    ensure_users_schema()

    # Seed demo data (B12 fix — seed now lives in ecosystem/, not backend/scripts/).
    try:
        from ecosystem.seed_ecosystem import (
            seed_capabilities,
            seed_learned,
            seed_opportunities,
            seed_policies,
            seed_proposals,
        )

        seed_capabilities()
        seed_policies()
        seed_learned()
        seed_opportunities()
        seed_proposals()
        print("[ecosystem] seed complete", flush=True)
    except Exception as exc:  # pragma: no cover — defensive
        print(f"[ecosystem] seed failed: {exc}", flush=True)

    yield


# ---------------------------------------------------------------------------
# FastAPI app + middleware
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SupremeAI Ecosystem",
    version=_VERSION,
    description="Standalone ecosystem API — 47 endpoints, multi-user, stdlib auth.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
        "apikey",
        "X-Ecosystem-Token",
    ],
    expose_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth helpers (Bearer token via Authorization header)
# ---------------------------------------------------------------------------


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
        return None
    return authorization[7:].strip() or None


def _optional_user(request: Request) -> User | None:
    """Resolve the user from the Bearer token, or return None if absent/invalid."""
    tok = _extract_bearer(request.headers.get("Authorization"))
    if not tok:
        return None
    sess = get_session_store().validate(tok)
    return sess.user if sess else None


def _require_user(request: Request) -> User:
    user = _optional_user(request)
    if user is None:
        raise HTTPException(401, "authentication required")
    return user


def _require_admin(request: Request) -> User:
    user = _require_user(request)
    if user.role != UserRole.ADMIN:
        raise HTTPException(403, "admin role required")
    return user


def _dump(model: BaseModel | None) -> dict[str, Any] | None:
    """Pydantic model → dict with enums serialized as their values."""
    if model is None:
        return None
    return model.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Request models — Auth
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class RoleUpdateRequest(BaseModel):
    role: UserRole


# ---------------------------------------------------------------------------
# Request models — Public / User ecosystem
# ---------------------------------------------------------------------------


class CapabilitySearchRequest(BaseModel):
    requirement: str
    signature_hint: str | None = None
    limit: int = 10


class TaskSubmitRequest(BaseModel):
    goal: str
    success_criteria: dict[str, Any] = Field(default_factory=dict)
    capability_requirements: list[dict[str, Any]] = Field(default_factory=list)
    risk_level: str = "LOW"
    tenant_id: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)


class TaskCancelRequest(BaseModel):
    reason: str | None = None


class McpCallRequest(BaseModel):
    operation: str
    params: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Request models — Admin
# ---------------------------------------------------------------------------


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


class LifecycleTransitionRequest(BaseModel):
    to_state: str
    actor: str = "admin"


class ProposalCreateRequest(BaseModel):
    kind: str
    title: str
    summary: str = ""
    priority: str = "MEDIUM"
    risk_level: str = "MEDIUM"
    payload: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str | None = None
    requested_by: str | None = None  # defaults to the authenticated admin's email


class ProposalDecisionRequest(BaseModel):
    decision: str  # APPROVED | REJECTED | DEFERRED
    decided_by: str
    rationale: str = ""


class OpportunityCreateRequest(BaseModel):
    capability_hint: str
    gap_description: str = ""
    signal_id: str | None = None
    predicted_value: float = 0.0
    predicted_effort: float = 0.0


class OpportunityAdvanceRequest(BaseModel):
    to_stage: str
    proposal_id: str | None = None


class SourceDiscoverRequest(BaseModel):
    url: str
    category: str | None = None


class SourceTransitionRequest(BaseModel):
    to_state: str


class PolicyCreateRequest(BaseModel):
    url_pattern: str
    category: str = "UNKNOWN"
    state: str = "UNKNOWN"
    allowed_actions: list[str] = Field(default_factory=lambda: ["read"])
    source_weight: float = 1.0
    expires_at: str | None = None


class PruneLearnedRequest(BaseModel):
    threshold: float = 0.1
    max_age_days: int = 30


# ---------------------------------------------------------------------------
# Direct-SQL helpers — for things the registries don't expose
# ---------------------------------------------------------------------------


def _task_row_to_dict(r: Any) -> dict[str, Any]:
    """Build a JSON-friendly dict from a raw ecosystem_tasks row."""
    return {
        "task_id": r["task_id"],
        "goal": r["goal"],
        "owner": r["owner"],
        "scope": jload(r["scope"], {}),
        "state": r["state"],
        "plan": jload(r["plan"], {}),
        "capability_requirements": jload(r["capability_requirements"], []),
        "resource_id": r["resource_id"],
        "capability_id": r["capability_id"],
        "artifacts": jload(r["artifacts"], []),
        "result": jload(r["result"], {}),
        "success_criteria": jload(r["success_criteria"], {}),
        "verification_result": jload(r["verification_result"], {}),
        "retry_count": int(r["retry_count"] or 0),
        "retry_limit": int(r["retry_limit"] or 3),
        "time_limit_seconds": r["time_limit_seconds"],
        "risk_level": r["risk_level"],
        "correlation": jload(r["correlation"], {}),
        "created_by": r["created_by"],
        "tenant_id": r["tenant_id"],
        "audit_id": r["audit_id"],
        "error": r["error"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "started_at": r["started_at"],
        "completed_at": r["completed_at"],
        "user_id": r["user_id"] if "user_id" in r else None,
        "user_email": r["user_email"] if "user_email" in r else None,
    }


def _list_tasks_filtered(
    *,
    user_id: str | None = None,
    state: str | None = None,
    owner: str | None = None,
    tenant_id: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    clauses, params = [], []
    if user_id:
        clauses.append("user_id=?")
        params.append(user_id)
    if state:
        clauses.append("state=?")
        params.append(state)
    if owner:
        clauses.append("owner=?")
        params.append(owner)
    if tenant_id:
        clauses.append("tenant_id=?")
        params.append(tenant_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM ecosystem_tasks {where} ORDER BY created_at DESC LIMIT ?", params
        ).fetchall()
    return [_task_row_to_dict(r) for r in rows]


def _get_task_row(task_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM ecosystem_tasks WHERE task_id=?", (task_id,)).fetchone()
    return _task_row_to_dict(r) if r else None


def _attach_user_to_task(task_id: str, user: User) -> None:
    """Set user_id / user_email on a freshly-submitted task row."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE ecosystem_tasks SET user_id=?, user_email=? WHERE task_id=?",
            (user.user_id, user.email, task_id),
        )
        conn.commit()


def _list_sources(
    *, state: str | None = None, category: str | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    clauses, params = [], []
    if state:
        clauses.append("state=?")
        params.append(state)
    if category:
        clauses.append("category=?")
        params.append(category)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM ecosystem_sources {where} ORDER BY first_seen_at DESC LIMIT ?", params
        ).fetchall()
    return [
        {
            "source_id": r["source_id"],
            "url": r["url"],
            "category": r["category"],
            "state": r["state"],
            "first_seen_at": r["first_seen_at"],
            "last_seen_at": r["last_seen_at"],
            "metadata": jload(r["metadata"], {}),
        }
        for r in rows
    ]


def _get_source(source_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM ecosystem_sources WHERE source_id=?", (source_id,)
        ).fetchone()
    if not r:
        return None
    return {
        "source_id": r["source_id"],
        "url": r["url"],
        "category": r["category"],
        "state": r["state"],
        "first_seen_at": r["first_seen_at"],
        "last_seen_at": r["last_seen_at"],
        "metadata": jload(r["metadata"], {}),
    }


def _list_policies(limit: int = 200) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM ecosystem_source_policies ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "policy_id": r["policy_id"],
            "url_pattern": r["url_pattern"],
            "category": r["category"],
            "state": r["state"],
            "allowed_actions": jload(r["allowed_actions"], []),
            "source_weight": float(r["source_weight"] or 1.0),
            "expires_at": r["expires_at"],
            "created_by": r["created_by"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def _delete_policy(policy_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM ecosystem_source_policies WHERE policy_id=?", (policy_id,))
        conn.commit()
        return cur.rowcount > 0


def _delete_learned(item_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM ecosystem_learned_items WHERE item_id=?", (item_id,))
        conn.commit()
        return cur.rowcount > 0


def _list_governance_decisions(
    *, actor: str | None = None, operation: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    clauses, params = [], []
    if actor:
        # No actor column — but correlation / reason may reference. Match on reason prefix.
        clauses.append("reason LIKE ?")
        params.append(f"%{actor}%")
    if operation:
        clauses.append("action=?")
        params.append(operation)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM ecosystem_governance_decisions {where} "
            "ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
    return [
        {
            "decision_id": r["decision_id"],
            "action": r["action"],
            "risk_level": r["risk_level"],
            "allowed": bool(r["allowed"]),
            "budget_check_passed": bool(r["budget_check_passed"]),
            "requires_approval": bool(r["requires_approval"]),
            "reason": r["reason"],
            "budget_used": jload(r["budget_used"], {}),
            "remaining_budget": jload(r["remaining_budget"], {}),
            "correlation": jload(r["correlation"], {}),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def _dep_row_to_dict(r: Any) -> dict[str, Any]:
    return {
        "deployment_id": r["deployment_id"],
        "resource_id": r["resource_id"],
        "commit_sha": r["commit_sha"],
        "branch": r["branch"],
        "version": r["version"],
        "status": r["status"],
        "started_by": r["started_by"],
        "correlation": jload(r["correlation"], {}),
        "started_at": r["started_at"],
        "finished_at": r["finished_at"],
        "log_url": r["log_url"],
        "rollback_of": r["rollback_of"],
        "notes": r["notes"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }


# ===========================================================================
#  AUTH ENDPOINTS  (A1–A7)  — 7 endpoints
# ===========================================================================


@app.post("/api/v1/auth/register", status_code=201, tags=["auth"])
def auth_register(req: RegisterRequest) -> dict[str, Any]:
    """A1 — register a new user. First user becomes admin. Returns ``{user, token}``."""
    if not _ALLOW_SIGNUP:
        raise HTTPException(403, "signup disabled (ECOSYSTEM_ALLOW_SIGNUP=false)")
    store = get_user_store()
    try:
        user = store.register(req.email, req.password, req.name)
    except UserExistsError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.touch_last_login(user.user_id)
    token, sess = get_session_store().issue(user)
    return {"user": _dump(user), "token": token, "session_id": sess.session_id}


@app.post("/api/v1/auth/login", tags=["auth"])
def auth_login(req: LoginRequest) -> dict[str, Any]:
    """A2 — email + password login. Returns ``{user, token}``."""
    store = get_user_store()
    user = store.authenticate(req.email, req.password)
    if user is None:
        raise HTTPException(401, "invalid email or password")
    store.touch_last_login(user.user_id)
    token, sess = get_session_store().issue(user)
    return {"user": _dump(user), "token": token, "session_id": sess.session_id}


@app.get("/api/v1/auth/me", tags=["auth"])
def auth_me(user: User = Depends(_require_user)) -> dict[str, Any]:
    """A3 — return the current user profile."""
    return _dump(user)  # type: ignore[return-value]


@app.post("/api/v1/auth/logout", tags=["auth"])
def auth_logout(user: User = Depends(_require_user), request: Request = None) -> dict[str, Any]:
    """A4 — invalidate the current session."""
    tok = _extract_bearer(request.headers.get("Authorization"))  # type: ignore[union-attr]
    if tok:
        get_session_store().revoke_by_token(tok)
    return {"ok": True}


@app.post("/api/v1/auth/refresh", tags=["auth"])
def auth_refresh(user: User = Depends(_require_user), request: Request = None) -> dict[str, Any]:
    """A7 — rotate the current session and return a fresh token."""
    tok = _extract_bearer(request.headers.get("Authorization"))  # type: ignore[union-attr]
    if not tok:
        raise HTTPException(401, "missing token")
    refreshed = get_session_store().refresh(tok)
    if refreshed is None:
        raise HTTPException(401, "session not refreshable")
    new_token, _sess = refreshed
    return {"token": new_token}


@app.get("/api/v1/auth/users", tags=["auth"])
def auth_list_users(_: User = Depends(_require_admin)) -> list[dict[str, Any]]:
    """A5 — list all users (admin only)."""
    return [_dump(u) for u in get_user_store().list_users()]  # type: ignore[list-item]


@app.patch("/api/v1/auth/users/{user_id}/role", tags=["auth"])
def auth_set_role(
    user_id: str, req: RoleUpdateRequest, _: User = Depends(_require_admin)
) -> dict[str, Any]:
    """A6 — promote/demote a user (admin only)."""
    try:
        user = get_user_store().set_role(user_id, req.role)
    except UserNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _dump(user)  # type: ignore[return-value]


# ===========================================================================
#  PUBLIC ECOSYSTEM ENDPOINTS  (P1–P11)  — 11 endpoints
# ===========================================================================


@app.get("/health", tags=["public"])
def health() -> dict[str, Any]:
    """P1 — app-level health."""
    return {
        "status": "ok",
        "service": "supremeai-ecosystem",
        "version": _VERSION,
        "uptime": round(time.time() - _START_TIME, 2),
    }


@app.get("/api/v1/ecosystem/capabilities", tags=["public"])
def list_capabilities(
    state: str | None = None,
    category: str | None = None,
    limit: int = Query(200, le=500),
) -> list[dict[str, Any]]:
    """P2 — list capabilities."""
    caps = get_capability_registry().list(
        state=CapabilityLifecycleState(state) if state else None,
        category=category,
        limit=limit,
    )
    return [_dump(c) for c in caps]  # type: ignore[list-item]


@app.post("/api/v1/ecosystem/capabilities/search", tags=["public"])
def search_capabilities(req: CapabilitySearchRequest) -> dict[str, Any]:
    """P3 — REUSE > ADAPT > EXTEND > CREATE search (B4 fix: no category_hint)."""
    caps = get_capability_registry().search(
        req.requirement,
        signature_hint=req.signature_hint,
        limit=req.limit,
    )
    return {
        "requirement": req.requirement,
        "candidates": [_dump(c) for c in caps],
        "rule": "REUSE > ADAPT > EXTEND > CREATE",
        "gap_detected": len(caps) == 0,
    }


@app.get("/api/v1/ecosystem/capabilities/{capability_id}", tags=["public"])
def get_capability(capability_id: str) -> dict[str, Any]:
    """P4 — get one capability. 404 if missing."""
    c = get_capability_registry().get(capability_id)
    if c is None:
        raise HTTPException(404, f"capability not found: {capability_id}")
    return _dump(c)  # type: ignore[return-value]


@app.get("/api/v1/ecosystem/tasks", tags=["public"])
def list_tasks(
    state: str | None = None,
    owner: str | None = None,
    user_id: str | None = None,
    limit: int = Query(200, le=500),
    request: Request = None,
) -> list[dict[str, Any]]:
    """P5 — list tasks (PUBLIC* — authed non-admins see only their own)."""
    caller = _optional_user(request)  # type: ignore[arg-type]
    if caller is None:
        # Anonymous.
        if _REQUIRE_AUTH:
            raise HTTPException(401, "authentication required")
        # Legacy mode: return all.
        return _list_tasks_filtered(state=state, owner=owner, user_id=user_id, limit=limit)
    # Authed caller.
    if caller.role == UserRole.ADMIN:
        return _list_tasks_filtered(state=state, owner=owner, user_id=user_id, limit=limit)
    # Non-admin — restrict to own tasks.
    return _list_tasks_filtered(state=state, owner=owner, user_id=caller.user_id, limit=limit)


@app.get("/api/v1/ecosystem/tasks/{task_id}", tags=["public"])
def get_task(task_id: str, request: Request = None) -> dict[str, Any]:
    """P6 — get one task (non-admins can only fetch their own — 404 otherwise)."""
    row = _get_task_row(task_id)
    if row is None:
        raise HTTPException(404, f"task not found: {task_id}")
    caller = _optional_user(request)  # type: ignore[arg-type]
    if caller is None:
        if _REQUIRE_AUTH:
            raise HTTPException(404, f"task not found: {task_id}")
        return row
    if caller.role != UserRole.ADMIN and row.get("user_id") != caller.user_id:
        # Don't leak existence.
        raise HTTPException(404, f"task not found: {task_id}")
    return row


@app.get("/api/v1/ecosystem/resources", tags=["public"])
def list_resources(
    provider: str | None = None,
    environment: str | None = None,
    state: str | None = None,
    limit: int = Query(200, le=500),
) -> list[dict[str, Any]]:
    """P7 — list resources. (``environment`` is filtered in-memory — ResourceRegistry.list ignores it.)"""
    items = get_resource_registry().list(
        provider=ProviderKind(provider) if provider else None,
        state=ResourceState(state) if state else None,
        limit=limit,
    )
    if environment:
        items = [r for r in items if (r.metadata or {}).get("environment") == environment]
    return [_dump(r) for r in items]  # type: ignore[list-item]


@app.get("/api/v1/ecosystem/health", tags=["public"])
def ecosystem_health() -> dict[str, Any]:
    """P8 — ecosystem composite health."""
    agg = get_health_aggregator()
    return {
        "composite": str(agg.composite_status()),
        "resources": [_dump(h) for h in agg.all_latest()],
        "top_memory": [_dump(h) for h in agg.top_memory_consumers(limit=5)],
    }


@app.get("/api/v1/ecosystem/deployments", tags=["public"])
def list_deployments(
    resource_id: str | None = None,
    commit_sha: str | None = None,
    limit: int = Query(50, le=200),
) -> list[dict[str, Any]]:
    """P9 — list deployments."""
    dt = get_deployment_tracker()
    if commit_sha:
        return [_dump(d) for d in dt.list_by_commit(commit_sha, limit=limit)]  # type: ignore[list-item]
    if resource_id:
        return [_dump(d) for d in dt.list_by_resource(resource_id, limit=limit)]  # type: ignore[list-item]
    # No filter → return most recent deployments across all resources.
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM ecosystem_deployments ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_dep_row_to_dict(r) for r in rows]


@app.get("/api/v1/ecosystem/deployments/trace/{commit_sha}", tags=["public"])
def trace_commit(commit_sha: str) -> dict[str, Any]:
    """P10 — deployment trace for a commit (B-fix: list_by_commit, not buggy .trace())."""
    deps = get_deployment_tracker().list_by_commit(commit_sha)
    return {
        "commit_sha": commit_sha,
        "deployments": [_dump(d) for d in deps],
        "count": len(deps),
    }


@app.get("/api/v1/ecosystem/mcp/manifest", tags=["public"])
def mcp_manifest() -> dict[str, Any]:
    """P11 — MCP operations manifest."""
    mcp = get_mcp_skeleton()
    ops = mcp.list_operations()
    cats = sorted({op["category"] for op in ops})
    return {
        "operations": ops,
        "categories": cats,
        "count": len(ops),
    }


# ===========================================================================
#  USER-AUTHENTICATED ENDPOINTS  (U1–U4)  — 4 endpoints
# ===========================================================================


@app.post("/api/v1/ecosystem/tasks", status_code=201, tags=["user"])
def submit_task(
    req: TaskSubmitRequest,
    user: User = Depends(_require_user),
) -> dict[str, Any]:
    """U1 — submit a task. ``created_by`` is forced to the caller's email; ``user_id`` injected."""
    record = TaskRecord(
        goal=req.goal,
        owner=TaskOwner.USER,
        scope=req.scope,
        success_criteria=req.success_criteria,
        capability_requirements=req.capability_requirements,
        risk_level=(req.risk_level or "LOW").upper(),
        tenant_id=req.tenant_id,
        created_by=user.email,
    )
    submitted = get_task_engine().submit(record)  # B1 fix — submit(TaskRecord).
    _attach_user_to_task(submitted.task_id, user)  # §3.3 user_id isolation.
    row = _get_task_row(submitted.task_id)
    return row or _dump(submitted)  # type: ignore[return-value]


@app.post("/api/v1/ecosystem/tasks/{task_id}/cancel", tags=["user"])
def cancel_task(
    task_id: str,
    req: TaskCancelRequest,
    user: User = Depends(_require_user),
) -> dict[str, Any]:
    """U2 — cancel a task. Caller must own it (or be admin)."""
    row = _get_task_row(task_id)
    if row is None:
        raise HTTPException(404, f"task not found: {task_id}")
    if user.role != UserRole.ADMIN and row.get("user_id") != user.user_id:
        raise HTTPException(404, f"task not found: {task_id}")
    try:
        # B2 fix — TaskEngine.cancel(tid, *, reason=..., actor=...).
        get_task_engine().cancel(task_id, reason=req.reason, actor=user.email)
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc
    return _get_task_row(task_id) or {}


@app.get("/api/v1/ecosystem/tasks/{task_id}/events", tags=["user"])
async def task_events(
    task_id: str,
    request: Request,
    user: User = Depends(_require_user),
) -> EventSourceResponse:
    """U3 — SSE stream of task state transitions (heartbeat every 15s)."""
    row = _get_task_row(task_id)
    if row is None:
        raise HTTPException(404, f"task not found: {task_id}")
    if user.role != UserRole.ADMIN and row.get("user_id") != user.user_id:
        raise HTTPException(404, f"task not found: {task_id}")

    terminal = {
        TaskState.COMPLETED.value,
        TaskState.FAILED.value,
        TaskState.CANCELLED.value,
        TaskState.ESCALATED.value,
    }

    async def event_gen() -> AsyncIterator[dict[str, str]]:
        last_state: str | None = None
        start = time.time()
        max_seconds = 600  # 10 min hard cap to avoid leaks.
        # Emit initial snapshot.
        current = _get_task_row(task_id)
        if current:
            last_state = current["state"]
            yield {"event": "task", "data": json.dumps(current, default=str)}
            if current["state"] in terminal:
                yield {"event": "close", "data": current["state"]}
                return
        while True:
            if await request.is_disconnected():
                return
            if time.time() - start > max_seconds:
                yield {"event": "close", "data": "timeout"}
                return
            await asyncio.sleep(2.0)
            current = _get_task_row(task_id)
            if not current:
                yield {"event": "close", "data": "deleted"}
                return
            if current["state"] != last_state:
                last_state = current["state"]
                yield {"event": "task", "data": json.dumps(current, default=str)}
                if current["state"] in terminal:
                    yield {"event": "close", "data": current["state"]}
                    return
            # Heartbeat every ~15s as a comment line (sse-starlette sends a `ping`).
            if int(time.time() - start) % 15 == 0:
                yield {"event": "ping", "data": str(int(time.time()))}

    return EventSourceResponse(event_gen())


@app.post("/api/v1/ecosystem/mcp/call", tags=["user"])
def mcp_call(
    req: McpCallRequest,
    user: User = Depends(_require_user),
) -> dict[str, Any]:
    """U4 — call an MCP operation. ACT-category ops require admin."""
    mcp = get_mcp_skeleton()
    ops = {op["operation"]: op["category"] for op in mcp.list_operations()}
    cat = ops.get(req.operation)
    if cat is None:
        raise HTTPException(404, f"unknown operation: {req.operation}")
    if cat == str(MCPOperationCategory.ACT) and user.role != UserRole.ADMIN:
        raise HTTPException(403, f"ACT operation '{req.operation}' requires admin role")
    # B5 fix — sync call(operation, *, params=..., correlation=..., actor=...).
    try:
        return mcp.call(
            req.operation,
            params=req.params or {},
            correlation={"actor_user_id": user.user_id},
            actor=user.email,
        )
    except Exception as exc:
        # Governance denials → 403; unknown ops → 404; everything else → 500.
        msg = str(exc)
        if "denied" in msg.lower():
            raise HTTPException(403, msg) from exc
        raise HTTPException(500, msg) from exc


# ===========================================================================
#  ADMIN ENDPOINTS  (25)  — /api/v1/ecosystem/admin/*
# ===========================================================================

# --- 2.4.1 Capabilities (5) ------------------------------------------------


@app.post("/api/v1/ecosystem/admin/capabilities", status_code=201, tags=["admin"])
def admin_create_capability(
    req: CapabilityCreateRequest,
    _: User = Depends(_require_admin),
) -> dict[str, Any]:
    """C1 — create a capability."""
    try:
        rt = CapabilityRuntimeTier(req.runtime_tier)
    except ValueError as exc:
        raise HTTPException(400, f"invalid runtime_tier: {req.runtime_tier}") from exc
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
        return _dump(get_capability_registry().register(cap))  # type: ignore[arg-type]
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/v1/ecosystem/admin/capabilities/{capability_id}/lifecycle", tags=["admin"])
def admin_transition_capability(
    capability_id: str,
    req: LifecycleTransitionRequest,
    _: User = Depends(_require_admin),
) -> dict[str, Any]:
    """C2 — transition capability lifecycle. B6 fix: no `reason` kwarg."""
    try:
        to = CapabilityLifecycleState(req.to_state)
    except ValueError as exc:
        raise HTTPException(400, f"invalid state: {req.to_state}") from exc
    try:
        cap = get_capability_registry().transition(capability_id, to, actor=req.actor)
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc
    return _dump(cap)  # type: ignore[return-value]


@app.post("/api/v1/ecosystem/admin/capabilities/{capability_id}/promote", tags=["admin"])
def admin_promote_capability(
    capability_id: str,
    _: User = Depends(_require_admin),
    actor: str = "admin",
) -> dict[str, Any]:
    """C3 — promote capability to HOT runtime tier."""
    try:
        cap = get_capability_registry().promote(capability_id, actor=actor)
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc
    return _dump(cap)  # type: ignore[return-value]


@app.post("/api/v1/ecosystem/admin/capabilities/{capability_id}/archive", tags=["admin"])
def admin_archive_capability(
    capability_id: str,
    _: User = Depends(_require_admin),
    actor: str = "admin",
) -> dict[str, Any]:
    """C4 — archive capability."""
    try:
        cap = get_capability_registry().archive(capability_id, actor=actor)
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc
    return _dump(cap)  # type: ignore[return-value]


@app.delete("/api/v1/ecosystem/admin/capabilities/{capability_id}", tags=["admin"])
def admin_delete_capability(
    capability_id: str,
    _: User = Depends(_require_admin),
) -> dict[str, Any]:
    """C5 — hard-delete a capability (off by default; env ``ECOSYSTEM_ALLOW_DELETE=true``)."""
    if not _ALLOW_DELETE:
        raise HTTPException(403, "hard-delete disabled (set ECOSYSTEM_ALLOW_DELETE=true to enable)")
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM ecosystem_capabilities WHERE capability_id=?", (capability_id,)
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, f"capability not found: {capability_id}")
    return {"ok": True, "capability_id": capability_id}


# --- 2.4.2 Proposals & Decisions (4) -------------------------------------


@app.get("/api/v1/ecosystem/admin/proposals", tags=["admin"])
def admin_list_proposals(
    _: User = Depends(_require_admin),
    kind: str | None = None,
    priority: str | None = None,
    limit: int = Query(50, le=200),
) -> list[dict[str, Any]]:
    """PR1 — list pending proposals."""
    pending = get_approval_workflow().list_pending(
        kind=ProposalKind(kind) if kind else None,
        priority=ProposalPriority(priority) if priority else None,
        limit=limit,
    )
    return [_dump(p) for p in pending]  # type: ignore[list-item]


@app.post("/api/v1/ecosystem/admin/proposals", status_code=201, tags=["admin"])
def admin_create_proposal(
    req: ProposalCreateRequest,
    admin: User = Depends(_require_admin),
) -> dict[str, Any]:
    """PR2 — create a proposal. B7 fix: use ``summary`` + ``requested_by`` (not description/proposed_by)."""
    try:
        k = ProposalKind(req.kind)
        p = ProposalPriority(req.priority)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    prop = ApprovalProposal(
        kind=k,
        priority=p,
        title=req.title,
        summary=req.summary,
        risk_level=(req.risk_level or "MEDIUM").upper(),
        payload=req.payload,
        tenant_id=req.tenant_id,
        requested_by=req.requested_by or admin.email,
    )
    try:
        return _dump(get_approval_workflow().propose(prop))  # type: ignore[arg-type]
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/v1/ecosystem/admin/proposals/{proposal_id}/decide", tags=["admin"])
def admin_decide_proposal(
    proposal_id: str,
    req: ProposalDecisionRequest,
    admin: User = Depends(_require_admin),
) -> dict[str, Any]:
    """PR3 — decide a proposal. B8 fix: use ``decided_by`` + ``rationale``."""
    try:
        d = ProposalState(req.decision)
    except ValueError as exc:
        raise HTTPException(400, f"invalid decision: {req.decision}") from exc
    if d not in {ProposalState.APPROVED, ProposalState.REJECTED, ProposalState.DEFERRED}:
        raise HTTPException(400, "decision must be APPROVED/REJECTED/DEFERRED")
    if d == ProposalState.REJECTED and not req.rationale:
        raise HTTPException(400, "rationale is required for REJECT")
    dec = ApprovalDecision(
        proposal_id=proposal_id,
        decision=d,
        decided_by=req.decided_by or admin.email,
        rationale=req.rationale,
    )
    try:
        prop = get_approval_workflow().decide(proposal_id, dec)
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc
    return _dump(prop)  # type: ignore[return-value]


@app.get("/api/v1/ecosystem/admin/proposals/{proposal_id}/decisions", tags=["admin"])
def admin_list_decisions(
    proposal_id: str,
    _: User = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """PR4 — decision history for a proposal. B9 fix: list_decisions(proposal_id) takes a single arg."""
    decisions = get_approval_workflow().list_decisions(proposal_id)
    return [_dump(d) for d in decisions]  # type: ignore[list-item]


# --- 2.4.3 Sources (4) ---------------------------------------------------


@app.get("/api/v1/ecosystem/admin/sources", tags=["admin"])
def admin_list_sources(
    _: User = Depends(_require_admin),
    state: str | None = None,
    category: str | None = None,
    limit: int = Query(200, le=500),
) -> list[dict[str, Any]]:
    """SO1 — list discovered sources."""
    return _list_sources(state=state, category=category, limit=limit)


@app.post("/api/v1/ecosystem/admin/sources/discover", status_code=201, tags=["admin"])
def admin_discover_source(
    req: SourceDiscoverRequest,
    _: User = Depends(_require_admin),
) -> dict[str, Any]:
    """SO2 — discover a new URL."""
    cat = SourceCategory(req.category) if req.category else SourceCategory.UNKNOWN
    return get_source_governance().discover(req.url, category=cat)


@app.post("/api/v1/ecosystem/admin/sources/{source_id}/transition", tags=["admin"])
def admin_transition_source(
    source_id: str,
    req: SourceTransitionRequest,
    _: User = Depends(_require_admin),
) -> dict[str, Any]:
    """SO3 — transition source state."""
    try:
        to = SourceState(req.to_state)
    except ValueError as exc:
        raise HTTPException(400, f"invalid state: {req.to_state}") from exc
    try:
        return get_source_governance().transition_source(source_id, to)
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/v1/ecosystem/admin/sources/{source_id}", tags=["admin"])
def admin_get_source(
    source_id: str,
    _: User = Depends(_require_admin),
) -> dict[str, Any]:
    """SO4 — get one source with metadata."""
    src = _get_source(source_id)
    if src is None:
        raise HTTPException(404, f"source not found: {source_id}")
    return src


# --- 2.4.4 Source Policies (4) ------------------------------------------


@app.get("/api/v1/ecosystem/admin/policies", tags=["admin"])
def admin_list_policies(
    _: User = Depends(_require_admin),
    limit: int = Query(200, le=500),
) -> list[dict[str, Any]]:
    """SP1 — list source policies."""
    return _list_policies(limit=limit)


@app.post("/api/v1/ecosystem/admin/policies", status_code=201, tags=["admin"])
def admin_create_policy(
    req: PolicyCreateRequest,
    _: User = Depends(_require_admin),
) -> dict[str, Any]:
    """SP2 — create a source policy."""
    try:
        cat = SourceCategory(req.category)
        state = SourceState(req.state)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    policy = SourcePolicy(
        url_pattern=req.url_pattern,
        category=cat,
        state=state,
        allowed_actions=req.allowed_actions,
        source_weight=req.source_weight,
        expires_at=req.expires_at,
        created_by="admin",
    )
    try:
        return _dump(get_source_governance().add_policy(policy))  # type: ignore[arg-type]
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc


@app.delete("/api/v1/ecosystem/admin/policies/{policy_id}", tags=["admin"])
def admin_delete_policy(
    policy_id: str,
    _: User = Depends(_require_admin),
) -> dict[str, Any]:
    """SP3 — delete a source policy."""
    if not _delete_policy(policy_id):
        raise HTTPException(404, f"policy not found: {policy_id}")
    return {"ok": True, "policy_id": policy_id}


@app.get("/api/v1/ecosystem/admin/policies/match", tags=["admin"])
def admin_match_policy(
    _: User = Depends(_require_admin),
    url: str = Query(..., description="URL to test against all source policies"),
) -> dict[str, Any]:
    """SP4 — test-match a URL against policies."""
    policy = get_source_governance().match_policy(url)
    return {
        "url": url,
        "matched": policy is not None,
        "policy": _dump(policy),
    }


# --- 2.4.5 Learned Items (3) --------------------------------------------


@app.get("/api/v1/ecosystem/admin/learned", tags=["admin"])
def admin_list_learned(
    _: User = Depends(_require_admin),
    category: str | None = None,
    min_value: float = 0.0,
    limit: int = Query(100, le=500),
) -> list[dict[str, Any]]:
    """LE1 — list learned items."""
    cat = SourceCategory(category) if category else None
    items = get_source_governance().list_learned(category=cat, min_value=min_value, limit=limit)
    return [_dump(i) for i in items]  # type: ignore[list-item]


@app.post("/api/v1/ecosystem/admin/learned/prune", tags=["admin"])
def admin_prune_learned(
    req: PruneLearnedRequest,
    _: User = Depends(_require_admin),
) -> dict[str, Any]:
    """LE2 — prune low-value learned items."""
    n = get_source_governance().prune_low_value(
        threshold=req.threshold, max_age_days=req.max_age_days
    )
    return {"pruned_count": n}


@app.delete("/api/v1/ecosystem/admin/learned/{item_id}", tags=["admin"])
def admin_delete_learned(
    item_id: str,
    _: User = Depends(_require_admin),
) -> dict[str, Any]:
    """LE3 — hard-delete a learned item."""
    if not _delete_learned(item_id):
        raise HTTPException(404, f"learned item not found: {item_id}")
    return {"ok": True, "item_id": item_id}


# --- 2.4.6 Opportunities (3) --------------------------------------------


@app.get("/api/v1/ecosystem/admin/opportunities", tags=["admin"])
def admin_list_opportunities(
    _: User = Depends(_require_admin),
    stage: str | None = None,
    include_archived: bool = False,
    limit: int = Query(100, le=500),
) -> list[dict[str, Any]]:
    """OP1 — list opportunities."""
    st = LearningStage(stage) if stage else None
    opps = get_learning_loop().list_opportunities(
        stage=st, include_archived=include_archived, limit=limit
    )
    return [_dump(o) for o in opps]  # type: ignore[list-item]


@app.post("/api/v1/ecosystem/admin/opportunities", status_code=201, tags=["admin"])
def admin_surface_opportunity(
    req: OpportunityCreateRequest,
    _: User = Depends(_require_admin),
) -> dict[str, Any]:
    """OP2 — surface a new opportunity. B10 fix: use ``capability_hint`` + ``gap_description`` + ``predicted_value`` + ``predicted_effort``."""
    opp = LearningOpportunity(
        capability_hint=req.capability_hint,
        gap_description=req.gap_description,
        signal_id=req.signal_id,
        predicted_value=req.predicted_value,
        predicted_effort=req.predicted_effort,
    )
    return _dump(get_learning_loop().surface_opportunity(opp))  # type: ignore[arg-type]


@app.post("/api/v1/ecosystem/admin/opportunities/{opportunity_id}/advance", tags=["admin"])
def admin_advance_opportunity(
    opportunity_id: str,
    req: OpportunityAdvanceRequest,
    _: User = Depends(_require_admin),
) -> dict[str, Any]:
    """OP3 — advance opportunity stage."""
    try:
        to = LearningStage(req.to_stage)
    except ValueError as exc:
        raise HTTPException(400, f"invalid stage: {req.to_stage}") from exc
    try:
        opp = get_learning_loop().advance_stage(opportunity_id, to, proposal_id=req.proposal_id)
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc
    return _dump(opp)  # type: ignore[return-value]


# --- 2.4.7 Governance (2) -----------------------------------------------


@app.get("/api/v1/ecosystem/admin/governance/decisions", tags=["admin"])
def admin_governance_decisions(
    _: User = Depends(_require_admin),
    actor: str | None = None,
    operation: str | None = None,
    limit: int = Query(100, le=500),
) -> list[dict[str, Any]]:
    """GO1 — list recent governance decisions (authz log)."""
    return _list_governance_decisions(actor=actor, operation=operation, limit=limit)


@app.get("/api/v1/ecosystem/admin/governance/budgets", tags=["admin"])
def admin_governance_budgets(
    _: User = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """GO2 — inspect current budgets per ``BudgetKind``."""
    gov = get_governance_engine()
    out = []
    for kind in BudgetKind:
        limit = gov.budgets._budget_for(kind)
        used = gov.budgets.used.get(kind, 0.0)
        out.append(
            {
                "kind": kind.value,
                "limit": limit,
                "used": used,
                "remaining": gov.budgets.remaining(kind),
            }
        )
    return out


# --- 2.4.8 Overview (1) -------------------------------------------------


@app.get("/api/v1/ecosystem/admin/overview", tags=["admin"])
def admin_overview(_: User = Depends(_require_admin)) -> dict[str, Any]:
    """OV1 — aggregated dashboard KPIs."""
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


# ---------------------------------------------------------------------------
# Dev runner
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "ecosystem.standalone_app:app",
        host=os.getenv("ECOSYSTEM_BIND_HOST", default="0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
