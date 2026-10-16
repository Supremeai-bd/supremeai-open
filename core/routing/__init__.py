"""SupremeAI dynamic task routing engine (issue #330).

Offline-safe by doctrine: importing this package performs zero file/network
I/O and has zero third-party dependencies (AGENT_RULES.md §13). All
behaviour lives in :mod:`core.routing.dynamic_router`; this module only
re-exports the public surface.
"""

from core.routing.dynamic_router import (  # noqa: F401
    GRADES,
    ROUTER_CONTRACT_VERSION,
    VALID_PROVIDERS,
    RoutingError,
    TableError,
    build_chain,
    classify_task,
    estimate_cost_usd,
    evaluate_budget,
    load_routing_table,
    route,
    run_chain,
)

__all__ = [
    "GRADES",
    "ROUTER_CONTRACT_VERSION",
    "VALID_PROVIDERS",
    "RoutingError",
    "TableError",
    "build_chain",
    "classify_task",
    "estimate_cost_usd",
    "evaluate_budget",
    "load_routing_table",
    "route",
    "run_chain",
]
