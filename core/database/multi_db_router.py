"""
SupremeAI — Multi-Database Router & Transactional Outbox System
===============================================================

Router for multi-database architecture.
- Transactional Outbox Pattern: local write-behind persistence
- Connection pooling & circuit breaker isolation
- Failover handling across Supabase, Cloudflare D1, Upstash Redis & Firestore
- Bangla inline comments for team clarity (AGENTS.md compliant)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from core.cache import get_cache
from core.logging_config import logger
from core.persistence.write_behind import WriteBehindBatcher

# ── Constants & Outbox Batcher ────────────────────────────────────────────────
ROUTING_CACHE_TTL = 300

# বাংলা ব্যাখ্যা: ডাটাবেস আউটবক্স ব্যাচার - ব্যাকগ্রাউন্ড সিঙ্ক ও ফেলওভার নিশ্চিত করার জন্য লোকালে রাইট-বিহাইন্ড মেমোরিতে পেন্ডিং ট্রানজ্যাকশন জমা রাখে।
outbox_batcher = WriteBehindBatcher(
    name="multi_db_outbox", max_batch=50, flush_interval=2.0
)  # M0-D (AUDIT F4): kwarg was max_batch_size; signature is max_batch


class DatabaseType(StrEnum):
    POSTGRES = "postgres"
    D1 = "d1"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    FIREBASE = "firebase"
    MONGODB = "mongodb"
    REDIS = "redis"


class QueryPattern(StrEnum):
    READ = "read"
    WRITE = "write"
    ANALYTICS = "analytics"
    CACHE = "cache"


@dataclass(frozen=True)
class DatabaseConfig:
    """Database connection configuration."""

    db_type: DatabaseType
    connection_string: str
    pool_size: int
    priority: int
    read_replica: bool = False
    is_healthy: bool = True


class MultiDBRouter:
    """
    Routes queries to appropriate database connections with Outbox Pattern & Circuit Breaker.
    """

    def __init__(self) -> None:
        self.cache = get_cache()
        self.databases: dict[str, DatabaseConfig] = {}
        self._connections: dict[str, Any] = {}
        self._circuit_breakers: dict[str, bool] = {}  # True = Open (Unhealthy)
        logger.info("MultiDBRouter initialized with Transactional Outbox integration")

    def register_database(self, name: str, config: DatabaseConfig) -> None:
        """Register a database configuration."""
        self.databases[name] = config
        self._circuit_breakers[name] = False
        # বাংলা ব্যাখ্যা: ডাটাবেস রেজিস্টার করার সময় সার্কিট ব্রেকার ইনিশিয়াল স্টেট হেলাদি (Healthy/Closed) রাখা হয়।

    def mark_unhealthy(self, name: str) -> None:
        """
        Mark database as unhealthy to trip circuit breaker.
        বাংলা ব্যাখ্যা: নির্দিষ্ট ডাটাবেসে ত্রুটি বা রেট-লিমিট (429) আসলে সার্কিট ব্রেকার ট্রিপ করা হয়।
        """
        self._circuit_breakers[name] = True
        logger.warning(f"MultiDBRouter: Circuit breaker TRIPPED for database '{name}'")

    def mark_healthy(self, name: str) -> None:
        """Mark database as healthy."""
        self._circuit_breakers[name] = False
        logger.info(f"MultiDBRouter: Circuit breaker CLOSED (Healthy) for database '{name}'")

    def _select_database(self, pattern: QueryPattern) -> str | None:
        """Select best database for query pattern considering health status."""
        # বাংলা ব্যাখ্যা: শুধু মাত্র সক্রিয় ও সার্কিট ব্রেকার ওপেন না থাকা ডাটাবেস ফিল্টার করা হয়।
        candidates = {
            name: config
            for name, config in self.databases.items()
            if not self._circuit_breakers.get(name, False)
            and (
                (pattern == QueryPattern.READ and not config.read_replica)
                or (pattern == QueryPattern.WRITE and not config.read_replica)
                or (pattern == QueryPattern.ANALYTICS and config.db_type == DatabaseType.POSTGRES)
                or (pattern == QueryPattern.CACHE and config.db_type == DatabaseType.REDIS)
            )
        }

        if not candidates:
            # Fallback to any healthy DB
            candidates = {
                name: cfg
                for name, cfg in self.databases.items()
                if not self._circuit_breakers.get(name, False)
            }

        if not candidates:
            # বাংলা মন্তব্য: সব ডাটাবেসের সার্কিট ব্রেকার open থাকা অবস্থায় নির্বিচারে কোনো একটাকে
            # বেছে নিয়ে নিশ্চিত-ব্যর্থ রিকোয়েস্ট পাঠানো হচ্ছে না — বরং None রিটার্ন করে fail-closed (Patch 15 fix)
            logger.error("MultiDBRouter: All databases unhealthy — refusing to route (fail-closed)")
            return None

        # Select by priority (highest first)
        return max(candidates.items(), key=lambda x: x[1].priority)[0]

    async def route_query(
        self,
        query: str,
        pattern: QueryPattern = QueryPattern.READ,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Route query to appropriate database and handle transactional outbox enqueue on WRITE.

        Args:
            query: SQL or query string.
            pattern: Query pattern type.
            idempotency_key: Optional unique key for idempotent writes.

        Returns:
            Routing decision with target database and outbox status.
        """
        import hashlib

        target_db = self._select_database(pattern)

        if not target_db:
            return {"error": "No databases configured or all circuit breakers open"}

        # বাংলা মন্তব্য: sha256 hash ব্যবহার করা হলো deterministic cache key-এর জন্য (Patch 18 fix)
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        cache_key = f"query_route:{pattern.value}:{query_hash}"
        cached = await self.cache.get(cache_key)
        if cached and pattern == QueryPattern.READ:
            return cached  # type: ignore

        # বাংলা ব্যাখ্যা: রাইট অপারেশনের ক্ষেত্রে ট্রানজ্যাকশনাল আউটবক্সে মেসেজ এঙ্কুউ করা হয় যাতে প্রাইমারি ব্লকিং না ঘটে।
        outbox_enqueued = False
        if pattern == QueryPattern.WRITE:
            outbox_payload = {
                "query": query,
                "target_db": target_db,
                "idempotency_key": idempotency_key,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            outbox_batcher.enqueue(outbox_payload)
            outbox_enqueued = True
            logger.debug(f"MultiDBRouter: Write operation enqueued to Outbox [{target_db}]")

        routing = {
            "target_database": target_db,
            "db_type": self.databases[target_db].db_type.value,
            "pattern": pattern.value,
            "outbox_enqueued": outbox_enqueued,
            "routed_at": datetime.now(UTC).isoformat(),
        }

        if pattern == QueryPattern.READ:
            await self.cache.set(
                cache_key,
                routing,
                ttl=ROUTING_CACHE_TTL,
            )

        return routing

    async def get_connection(self, db_name: str) -> Any | None:
        """Get database connection."""
        return self._connections.get(db_name)

    def set_connection(self, db_name: str, connection: Any) -> None:
        """Set database connection."""
        self._connections[db_name] = connection


# Singleton
_router_instance: MultiDBRouter | None = None


def get_multi_db_router() -> MultiDBRouter:
    """Get or create the singleton MultiDBRouter instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = MultiDBRouter()
    return _router_instance
