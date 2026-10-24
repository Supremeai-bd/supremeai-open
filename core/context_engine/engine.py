"""The Context Engine itself (M2) — deterministic, budgeted prompt assembly.

বাংলা: "Smallest-sufficient-context" নীতি — প্রশ্নের উত্তরে যতটুকু প্রসঙ্গ
যথেষ্ট, তার বেশি কখনোই পাঠানো হয় না। অ্যালগরিদম (সম্পূর্ণ deterministic,
কোনো I/O নেই — টেস্টযোগ্য):

1. user block-গুলো সর্বদা রাখা হয় (hard reserve, যেকোনো user block বাজেটের
   ৫০%-এর বেশি হলে সেটি hard-truncate হয় — রিপোর্টে স্পষ্ট);
2. system block cap-এ রাখা হয় (বাজেটের ২৫%);
3. বাকি জায়গায় memory → knowledge → history ক্রমে priority-ভিত্তিক
   best-fit greedy fill (বড় ব্লক না ঢুকলে ছোটগুলো এখনো ঢুকতে পারে);
4. section header সহ একটি একক prompt string + পূর্ণাঙ্গ রিপোর্ট রিটার্ন।
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from context_engine.budget import (
    SECTION_CAPS,
    estimate_tokens,
    resolve_input_budget,
    resolve_section_caps,
)

_TRUNCATION_MARK = "\n…[context truncated]"


class Section(enum.StrEnum):
    """Prompt sections, in final assembly order."""

    SYSTEM = "system"
    MEMORY = "memory"
    KNOWLEDGE = "knowledge"
    HISTORY = "history"
    USER = "user"


#: Final prompt ordering of the sections.
SECTION_ORDER: tuple[Section, ...] = (
    Section.SYSTEM,
    Section.MEMORY,
    Section.KNOWLEDGE,
    Section.HISTORY,
    Section.USER,
)

_SECTION_HEADERS: dict[Section, str] = {
    Section.SYSTEM: "[System Instructions]",
    Section.MEMORY: "[Relevant Memory Context]",
    Section.KNOWLEDGE: "[System Knowledge Base]",
    Section.HISTORY: "[Conversation History]",
    # No header for USER: the user's message stays the bare tail of the
    # prompt (identical shape to the pre-M2 `f"{memory_ctx}{prompt}"`),
    # which keeps prompt-level caches and provider behaviour unchanged.
}


@dataclass
class ContextBlock:
    """One independently-droppable piece of context.

    ``priority`` — lower value = keep first within its section (0 = highest).
    Ties keep input order (stable sort) so assembly is deterministic.
    """

    section: Section
    text: str
    priority: int = 0
    block_id: str | None = None

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)


@dataclass
class BudgetReport:
    """Observability for one assemble() call."""

    budget: int = 0
    total_tokens: int = 0
    section_tokens: dict[str, int] = field(default_factory=dict)
    kept: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    truncated_sections: list[str] = field(default_factory=list)

    @property
    def fits(self) -> bool:
        return self.total_tokens <= self.budget

    def as_detail(self) -> dict[str, Any]:
        """Structured-log/audit friendly view."""
        return {
            "budget": self.budget,
            "total_tokens": self.total_tokens,
            "fits": self.fits,
            "section_tokens": dict(self.section_tokens),
            "kept": len(self.kept),
            "dropped": list(self.dropped),
            "truncated_sections": list(self.truncated_sections),
        }


@dataclass
class AssembledContext:
    """The assembled prompt + its full budget report."""

    prompt: str
    report: BudgetReport


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Hard-truncate ``text`` to fit ``max_tokens`` (estimate-based).

    The truncation marker's own character cost is reserved up-front so the
    result re-estimates to ≤ ``max_tokens`` (self-consistent accounting).
    """
    if max_tokens <= 0:
        return ""
    max_chars = max_tokens * 4 - len(_TRUNCATION_MARK)
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # Prefer cutting at a sentence boundary when one is nearby.
    for sep in (". ", "। ", "\n"):
        idx = cut.rfind(sep, int(len(cut) * 0.6))
        if idx != -1:
            return cut[: idx + len(sep)].rstrip() + _TRUNCATION_MARK
    return cut.rstrip() + _TRUNCATION_MARK


