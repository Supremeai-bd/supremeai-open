import json
import secrets
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from api.dependencies import get_fitness_engine, get_tenant_db
from api.deps import get_current_user_token
from core.config import settings
from core.logging_config import logger
from core.self_evolution.agent_breeder import AgentBreeder, BreederConfig
from core.self_evolution.auto_skill_creator import AutoSkillCreator
from core.self_evolution.fitness_engine import FitnessEngine
from core.self_evolution.performance_oracle import PerformanceOracle
from database.session import get_db_session
from database.tenant_db import TenantAwareFirestore
from models.evolution import CodeProposal
from models.meta_ai import AgentGenome


class GraphNode(BaseModel):
    id: str
    label: str
    type: str  # e.g., 'agent', 'skill'


class GraphEdge(BaseModel):
    source: str
    target: str
    relationship: str


class SwarmGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


router = APIRouter(prefix="/evolution", tags=["self-evolution-engine"])

security = HTTPBearer()


def require_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        jwt_secret = settings.jwt_secret
        decoded = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        if decoded.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Forbidden: User does not have admin role.")
        return decoded
    except Exception as e:
        expected = getattr(settings, "supremeai_api_token", None) or ""
        if expected and secrets.compare_digest(token, expected):
            return {"uid": "admin", "role": "admin"}
        raise HTTPException(
            status_code=401, detail=f"Invalid Admin Authorization Token: {e!s}"
        ) from e


@router.get("/logs")
async def get_evolution_logs(admin: dict = Depends(require_admin_token)):
    try:
        from database.supabase_client import db

        if db.client:
            logs = db.get_evolution_logs(limit=500)
            return {"logs": logs}
    except Exception as exc:
        # বল মনতবয: Supabase থক লগ আনত বযরথ হল লকল JSONL ফলবযক বযবহত হয়;
        # নরব সযলপ ন কর ডবগ লগ কর হল যত DB সমসয দশযমন থক
        logger.debug(f"Supabase evolution logs fetch failed, using local fallback: {exc}")

    base_dir = Path(__file__).resolve().parent.parent.parent
    log_path = base_dir / "backend" / "data" / "evolution_logs.jsonl"
    if not log_path.exists():
        return {"logs": []}
    try:
        with open(log_path, encoding="utf-8") as f:
            lines = f.readlines()
        logs = [json.loads(line) for line in lines if line.strip()]
        return {"logs": logs}
    except Exception as e:
        logger.error(f"Failed to read evolution logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to read evolution logs") from e


class CanaryObservation(BaseModel):
    success: bool
    latency_ms: float = 0.0


@router.post("/canary/{proposal_id}/observation")
async def record_canary_observation(
    proposal_id: str,
    observation: CanaryObservation,
    admin: dict = Depends(require_admin_token),
):
    """Sprint 6: feed REAL canary observations into the rollout controller.

    Closes the plan's canary gap: ``CanaryRolloutController.record_observation``
    previously had no production caller, so staged rollouts could never
    accumulate evidence. Requires admin token (HITL-gated by construction).
    """
    try:
        from evolution.canary_manager import get_canary_controller

        controller = get_canary_controller()
        controller.record_observation(
            proposal_id,
            success=observation.success,
            latency_ms=observation.latency_ms,
        )
        stats = controller.get_canary_stats(proposal_id)
        return {"success": True, "canary_stats": stats}
    except Exception as exc:
        logger.error(f"canary observation failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/canary/{proposal_id}/route")
async def evaluate_canary_route(
    proposal_id: str,
    request: Request,
    client_id: str | None = None,
    user: dict = Depends(get_current_user_token),
):
    """Evaluate if caller should route to canary or baseline for proposal_id.

    Supports 'X-Canary' header override (true/false) and sticky client_id hashing.

    AUDIT-FIX (#1704 P0): আগে এই endpoint-এ কোনো auth dependency ছিল না —
    যে কেউ proposal_id দিয়ে active canary trial-এর state দেখতে পারত (active,
    sample_ratio)। যদিও operational endpoint, এটি still information disclosure —
    unauthenticated caller যে কোনো proposal_id-এর canary state এনুমারেট করতে
    পারত। এখন authenticated user_token দিয়ে বাধ্যতামূলক করা হয়েছে।
    """
    from evolution.canary_manager import get_canary_controller

    controller = get_canary_controller()
    headers_dict = dict(request.headers)
    is_canary = controller.route_request(
        proposal_id=proposal_id,
        headers=headers_dict,
        client_id=client_id or user.get("sub"),
    )
    trial = controller.active_canaries.get(proposal_id)
    return {
        "proposal_id": proposal_id,
        "is_canary": is_canary,
        "active": trial is not None,
        "sample_ratio": trial.sample_ratio if trial else 0.0,
    }


