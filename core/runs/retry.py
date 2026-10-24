"""Retry classification for canonical Runs (M1).

Every failure observed by the execution boundary is classified into exactly
one :class:`RetryClass`. The classification decides whether the run may move
``RUNNING -> RETRYING`` (see :mod:`runs.state_machine` guard) or must go to a
terminal / HITL state.

Roadmap M1 enum (fixed, user-approved):

``transient | rate_limited | dependency_unavailable | policy_blocked |
invalid_input | deterministic | resource_exhausted | approval_required``

Pure module — no imports beyond the standard library.
"""

from __future__ import annotations

import enum

_RETRYABLE = frozenset(
    {"transient", "rate_limited", "dependency_unavailable", "resource_exhausted"}
)


class RetryClass(enum.StrEnum):
    """Why a run (attempt) failed, and whether retrying is meaningful."""

    #: Random hiccup (network blip, temporary IO error) — retry with backoff.
    transient = "transient"
    #: Provider returned 429 / quota throttle — retry with longer backoff.
    rate_limited = "rate_limited"
    #: Upstream dependency down (DB, queue, MCP server) — retry until TTL.
    dependency_unavailable = "dependency_unavailable"
    #: Policy engine refused the action — deterministic refusal, never auto-retry.
    policy_blocked = "policy_blocked"
    #: Caller input failed validation — fixing input is the caller's job.
    invalid_input = "invalid_input"
    #: Failure will reproduce identically (bug, missing resource) — no retry.
    deterministic = "deterministic"
    #: Budget / quota / sandbox capacity exhausted — retry may succeed later,
    #: but only with an explicit budget refresh.
    resource_exhausted = "resource_exhausted"
    #: Human approval required (HITL) — not a retry; route to
    #: ``WAITING_APPROVAL`` and resume via the approval decision.
    approval_required = "approval_required"


#: Classes for which ``RUNNING -> RETRYING`` is legal.
RETRYABLE_CLASSES: frozenset[str] = _RETRYABLE


def is_retryable(retry_class: str | RetryClass | None) -> bool:
    """Whether the classified failure may legally retry.

    ``None`` (unclassified) is never retryable — unclassified failures must
    be classified before a retry decision, keeping the audit trail honest.
    """
    if retry_class is None:
        return False
    return str(retry_class) in _RETRYABLE


def maps_to_waiting_approval(retry_class: str | RetryClass | None) -> bool:
    """Whether the failure is a HITL suspension rather than a failure."""
    if retry_class is None:
        return False
    return str(retry_class) == str(RetryClass.approval_required)
