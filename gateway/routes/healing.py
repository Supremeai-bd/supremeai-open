"""
Backward compatibility bridge: re-export all from healing_stats.
Preserves legacy imports for 'api.routes.healing' and 'backend.api.routes.healing'.
"""

from api.routes.healing_stats import (  # noqa: F401
    get_predictions,
    get_stats,
    router,
)

__all__ = [
    "get_predictions",
    "get_stats",
    "router",
]
