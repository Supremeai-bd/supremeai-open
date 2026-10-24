from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Candidate:
    model: str
    role: str
    content: str
    created_at: str = field(default_factory=utc_now)


@dataclass
class Critique:
    model: str
    role: str
    content: str
    created_at: str = field(default_factory=utc_now)


@dataclass
class KnowledgeArtifact:
    title: str
    domain: str
    claim: str
    solution: str
    assumptions: list[str]
    invariants: list[str]
    failure_modes: list[str]
    counterarguments: list[str]
    evidence: list[str]
    confidence: float
    verification_status: Literal["unverified", "reviewed", "verified"] = "unverified"
    provenance: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    expires_at: str | None = None
    artifact_id: str = ""

    def __post_init__(self) -> None:
        if not self.artifact_id:
            raw = f"{self.domain}|{self.title}|{self.claim}|{self.solution}"
            self.artifact_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def stable_text(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


@dataclass
class SqueezeResult:
    topic: str
    candidates: list[Candidate]
    critiques: list[Critique]
    gaps: list[str]
    artifact: KnowledgeArtifact
    promotion_eligible: bool
    score_breakdown: dict[str, float]
