"""
STATUS: orphaned — see docs/operations/MODULE_STATUS_REGISTRY.md (#449).
Backward compatibility bridge: re-export all from delivery_fleet_tracker.
Preserves legacy imports for 'services.rider_tracker' and 'backend.services.rider_tracker'.
"""

from services.delivery_fleet_tracker import (  # noqa: F401
    LOCATION_TTL,
    TRACKING_CACHE_TTL,
    DeliveryFleetTracker,
    Location,
    LocationTracker,
    Order,
    Rider,
    RiderStatus,
    RiderTracker,
    RouteOptimizer,
    get_delivery_fleet_tracker,
    get_rider_tracker,
)

__all__ = [
    "LOCATION_TTL",
    "TRACKING_CACHE_TTL",
    "DeliveryFleetTracker",
    "Location",
    "LocationTracker",
    "Order",
    "Rider",
    "RiderStatus",
    "RiderTracker",
    "RouteOptimizer",
    "get_delivery_fleet_tracker",
    "get_rider_tracker",
]
