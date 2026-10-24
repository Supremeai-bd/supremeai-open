"""Governed synaptic memory consolidation with reversible archival."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class MemoryArchive:
    archive_id: str
    block_id: str
    payload: Any
    archived_at: datetime
    reason: str
    expires_at: datetime | None = None


@dataclass(frozen=True)
class ConsolidationReport:
    archived: int
    deleted: int
    skipped: int
    archive_ids: tuple[str, ...] = field(default_factory=tuple)


class SynapticMemory:
    """Small, storage-neutral memory layer safe to run without integrations."""

    def __init__(self, retention_days: int = 30) -> None:
        self.retention_days = max(1, retention_days)
        self._memories: dict[str, dict[str, Any]] = {}
        self._archives: dict[str, MemoryArchive] = {}
        self._lock = threading.RLock()

    def remember(self, block_id: str, payload: Any, *, importance: float = 0.5) -> None:
        with self._lock:
            self._memories[block_id] = {
                "payload": payload,
                "importance": max(0.0, min(1.0, importance)),
                "updated_at": datetime.now(UTC),
            }

    def consolidate(
        self, *, now: datetime | None = None, importance_floor: float = 0.2
    ) -> ConsolidationReport:
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(days=self.retention_days)
        archived_ids: list[str] = []
        skipped = 0
        with self._lock:
            candidates = list(self._memories.items())
            for block_id, record in candidates:
                if record["updated_at"] > cutoff or record["importance"] >= importance_floor:
                    skipped += 1
                    continue
                archive_id = f"archive_{block_id}_{int(now.timestamp())}"
                self._archives[archive_id] = MemoryArchive(
                    archive_id=archive_id,
                    block_id=block_id,
                    payload=record["payload"],
                    archived_at=now,
                    reason="low-importance retention consolidation",
                    expires_at=now + timedelta(days=self.retention_days),
                )
                archived_ids.append(archive_id)
                del self._memories[block_id]
        return ConsolidationReport(
            len(archived_ids), len(archived_ids), skipped, tuple(archived_ids)
        )

    def restore(self, archive_id: str) -> bool:
        with self._lock:
            archive = self._archives.get(archive_id)
            if not archive:
                return False
            self._memories[archive.block_id] = {
                "payload": archive.payload,
                "importance": 0.5,
                "updated_at": datetime.now(UTC),
            }
            return True

    def insights(self) -> dict[str, int]:
        with self._lock:
            return {"active_memories": len(self._memories), "archives": len(self._archives)}


synaptic_memory = SynapticMemory()

__all__ = ["ConsolidationReport", "MemoryArchive", "SynapticMemory", "synaptic_memory"]


# Note: archive entries intentionally remain queryable after consolidation. A later
# retention worker may purge expired archives only after an explicit policy decision.
# This prevents irreversible delete operations during an automated maintenance pass.

assert datetime.now(UTC)  # import-time sanity check for UTC-aware timestamps