@router.get("/metrics")
async def get_evolution_metrics(admin: dict = Depends(require_admin_token)):
    """Plan §20 observability: one autonomous-evolution dashboard payload.

    Every number is MEASURED from the durable learning store or the
    improvement-proposal lifecycle — nothing is fabricated. When the store
    is unavailable the endpoint reports ``available: false`` instead of
    inventing values.
    """
    payload: dict[str, Any] = {"available": False}
    try:
        from database.supabase_client import db

        if not db.client:
            return payload

        events = db.get_learning_events(limit=2000, hours=24) or []
        total = len(events)
        successes = sum(1 for e in events if e.get("success") is True)
        failures = sum(1 for e in events if e.get("success") is False)
        cache_hits = sum(1 for e in events if e.get("cache_hit") is True)
        feedback_events = [e for e in events if e.get("feedback")]
        est_cost = sum(float(e.get("estimated_cost") or 0) for e in events)
        act_cost = sum(float(e.get("actual_cost") or 0) for e in events)

        # Token estimation error: mean absolute ratio where both sides exist
        ratios = [
            (float(e["input_tokens"]) + float(e.get("output_tokens") or 0))
            / float(e["metadata"]["estimated_tokens"])
            for e in events
            if e.get("input_tokens")
            and isinstance(e.get("metadata"), dict)
            and e["metadata"].get("estimated_tokens")
        ]
        est_error = round(sum(abs(r - 1.0) for r in ratios) / len(ratios), 4) if ratios else None

        provider_rows = db.get_provider_metrics(hours=24) or []
        providers = [
            {
                "provider": r.get("provider"),
                "model": r.get("model"),
                "requests": r.get("requests"),
                "success_rate": (
                    round(
                        r.get("successes", 0)
                        / max(1, r.get("successes", 0) + r.get("failures", 0)),
                        4,
                    )
                    if (r.get("successes") is not None)
                    else None
                ),
                "rate_limited": r.get("rate_limited"),
                "latency_p95_ms": r.get("latency_p95_ms"),
                "estimated_cost": r.get("estimated_cost"),
                "actual_cost": r.get("actual_cost"),
            }
            for r in provider_rows
        ]

        proposals = db.get_improvement_proposals(limit=200) or []
        by_status: dict[str, int] = {}
        for p in proposals:
            key = str(p.get("status") or "UNKNOWN")
            by_status[key] = by_status.get(key, 0) + 1

        payload = {
            "available": True,
            "window_hours": 24,
            "learning_events_24h": total,
            "successful_tasks": successes,
            "failed_tasks": failures,
            "cache_hit_rate_24h": round(cache_hits / total, 4) if total else None,
            "feedback_events_24h": len(feedback_events),
            "estimated_cost_24h": round(est_cost, 6),
            "actual_cost_24h": round(act_cost, 6),
            "token_estimation_error": est_error,
            "providers_24h": providers,
            "autonomous_changes": {
                "proposals_by_status": by_status,
                "total_proposals": len(proposals),
                "rejected": by_status.get("REJECTED", 0),
                "promoted": by_status.get("PROMOTED", 0),
                "rolled_back": by_status.get("ROLLED_BACK", 0),
            },
            "learning_store": get_learning_store().get_stats(),
            "calibration": get_calibration_stats(),
        }
        return payload
    except Exception as exc:
        logger.debug(f"evolution metrics degraded: {exc}")
        payload["error"] = str(exc)[:200]
        return payload


def get_learning_store():
    from core.learning import get_learning_store as _f

    return _f()


