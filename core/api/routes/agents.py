from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agents.research_assistant import ResearchAssistant, ResearchSourceError
from core.logging_config import logger
from core.security.authentication.rbac import get_current_user_token

# ERR-H07 CONTRACT: this router is the USER-facing read surface (catalog,
# status, research tools). The canonical EXECUTION surface lives in
# ``api.routes.agent`` at ``/api/v1/agents/execute`` (integration JWT).
# Do not add execution endpoints here; see the drift-guard contract test
# ``backend/tests/api/test_agent_execute_contract.py``.
router = APIRouter(
    prefix="/api/agents",
    tags=["specialized-agents"],
    dependencies=[Depends(get_current_user_token)],
)


class ResearchRequest(BaseModel):
    query: str
    source: str = "arxiv"
    max_results: int = 5


class SummarizeRequest(BaseModel):
    paper: dict[str, Any]
    style: str = "apa"


# ERR-G08 FIX (2026-09-16): list_agents() used to return a single hardcoded
# {"id": "research", ...} literal. The catalog is now derived from the real
# backend/agents/ directory (module stem + first docstring line) so it always
# reflects what actually ships, and never invents agents that do not exist.
_AGENTS_DIR = Path(__file__).resolve().parent.parent.parent / "agents"


@lru_cache(maxsize=1)
def _agent_catalog() -> tuple[dict[str, str], ...]:
    """Real catalog of top-level agent modules shipped in backend/agents/."""
    entries: list[dict[str, str]] = []
    if not _AGENTS_DIR.exists():
        return ()
    for path in sorted(_AGENTS_DIR.glob("*.py")):
        stem = path.stem
        if stem.startswith("_"):
            continue
        description = ""
        try:
            module = importlib.import_module(f"agents.{stem}")
            doc = (module.__doc__ or "").strip()
        except Exception as exc:  # noqa: BLE001 — a broken module must not hide the catalog entry
            doc = ""  # import failure is reported truthfully by /status
            logger.warning(f"[agent-catalog] import check failed for agents.{stem}: {exc}")
        for line in doc.splitlines():
            line = line.strip()
            if line:
                description = line
                break
        entries.append(
            {
                "id": stem,
                "name": stem.replace("_", " ").title(),
                "description": description,
            }
        )
    return tuple(entries)


@router.get("/", tags=["specialized-agents"])
async def list_agents():
    """List all available specialized agent types (real catalog, not hardcoded)."""
    return {"agents": list(_agent_catalog()), "count": len(_agent_catalog())}


@router.get("/{agent_id}/status", tags=["specialized-agents"])
async def get_agent_status(agent_id: str):
    """Honest status for a specialized agent type.

    ERR-G07 FIX: previously ANY agent id got a hardcoded status "active"
    with a frozen January-2026 timestamp — a value that could not
    distinguish alive from dead. Now an unknown id is a 404, and a known id
    reports a real import-based availability check with an explicit "no
    runtime telemetry" note instead of a fabricated timestamp.
    """
    known = {entry["id"] for entry in _agent_catalog()}
    if agent_id not in known:
        raise HTTPException(status_code=404, detail=f"Unknown agent type: {agent_id}")
    try:
        importlib.import_module(f"agents.{agent_id}")
        return {
            "agent_id": agent_id,
            "status": "available",
            "last_activity": None,
            "detail": "Capability catalog entry — no per-agent runtime telemetry is recorded; last_activity is intentionally not fabricated.",
        }
    except Exception as exc:  # noqa: BLE001 — verbatim import failure is the honest status
        return {
            "agent_id": agent_id,
            "status": "unavailable",
            "last_activity": None,
            "detail": f"Module import failed: {exc}",
        }


@router.post("/research/search")
async def research_search(payload: ResearchRequest):
    """Real research search (live arXiv). Errors map honestly: bad input → 400,
    upstream failure → 502 with the verbatim reason."""
    try:
        assistant = ResearchAssistant()
        results = assistant.search(
            payload.query, source=payload.source, max_results=payload.max_results
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ResearchSourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("research_search failed")
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    return {
        "query": payload.query,
        "source": payload.source,
        "papers": results,
        "count": len(results),
    }


@router.post("/research/summarize")
async def research_summarize(payload: SummarizeRequest):
    """Real extractive summarization (no fabricated text)."""
    try:
        assistant = ResearchAssistant()
        return assistant.summarize(payload.paper)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("research_summarize failed")
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/research/cite")
async def research_cite(payload: SummarizeRequest):
    """Real deterministic citation formatting."""
    try:
        assistant = ResearchAssistant()
        return {"citation": assistant.citations(payload.paper, style=payload.style)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("research_cite failed")
        raise HTTPException(status_code=500, detail="Internal server error") from exc
