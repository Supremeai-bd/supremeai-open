"""Canonical Run lifecycle state machine (M1) — pure functions, fully
unit-testable.

Lifecycle (roadmap M1 / user-approved verdict)
----------------------------------------------
``REQUESTED -> POLICY_CHECKED -> PLANNED -> RUNNING -> terminal -> FINALIZED``

``RUNNING`` carries a sub-state cluster for real execution reality:

- ``WAITING_APPROVAL`` — HITL suspension (approvals via the existing HITL
  contract; ``pending_tasks`` maps onto this cluster).
- ``RETRYING`` — a failure was classified retryable and a next attempt is
  scheduled (retry budget permitting). Cancellation stays legal here.
- ``DEGRADED`` — the run continues with reduced capability instead of
  failing outright.
- ``BLOCKED`` — policy / prerequisite refusal; needs external resolution.

Terminals: ``SUCCEEDED`` / ``FAILED`` / ``CANCELLED``, each of which may be
sealed once more into ``FINALIZED`` (audit-locked: no further mutation —
post-terminal reconciliation, billing flush, artifact GC bookkeeping).

This module imports ONLY the standard library (+ ``runs.retry`` which is
itself stdlib-only) — no database coupling, importable in any environment
(same discipline as ``missions/state_machine.py``).

Guards (enforced by :func:`assert_transition`):
- ``RUNNING -> RETRYING`` requires a *retryable* ``retry_class`` AND a
  non-exhausted retry budget (``max_retries is None or retries_used <
  max_retries``).
- Terminal -> ``FINALIZED`` requires nothing extra (any terminal may seal).
"""

from __future__ import annotations

from runs.retry import is_retryable as _is_retryable_class

# ---------------------------------------------------------------------------
# States (stored as lowercase strings in runs.status)
# ---------------------------------------------------------------------------
REQUESTED = "requested"
POLICY_CHECKED = "policy_checked"
PLANNED = "planned"
RUNNING = "running"
WAITING_APPROVAL = "waiting_approval"
RETRYING = "retrying"
DEGRADED = "degraded"
BLOCKED = "blocked"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"
FINALIZED = "finalized"

#: All valid run states.
STATES: tuple[str, ...] = (
    REQUESTED,
    POLICY_CHECKED,
    PLANNED,
    RUNNING,
    WAITING_APPROVAL,
    RETRYING,
    DEGRADED,
    BLOCKED,
    SUCCEEDED,
    FAILED,
    CANCELLED,
    FINALIZED,
)

#: Fully sealed — audit-locked, no further transitions.
IMMUTABLE_STATES: frozenset[str] = frozenset({FINALIZED})

#: Terminal states: no further execution work; only ``-> FINALIZED`` remains.
TERMINAL_STATES: frozenset[str] = frozenset({SUCCEEDED, FAILED, CANCELLED, FINALIZED})

#: The RUNNING cluster: states in which the run is (or was) actively
#: executing, including its suspended / degraded / blocked forms.
RUNNING_CLUSTER: frozenset[str] = frozenset(
    {RUNNING, WAITING_APPROVAL, RETRYING, DEGRADED, BLOCKED}
)

#: Pre-execution states: nothing has run yet; cancellation is always legal.
PRE_EXECUTION_STATES: frozenset[str] = frozenset({REQUESTED, POLICY_CHECKED, PLANNED})

#: Legal state transitions. ``FINALIZED`` has no outgoing edges. Terminal
#: states' only outgoing edge is the seal into ``FINALIZED``.
LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    REQUESTED: frozenset({POLICY_CHECKED, CANCELLED}),
    POLICY_CHECKED: frozenset({PLANNED, BLOCKED, CANCELLED}),
    PLANNED: frozenset({RUNNING, BLOCKED, CANCELLED}),
    RUNNING: frozenset(
        {SUCCEEDED, FAILED, WAITING_APPROVAL, RETRYING, DEGRADED, BLOCKED, CANCELLED}
    ),
    WAITING_APPROVAL: frozenset({RUNNING, FAILED, CANCELLED}),
    RETRYING: frozenset({RUNNING, FAILED, CANCELLED}),
    DEGRADED: frozenset({RUNNING, SUCCEEDED, FAILED, CANCELLED}),
    BLOCKED: frozenset({RUNNING, FAILED, CANCELLED}),
    SUCCEEDED: frozenset({FINALIZED}),
    FAILED: frozenset({FINALIZED}),
    CANCELLED: frozenset({FINALIZED}),
    FINALIZED: frozenset(),
}


class IllegalTransition(ValueError):
    """Raised when a run state change violates the lifecycle state machine."""


def assert_transition(
    current: str,
    nxt: str,
    *,
    retry_class: str | None = None,
    retries_used: int = 0,
    max_retries: int | None = None,
) -> str:
    """Validate ``current -> nxt`` and return ``nxt`` if legal.

    Args:
        current: current ``runs.status`` value.
        nxt: proposed next state.
        retry_class: classification of the failure being retried (required
            for ``RUNNING -> RETRYING``; see :mod:`runs.retry`).
        retries_used: attempts consumed so far (guard input).
        max_retries: retry budget; ``None`` means "no explicit cap".

    Raises:
        IllegalTransition: when either state is unknown, the edge is not in
            :data:`LEGAL_TRANSITIONS`, or a guard fails:
            - ``RUNNING -> RETRYING`` requires a retryable ``retry_class``
              and ``max_retries is None or retries_used < max_retries``.
    """
    if current not in STATES:
        raise IllegalTransition(f"unknown current run state: {current!r}")
    if nxt not in STATES:
        raise IllegalTransition(f"unknown next run state: {nxt!r}")

    allowed = LEGAL_TRANSITIONS[current]
    if nxt not in allowed:
        raise IllegalTransition(
            f"illegal run transition {current!r} -> {nxt!r}; "
            f"allowed: {sorted(allowed) or '<terminal>'}"
        )

    if current == RUNNING and nxt == RETRYING:
        if retry_class is None:
            raise IllegalTransition("RUNNING -> RETRYING requires a retry_class classification")
        if not _is_retryable_class(retry_class):
            raise IllegalTransition(
                f"retry_class {retry_class!r} is not retryable; the run must "
                "go to FAILED (or WAITING_APPROVAL for approval_required)"
            )
        if max_retries is not None and retries_used >= max_retries:
            raise IllegalTransition(
                f"retry budget exhausted: retries_used={retries_used} >= max_retries={max_retries}"
            )

    return nxt


def is_terminal(state: str) -> bool:
    """Whether ``state`` is terminal (execution work finished)."""
    return state in TERMINAL_STATES


def is_immutable(state: str) -> bool:
    """Whether ``state`` is audit-locked (``FINALIZED``)."""
    return state in IMMUTABLE_STATES


def is_active(state: str) -> bool:
    """Whether ``state`` is inside the RUNNING cluster (work in flight)."""
    return state in RUNNING_CLUSTER
