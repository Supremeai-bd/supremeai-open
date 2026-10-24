"""Context budgeter (M2-B) — smallest-sufficient-context under a budget.

Roadmap M2: yaml-shaped budget (OSS plan §3.4) + token accounting on the
canonical estimator (:func:`core.llm.token_budget.estimate_tokens` — the
repo's budget utility; the M2 measurement harness centralizes on it).

Packing policy (greedy, deterministic, auditable):
1. de-duplicate by ``item_id`` (and by ``provenance.source_ref`` + summary
   level — the same source at the same level must not enter twice);
2. sort by score desc, then by cheaper summary level (L0 < L1 < L2) as a
   tie-break — prefer the smallest sufficient layer;
3. admit items while the running total stays within ``total_tokens``;
   per-kind caps can reserve/limit sections;
4. everything dropped is REPORTED (ids + reasons) — the measurement harness
   reads these reports, nothing is silently lost.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from context.items import ContextItem, ItemKind, SummaryLevel

#: Cheap-layer tie-break order.
_LEVEL_ORDER: dict[SummaryLevel, int] = {
    SummaryLevel.L0: 0,
    SummaryLevel.L1: 1,
    SummaryLevel.L2: 2,
}


@dataclass(frozen=True)
class ContextBudget:
    """OSS-plan-§3.4-shaped budget (yaml-mappable)."""

    total_tokens: int = 4_000
    per_kind: dict[str, int] | None = None  # kind value -> max tokens
    min_score: float = 0.0  # items below are never admitted


@dataclass(frozen=True)
class BudgetReport:
    """What was admitted and what was dropped — the audit trail of packing."""

    requested_items: int = 0
    admitted_items: int = 0
    admitted_tokens: int = 0
    total_tokens: int = 0
    dropped: tuple[dict, ...] = field(default_factory=tuple)

    def as_detail(self) -> dict:
        return {
            "requested_items": self.requested_items,
            "admitted_items": self.admitted_items,
            "admitted_tokens": self.admitted_tokens,
            "total_tokens": self.total_tokens,
            "dropped": list(self.dropped),
        }


def pack_items(
    items: list[ContextItem],
    budget: ContextBudget,
    *,
    estimate_tokens: Callable[[str], int],
) -> tuple[list[ContextItem], BudgetReport]:
    """Greedy score-desc packing with dedup + per-kind caps + drop report."""
    # 1. dedup by item_id, then by (source_ref, summary_level)
    seen_ids: set[str] = set()
    seen_refs: set[tuple[str, str]] = set()
    unique: list[ContextItem] = []
    duplicates = 0
    for item in items:
        ref_key = (item.provenance.source_ref, item.summary_level.value)
        if item.item_id in seen_ids or ref_key in seen_refs:
            duplicates += 1
            continue
        seen_ids.add(item.item_id)
        seen_refs.add(ref_key)
        unique.append(item)

    # 2. score desc; cheaper layer wins ties
    ordered = sorted(unique, key=lambda i: (-i.score, _LEVEL_ORDER[i.summary_level]))

    admitted: list[ContextItem] = []
    dropped: list[dict] = []
    used = 0
    per_kind_used: dict[str, int] = {}
    per_kind_caps = budget.per_kind or {}

    for item in ordered:
        tokens = item.tokens if item.tokens is not None else estimate_tokens(item.content)
        item = item.with_tokens(tokens)
        reason: str | None = None
        if item.score < budget.min_score:
            reason = "below_min_score"
        elif used + tokens > budget.total_tokens:
            reason = "over_total_budget"
        else:
            cap = per_kind_caps.get(item.kind.value)
            if cap is not None and per_kind_used.get(item.kind.value, 0) + tokens > cap:
                reason = "over_kind_cap"
        if reason is not None:
            dropped.append({"item_id": item.item_id, "reason": reason, "tokens": tokens})
            continue
        admitted.append(item)
        used += tokens
        per_kind_used[item.kind.value] = per_kind_used.get(item.kind.value, 0) + tokens

    report = BudgetReport(
        requested_items=len(items),
        admitted_items=len(admitted),
        admitted_tokens=used,
        total_tokens=budget.total_tokens,
        dropped=tuple(dropped),
    )
    return admitted, report
