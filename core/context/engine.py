"""ContextEngine (M2-B) — smallest-sufficient-context assembly boundary.

Roadmap M2: assemble context over **existing** Files/Memory/RAG with L0/L1/L2
layering, scope chain, provenance + tenant filter on EVERY item, and a
token budget. No new context database — sources are injectable adapters
over the existing retrieval surfaces (memory_service.recall_memories,
chat_attachments metadata, rag/vector stores).

Invariants enforced here (roadmap §19):
- **Tenant filter**: a candidate whose ``user_id`` does not equal the
  request scope's ``user_id`` is dropped BEFORE it can become an item
  (deny-by-default; only sources explicitly marking a candidate
  ``public=True`` may pass, and such items are labeled ``public``).
- **Provenance**: every admitted item carries immutable provenance; the
  bundle exposes the full provenance list (audit contract).
- **Budget honesty**: the packer's drop report is part of the bundle.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from context.budget import BudgetReport, ContextBudget, pack_items
from context.items import ContextItem, ItemKind, Provenance, SummaryLevel
from context.scopes import (
    Scope,
    ScopeChainError,
    ScopeLevel,
    scope_match_score,
    validate_scope,
)
from core.llm.token_budget import estimate_tokens

#: A source adapter: (scope, query) -> candidates. Each wraps ONE existing
#: retrieval surface; the engine owns filtering/scoring/packing.
SourceFn = Callable[[Scope, str], Awaitable[Iterable["RawCandidate"]]]


@dataclass(frozen=True)
class RawCandidate:
    """What a source adapter yields — NOT yet admitted into context.

    Two orthogonal levels:
    - ``layer`` — L0/L1/L2 summary granularity (OSS plan §4);
    - ``item_scope`` — chain position for scope-match scoring (chat/run/…).
    """

    content: str
    source_type: str
    source_ref: str
    user_id: str | None = None  # tenant owner; engine enforces the match
    layer: str = SummaryLevel.L2.value  # "l0" | "l1" | "l2"
    item_scope: str = "chat"  # ScopeLevel value (chain position)
    kind: ItemKind = ItemKind.rag_chunk
    base_score: float = 0.0
    content_hash: str | None = None
    created_at: datetime | None = None
    # Explicit public mark: allows background material past the tenant
    # filter. Deny-by-default otherwise.
    public: bool = False


@dataclass(frozen=True)
class ContextBundle:
    """The assembled result: admitted items + audit trail + rendered text."""

    scope: Scope
    query: str
    items: tuple[ContextItem, ...]
    report: BudgetReport
    rendered: str
    dropped_candidates: tuple[dict, ...] = field(default_factory=tuple)

    @property
    def total_tokens(self) -> int:
        return self.report.admitted_tokens

    def provenance_list(self) -> list[dict]:
        return [item.provenance.as_detail() for item in self.items]

    def as_detail(self) -> dict:
        return {
            "scope": self.scope.as_dict(),
            "query_chars": len(self.query),
            "items": [i.as_detail() for i in self.items],
            "budget": self.report.as_detail(),
            "dropped_candidates": list(self.dropped_candidates),
        }


def _safe_summary_level(raw: str) -> SummaryLevel:
    try:
        return SummaryLevel(raw)
    except ValueError:
        return SummaryLevel.L2  # most conservative fallback


def _safe_scope_level(raw: str) -> ScopeLevel:
    try:
        return ScopeLevel(raw)
    except ValueError:
        return ScopeLevel.GLOBAL  # broadest fallback (weakest scope claim)


def render_bundle(bundle: ContextBundle) -> str:
    """Deterministic text rendering (provenance refs inline, no payloads)."""
    lines = [f"[context scope={bundle.scope.level.value} items={len(bundle.items)}]"]
    current_kind: ItemKind | None = None
    for item in bundle.items:
        if item.kind != current_kind:
            current_kind = item.kind
            lines.append(f"## {current_kind.value}")
        lines.append(
            f"- ({item.summary_level.value}; src={item.provenance.source_ref}) {item.content}"
        )
    return "\n".join(lines)


class ContextEngine:
    """Injectable-sources context assembler (offline-testable)."""

    def __init__(
        self,
        *,
        memory_source: SourceFn | None = None,
        file_source: SourceFn | None = None,
        rag_source: SourceFn | None = None,
        conversation_source: SourceFn | None = None,
        estimator: Callable[[str], int] = estimate_tokens,
    ) -> None:
        self._sources: list[tuple[SourceFn, str]] = [
            (fn, name)
            for fn, name in (
                (memory_source, "memory"),
                (file_source, "file"),
                (rag_source, "rag"),
                (conversation_source, "conversation"),
            )
            if fn is not None
        ]
        self._estimate = estimator

    async def assemble(
        self,
        *,
        scope: Scope,
        query: str,
        budget: ContextBudget | None = None,
    ) -> ContextBundle:
        """Assemble the bundle for (scope, query) under the budget.

        Raises ScopeChainError for malformed scopes (a required level
        without identity, or narrower ids than the requested level).
        """
        validate_scope(scope)
        budget = budget or ContextBudget()

        candidates: list[RawCandidate] = []
        for fn, _name in self._sources:
            candidates.extend(await fn(scope, query))

        admitted_items, dropped_candidates = self._filter_and_score(candidates, scope)
        packed, report = pack_items(admitted_items, budget, estimate_tokens=self._estimate)

        bundle = ContextBundle(
            scope=scope,
            query=query,
            items=tuple(packed),
            report=report,
            rendered="",
            dropped_candidates=tuple(dropped_candidates),
        )
        return ContextBundle(
            scope=scope,
            query=query,
            items=bundle.items,
            report=report,
            rendered=render_bundle(bundle),
            dropped_candidates=bundle.dropped_candidates,
        )

    # ------------------------------------------------------------------
    # Filtering + scoring
    # ------------------------------------------------------------------
    def _filter_and_score(
        self,
        candidates: Iterable[RawCandidate],
        scope: Scope,
    ) -> tuple[list[ContextItem], list[dict]]:
        """Tenant filter (deny-by-default) + cross-source hash dedup + score.

        Score composition (recorded in provenance.score_components):
        ``score = 0.7 * base_score + 0.3 * scope_match``.
        """
        items: list[ContextItem] = []
        dropped: list[dict] = []
        by_hash: dict[str, ContextItem] = {}

        for cand in candidates:
            # --- tenant filter (§19): deny-by-default --------------------
            if not cand.public and cand.user_id != scope.user_id:
                dropped.append(
                    {
                        "source_ref": cand.source_ref,
                        "reason": "tenant_mismatch",
                        "claimed_user": cand.user_id,
                    }
                )
                continue

            base = max(0.0, min(1.0, cand.base_score))
            item_scope = _safe_scope_level(cand.item_scope)
            match = scope_match_score(item_scope, scope.level)
            score = round(0.7 * base + 0.3 * match, 4)
            item = ContextItem(
                item_id=cand.source_ref,
                kind=cand.kind,
                summary_level=_safe_summary_level(cand.layer),
                content=cand.content,
                score=score,
                tokens=None,
                provenance=Provenance(
                    source_type=cand.source_type,
                    source_ref=cand.source_ref,
                    user_id=cand.user_id or "public",
                    scope_level=item_scope.value,
                    content_hash=cand.content_hash,
                    created_at=cand.created_at or datetime.now(UTC),
                    score_components={"base": base, "scope_match": match},
                ),
            )

            # --- cross-source dedup by content hash (keep highest score) --
            if cand.content_hash:
                existing = by_hash.get(cand.content_hash)
                if existing is not None:
                    if item.score > existing.score:
                        items = [i for i in items if i.item_id != existing.item_id]
                        dropped.append(
                            {
                                "source_ref": existing.provenance.source_ref,
                                "reason": "duplicate_hash",
                            }
                        )
                        items.append(item)
                        by_hash[cand.content_hash] = item
                    else:
                        dropped.append({"source_ref": cand.source_ref, "reason": "duplicate_hash"})
                    continue
                by_hash[cand.content_hash] = item

            items.append(item)

        return items, dropped
