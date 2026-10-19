#!/usr/bin/env python3
"""Single Active Claim Quota reference — S06 (task #479).

Enforces Max 1 In-Flight Claim per Agent in the MCP Control Tower.
Today work.claim only checks whether the TARGET issue has an existing
lock; it never asks whether the CALLING agent already holds a live claim
on another open issue, so one agent can hoard the whole board. This
module is the executable, network-free reference for the guard specified
in docs/S06_CLAIM_QUOTA_SPEC.md. The production implementation
(TypeScript, infrastructure/mcp-control-plane bridge.tools.ts) must
satisfy the same decision matrix and the exact rejection envelope.

Claim identity reuses the S0.1 atomic-claim ledger (single line, the
comment IS the ledger):

    <!-- atomic-claim:issue=456,agent=AGENT_ID,ts=2026-10-17T02:40:52Z,ttl=30m -->

Parsers unescape only, never strip HTML comment tags (doctrine x).
Pure functions only; the board snapshot is plain data so the logic is
fully testable offline. Constants are the single source of truth and are
imported by the test suite, never copied.

Self-test: python3 claim_quota_reference.py --self-test
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# --- Single sources of truth (imported by the test suite; never copy) ------
TTL_MINUTES_DEFAULT = 30  # AUTONOMOUS_TRANSIT_PIPELINE.md stale-claim expiry
MAX_ACTIVE_CLAIMS = 1  # task #479 normative limit (supersedes the
# S0.1 placeholder value of 3)
AGENT_CONCURRENCY_LIMIT_REACHED = "AGENT_CONCURRENCY_LIMIT_REACHED"

MESSAGE_TEMPLATE = (
    "Agent '{agent}' already holds active claim on Issue #{issue}. "
    "Submit patch or release before claiming new work."
)

# Granting paths the quota gates. The task text names GRANT_NEW /
# GRANT_RENEW; GRANT_TAKEOVER is included as defense-in-depth because it
# is also a grant (taking a freshly expired lease while holding another
# live claim would reintroduce hoarding). Trim only with an ops note.
QUOTA_APPLIES_TO = frozenset({"GRANT_NEW", "GRANT_RENEW", "GRANT_TAKEOVER"})

_MARKERTED_RE = re.compile(
    r"<!--\s*atomic-claim:issue=(?P<issue>\d+),agent=(?P<agent>[^,]+),"
    r"ts=(?P<ts>[^,]+),ttl=(?P<ttl>\S+?)\s*-->"
)
_ISO = "%Y-%m-%dT%H:%M:%S.%fZ"
_ISO_S = "%Y-%m-%dT%H:%M:%SZ"


def parse_ts(value: str) -> datetime:
    """Parse the ISO-8601 Z timestamps used across the board. Fail-closed."""
    for fmt in (_ISO, _ISO_S):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    raise ValueError(f"unparseable timestamp: {value!r}")


def _aware(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now


def validate_board(board: dict) -> list[dict]:
    """Validate a board snapshot; returns the issues list. Fail-closed."""
    if not isinstance(board, dict) or not isinstance(board.get("issues"), list):
        raise ValueError('board must be {"issues": [...]}')
    for issue in board["issues"]:
        number = issue.get("number")
        if not isinstance(number, int) or number <= 0:
            raise ValueError(f"bad issue number: {number!r}")
    return board["issues"]


def claim_is_released(
    issue: dict, claimed_at: datetime, now: datetime, ttl_minutes: int
) -> bool:
    """Release semantics (spec section 4). A slot is freed when:
    (a) the lease expired (Rule 9, strict-greater: exactly-TTL is live);
    (b) the holding issue is closed;
    (c) the claimant's Bridge Work Order was submitted and verified
        (tower-visible intake ack; board field wo_verified=True).
    """
    if str(issue.get("state", "open")) != "open":
        return True
    if issue.get("wo_verified") is True:
        return True
    if now < claimed_at:
        raise ValueError("clock skew: now earlier than claim time")
    return (now - claimed_at) > timedelta(minutes=ttl_minutes)


def scan_active_claims(board: dict, agent_id: str, now: datetime) -> list[int]:
    """Issue numbers of the agent's live claims on open issues.

    Detection: status:claimed label + latest S0.1 atomic-claim marker.
    Marker-less label-plane claims are honored only when the snapshot
    carries label_claimed_at (Rule 9 parity); unattributable claims
    (no marker, no timestamp) cannot be proven to belong to the agent
    and therefore never block (the guard blocks provable hoards only).
    Malformed markers are ignored (fail-closed garbage handling).
    Deterministic output: ascending issue numbers.
    """
    _aware(now)
    live: list[int] = []
    for issue in validate_board(board):
        if "status:claimed" not in (issue.get("labels") or []):
            continue
        best_ts: datetime | None = None
        best_agent: str | None = None
        for comment in issue.get("comments") or []:
            body = comment.get("body") or ""
            m = _MARKERTED_RE.search(body)
            if not m:
                continue
            marker_issue = int(m.group("issue"))
            if marker_issue != issue["number"]:
                continue  # ledger mismatch = garbage, ignore
            ts = parse_ts(m.group("ts"))
            ttl_raw = m.group("ttl")
            minutes = TTL_MINUTES_DEFAULT
            tm = re.fullmatch(r"(\d+)m", ttl_raw)
            if tm:
                minutes = int(tm.group(1))
            if best_ts is None or ts > best_ts:
                best_ts, best_agent, best_ttl = ts, m.group("agent").strip(), minutes
        if best_ts is None:
            lt = issue.get("label_claimed_at")
            if not lt:
                continue  # unattributable -> never blocks
            best_ts = parse_ts(lt)
            best_agent = issue.get("label_claimed_agent") or "unknown"
            best_ttl = TTL_MINUTES_DEFAULT
        if best_agent != agent_id:
            continue
        if claim_is_released(issue, best_ts, now, best_ttl):
            continue
        live.append(issue["number"])
    return sorted(live)


@dataclass(frozen=True)
class QuotaDecision:
    granted: bool
    code: str
    active_claims: tuple[int, ...]
    blocking_issue: int | None
    message: str


def rejection_payload(agent_id: str, blocking_issue: int) -> dict:
    """The exact MCP rejection envelope mandated by task #479."""
    return {
        "isError": True,
        "code": AGENT_CONCURRENCY_LIMIT_REACHED,
        "message": MESSAGE_TEMPLATE.format(agent=agent_id, issue=blocking_issue),
    }


