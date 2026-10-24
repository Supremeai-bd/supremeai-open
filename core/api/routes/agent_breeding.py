# backend/api/routes/agent_breeding.py
"""
Layer 6: Self-Evolution (Agent Breeding & Performance Tracking) — REST API Routes.

Endpoints:
- POST /meta-ai/breed              — Run one breeding cycle
- GET  /meta-ai/pool               — List breeding pools
- POST /meta-ai/pool               — Create/update breeding pool
- POST /meta-ai/metrics            — Record a performance metric
- GET  /meta-ai/metrics/{agent}    — Get agent performance stats
- GET  /meta-ai/weakest-links      — Identify and list weakest links
- POST /meta-ai/weakest-links/{id}/ack — Acknowledge a report
- GET  /meta-ai/top-performers     — Top-N performing agents

বাংলা মন্তব্য: Agent breeding, performance tracking, weakest link detection API routes.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.logging_config import logger
from core.self_evolution.agent_breeder import AgentBreeder, BreederConfig
from core.self_evolution.performance_oracle import OracleConfig, PerformanceOracle
from database.session import get_db_session
from models.meta_ai import AgentGenome, BreedingPool, MetricType

router = APIRouter(prefix="/meta-ai", tags=["layer-6-agent-breeding"])

security = HTTPBearer()


# ────────────────────────────────
# Auth helper
# ────────────────────────────────


def _require_admin(credentials: HTTPAuthorizationCredentials) -> dict[str, Any]:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        if payload.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin role required",
            )
        return payload
    except HTTPException:
        raise
    except Exception as e:
        # Fallback: check supremeai token
        expected = getattr(settings, "supremeai_api_token", None) or ""
        if expected and secrets.compare_digest(token.encode(), expected.encode()):
            return {"uid": "admin", "role": "admin"}
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid admin auth: {e}",
        ) from e


# ────────────────────────────────
# Pydantic Request/Response Models
# ────────────────────────────────


class BreedRequest(BaseModel):
    pool_name: str | None = Field(None, description="Specific breeding pool to use")
    parent_a: str | None = Field(None, description="Explicit parent A name")
    parent_b: str | None = Field(None, description="Explicit parent B name")
    offspring_name: str | None = Field(None, description="Desired offspring name")


class BreedResponse(BaseModel):
    success: bool
    offspring: dict[str, Any] | None = None
    message: str


class MetricRecordRequest(BaseModel):
    agent_name: str
    metric_type: MetricType
    value: float
    unit: str = "ms"
    context: dict[str, Any] = Field(default_factory=dict)


class MetricRecordResponse(BaseModel):
    success: bool
    metric_id: uuid.UUID | None = None


class AgentStatsResponse(BaseModel):
    agent_name: str
    stats: dict[str, Any]


class WeakestLinkResponse(BaseModel):
    reports: list[dict[str, Any]]
    generated_at: str


class TopPerformerResponse(BaseModel):
    top_performers: list[dict[str, Any]]


class PoolCreateRequest(BaseModel):
    pool_name: str
    agent_names: list[str]
    min_fitness_threshold: float = 0.6
    max_pool_size: int = 20


class PoolResponse(BaseModel):
    pools: list[dict[str, Any]]


# ────────────────────────────────
# Routes
# ────────────────────────────────


@router.post("/breed", response_model=BreedResponse)
async def run_breeding_cycle(
    request: BreedRequest,
    db: AsyncSession = Depends(get_db_session),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> BreedResponse:
    """
    Run a full breeding cycle: select parents → breed → evaluate → promote.
    """
    _require_admin(credentials)

    breeder = AgentBreeder(db, config=BreederConfig.from_settings())

    try:
        if request.parent_a and request.parent_b:
            # Explicit parents
            from sqlalchemy import select

            q = select(AgentGenome).where(
                AgentGenome.agent_name.in_([request.parent_a, request.parent_b])
            )
            r = await db.execute(q)
            genomes = {g.agent_name: g for g in r.scalars().all()}

            if request.parent_a not in genomes or request.parent_b not in genomes:
                missing = [p for p in [request.parent_a, request.parent_b] if p not in genomes]
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Parent genome(s) not found: {missing}",
                )

            parent_a = genomes[request.parent_a]
            parent_b = genomes[request.parent_b]
            offspring = await breeder.breed(parent_a, parent_b, request.offspring_name)
            await breeder.evaluate_offspring(offspring)
            promoted = await breeder.promote_if_elite(offspring, parent_a, parent_b)
            return BreedResponse(
                success=True,
                offspring={
                    "offspring_name": offspring.offspring_name,
                    "fitness_score": offspring.fitness_score,
                    "crossover_method": offspring.crossover_method,
                    "promoted": promoted is not None,
                },
                message="Custom breeding cycle completed successfully.",
            )
        else:
            promoted = await breeder.run_breeding_cycle(request.pool_name)
            return BreedResponse(
                success=True,
                offspring={
                    "agent_name": promoted.agent_name if promoted else None,
                    "fitness_score": promoted.fitness_score if promoted else None,
                    "promoted": promoted is not None,
                },
                message="Pool breeding cycle completed successfully.",
            )
    except Exception as e:
        logger.error(f"Breeding cycle failed: {e}")
        return BreedResponse(
            success=False,
            message=f"Breeding cycle failed: {e}",
        )


@router.get("/pool", response_model=PoolResponse)
async def list_breeding_pools(
    db: AsyncSession = Depends(get_db_session),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> PoolResponse:
    """List breeding pools."""
    _require_admin(credentials)
    from sqlalchemy import select

    result = await db.execute(select(BreedingPool))
    pools = result.scalars().all()
    return PoolResponse(
        pools=[
            {
                "id": p.id,
                "pool_name": p.pool_name,
                "agent_names": p.agent_names,
                "min_fitness_threshold": p.min_fitness_threshold,
                "max_pool_size": p.max_pool_size,
                "is_active": p.is_active,
            }
            for p in pools
        ]
    )


@router.post("/pool", response_model=dict[str, Any])
async def create_breeding_pool(
    request: PoolCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    """Create or update breeding pool."""
    _require_admin(credentials)
    from sqlalchemy import select

    # Check if pool exists
    q = select(BreedingPool).where(BreedingPool.pool_name == request.pool_name)
    r = await db.execute(q)
    pool = r.scalar_one_or_none()
    if pool:
        pool.agent_names = request.agent_names
        pool.min_fitness_threshold = request.min_fitness_threshold
        pool.max_pool_size = request.max_pool_size
        message = "Breeding pool updated."
    else:
        pool = BreedingPool(
            pool_name=request.pool_name,
            agent_names=request.agent_names,
            min_fitness_threshold=request.min_fitness_threshold,
            max_pool_size=request.max_pool_size,
            is_active=True,
        )
        db.add(pool)
        message = "Breeding pool created."
    await db.commit()
    return {"success": True, "message": message, "pool_name": pool.pool_name}


@router.post("/metrics", response_model=MetricRecordResponse)
async def record_performance_metric(
    request: MetricRecordRequest,
    db: AsyncSession = Depends(get_db_session),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> MetricRecordResponse:
    """Record performance metrics."""
    _require_admin(credentials)
    oracle = PerformanceOracle(db, config=OracleConfig.from_settings())
    metric = await oracle.record_metric(
        agent_name=request.agent_name,
        metric_type=request.metric_type,
        value=request.value,
        unit=request.unit,
        context=request.context,
    )
    return MetricRecordResponse(success=True, metric_id=metric.id)


@router.get("/metrics/{agent}", response_model=AgentStatsResponse)
async def get_agent_stats(
    agent: str,
    lookback_hours: int | None = None,
    db: AsyncSession = Depends(get_db_session),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AgentStatsResponse:
    """Get agent performance stats."""
    _require_admin(credentials)
    oracle = PerformanceOracle(db, config=OracleConfig.from_settings())
    stats = await oracle.get_agent_stats(agent_name=agent, lookback_hours=lookback_hours)
    return AgentStatsResponse(agent_name=agent, stats=stats)


@router.get("/weakest-links", response_model=WeakestLinkResponse)
async def get_weakest_links(
    agent_names: str | None = None,  # Comma separated
    db: AsyncSession = Depends(get_db_session),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> WeakestLinkResponse:
    """Identify and list weakest links."""
    _require_admin(credentials)
    oracle = PerformanceOracle(db, config=OracleConfig.from_settings())
    names_list = [n.strip() for n in agent_names.split(",")] if agent_names else None
    reports = await oracle.identify_weakest_links(names_list)
    return WeakestLinkResponse(
        reports=[
            {
                "id": r.id,
                "agent_name": r.agent_name,
                "composite_score": r.composite_score,
                "response_time_percentile": r.response_time_percentile,
                "accuracy_percentile": r.accuracy_percentile,
                "cost_percentile": r.cost_percentile,
                "error_rate_percentile": r.error_rate_percentile,
                "suggestion": r.suggestion,
                "reasoning": r.reasoning,
                "is_acknowledged": r.is_acknowledged,
            }
            for r in reports
        ],
        generated_at=datetime.now(UTC).isoformat(),
    )


@router.post("/weakest-links/{id}/ack", response_model=dict[str, Any])
async def acknowledge_weakest_link(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    """Acknowledge weakest link report."""
    _require_admin(credentials)
    oracle = PerformanceOracle(db, config=OracleConfig.from_settings())
    success = await oracle.acknowledge_report(id)
    if not success:
        raise HTTPException(status_code=404, detail="WeakestLinkReport not found")
    return {"success": True, "message": "Report acknowledged."}


@router.get("/top-performers", response_model=TopPerformerResponse)
async def get_top_performers(
    limit: int = 5,
    lookback_hours: int | None = None,
    db: AsyncSession = Depends(get_db_session),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TopPerformerResponse:
    """Get top-N performing agents."""
    _require_admin(credentials)
    oracle = PerformanceOracle(db, config=OracleConfig.from_settings())
    performers = await oracle.get_top_performers(limit=limit, lookback_hours=lookback_hours)
    return TopPerformerResponse(top_performers=performers)
