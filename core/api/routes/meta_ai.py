"""Backward compatibility shim for api.routes.meta_ai.

Canonical domain module: api.routes.agent_breeding
"""

from api.routes.agent_breeding import (  # noqa: F401
    AgentStatsResponse,
    BreedRequest,
    BreedResponse,
    MetricRecordRequest,
    MetricRecordResponse,
    PoolCreateRequest,
    PoolResponse,
    TopPerformerResponse,
    WeakestLinkResponse,
    router,
)

__all__ = [
    "router",
    "BreedRequest",
    "BreedResponse",
    "MetricRecordRequest",
    "MetricRecordResponse",
    "AgentStatsResponse",
    "WeakestLinkResponse",
    "TopPerformerResponse",
    "PoolCreateRequest",
    "PoolResponse",
]
