"""Deterministic local runtime for replayable realtime and memory promotion."""

from __future__ import annotations

from dataclasses import dataclass, field

from .control_plane import LearningPromotion, MemoryCandidate, RealtimeEnvelope


@dataclass
class LocalRealtimeStream:
    events: list[RealtimeEnvelope] = field(default_factory=list)

    def publish(self, event: RealtimeEnvelope) -> RealtimeEnvelope:
        if any(
            existing.context.tenant_id == event.context.tenant_id
            and existing.sequence == event.sequence
            for existing in self.events
        ):
            return next(
                existing
                for existing in self.events
                if existing.context.tenant_id == event.context.tenant_id
                and existing.sequence == event.sequence
            )
        self.events.append(event)
        return event

    def replay(self, tenant_id: str, after_sequence: int = 0) -> list[RealtimeEnvelope]:
        return sorted(
            (
                event
                for event in self.events
                if event.context.tenant_id == tenant_id and event.sequence > after_sequence
            ),
            key=lambda event: event.sequence,
        )


@dataclass
class LocalMemoryPromotion:
    threshold: float = 0.7
    promoted: dict[str, LearningPromotion] = field(default_factory=dict)

    def evaluate(
        self, candidate: MemoryCandidate, evaluator: str, score: float
    ) -> LearningPromotion:
        if not 0 <= score <= 1:
            raise ValueError("score must be between 0 and 1")
        promoted = score >= self.threshold and candidate.importance >= self.threshold
        result = LearningPromotion(
            candidate.fingerprint,
            evaluator,
            score,
            promoted,
            "meets_threshold" if promoted else "below_threshold",
        )
        self.promoted[candidate.fingerprint] = result
        return result
