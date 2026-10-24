"""Mission state machine (Task 7-c) — pure functions, fully unit-testable.

States
------
planned → approved → assigned → running → succeeded
                              ↘ failed → repairing → running  (repair loop)
Any of planned/approved/assigned/running → cancelled (terminal)
succeeded / cancelled are terminal; failed is terminal once repair options or
``MAX_REPAIRS`` are exhausted.

Guards (enforced by :func:`assert_transition`):
- ``APPROVED → ASSIGNED`` requires a chosen strategy (``strategy_chosen=True``).
- ``FAILED → REPAIRING`` requires ``repair_count < MAX_REPAIRS`` (const 3).
- ``REPAIRING → RUNNING`` requires the phase cursor to be reset — since that is
  an action (not a checkable fact), :func:`requires_phase_reset` reports it and
  :mod:`missions.service` performs the reset before the transition.

This module has NO imports beyond the standard library — it is importable in
any environment and has no database coupling.
"""

from __future__ import annotations

PLANNED = "planned"
APPROVED = "approved"
ASSIGNED = "assigned"
RUNNING = "running"
REPAIRING = "repairing"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"

#: All valid mission states.
STATES: tuple[str, ...] = (
    PLANNED,
    APPROVED,
    ASSIGNED,
    RUNNING,
    REPAIRING,
    SUCCEEDED,
    FAILED,
    CANCELLED,
)

#: Maximum number of repair rotations a mission may attempt.
MAX_REPAIRS = 3

#: Legal state transitions. Terminal states (succeeded, cancelled) have no
#: outgoing edges; failed's only outgoing edge is the repair loop.
LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    PLANNED: frozenset({APPROVED, CANCELLED}),
    APPROVED: frozenset({ASSIGNED, CANCELLED}),
    ASSIGNED: frozenset({RUNNING, CANCELLED}),
    RUNNING: frozenset({SUCCEEDED, FAILED, CANCELLED}),
    REPAIRING: frozenset({RUNNING, FAILED}),
    SUCCEEDED: frozenset(),
    FAILED: frozenset({REPAIRING}),
    CANCELLED: frozenset(),
}


class IllegalTransition(ValueError):
    """Raised when a mission state change violates the state machine."""


def assert_transition(
    current: str,
    nxt: str,
    *,
    strategy_chosen: bool = True,
    repair_count: int = 0,
) -> str:
    """Validate ``current -> nxt`` and return ``nxt`` if legal.

    Raises:
        IllegalTransition: (a ``ValueError`` subclass) when either state is
            unknown, the edge is not in :data:`LEGAL_TRANSITIONS`, or a guard
            fails:
            - ``APPROVED -> ASSIGNED`` requires ``strategy_chosen=True``;
            - ``FAILED -> REPAIRING`` requires ``repair_count < MAX_REPAIRS``.
    """
    if current not in STATES:
        raise IllegalTransition(f"unknown current mission state: {current!r}")
    if nxt not in STATES:
        raise IllegalTransition(f"unknown next mission state: {nxt!r}")

    allowed = LEGAL_TRANSITIONS[current]
    if nxt not in allowed:
        raise IllegalTransition(
            f"illegal mission transition {current!r} -> {nxt!r}; "
            f"allowed: {sorted(allowed) or '<terminal>'}"
        )

    if current == APPROVED and nxt == ASSIGNED and not strategy_chosen:
        raise IllegalTransition(
            "APPROVED -> ASSIGNED requires a chosen strategy "
            "(set `strategy` or provide `strategy_options`)"
        )

    if current == FAILED and nxt == REPAIRING and repair_count >= MAX_REPAIRS:
        raise IllegalTransition(
            f"FAILED -> REPAIRING requires repair_count < {MAX_REPAIRS} (got {repair_count})"
        )

    return nxt


def requires_phase_reset(current: str, nxt: str) -> bool:
    """Whether the transition demands a phase-cursor reset before it happens.

    The repair loop re-runs the mission from Phase 01, so ``REPAIRING ->
    RUNNING`` must reset the mission's ``current_phase`` (and phase statuses).
    The reset itself is performed by the service layer.
    """
    return (current, nxt) == (REPAIRING, RUNNING)


def is_terminal(state: str) -> bool:
    """Whether ``state`` is terminal (no outgoing transitions)."""
    return not LEGAL_TRANSITIONS.get(state, frozenset())
