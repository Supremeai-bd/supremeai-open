"""ContextItem + provenance (M2-B) — every context entry is auditable.

Roadmap M2 invariant (§19): provenance + tenant filter enforced on EVERY
item. A ContextItem cannot be constructed without its provenance — the
dataclass has no default for it, and the engine never fabricates one.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from context.scopes import Scope


class SummaryLevel(enum.StrEnum):
    """The L0/L1/L2 layering (OSS plan §4):

    - ``L0`` — small semantic summary (one-two sentences; budgeter's pick)
    - ``L1`` — structured summary (sections/entities/keywords)
    - ``L2`` — raw source content (loaded via ``content_ref``)
    """

    L0 = "l0"
    L1 = "l1"
    L2 = "l2"


class ItemKind(enum.StrEnum):
    """Where a context item came from (existing surfaces only — no new DB)."""

    memory = "memory"  # ai_memory / memory_service recall
    file = "file"  # chat_attachments (L0/L1 metadata + optional L2 load)
    rag_chunk = "rag_chunk"  # vector store / rag_pipeline chunks
    conversation = "conversation"  # in-thread history


@dataclass(frozen=True)
class Provenance:
    """Where an item came from and who can see it — immutable."""

    source_type: str  # ItemKind value or fine-grained subsystem label
    source_ref: str  # e.g. "ai_memory:<uuid>", "chat_attachment:<uuid>"
    user_id: str  # the tenant owner — the engine enforces scope.user_id match
    scope_level: str  # ScopeLevel value the item belongs to
    content_hash: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    score_components: dict[str, float] = field(default_factory=dict)

    def as_detail(self) -> dict[str, str | None]:
        """Audit/serial form (no content — refs only)."""
        return {
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "user_id": self.user_id,
            "scope_level": self.scope_level,
            "content_hash": self.content_hash,
            "created_at": self.created_at.isoformat(),
            "score_components": dict(self.score_components),
        }


@dataclass(frozen=True)
class ContextItem:
    """One admissible unit of context, with mandatory provenance."""

    item_id: str
    kind: ItemKind
    summary_level: SummaryLevel
    content: str  # the text actually injected into the prompt
    score: float  # combined relevance+scope+recency (engine computes)
    provenance: Provenance
    tokens: int | None = None  # filled by the budgeter via the estimator

    def with_tokens(self, tokens: int) -> ContextItem:
        """Budgeter helper — returns a copy carrying the token count."""
        return ContextItem(
            item_id=self.item_id,
            kind=self.kind,
            summary_level=self.summary_level,
            content=self.content,
            score=self.score,
            provenance=self.provenance,
            tokens=tokens,
        )

    def as_detail(self) -> dict:
        """Audit/serial form (content truncated — refs, not payloads)."""
        return {
            "item_id": self.item_id,
            "kind": self.kind.value,
            "summary_level": self.summary_level.value,
            "score": round(self.score, 4),
            "tokens": self.tokens,
            "content_chars": len(self.content),
            "provenance": self.provenance.as_detail(),
        }


def new_item_id(prefix: str) -> str:
    """Deterministic-shape id for items the engine materializes."""
    return f"{prefix}:{uuid.uuid4()}"