def get_calibration_stats():
    from core.learning import get_calibration_stats as _f

    return _f()


class EvolutionRequest(BaseModel):
    skill_name: str
    user_demand: str


@router.post("/forge")
async def forge_dynamic_skill(
    payload: EvolutionRequest,
    db: TenantAwareFirestore = Depends(get_tenant_db),
    user: dict = Depends(get_current_user_token),
):
    """On-the-fly AI Skill Generation and Sandbox Deployed Gate.

    Issue #1651: identity is now bound INSIDE the route (not only via the
    mount-time is_admin flag) so the guard survives re-mounting. Admin-only
    would break the user-facing EvolutionForge feature — the deploy path is
    sandbox-verified upstream (banned-keyword scan + sandbox gate).
    """
    """
    On-the-fly AI Skill Generation and Sandbox Deployed Gate.
    """
    creator = AutoSkillCreator(db=db)
    result = await creator.generate_and_deploy_skill(
        user_demand=payload.user_demand, skill_name=payload.skill_name
    )

    if not result["success"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])

    return result


class QuarantineRequest(BaseModel):
    skill_name: str = Field(..., min_length=1, max_length=200)


@router.get("/swarm-graph")
async def get_swarm_graph(user: dict = Depends(get_current_user_token)):
    """Real swarm topology (issue #446 honest-telemetry fix).

    Nodes come from the live agent_supervisor health map (same truth-source as
    /api/v1/health/agents).  Edges are an honest empty list — no real
    edge/relationship telemetry source exists yet, and the previous hardcoded
    prototype graph ("Code-Optimizer teaches FastAPI Refactor") was pure
    simulation feeding the Swarm Map UI.
    """
    from core.agent_supervisor import agent_supervisor

    health = agent_supervisor.get_health() or {}
    nodes = [
        {
            "id": agent_id,
            "label": agent_id,
            "type": "agent",
            "status": (info or {}).get("status", "unknown")
            if isinstance(info, dict)
            else "unknown",
        }
        for agent_id, info in health.items()
    ]
    return {
        "nodes": nodes,
        "edges": [],
        "source": "agent_supervisor",
        "simulated": False,
    }


@router.post("/quarantine")
async def quarantine_skill(
    payload: QuarantineRequest,
    admin: dict = Depends(require_admin_token),
    fitness_engine: FitnessEngine = Depends(get_fitness_engine),
):
    skill_name = payload.skill_name.strip()
    try:
        skill_data = fitness_engine.registry.get_skill(skill_name)
        if skill_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Skill not found in registry",
            )
        skill_data["status"] = "QUARANTINED"
        fitness_engine.registry.skills["skills"][skill_name] = skill_data
        with open(fitness_engine.registry.registry_path, "w", encoding="utf-8") as f:
            json.dump(fitness_engine.registry.skills, f, indent=4)
        base_dir = Path(__file__).resolve().parent.parent.parent
        src = base_dir / "skills" / "dynamic" / skill_name
        dst = base_dir / "skills" / "quarantine" / skill_name
        if src.exists():
            (base_dir / "skills" / "quarantine").mkdir(parents=True, exist_ok=True)
            if dst.exists():
                shutil.rmtree(dst)
            shutil.move(str(src), str(dst))
            logger.info(f"Skill '{skill_name}' quarantined: {src} -> {dst}")
        else:
            logger.info(
                f"Skill '{skill_name}' marked QUARANTINED in registry (no dynamic directory found)"
            )
        base_dir_for_logs = Path(__file__).resolve().parent.parent.parent
        log_path = base_dir_for_logs / "backend" / "data" / "evolution_logs.jsonl"
        try:
            from database.supabase_client import db as db_client

            if db_client.client:
                db_client.append_evolution_log(
                    {
                        "event": {
                            "action": "quarantine",
                            "skill_name": skill_name,
                            "admin_uid": admin.get("uid"),
                            "timestamp": time.time(),
                        },
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                )
        except Exception as db_err:
            logger.warning(f"Failed to log quarantine action to Supabase: {db_err}")

        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "action": "quarantine",
                            "skill_name": skill_name,
                            "admin_uid": admin.get("uid"),
                            "timestamp": time.time(),
                        },
                        default=str,
                    )
                    + "\n"
                )
        except Exception as log_err:
            logger.warning(f"Failed to append quarantine log: {log_err}")
        return {"success": True, "skill_name": skill_name, "new_status": "QUARANTINED"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Quarantine failed for '{skill_name}'")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Quarantine failed",
        ) from exc