class ContextEngine:
    """Assemble a budgeted prompt from prioritized context blocks."""

    def assemble(
        self,
        blocks: list[ContextBlock],
        *,
        provider: str | None = None,
        max_input_tokens: int | None = None,
    ) -> AssembledContext:
        """Build the smallest-sufficient prompt within the resolved budget.

        বাংলা: ``provider`` দিলে সেই provider-এর ``max_input_tokens`` বাজেট হয়,
        নাহলে conservative default। রিটার্ন করা prompt কখনোই বাজেট ছাড়ায় না।
        """
        budget = (
            max_input_tokens if max_input_tokens is not None else resolve_input_budget(provider)
        )
        report = BudgetReport(budget=budget)

        by_section: dict[Section, list[ContextBlock]] = {s: [] for s in SECTION_ORDER}
        for b in blocks:
            by_section.setdefault(b.section, []).append(b)

        kept_by_section: dict[Section, list[ContextBlock]] = {s: [] for s in SECTION_ORDER}
        used = 0

        # M07 P-F: caps env-চালিত (zero-hardcode) — ডিফল্ট SECTION_CAPS অপরিবর্তিত।
        caps = resolve_section_caps()

        # 1) USER — hard reserve. Never dropped; any user block that alone
        #    exceeds half the budget is hard-truncated (P-G honesty: the
        #    truncation is always reported — নীরব বাজেট-উল্লঙ্ঘন নিষিদ্ধ),
        #    regardless of arrival order.
        user_blocks = sorted(by_section.get(Section.USER, []), key=lambda b: b.priority)
        user_cap = int(budget * 0.50)
        for b in user_blocks:
            t = b.tokens
            if t > user_cap:
                trimmed = _truncate_to_tokens(b.text, user_cap)
                kept_by_section[Section.USER].append(
                    ContextBlock(Section.USER, trimmed, b.priority, b.block_id)
                )
                used += estimate_tokens(trimmed)
                report.truncated_sections.append(Section.USER.value)
            else:
                kept_by_section[Section.USER].append(b)
                used += t

        # 2) SYSTEM — capped (a runaway system prompt must not crowd out the user).
        #    "One system block is the contract" — অতিরিক্ত system block ফেলে
        #    দেওয়া হয়, কিন্তু drop-টি রিপোর্টে স্পষ্ট থাকে (নীরব বর্জন নিষিদ্ধ)।
        system_blocks = sorted(by_section.get(Section.SYSTEM, []), key=lambda b: b.priority)
        for i, b in enumerate(system_blocks):
            if i > 0:
                report.dropped.append(b.block_id or f"{Section.SYSTEM.value}#{b.priority}")
                continue
            sys_cap = int(budget * caps["system"])
            t = b.tokens
            if t <= sys_cap:
                kept_by_section[Section.SYSTEM].append(b)
                used += t
            else:
                trimmed = _truncate_to_tokens(b.text, sys_cap)
                kept_by_section[Section.SYSTEM].append(
                    ContextBlock(Section.SYSTEM, trimmed, b.priority, b.block_id)
                )
                used += estimate_tokens(trimmed)
                report.truncated_sections.append(Section.SYSTEM.value)

        # 3) Best-fit greedy fill for the droppable sections.
        for section in (Section.MEMORY, Section.KNOWLEDGE, Section.HISTORY):
            remaining = budget - used
            cap = int(budget * caps.get(section.value, 1.0))
            section_used = 0
            ordered = sorted(
                by_section.get(section, []),
                key=lambda b: (b.priority,),  # stable → deterministic ties
            )
            for b in ordered:
                t = b.tokens
                if section_used + t <= cap and t <= remaining:
                    kept_by_section[section].append(b)
                    section_used += t
                    used += t
                    remaining -= t
                else:
                    report.dropped.append(b.block_id or f"{section.value}#{b.priority}")
            if section_used and kept_by_section[section]:
                report.section_tokens[section.value] = section_used

        # 4) Compose the final prompt (stable section order, input order inside).
        parts: list[str] = []
        for section in SECTION_ORDER:
            group = kept_by_section.get(section) or []
            if not group:
                continue
            body = "\n".join(b.text for b in group)
            header = _SECTION_HEADERS.get(section)
            parts.append(f"{header}:\n{body}" if header else body)
            report.section_tokens.setdefault(section.value, sum(b.tokens for b in group))
            report.kept.extend(b.block_id or f"{section.value}#{b.priority}" for b in group)

        # The USER block never carries a section header — it IS the prompt.
        prompt = "\n\n".join(parts)
        report.total_tokens = estimate_tokens(prompt) if prompt else 0
        return AssembledContext(prompt=prompt, report=report)
