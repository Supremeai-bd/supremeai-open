"""Unified Health Model (ROADMAP §41, §42).

বাংলা: সব provider কে একটি normalized health status-এ আনা হয়:
HEALTHY / DEGRADED / WARNING / CRITICAL / UNKNOWN / MAINTENANCE।

ROADMAP §42 — unified memory model: startup / idle / peak / current / limit /
percent / trend। এটি top memory consumers ও memory regression detection দেয়।
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from adaptive_engine._store import get_conn, jdump, jload


class HealthStatus(enum.StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"
    MAINTENANCE = "MAINTENANCE"


class MemoryInfo(BaseModel):
    """Memory usage snapshot."""

    current_mb: float = 0.0
    peak_mb: float = 0.0
    limit_mb: float = 0.0
    percent: float = 0.0
    trend: str = "stable"


# বাংলা: ROADMAP §41 — severity ordering, composite scoring-এ ব্যবহৃত।
_SEVERITY = {
    HealthStatus.HEALTHY: 0,
    HealthStatus.MAINTENANCE: 1,
    HealthStatus.UNKNOWN: 2,
    HealthStatus.WARNING: 3,
    HealthStatus.DEGRADED: 4,
    HealthStatus.CRITICAL: 5,
}


class UnifiedHealth(BaseModel):
    """ROADMAP §41, §42 — normalized health snapshot for a resource."""

    resource_id: str
    status: HealthStatus = HealthStatus.UNKNOWN
    availability: float = 0.0  # 0..1
    latency_ms: float | None = None
    error_rate: float | None = None  # 0..1
    cpu_percent: float | None = None
    memory_current_mb: float | None = None
    memory_peak_mb: float | None = None
    memory_limit_mb: float | None = None
    memory_percent: float | None = None
    memory_trend: str = "stable"  # increasing | stable | decreasing
    startup_memory_mb: float | None = None
    idle_memory_mb: float | None = None
    version: str | None = None
    dependency_health: dict[str, HealthStatus] = Field(default_factory=dict)
    captured_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


class HealthAggregator:
    """Aggregate health snapshots across the ecosystem (ROADMAP §41)."""

    TABLE = "ecosystem_health"

    def __init__(self) -> None:
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with get_conn() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
                    snapshot_id TEXT PRIMARY KEY,
                    resource_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    availability REAL NOT NULL DEFAULT 0,
                    latency_ms REAL,
                    error_rate REAL,
                    cpu_percent REAL,
                    memory_current_mb REAL,
                    memory_peak_mb REAL,
                    memory_limit_mb REAL,
                    memory_percent REAL,
                    memory_trend TEXT,
                    startup_memory_mb REAL,
                    idle_memory_mb REAL,
                    version TEXT,
                    dependency_health TEXT NOT NULL DEFAULT '{{}}',
                    captured_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{{}}'
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_resource_time "
                f"ON {self.TABLE}(resource_id, captured_at)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_status ON {self.TABLE}(status)"
            )
            conn.commit()

    def record(self, health: UnifiedHealth) -> UnifiedHealth:
        snapshot_id = f"snap-{uuid.uuid4().hex[:16]}"
        with get_conn() as conn:
            conn.execute(
                self._insert_sql(),
                (
                    snapshot_id,
                    health.resource_id,
                    health.status,
                    health.availability,
                    health.latency_ms,
                    health.error_rate,
                    health.cpu_percent,
                    health.memory_current_mb,
                    health.memory_peak_mb,
                    health.memory_limit_mb,
                    health.memory_percent,
                    health.memory_trend,
                    health.startup_memory_mb,
                    health.idle_memory_mb,
                    health.version,
                    jdump({k: str(v) for k, v in health.dependency_health.items()}),
                    health.captured_at,
                    jdump(health.metadata),
                ),
            )
            conn.commit()

        # ROADMAP §15: Health + Deployment Correlation
        if health.status in (HealthStatus.DEGRADED, HealthStatus.DOWN):
            try:
                import logging

                from adaptive_engine.deployment_tracker import get_deployment_tracker

                logger = logging.getLogger(__name__)

                dt = get_deployment_tracker()
                recent_deploys = dt.list_by_resource(health.resource_id, limit=1)
                if recent_deploys:
                    deploy = recent_deploys[0]
                    # If health degraded right after a deployment, flag for rollback
                    logger.warning(
                        f"[Health Correlation] Resource {health.resource_id} is {health.status.value}. "
                        f"Possible cause: Deployment {deploy.deployment_id} (commit: {deploy.commit_sha}). "
                        f"Recommend rollback if condition persists."
                    )
            except Exception as e:
                logger.error(f"[Health Correlation] Error analyzing deployment correlation: {e}")

        return health

    def latest(self, resource_id: str) -> UnifiedHealth | None:
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE resource_id = ? "
                f"ORDER BY captured_at DESC LIMIT 1",
                (resource_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def all_latest(self) -> list[UnifiedHealth]:
        """ROADMAP §47 — admin sees current health of every resource."""
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT h.* FROM {self.TABLE} h "
                f"INNER JOIN ("
                f"  SELECT resource_id, MAX(captured_at) AS max_ts "
                f"  FROM {self.TABLE} GROUP BY resource_id"
                f") latest ON h.resource_id = latest.resource_id "
                f"AND h.captured_at = latest.max_ts"
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def composite_status(self) -> HealthStatus:
        """ROADMAP §41 — single roll-up status across all resources (worst wins)."""
        latest = self.all_latest()
        if not latest:
            return HealthStatus.UNKNOWN
        worst = HealthStatus.HEALTHY
        for h in latest:
            if _SEVERITY[h.status] > _SEVERITY[worst]:
                worst = h.status
        return worst

    def top_memory_consumers(self, limit: int = 10) -> list[UnifiedHealth]:
        """ROADMAP §42 — top memory consumers for resource reallocation."""
        latest = self.all_latest()
        with_mem = [h for h in latest if h.memory_current_mb is not None]
        with_mem.sort(key=lambda h: h.memory_current_mb or 0, reverse=True)
        return with_mem[:limit]

    def detect_memory_regression(
        self, baseline_mb: float, *, tolerance: float = 1.2
    ) -> list[dict[str, Any]]:
        """ROADMAP §42 — flag resources whose current memory exceeds baseline * tolerance."""
        regressions: list[dict[str, Any]] = []
        for h in self.all_latest():
            if h.memory_current_mb and h.memory_current_mb > baseline_mb * tolerance:
                regressions.append(
                    {
                        "resource_id": h.resource_id,
                        "current_mb": h.memory_current_mb,
                        "baseline_mb": baseline_mb,
                        "ratio": round(h.memory_current_mb / baseline_mb, 2),
                        "captured_at": h.captured_at,
                    }
                )
        return regressions

    # -- internals ----------------------------------------------------------

    def _insert_sql(self) -> str:
        cols = (
            "snapshot_id, resource_id, status, availability, latency_ms, "
            "error_rate, cpu_percent, memory_current_mb, memory_peak_mb, "
            "memory_limit_mb, memory_percent, memory_trend, startup_memory_mb, "
            "idle_memory_mb, version, dependency_health, captured_at, metadata"
        )
        placeholders = ", ".join(["?"] * 18)
        return f"INSERT INTO {self.TABLE} ({cols}) VALUES ({placeholders})"

    def _from_row(self, row: Any) -> UnifiedHealth:
        deps = jload(row["dependency_health"], {})
        return UnifiedHealth(
            resource_id=row["resource_id"],
            status=HealthStatus(row["status"]),
            availability=float(row["availability"] or 0),
            latency_ms=row["latency_ms"],
            error_rate=row["error_rate"],
            cpu_percent=row["cpu_percent"],
            memory_current_mb=row["memory_current_mb"],
            memory_peak_mb=row["memory_peak_mb"],
            memory_limit_mb=row["memory_limit_mb"],
            memory_percent=row["memory_percent"],
            memory_trend=row["memory_trend"] or "stable",
            startup_memory_mb=row["startup_memory_mb"],
            idle_memory_mb=row["idle_memory_mb"],
            version=row["version"],
            dependency_health={k: HealthStatus(v) for k, v in deps.items()},
            captured_at=row["captured_at"],
            metadata=jload(row["metadata"], {}),
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_agg: HealthAggregator | None = None


def get_health_aggregator() -> HealthAggregator:
    global _agg
    if _agg is None:
        _agg = HealthAggregator()
    return _agg


__all__ = [
    "HealthStatus",
    "MemoryInfo",
    "UnifiedHealth",
    "HealthAggregator",
    "get_health_aggregator",
]