def enforce_quota(
    board: dict,
    target_issue: int,
    agent_id: str,
    now: datetime,
    target_decision: str | None = None,
    max_active: int = MAX_ACTIVE_CLAIMS,
) -> QuotaDecision:
    """Quota gate for work.claim (spec section 3).

    Runs AFTER the S0.1 target-issue decision matrix and BEFORE any
    write. target_decision is the S0.1 decision for the target issue;
    paths outside QUOTA_APPLIES_TO (e.g. NOOP_SELF idempotent re-claim,
    which mutates nothing) bypass the scan. When target_decision is None
    the scan always runs (conservative default). Multiple live claims
    block on the lowest issue number (deterministic anchor). Re-claiming
    an issue already in the agent's own live set is a renewal of that
    slot, never a hoard.
    """
    _aware(now)
    if not isinstance(max_active, int) or max_active < 1:
        raise ValueError("max_active must be a positive integer")
    if target_decision is not None and target_decision not in QUOTA_APPLIES_TO:
        return QuotaDecision(True, target_decision, (), None, "")
    active = scan_active_claims(board, agent_id, now)
    if target_issue in active:
        active = [n for n in active if n != target_issue]
    if len(active) < max_active:
        code = target_decision or "GRANT_NEW"
        return QuotaDecision(True, code, tuple(active), None, "")
    blocking = min(active)
    return QuotaDecision(
        False,
        AGENT_CONCURRENCY_LIMIT_REACHED,
        tuple(active),
        blocking,
        MESSAGE_TEMPLATE.format(agent=agent_id, issue=blocking),
    )


