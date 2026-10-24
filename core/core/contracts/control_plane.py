"""Memory candidate, learning promotion, realtime, and frontend envelopes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .canonical import ExecutionContext
from .redaction import redact


@dataclass(frozen=True)
class MemoryCandidate:
    context: ExecutionContext
    content: str
    importance: float
    source_event_id: str

    def __post_init__(self) -> None:
        if not 0 <= self.importance <= 1:
            raise ValueError("importance must be between 0 and 1")
        if not self.content.strip():
            raise ValueError("memory content cannot be empty")

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(f"{self.context.tenant_id}:{self.content}".encode()).hexdigest()


@dataclass(frozen=True)
class LearningPromotion:
    candidate_fingerprint: str
    evaluator: str
    score: float
    promoted: bool
    reason: str


@dataclass(frozen=True)
class RealtimeEnvelope:
    topic: str
    event: str
    context: ExecutionContext
    sequence: int
    payload: dict[str, Any]

    def to_client_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "event": self.event,
            "sequence": self.sequence,
            "payload": redact(self.payload),
            "correlation_id": self.context.correlation_id,
        }


def frontend_request(
    context: ExecutionContext, action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    if not action or len(action) > 80:
        raise ValueError("invalid frontend action")
    return {"action": action, "context": context.to_dict(), "payload": redact(payload)}


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
