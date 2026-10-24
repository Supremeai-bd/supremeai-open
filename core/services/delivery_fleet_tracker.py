"""
STATUS: orphaned — see docs/operations/MODULE_STATUS_REGISTRY.md (#449).
SupremeAI — Delivery Fleet Tracker Service
=================================================

Rider tracking system for delivery management.
- Real-time location tracking
- Route optimization
- Status updates
- Delivery verification
- Zero-cost: uses Upstash Redis + free map APIs
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from core.cache import get_cache
from core.logging_config import logger

# ── Constants ────────────────────────────────────────────────────────────────
LOCATION_TTL = 3600  # 1 hour
TRACKING_CACHE_TTL = 1800


class RiderStatus(StrEnum):
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    PICKING_UP = "picking_up"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    UNAVAILABLE = "unavailable"
    OFFLINE = "offline"


@dataclass(frozen=True)
class Location:
    """Geographic location."""

    latitude: float
    longitude: float
    timestamp: datetime


@dataclass(frozen=True)
class Rider:
    """Rider profile and state."""

    rider_id: str
    name: str
    phone: str
    vehicle_type: str
    status: RiderStatus
    current_location: Location | None
    active_order: str | None


@dataclass(frozen=True)
class Order:
    """Delivery order."""

    order_id: str
    customer_id: str
    pickup_location: Location
    dropoff_location: Location
    assigned_rider: str | None
    status: str
    created_at: datetime


class LocationTracker:
    """
    Tracks rider locations with Redis persistence.
    """

    def __init__(self) -> None:
        self.cache = get_cache()

    def _location_key(self, rider_id: str) -> str:
        return f"rider:location:{rider_id}"

    async def update_location(self, rider_id: str, latitude: float, longitude: float) -> Location:
        """Update rider location."""
        location = Location(
            latitude=latitude,
            longitude=longitude,
            timestamp=datetime.now(UTC),
        )

        await self.cache.set(
            self._location_key(rider_id),
            location.__dict__,
            ttl=LOCATION_TTL,
        )

        return location

    async def get_location(self, rider_id: str) -> Location | None:
        """Get rider location."""
        data = await self.cache.get(self._location_key(rider_id))
        if not data:
            return None

        return Location(
            latitude=data.get("latitude", 0),
            longitude=data.get("longitude", 0),
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now(UTC).isoformat())),
        )


class RouteOptimizer:
    """
    Optimizes delivery routes using distance calculations.
    Zero-cost heuristic: uses Haversine distance.
    """

    EARTH_RADIUS_KM = 6371.0

    @staticmethod
    def haversine_distance(loc1: Location, loc2: Location) -> float:
        """Calculate distance between two points."""
        lat1, lon1 = math.radians(loc1.latitude), math.radians(loc1.longitude)
        lat2, lon2 = math.radians(loc2.latitude), math.radians(loc2.longitude)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        # EARTH_RADIUS_KM ধ্রুবকটি RouteOptimizer ক্লাসে ডিফাইন করা আছে, RiderTracker ক্লাসে নয়।
        return round(RouteOptimizer.EARTH_RADIUS_KM * c, 2)

    @classmethod
    def estimate_eta(cls, distance_km: float, avg_speed_kmh: float = 30.0) -> int:
        """Estimate ETA in minutes."""
        return int((distance_km / avg_speed_kmh) * 60)

    async def find_nearest_rider(
        self,
        riders: dict[str, Rider],
        target_location: Location,
    ) -> Rider | None:
        """Find nearest available rider."""
        nearest = None
        min_distance = float("inf")

        for rider in riders.values():
            if rider.status != RiderStatus.AVAILABLE:
                continue

            if not rider.current_location:
                continue

            distance = self.haversine_distance(rider.current_location, target_location)
            if distance < min_distance:
                min_distance = distance
                nearest = rider

        return nearest


class DeliveryFleetTracker:
    """
    Main rider tracking service.
    """

    def __init__(
        self,
        location_tracker: LocationTracker | None = None,
        optimizer: RouteOptimizer | None = None,
    ) -> None:
        self.location = location_tracker or LocationTracker()
        self.optimizer = optimizer or RouteOptimizer()
        self.cache = get_cache()
        self.rider_key = "rider_registry"
        self.order_key = "order_registry"
        self.events: dict[str, list[dict[str, Any]]] = {}
        logger.info("RiderTracker initialized")

    def track_event(
        self, user_id: str, event_type: str, data: dict[str, Any] | None = None
    ) -> None:
        """Track user or rider activity event."""
        if user_id not in self.events:
            self.events[user_id] = []
        self.events[user_id].append(
            {
                "type": event_type,
                "data": data or {},
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    def get_user_events(self, user_id: str) -> list[dict[str, Any]]:
        """Get event log for specified user/rider."""
        return self.events.get(user_id, [])

    def aggregate_metrics(self) -> dict[str, Any]:
        """Aggregate event metrics across all riders/users."""
        total_events = sum(len(evs) for evs in self.events.values())
        return {
            "total_users": len(self.events),
            "total_events": total_events,
        }

    async def register_rider(
        self,
        rider_id: str,
        name: str,
        phone: str,
        vehicle_type: str,
    ) -> Rider:
        """Register a new rider."""
        rider = Rider(
            rider_id=rider_id,
            name=name,
            phone=phone,
            vehicle_type=vehicle_type,
            status=RiderStatus.AVAILABLE,
            current_location=None,
            active_order=None,
        )

        riders = await self.cache.get(self.rider_key) or {}
        riders[rider_id] = rider.__dict__
        await self.cache.set(self.rider_key, riders, ttl=TRACKING_CACHE_TTL)

        return rider

    async def assign_order(self, rider_id: str, order_id: str) -> bool:
        """Assign order to rider."""
        riders = await self.cache.get(self.rider_key) or {}
        if rider_id not in riders:
            return False

        riders[rider_id]["status"] = RiderStatus.ASSIGNED.value
        riders[rider_id]["active_order"] = order_id

        await self.cache.set(self.rider_key, riders, ttl=TRACKING_CACHE_TTL)
        return True

    async def update_order_status(self, order_id: str, status: str) -> bool:
        """Update order status."""
        orders = await self.cache.get(self.order_key) or {}
        if order_id not in orders:
            return False

        orders[order_id]["status"] = status
        await self.cache.set(self.order_key, orders, ttl=TRACKING_CACHE_TTL)

        # Update rider status
        rider_id = orders[order_id].get("assigned_rider")
        if rider_id:
            riders = await self.cache.get(self.rider_key) or {}
            if rider_id in riders:
                riders[rider_id]["status"] = status.lower()
                await self.cache.set(self.rider_key, riders, ttl=TRACKING_CACHE_TTL)

        return True

    async def get_tracking_info(self, order_id: str) -> dict[str, Any]:
        """Get order tracking information."""
        orders = await self.cache.get(self.order_key) or {}
        if order_id not in orders:
            return {}

        order = orders[order_id]
        rider_id = order.get("assigned_rider")

        riders = await self.cache.get(self.rider_key) or {}
        rider = riders.get(rider_id)

        if rider:
            location_data = await self.location.get_location(rider_id)
            return {
                "order_id": order_id,
                "status": order.get("status"),
                "rider": {
                    "name": rider.get("name"),
                    "phone": rider.get("phone"),
                    "status": rider.get("status"),
                    "location": {
                        "lat": location_data.latitude if location_data else None,
                        "lng": location_data.longitude if location_data else None,
                    },
                },
            }

        return {"order_id": order_id, "status": order.get("status")}


# Singleton
_tracker_instance: RiderTracker | None = None


def get_rider_tracker() -> RiderTracker:
    """Get or create the singleton RiderTracker instance."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = RiderTracker()
    return _tracker_instance


# Canonical alias for backward compatibility
RiderTracker = DeliveryFleetTracker

_fleet_tracker_instance: DeliveryFleetTracker | None = None


def get_delivery_fleet_tracker() -> DeliveryFleetTracker:
    """Get or create the singleton DeliveryFleetTracker instance."""
    global _fleet_tracker_instance
    if _fleet_tracker_instance is None:
        _fleet_tracker_instance = DeliveryFleetTracker()
    return _fleet_tracker_instance


get_rider_tracker = get_delivery_fleet_tracker
