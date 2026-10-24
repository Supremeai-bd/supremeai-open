"""Epistemic endpoints (ChronoFact/SPINE patterns) for SupremeAI gateway.

Exposes:
- POST /api/v1/tools/prune      (TF-IDF tool schema pruning)
- POST /api/v1/memory/gate      (relevance-gated memory, 0.72 cosine gate)
- GET  /api/v1/model-horizon    (list calibrated models)
- POST /api/v1/model-horizon/intercept  (drift interception)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("supremeai.epistemic")

router = APIRouter(prefix="/api/v1", tags=["epistemic"])


class ToolPruneRequest(BaseModel):
    query: str
    tools: list[dict[str, Any]]
    threshold: float = 0.45


class MemoryGateRequest(BaseModel):
    query: str
    entries: list[dict[str, Any]]
    threshold: float = 0.72


class InjectionScanRequest(BaseModel):
    text: str
    threshold: float = 0.3


class HorizonInterceptRequest(BaseModel):
    model_id: str
    as_of: Optional[str] = None


@router.post("/prompt-injection/scan")
async def scan_prompt_injection(req: InjectionScanRequest) -> dict[str, Any]:
    try:
        from gateway.prompt_injection import detect_injection
    except ImportError:
        from prompt_injection import detect_injection  # type: ignore[no-redef]
    res = detect_injection(req.text, threshold=req.threshold)
    return {
        "is_injection": res.is_injection,
        "score": res.score,
        "matched": res.matched,
        "sanitized": res.sanitized,
    }


def _import_pruner():
    try:
        from gateway.tool_pruner import ToolSchema, route_tools
    except ImportError:
        from tool_pruner import ToolSchema, route_tools  # type: ignore[no-redef]
    return ToolSchema, route_tools


def _import_memory_gate():
    try:
        from gateway.memory_gate import MemoryEntry, MemoryGate
    except ImportError:
        from memory_gate import MemoryEntry, MemoryGate  # type: ignore[no-redef]
    return MemoryEntry, MemoryGate


def _import_horizon():
    try:
        from gateway.model_horizon import (
            ModelHorizonRegistry,
            intercept_drift,
            reset_registry,
        )
    except ImportError:
        from model_horizon import (  # type: ignore[no-redef]
            ModelHorizonRegistry,
            intercept_drift,
            reset_registry,
        )
    return ModelHorizonRegistry, intercept_drift, reset_registry


@router.post("/tools/prune")
async def prune_tools(req: ToolPruneRequest) -> dict[str, Any]:
    ToolSchema, route_tools = _import_pruner()
    tools = [ToolSchema(name=t.get("name", ""), description=t.get("description", ""), tokens=int(t.get("tokens", 0))) for t in req.tools]
    res = route_tools(req.query, tools, threshold=req.threshold)
    return {
        "retained": [{"name": t.name, "description": t.description, "tokens": t.tokens} for t in res.retained],
        "pruned": [{"name": t.name, "description": t.description, "tokens": t.tokens} for t in res.pruned],
        "threshold": res.threshold,
        "reduction_pct": res.reduction_pct,
        "original_tokens": res.original_tokens,
        "retained_tokens": res.retained_tokens,
    }


@router.post("/memory/gate")
async def gate_memory(req: MemoryGateRequest) -> dict[str, Any]:
    MemoryEntry, MemoryGate = _import_memory_gate()
    entries = [MemoryEntry(entry_id=e.get("id", ""), domain=e.get("domain", ""), content=e.get("content", ""), metadata=e.get("metadata") or {}) for e in req.entries]
    gate = MemoryGate(threshold=req.threshold)
    res = gate.gate(req.query, entries)
    return {
        "retained": [{"id": e.entry_id, "domain": e.domain, "content": e.content} for e in res.retained],
        "rejected": [{"id": e.entry_id, "domain": e.domain, "content": e.content} for e in res.rejected],
        "threshold": res.threshold,
        "leak_count": res.leak_count,
        "leak_rate": res.leak_rate,
    }


@router.get("/model-horizon")
async def list_model_horizon() -> dict[str, Any]:
    ModelHorizonRegistry, _, _ = _import_horizon()
    reg = ModelHorizonRegistry()
    return {
        "models": [
            {
                "id": m.model_id,
                "provider": m.provider,
                "official_cutoff": m.official_cutoff.isoformat(),
                "training_freeze": m.training_freeze.isoformat(),
                "status": m.status,
                "successor": m.successor,
            }
            for m in reg.all()
        ]
    }


@router.post("/model-horizon/intercept")
async def intercept_horizon(req: HorizonInterceptRequest) -> dict[str, Any]:
    _, intercept_drift, _ = _import_horizon()
    from datetime import date

    as_of = None
    if req.as_of:
        try:
            as_of = date.fromisoformat(req.as_of)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid as_of date (expected YYYY-MM-DD)")
    ev = intercept_drift(req.model_id, as_of=as_of)
    return {"model_id": ev.model_id, "kind": ev.kind, "detail": ev.detail, "successor": ev.successor}


@router.get("/epistemic/health")
async def epistemic_health() -> dict[str, Any]:
    """Swiss-Watch Duo Pairing (Way 9): Joint health check for SPINE Stream Sanitizer + ChronoFact Epistemic Backbone."""
    results: dict[str, Any] = {}

    # 1. ChronoFact Pillar 1 (Model Horizon)
    try:
        ModelHorizonRegistry, _, _ = _import_horizon()
        reg = ModelHorizonRegistry()
        models = reg.all()
        results["chronofact_model_horizon"] = {
            "status": "healthy" if len(models) > 0 else "degraded",
            "active_models_calibrated": len(models),
        }
    except Exception as exc:
        results["chronofact_model_horizon"] = {"status": "degraded", "error": str(exc)}

    # 2. ChronoFact Pillar 2 (Tool Pruner)
    try:
        ToolSchema, route_tools = _import_pruner()
        test_tools = [ToolSchema(name="ping", description="Ping health check")]
        prune_res = route_tools("ping server", test_tools, threshold=0.1)
        results["chronofact_tool_pruner"] = {
            "status": "healthy" if len(prune_res.retained) > 0 else "degraded",
            "target_reduction": 0.70,
        }
    except Exception as exc:
        results["chronofact_tool_pruner"] = {"status": "degraded", "error": str(exc)}

    # 3. ChronoFact Pillar 3 (Memory Gate)
    try:
        MemoryEntry, MemoryGate = _import_memory_gate()
        gate = MemoryGate(threshold=0.72)
        results["chronofact_memory_gate"] = {
            "status": "healthy",
            "threshold": gate.threshold,
        }
    except Exception as exc:
        results["chronofact_memory_gate"] = {"status": "degraded", "error": str(exc)}

    # 4. SPINE (Stream Sanitizer)
    try:
        try:
            from gateway.service.stream_sanitizer import sanitize_stream
        except ImportError:
            from service.stream_sanitizer import sanitize_stream  # type: ignore[no-redef]
        res = sanitize_stream("Certainly! Here is the answer.")
        results["spine_stream_sanitizer"] = {
            "status": "healthy" if not res.text.lower().startswith("certainly") else "degraded",
            "stripped_cushion": res.stripped_cushion,
        }
    except Exception as exc:
        results["spine_stream_sanitizer"] = {"status": "degraded", "error": str(exc)}

    all_healthy = all(v.get("status") == "healthy" for v in results.values())

    return {
        "status": "healthy" if all_healthy else "degraded",
        "duo_pairing": results,
        "invariants": {
            "memory_cosine_threshold": 0.72,
            "tool_pruning_reduction_target": 0.70,
            "sampling_lock_logic": 0.2,
            "sampling_lock_chat": 0.4,
        },
    }