# 🛑 ZERO-GAP: Admin Evolution Proposals API Routing
# Issue #1663 (unbounded query — OOM risk): the endpoint used to SELECT ALL
# proposals with no LIMIT — the admin dashboard would hang or OOM on large
# tables. Now bounded: `limit` defaults to 50 and is hard-capped at 200,
# `offset` enables pagination. The response stays a bare list, so existing
# clients remain compatible.
MAX_PROPOSALS_PAGE_SIZE = 200


@router.get("/proposals")
async def list_proposals(
    admin: dict = Depends(require_admin_token),
    session: AsyncSession = Depends(get_db_session),
    limit: int = Query(default=50, ge=1, le=MAX_PROPOSALS_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
):
    """
    List AI code proposals for admin review, newest first (paginated).

    বাংলা: প্রস্তাবগুলো নতুন-থেকে-পুরনো ক্রমে পেজিনেশন সহ ফেরত দেয়।
    `limit` ডিফল্ট ৫০ (সর্বোচ্চ ২০০), `offset` দিয়ে পেজ স্কিপ করা যায়।
    """
    result = await session.execute(
        select(CodeProposal).order_by(CodeProposal.created_at.desc()).offset(offset).limit(limit)
    )
    proposals = result.scalars().all()
    # Serialize to keep Pydantic serialization happy
    return [
        {
            "id": str(p.id),
            "proposal_id": p.proposal_id,
            "skill_name": p.skill_name,
            "generated_code": p.generated_code,
            "ast_validated": p.ast_validated,
            "ci_passed": p.ci_passed,
            "status": p.status,
            "metadata_json": p.metadata_json,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in proposals
    ]


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: str,
    admin: dict = Depends(require_admin_token),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Manually approve a proposal after security review.
    """
    async with session.begin():
        result = await session.execute(
            select(CodeProposal).where(CodeProposal.proposal_id == proposal_id)
        )
        proposal = result.scalars().first()
        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        proposal.status = "approved"
        # AUD-6.8: provenance — record WHO approved and WHEN (previously the
        # approver identity was silently dropped).
        proposal.metadata_json = {
            **(proposal.metadata_json or {}),
            "approval": {
                "approved_by": admin.get("sub"),
                "approved_at": datetime.now(UTC).isoformat(),
                "role": admin.get("role"),
            },
        }
        # এখানে ভবিষ্যতে আমাদের অটোনোমাস মার্জ লজিক বা GitOps ট্রিগার কল হবে।

    return {
        "status": "success",
        "message": f"Proposal {proposal_id} approved by {admin.get('sub')}.",
        "approved_by": admin.get("sub"),
    }


# 🛑 ZERO-GAP: Swarm Forge API Endpoints
# বাংলা মন্তব্য: ফ্রন্টএন্ড EvolutionForge পেজের সেভ এবং এক্সিকিউট রিকোয়েস্ট হ্যান্ডেল করার জন্য এন্ডপয়েন্ট যোগ করা হলো।

# Issue #446: blueprint persistence root. The old save endpoint returned a
# fabricated success WITHOUT writing anything anywhere (flow_id was just a
# timestamp; execute accepted any id and also fabricated success). Blueprints
# are now really persisted under data/swarm_blueprints/ as JSON files.
_BLUEPRINT_DIR = Path("data") / "swarm_blueprints"


def _blueprint_path(flow_id: str) -> Path:
    """Sanitized on-disk path for a blueprint id (id is validated, not trusted)."""
    safe = "".join(ch for ch in flow_id if ch.isalnum() or ch in "-_")
    if not safe or safe != flow_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid flow_id format (allowed: alphanumerics, dash, underscore)",
        )
    return _BLUEPRINT_DIR / f"{safe}.json"


@router.post("/swarm/forge")
async def save_swarm_blueprint(
    payload: dict,
    admin: dict = Depends(require_admin_token),
):
    """
    Save swarm blueprint configuration to persistent storage (real, not fabricated).

    বাংলা: ব্লুপ্রিন্ট এখন সত্যিই data/swarm_blueprints/ ফোল্ডারে JSON হিসেবে
    সেভ হয় — আগে কোনো সেভই হত না, শুধু ফাঁকি সাকসেস রিটার্ন হত (issue #446)।

    AUDIT-FIX (#1704 P0): আগে এই endpoint-এ কোনো auth dependency ছিল না —
    যে কেউ অথ ছাড়াই blueprint persist করতে পারত। এখন admin-only করা হয়েছে,
    কারণ blueprint পরবর্তী execution-এ প্রভাব ফেলে — high-risk action।
    """
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Blueprint 'name' is required",
        )
    _BLUEPRINT_DIR.mkdir(parents=True, exist_ok=True)
    flow_id = f"flow_{int(time.time() * 1000)}_{secrets.token_hex(3)}"
    record = {
        "flow_id": flow_id,
        "name": name,
        "saved_at": datetime.now(UTC).isoformat(),
        "saved_by": admin.get("sub", "unknown"),
        "blueprint": payload,
    }
    path = _blueprint_path(flow_id)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "Swarm blueprint persisted: %s (%s) by %s -> %s",
        flow_id,
        name,
        admin.get("sub", "unknown"),
        path,
    )
    return {
        "status": "success",
        "message": "Swarm blueprint saved to persistent storage",
        "flow_id": flow_id,
        "persisted": True,
        "path": str(path),
        "saved_by": admin.get("sub", "unknown"),
    }


@router.post("/swarm/forge/{flow_id}/execute")
async def execute_swarm_blueprint(
    flow_id: str,
    payload: dict | None = None,
    admin: dict = Depends(require_admin_token),
):
    """
    Trigger execution of a saved swarm blueprint.

    বাংলা: ব্লুপ্রিন্ট লোড ও ভ্যালিডেশন সত্যিই হয়; কিন্তু এক্সিকিউশন ইঞ্জিন
    এখনো ইমপ্লিমেন্ট হয়নি — তাই এটি সৎভাবে 501 NOT_IMPLEMENTED রিটার্ন করে।
    আগের "executed successfully" ছিল সম্পূর্ণ বানানো (issue #446)।

    AUDIT-FIX (#1704 P0): আগে এই endpoint-এ কোনো auth dependency ছিল না —
    যে কেউ অথ ছাড়াই blueprint execute করতে পারত (ভবিষ্যতে execution engine
    এলে code execution হতে পারত)। এখন admin-only করা হয়েছে।
    """
    path = _blueprint_path(flow_id)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Swarm blueprint '{flow_id}' not found. Save it first via POST /swarm/forge.",
        )
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Saved blueprint '{flow_id}' is unreadable: {exc}",
        ) from exc

    # Audit trail: who attempted execution
    logger.warning(
        "Swarm blueprint execution attempted: %s by %s (admin=%s) — NOT_IMPLEMENTED",
        flow_id,
        admin.get("sub", "unknown"),
        admin.get("role"),
    )

    # The blueprint is real and validated; the execution engine is not built yet.
    # Loud, honest 501 — never a fabricated "executed successfully".
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "error": "SWARM_EXECUTION_NOT_IMPLEMENTED",
            "message": (
                "The blueprint was loaded and validated, but the swarm execution "
                "engine has not been implemented yet — nothing was executed. "
                "Track: GitHub issue #446."
            ),
            "flow_id": flow_id,
            "blueprint_name": record.get("name"),
            "requested_by": admin.get("sub", "unknown"),
        },
    )


# --- Extended Breeder & Oracle Routes ---
# বাংলা মন্তব্য: জেনেটিক প্রম্পট ব্রিডার এবং পারফরম্যান্স মূল্যায়ন এপিআই এন্ডপয়েন্টসমূহ।


class BreedRequest(BaseModel):
    parent_1: dict[str, Any]
    parent_2: dict[str, Any]
    method: str = "uniform"
    mutation_rate: float = 0.05


class PerformanceRequest(BaseModel):
    agent_name: str
    metrics: dict[str, Any]


@router.post("/breed")
# 🛡️ SECURITY FIX: আগে এই endpoint-এ কোনো auth ছিল না — get_db_session() শুধু
# একটা DB connection দেয়, identity check করে না। /breed সত্যিকারের genetic
# breeding চালায়, DB-তে লেখে, এমনকি offspring-কে production-এ promote করতে
# পারে — এই ফাইলের নিজস্ব sibling endpoint (/quarantine, /proposals/approve)
# একই sensitivity-র জন্য require_admin_token ব্যবহার করে, তাই এখানেও একই
# প্যাটার্ন প্রয়োগ করা হলো।
async def breed_agents(
    payload: BreedRequest,
    db: AsyncSession = Depends(get_db_session),
    admin: dict = Depends(require_admin_token),
):
    """Breed new agent genetic offspring from parents."""
    # বাংলা মন্তব্য: জেনেটিক অ্যালগরিদমের মাধ্যমে এজেন্টের জিনোমে ব্রিডিং ও মিউটেশন পরিচালনা এন্ডপয়েন্ট
    config = BreederConfig.from_settings()
    if payload.mutation_rate:
        config = BreederConfig(
            mutation_rate=payload.mutation_rate,
            crossover_rate=config.crossover_rate,
            elite_ratio=config.elite_ratio,
            tournament_size=config.tournament_size,
            max_generations=config.max_generations,
            llm_temperature=config.llm_temperature,
            llm_model_name=config.llm_model_name,
        )
    breeder = AgentBreeder(db, config=config)
    from sqlalchemy import select

    q = select(AgentGenome).where(AgentGenome.agent_name.in_([payload.parent_1, payload.parent_2]))
    r = await db.execute(q)
    genomes = {g.agent_name: g for g in r.scalars().all()}
    if payload.parent_1 not in genomes or payload.parent_2 not in genomes:
        raise HTTPException(status_code=404, detail="Parent genomes not found")

    parent_a = genomes[payload.parent_1]
    parent_b = genomes[payload.parent_2]
    offspring = await breeder.breed(parent_a, parent_b)
    await breeder.evaluate_offspring(offspring)
    promoted = await breeder.promote_if_elite(offspring, parent_a, parent_b)

    return {
        "success": True,
        "method": payload.method,
        "inherited_traits": offspring.chromosome,
        "novel_traits": offspring.chromosome,
        "promoted": promoted is not None,
    }


@router.post("/evaluate-performance")
async def evaluate_performance(
    payload: PerformanceRequest,
    db: AsyncSession = Depends(get_db_session),
    admin: dict = Depends(require_admin_token),
):
    """Evaluate agent performance and trigger alerts if thresholds are breached."""
    # বাংলা মন্তব্য: এজেন্টের কাজের গতি ও নির্ভুলতা বিশ্লেষণ করে কোনো অ্যালার্ট ট্রিগার হচ্ছে কি না তা বের করা
    from models.meta_ai import MetricType, SuggestionAction

    oracle = PerformanceOracle(db)
    for key, value in payload.metrics.items():
        try:
            mtype = MetricType(key)
            await oracle.record_metric(
                agent_name=payload.agent_name,
                metric_type=mtype,
                value=float(value),
                unit="ms" if "time" in key or "latency" in key else "score",
            )
        except (ValueError, TypeError):
            continue

    reports = await oracle.identify_weakest_links([payload.agent_name])
    alerts = []
    for r in reports:
        if r.agent_name == payload.agent_name and r.suggestion != SuggestionAction.NO_ACTION:
            alerts.append(
                {
                    "severity": (
                        "critical"
                        if r.suggestion == SuggestionAction.DEPRECATE
                        or r.suggestion == SuggestionAction.REPLACE
                        else "warning"
                    ),
                    "recommended_action": r.suggestion.value,
                    "description": r.reasoning,
                }
            )

    return {
        "success": True,
        "agent_name": payload.agent_name,
        "alerts_triggered": alerts,
        "alerts_count": len(alerts),
    }
