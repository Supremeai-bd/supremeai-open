"""Unified Deployment Tracking (ROADMAP §40, §44).

বাংলা: প্রতিটি deployment record করে যে কোন commit/image কোন resource-এ গেছে।
admin যখন জিজ্ঞাসা করে "What changed? Which commit caused it? Which services
were affected?" — এই tracker উত্তর দেয়।

ROADMAP §44 — correlation IDs (deployment_id, resource_id, commit_sha) দিয়ে
distributed debugging সম্ভব হয়।
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from adaptive_engine._store import get_conn, jdump, jload


class DeploymentStatus(enum.StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    SUPERSEDED = "SUPERSEDED"


class DeploymentStateError(RuntimeError):
    """Raised when an illegal deployment transition occurs."""


class DeploymentNotFoundError(KeyError):
    """Raised when a deployment record is not found."""


class DeploymentRecord(BaseModel):
    """ROADMAP §40 — unified deployment tracking record."""

    deployment_id: str = Field(default_factory=lambda: f"dep-{uuid.uuid4().hex[:16]}")
    resource_id: str
    repository: str
    commit_sha: str | None = None
    image_digest: str | None = None
    environment: str = "production"
    status: DeploymentStatus = DeploymentStatus.PENDING
    health_after_deploy: str | None = None  # HEALTHY/DEGRADED/...
    rollback_status: str | None = None
    triggered_by: str = "system"
    correlation: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None


class DeploymentTracker:
    """Deployment tracking + correlation (ROADMAP §40, §44)."""

    TABLE = "ecosystem_deployments"

    def __init__(self) -> None:
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with get_conn() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
                    deployment_id TEXT PRIMARY KEY,
                    resource_id TEXT NOT NULL,
                    repository TEXT NOT NULL,
                    commit_sha TEXT,
                    image_digest TEXT,
                    environment TEXT NOT NULL DEFAULT 'production',
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    health_after_deploy TEXT,
                    rollback_status TEXT,
                    triggered_by TEXT NOT NULL DEFAULT 'system',
                    correlation TEXT NOT NULL DEFAULT '{{}}',
                    artifacts TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_resource "
                f"ON {self.TABLE}(resource_id, created_at)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_commit ON {self.TABLE}(commit_sha)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_status ON {self.TABLE}(status)"
            )
            conn.commit()

    def start(
        self,
        *,
        resource_id: str,
        repository: str,
        commit_sha: str | None = None,
        image_digest: str | None = None,
        environment: str = "production",
        triggered_by: str = "system",
        correlation: dict[str, Any] | None = None,
    ) -> DeploymentRecord:
        rec = DeploymentRecord(
            resource_id=resource_id,
            repository=repository,
            commit_sha=commit_sha,
            image_digest=image_digest,
            environment=environment,
            status=DeploymentStatus.IN_PROGRESS,
            triggered_by=triggered_by,
            correlation=correlation or {},
        )
        with get_conn() as conn:
            conn.execute(self._insert_sql(), self._row(rec))
            conn.commit()
        return rec

    def finish(
        self,
        deployment_id: str,
        *,
        status: DeploymentStatus,
        health_after_deploy: str | None = None,
        rollback_status: str | None = None,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> DeploymentRecord:
        now = datetime.now(UTC).isoformat()
        with get_conn() as conn:
            conn.execute(
                f"UPDATE {self.TABLE} SET status = ?, health_after_deploy = ?, "
                f"rollback_status = ?, artifacts = ?, updated_at = ?, completed_at = ? "
                f"WHERE deployment_id = ?",
                (
                    status,
                    health_after_deploy,
                    rollback_status,
                    jdump(artifacts or []),
                    now,
                    now,
                    deployment_id,
                ),
            )
            conn.commit()
        return self.get(deployment_id)  # type: ignore[return-value]

    def get(self, deployment_id: str) -> DeploymentRecord | None:
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE deployment_id = ?",
                (deployment_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def list_by_resource(self, resource_id: str, *, limit: int = 20) -> list[DeploymentRecord]:
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE resource_id = ? "
                f"ORDER BY created_at DESC LIMIT ?",
                (resource_id, limit),
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def list_by_commit(self, commit_sha: str) -> list[DeploymentRecord]:
        """ROADMAP §40 — which services were affected by a given commit."""
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE commit_sha = ? ORDER BY created_at DESC",
                (commit_sha,),
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def trace(self, commit_sha: str) -> dict[str, Any]:
        """ROADMAP §40 — full correlation trace for a commit (services + health)."""
        deps = self.list_by_commit(commit_sha)
        return {
            "commit_sha": commit_sha,
            "deployment_count": len(deps),
            "resources_affected": list({d.resource_id for d in deps}),
            "deployments": [d.model_dump() for d in deps],
        }

    # -- internals ----------------------------------------------------------

    def _insert_sql(self) -> str:
        cols = (
            "deployment_id, resource_id, repository, commit_sha, image_digest, "
            "environment, status, health_after_deploy, rollback_status, "
            "triggered_by, correlation, artifacts, created_at, updated_at, "
            "completed_at"
        )
        placeholders = ", ".join(["?"] * 15)
        return f"INSERT INTO {self.TABLE} ({cols}) VALUES ({placeholders})"

    def _row(self, d: DeploymentRecord) -> tuple[Any, ...]:
        return (
            d.deployment_id,
            d.resource_id,
            d.repository,
            d.commit_sha,
            d.image_digest,
            d.environment,
            d.status,
            d.health_after_deploy,
            d.rollback_status,
            d.triggered_by,
            jdump(d.correlation),
            jdump(d.artifacts),
            d.created_at,
            d.updated_at,
            d.completed_at,
        )

    def _from_row(self, row: Any) -> DeploymentRecord:
        return DeploymentRecord(
            deployment_id=row["deployment_id"],
            resource_id=row["resource_id"],
            repository=row["repository"],
            commit_sha=row["commit_sha"],
            image_digest=row["image_digest"],
            environment=row["environment"],
            status=DeploymentStatus(row["status"]),
            health_after_deploy=row["health_after_deploy"],
            rollback_status=row["rollback_status"],
            triggered_by=row["triggered_by"],
            correlation=jload(row["correlation"], {}),
            artifacts=jload(row["artifacts"], []),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_tracker: DeploymentTracker | None = None


def get_deployment_tracker() -> DeploymentTracker:
    global _tracker
    if _tracker is None:
        _tracker = DeploymentTracker()
    return _tracker


__all__ = [
    "DeploymentStatus",
    "DeploymentRecord",
    "DeploymentTracker",
    "get_deployment_tracker",
    "DeploymentStateError",
    "DeploymentNotFoundError",
]