def _self_test() -> int:
    t0 = parse_ts("2026-10-17T06:00:00Z")
    mid = parse_ts("2026-10-17T06:10:00Z")
    late = parse_ts("2026-10-17T06:31:00Z")

    def snap(rows):
        return {"issues": rows}

    def row(
        num,
        agent,
        ts="2026-10-17T06:00:00Z",
        state="open",
        labels=("status:claimed",),
        wo_verified=False,
    ):
        return {
            "number": num,
            "state": state,
            "labels": list(labels),
            "wo_verified": wo_verified,
            "label_claimed_at": None,
            "comments": [
                {
                    "ts": ts,
                    "body": f"<!-- atomic-claim:issue={num},agent={agent},ts={ts},ttl=30m -->",
                }
            ],
        }

    # spec test 1: clean board, A claims 900 -> GRANT_NEW (Success)
    board = snap([row(900, "agent-a", labels=[]), row(901, "agent-b", labels=[])])
    d = enforce_quota(board, 900, "agent-a", mid)
    assert d.granted and d.code == "GRANT_NEW", d
    # A now holds 900 live; claiming 902 must fail closed
    board = snap(
        [row(900, "agent-a"), row(901, "agent-b"), row(902, "agent-c", labels=[])]
    )
    d = enforce_quota(board, 902, "agent-a", mid)
    assert not d.granted and d.code == AGENT_CONCURRENCY_LIMIT_REACHED, d
    assert d.blocking_issue == 900 and d.active_claims == (900,)
    payload = rejection_payload("agent-a", 900)
    assert payload == {
        "isError": True,
        "code": AGENT_CONCURRENCY_LIMIT_REACHED,
        "message": MESSAGE_TEMPLATE.format(agent="agent-a", issue=900),
    }
    assert (
        "Issue #900" in payload["message"]
        and "Submit patch or release" in payload["message"]
    )
    # different agent still granted (spec test 3)
    d = enforce_quota(board, 902, "agent-c", mid)
    assert d.granted
    # lease expiry frees the slot
    d = enforce_quota(board, 902, "agent-a", late)
    assert d.granted and d.active_claims == ()
    # closed issue frees the slot
    board2 = snap([row(900, "agent-a", state="closed"), row(902, "agent-c", labels=[])])
    assert enforce_quota(board2, 902, "agent-a", mid).granted
    # submitted-and-verified WO frees the slot
    board3 = snap(
        [row(900, "agent-a", wo_verified=True), row(902, "agent-c", labels=[])]
    )
    assert enforce_quota(board3, 902, "agent-a", mid).granted
    # queued WO does NOT free the slot
    board4 = snap(
        [row(900, "agent-a", wo_verified=False), row(902, "agent-c", labels=[])]
    )
    assert not enforce_quota(board4, 902, "agent-a", mid).granted
    # renewal of own held issue never blocked, even at the cap
    board5 = snap([row(900, "agent-a"), row(902, "agent-c", labels=[])])
    d = enforce_quota(board5, 900, "agent-a", mid)
    assert d.granted and d.code == "GRANT_NEW"
    # NOOP_SELF bypasses the scan
    d = enforce_quota(board5, 902, "agent-a", mid, target_decision="NOOP_SELF")
    assert d.granted and d.code == "NOOP_SELF"
    # deterministic blocking anchor: lowest issue number
    board6 = snap(
        [row(910, "agent-a"), row(905, "agent-a"), row(920, "agent-b", labels=[])]
    )
    d = enforce_quota(board6, 920, "agent-a", mid)
    assert d.blocking_issue == 905 and d.active_claims == (905, 910)
    # max_active knob (ops-tunable; default 1 per task #479)
    assert not enforce_quota(board6, 920, "agent-a", mid, max_active=2).granted
    assert enforce_quota(board6, 920, "agent-a", mid, max_active=3).granted
    # fail-closed garbage
    for bad in ({}, {"issues": "x"}, {"issues": [{"number": "z"}]}):
        try:
            scan_active_claims(bad, "agent-a", mid)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
    try:
        enforce_quota(
            snap([row(900, "agent-a")]),
            902,
            "agent-a",
            parse_ts("2026-10-17T05:59:00Z"),
        )
        raise AssertionError("expected clock-skew ValueError")
    except ValueError:
        pass
    try:
        enforce_quota(snap([]), 902, "agent-a", mid, max_active=0)
        raise AssertionError("expected max_active ValueError")
    except ValueError:
        pass
    print("self-test OK: claim_quota_reference")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    print(__doc__)
    sys.exit(2)
