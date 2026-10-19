#!/usr/bin/env python3
"""work.next() reference implementation — S0.3 Computed Actionable Queue (task #458).

Executable, network-free reference for docs/S03_WORK_NEXT_SPEC.md.
One call returns THE claimable task: deterministic ranking over a board
snapshot, claimability via the S0.1 decision matrix (imported from
work_claim_reference — extraction SSOT, never copied), race guard via the
in-flight WO flag (U4 no-duplicates).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from work_claim_reference import (
    GRANT_NEW,
    GRANT_RENEW,
    GRANT_TAKEOVER,
    Claim,
    evaluate_claim,
)

# --- Single sources of truth (imported by tests; never copy) ----------------
PRIORITY_TIERS: dict[str, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
DEFAULT_TIER = 3
RUNNER_UP_COUNT = 3
DECISION_HORIZON_MINUTES = 30  # retry horizon for E_QUEUE_EMPTY agents


class WorkNextError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class IssueState:
    """One row of the board snapshot the tower feeds to work.next()."""

    number: int
    title: str
    state: str = "open"  # open | closed
    labels: tuple[str, ...] = ()
    claim: Claim | None = None  # parsed from the atomic-claim marker (S0.1 ledger)
    has_inflight_wo: bool = False  # WO queued / PR open targeting this issue
    blocked_label: bool = False  # sequence-hold / handoff block
    is_task_issue: bool = True  # False for bridge WOs

    @property
    def priority(self) -> str:
        for label in self.labels:
            head = label.split("-")[0].upper()
            if head in PRIORITY_TIERS:
                return head
        return f"P{DEFAULT_TIER}"

    @property
    def tier(self) -> int:
        return PRIORITY_TIERS.get(self.priority, DEFAULT_TIER)


@dataclass(frozen=True)
class Pick:
    issue: int
    title: str
    priority: str
    claim_decision: str
    why: str


@dataclass(frozen=True)
class WorkNextResult:
    pick: Pick
    runner_ups: tuple[Pick, ...]
    evaluated: int
    excluded: dict[str, int]
    computed_ts: str


def _decide(issue: IssueState, agent_id: str, now: datetime) -> str | None:
    """Return a claim_decision code if claimable, else None (fail-closed)."""
    if issue.state != "open":
        return None
    if not issue.is_task_issue:
        return None
    if issue.blocked_label:
        return None
    if issue.has_inflight_wo:
        return None
    decision = evaluate_claim(issue.claim, issue.number, agent_id, now)
    if decision == "CONFLICT_OTHER":
        return None
    return decision  # GRANT_NEW | NOOP_SELF | GRANT_RENEW | GRANT_TAKEOVER


def _why_for(decision: str) -> str:
    return {
        GRANT_NEW: "unclaimed — one call grants it",
        "NOOP_SELF": "already yours and live — resume",
        GRANT_RENEW: "your claim expired — renewing regrants it",
        GRANT_TAKEOVER: "previous claim expired — takeover allowed",
    }.get(decision, decision)


def _to_pick(issue: IssueState, decision: str) -> Pick:
    return Pick(
        issue=issue.number,
        title=issue.title,
        priority=issue.priority,
        claim_decision=decision,
        why=_why_for(decision),
    )


def work_next(
    snapshot: list[IssueState],
    agent_id: str,
    now: datetime | None = None,
) -> WorkNextResult:
    """The computed queue (spec sections 3-4). Pure; input never mutated."""
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise WorkNextError("INVALID_CLOCK", "now must be timezone-aware")
    if not snapshot:
        raise WorkNextError("E_BOARD_UNAVAILABLE", "empty snapshot is not a board")

    excluded = {"closed": 0, "live_foreign_claim": 0, "inflight": 0, "non_task": 0}
    claimable: list[tuple[int, int, Pick]] = []  # (tier, number, pick)

    for issue in snapshot:
        decision = _decide(issue, agent_id, now)
        if decision is None:
            if issue.state != "open":
                excluded["closed"] += 1
            elif issue.has_inflight_wo:
                excluded["inflight"] += 1
            elif not issue.is_task_issue:
                excluded["non_task"] += 1
            else:
                excluded["live_foreign_claim"] += 1
            continue
        claimable.append((issue.tier, issue.number, _to_pick(issue, decision)))

    claimable.sort(key=lambda t: (t[0], t[1]))
    if not claimable:
        raise WorkNextError(
            "E_QUEUE_EMPTY",
            f"nothing claimable; retry within {DECISION_HORIZON_MINUTES}m claim TTL horizon",
        )

    picks = [p for _, _, p in claimable]
    return WorkNextResult(
        pick=picks[0],
        runner_ups=tuple(picks[1 : 1 + RUNNER_UP_COUNT]),
        evaluated=len(snapshot),
        excluded=excluded,
        computed_ts=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def demo() -> int:
    t0 = datetime(2026, 10, 17, 4, 0, 0, tzinfo=timezone.utc)
    board = [
        IssueState(459, "[S0.4] consolidate 9 MCP tools", labels=("P2-medium",)),
        IssueState(
            402,
            "[Seq 0.2] failover chain",
            labels=("P0-critical",),
            has_inflight_wo=True,
        ),
        IssueState(413, "old P1 task", labels=("P1-high",), state="closed"),
        IssueState(458, "[S0.3] work.next computed queue", labels=("P1-high",)),
        IssueState(387, "ancient unlabeled task", labels=()),
        IssueState(
            453,
            "observability r1",
            labels=("P1-high",),
            claim=Claim(453, "fleet-bot", t0.replace(year=2020)),
        ),
    ]
    res = work_next(board, "zai-agent", now=t0)
    print("pick:", res.pick.issue, res.pick.priority, "-", res.pick.claim_decision)
    print("runners:", [p.issue for p in res.runner_ups])
    print("excluded:", res.excluded)
    return 0


if __name__ == "__main__":
    sys.exit(demo())
