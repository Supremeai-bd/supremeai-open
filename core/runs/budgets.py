"""Budget enforcement for canonical Runs (M1-B).

Roadmap M1: budgets = wall-clock / token / tool-call / retry — colibrì-free,
no new infra (plain DB columns on ``runs`` + this enforcement helper).

Pure functions over a budget snapshot (:class:`BudgetSnapshot`): given the
run's limits and consumption, return a :class:`BudgetVerdict`. The service
layer (:mod:`runs.service`) calls these BEFORE mutating a run and records a
``budget_exceeded`` event when a verdict fails. No DB coupling — fully
unit-testable.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class BudgetDimension(enum.StrEnum):
    """Which budget a verdict refers to."""

    wall_clock = "wall_clock"
    tokens = "tokens"
    tool_calls = "tool_calls"
    retries = "retries"


@dataclass(frozen=True)
class BudgetSnapshot:
    """Immutable view of a run's budget limits + consumption.

    ``None`` limits mean "no explicit cap" (the roadmap allows uncapped
    runs; production policy may set defaults at the service/policy layer).
    """

    max_wall_clock_ms: int | None = None
    max_tokens: int | None = None
    max_tool_calls: int | None = None
    max_retries: int | None = None

    tokens_used: int = 0
    tool_calls_used: int = 0
    retries_used: int = 0
    # Elapsed wall-clock since the run entered RUNNING (ms). The service
    # computes this from ``started_at``; a run that never started has 0.
    wall_clock_ms_used: int = 0

    def as_detail(self) -> dict[str, int | None]:
        """Structured payload for ``budget_exceeded`` audit events."""
        return {
            "max_wall_clock_ms": self.max_wall_clock_ms,
            "max_tokens": self.max_tokens,
            "max_tool_calls": self.max_tool_calls,
            "max_retries": self.max_retries,
            "tokens_used": self.tokens_used,
            "tool_calls_used": self.tool_calls_used,
            "retries_used": self.retries_used,
            "wall_clock_ms_used": self.wall_clock_ms_used,
        }


@dataclass(frozen=True)
class BudgetVerdict:
    """Result of a budget check — falsy when everything is within budget."""

    ok: bool
    violations: tuple[BudgetDimension, ...] = field(default=())

    def __bool__(self) -> bool:  # pragma: no cover — trivial
        return self.ok

    def as_detail(self) -> dict[str, list[str]]:
        return {"violations": [v.value for v in self.violations]}


def check_budgets(snapshot: BudgetSnapshot) -> BudgetVerdict:
    """Evaluate ALL budget dimensions; report every violation (not first-only).

    A dimension is violated when consumption is STRICTLY GREATER than the
    cap (consuming exactly the budget is legal; exceeding it is not).
    Uncapped dimensions never violate.
    """
    violations: list[BudgetDimension] = []
    if (
        snapshot.max_wall_clock_ms is not None
        and snapshot.wall_clock_ms_used > snapshot.max_wall_clock_ms
    ):
        violations.append(BudgetDimension.wall_clock)
    if snapshot.max_tokens is not None and snapshot.tokens_used > snapshot.max_tokens:
        violations.append(BudgetDimension.tokens)
    if snapshot.max_tool_calls is not None and snapshot.tool_calls_used > snapshot.max_tool_calls:
        violations.append(BudgetDimension.tool_calls)
    if snapshot.max_retries is not None and snapshot.retries_used > snapshot.max_retries:
        violations.append(BudgetDimension.retries)
    return BudgetVerdict(ok=not violations, violations=tuple(violations))


def can_admit_attempt(
    snapshot: BudgetSnapshot,
    *,
    extra_tokens: int = 0,
    extra_tool_calls: int = 0,
) -> BudgetVerdict:
    """Whether ANOTHER attempt (tool call / LLM turn) fits inside the budget.

    Proactive check: a run should consult this before spending, so the
    enforcement boundary stops the work BEFORE the overspend lands (the
    roadmap's "budget-violation count = 0 in prod" metric depends on
    admission control, not post-hoc detection).
    """
    projected = BudgetSnapshot(
        max_wall_clock_ms=snapshot.max_wall_clock_ms,
        max_tokens=snapshot.max_tokens,
        max_tool_calls=snapshot.max_tool_calls,
        max_retries=snapshot.max_retries,
        tokens_used=snapshot.tokens_used + extra_tokens,
        tool_calls_used=snapshot.tool_calls_used + extra_tool_calls,
        retries_used=snapshot.retries_used,
        wall_clock_ms_used=snapshot.wall_clock_ms_used,
    )
    return check_budgets(projected)


def can_retry(snapshot: BudgetSnapshot) -> bool:
    """Whether the retry budget allows one more attempt.

    Shared semantics with the state-machine guard (``max_retries is None or
    retries_used < max_retries``) — kept here so callers can gate retry
    scheduling without touching the state machine.
    """
    return snapshot.max_retries is None or snapshot.retries_used < snapshot.max_retries
