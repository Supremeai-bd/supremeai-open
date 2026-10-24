"""Compatibility bridge: re-export all from workspace_feature_routes.py."""

from api.routes.workspace_feature_routes import (  # noqa: F401
    TIER_S_ROUTER_OBJECTS,
    TIER_S_ROUTERS,
    TIER_S_TABLES_SQL,
    register_tier_s_routes,
    register_workspace_feature_routes,
)

__all__ = [
    "TIER_S_ROUTERS",
    "TIER_S_ROUTER_OBJECTS",
    "TIER_S_TABLES_SQL",
    "register_tier_s_routes",
    "register_workspace_feature_routes",
]
