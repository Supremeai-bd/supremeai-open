"""Provider-neutral task envelope and idempotency primitives."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")


class TaskState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TaskEnvelope:
    task_id: str
    tenant_id: str
    idempotency_key: str
    task_type: str
    payload: dict[str, Any]
    state: TaskState = TaskState.QUEUED
    attempt: int = 0

    def __post_init__(self) -> None:
        for name, value in (
            ("task_id", self.task_id),
            ("tenant_id", self.tenant_id),
            ("idempotency_key", self.idempotency_key),
        ):
            if not _ID_RE.fullmatch(value):
                raise ValueError(f"invalid {name}")
        if not self.task_type or len(self.task_type) > 80:
            raise ValueError("invalid task_type")
        if self.attempt < 0 or self.attempt > 5:
            raise ValueError("attempt must be between 0 and 5")

    @property
    def dedup_key(self) -> str:
        raw = f"{self.tenant_id}:{self.idempotency_key}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "state": self.state.value, "dedup_key": self.dedup_key}


def canonical_payload(payload: dict[str, Any]) -> str:
    """Stable representation for cache and idempotency fingerprints."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


__all__ = ["TaskEnvelope", "TaskState", "canonical_payload"]
