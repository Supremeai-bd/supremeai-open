"""
backend/api/routes/external_agents_admin.py
===========================================
Issue #2148 — smallest honest wire for ``backend/external_agents/`` (the
EAOL Part-3 seed of PLAN-EAOL-003; MODULE_STATUS_REGISTRY.md §11 records it
as NEAR-READY-UNWIRED with a wire-next recommendation, B12 deletion refuted).

Double-gated managed surface (near-ready wiring pattern):

1. **Env flag** ``SUPREMEAI_EXTERNAL_AGENTS_ENABLED`` (default: off) — while
   off, every endpoint fails closed with a clean 503 and the module still
   imports safely (no import-time side effects).
2. **Admin auth** — the ALL_ROUTERS entry is ``is_admin: True``, so the
   router-level ``get_current_user_token`` dependency is applied by
   ``routers.include_admin_routers()``.

Honesty contract (billing ERR-G01 precedent: fabricated states are forbidden
in EVERY environment): delegation REQUIRES an explicitly configured worker via
``SUPREMEAI_EXTERNAL_AGENTS_WORKER`` (dotted/colon path to an async
``WorkerFn(task, record) -> dict | None``). With no worker configured the
delegate endpoint fails closed with ``no_worker_configured`` — jobs are never
accepted into a queue that nothing will ever drain, and no progress is ever
fabricated. Provider execution itself stays behind PLAN-EAOL-003 milestones;
this wire exposes only the already-tested control-plane Job API.
"""

from __future__ import annotations

import importlib
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from external_agents.contracts.task_contract import AgentProvider, TaskContract
from external_agents.control.job_api import ExternalAgentJobAPI, WorkerFn
from integrations._flags import flag

router = APIRouter(prefix="/api/v1/external-agents", tags=["external-agents"])

FLAG_ENABLED = "SUPREMEAI_EXTERNAL_AGENTS_ENABLED"
FLAG_WORKER = "SUPREMEAI_EXTERNAL_AGENTS_WORKER"

# Process-wide Job API singleton. Created lazily on the first successful
# delegate (the only path that needs a worker); GET/DELETE reuse it so job
# handles stay queryable/cancellable within the process lifetime.
_job_api: ExternalAgentJobAPI | None = None
_job_api_worker_id: str | None = None


class DelegateRequest(BaseModel):
    """Request body for POST /jobs — the operator-visible TaskContract fields."""

    goal: str = Field(min_length=1, description="What the external agent must accomplish")
    issue_number: int | None = Field(
        default=None, description="GitHub issue this task implements, when applicable"
    )
    constraints: dict[str, Any] = Field(default_factory=dict)
    allowed_providers: list[str] | None = Field(
        default=None,
        description="Subset of provider ids (zcode, chatgpt, gemini, lovable, bolt); "
        "defaults to all known providers",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


def _ensure_enabled() -> None:
    """Fail closed with a clean 503 while the feature flag is off."""
    if not flag(FLAG_ENABLED):
        raise HTTPException(
            status_code=503,
            detail=f"external_agents_disabled: set {FLAG_ENABLED}=1 to enable "
            "(module is wired but intentionally gated; see MODULE_STATUS_REGISTRY.md §11)",
        )


def _load_worker_from_env() -> tuple[WorkerFn, str]:
    """Resolve the explicit WorkerFn from ``SUPREMEAI_EXTERNAL_AGENTS_WORKER``.

    Honesty rule: no default worker exists — the env var is the ONLY way a
    delegate can proceed. Import happens lazily per call so configuration
    errors surface as clean 503s, never as import-time crashes.
    """
    raw = (os.getenv(FLAG_WORKER) or "").strip()
    if not raw:
        raise HTTPException(
            status_code=503,
            detail="no_worker_configured: set "
            f"{FLAG_WORKER}='<module>:<async fn>' to attach a worker before "
            "delegating (no fabricated progress is ever reported)",
        )
    module_name, _, attr = raw.partition(":")
    if not attr:
        module_name, _, attr = raw.rpartition(".")
    try:
        worker = getattr(importlib.import_module(module_name), attr)
    except Exception as exc:  # noqa: BLE001 — any resolution failure is a config error
        raise HTTPException(
            status_code=503,
            detail=f"worker_unavailable: cannot resolve '{raw}' ({exc.__class__.__name__}: {exc})",
        ) from exc
    if not callable(worker):
        raise HTTPException(status_code=503, detail=f"worker_unavailable: '{raw}' is not callable")
    return worker, raw


def _get_job_api(
    worker: WorkerFn | None = None, worker_id: str | None = None
) -> ExternalAgentJobAPI:
    """Return the process-wide Job API, creating it on first delegate."""
    global _job_api, _job_api_worker_id
    if _job_api is None:
        if worker is None:
            # GET/DELETE before any delegate happened: no jobs can exist.
            raise HTTPException(status_code=404, detail="no jobs exist (no delegate has run yet)")
        _job_api = ExternalAgentJobAPI(worker=worker)
        _job_api_worker_id = worker_id
    return _job_api


def reset_job_api_singleton() -> None:
    """Test/ops hook: drop the cached singleton (and any running workers)."""
    global _job_api, _job_api_worker_id
    if _job_api is not None:
        _job_api.shutdown()
    _job_api = None
    _job_api_worker_id = None


def _parse_providers(raw: list[str] | None) -> list[AgentProvider]:
    if raw is None:
        return list(AgentProvider)
    known = {p.value for p in AgentProvider}
    unknown = [p for p in raw if p not in known]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unknown provider(s) {unknown}; known: {sorted(known)}",
        )
    return [AgentProvider(p) for p in raw]


@router.post("/jobs", status_code=202)
async def delegate_job(req: DelegateRequest) -> dict[str, Any]:
    """Delegate a task to the external-agents pipeline; returns the job handle."""
    _ensure_enabled()
    worker, worker_path = _load_worker_from_env()
    api = _get_job_api(worker=worker, worker_id=worker_path)
    contract = TaskContract(
        goal=req.goal,
        issue_number=req.issue_number,
        constraints=req.constraints,
        allowed_providers=_parse_providers(req.allowed_providers),
        metadata=req.metadata,
    )
    job = await api.delegate_web_agent(contract)
    return job.model_dump(mode="json")


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    """Return the current job handle (durable state machine is the truth)."""
    _ensure_enabled()
    api = _get_job_api()
    job = await api.get_web_agent_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job '{job_id}'")
    return job.model_dump(mode="json")


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str) -> dict[str, Any]:
    """Cancel a job; terminal jobs report ``cancelled: false`` (never faked)."""
    _ensure_enabled()
    api = _job_api  # GET/DELETE must not lazily require a worker
    if api is None:
        raise HTTPException(status_code=404, detail=f"unknown job '{job_id}'")
    job = await api.get_web_agent_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job '{job_id}'")
    cancelled = await api.cancel_web_agent_job(job_id)
    return {"job_id": job_id, "cancelled": cancelled}
