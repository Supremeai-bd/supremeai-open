#!/usr/bin/env python3
"""work.claim reference implementation — S0.1 Atomic Claim Tool (task #456).

This module is the executable, network-free reference for the tower tool
contract specified in docs/S01_ATOMIC_CLAIM_SPEC.md. The production
implementation (TypeScript, infrastructure/mcp-control-plane) must satisfy
the same decision matrix and marker format. Pure functions only in unit
mode; adapters isolate all I/O so the logic is fully testable offline.

Marker comment format (single line, the comment IS the ledger):

    <!-- atomic-claim:issue=456,agent=AGENT_ID,ts=2026-10-17T02:40:52Z,ttl=30m -->

Doctrine: parsers unescape only, never strip HTML comment tags (doctrine x);
constants live here and are imported by tests, never copied (extraction SSOT).
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Protocol

# --- Single sources of truth (imported by the test suite; never copy) ------
TTL_MINUTES = 30            # AUTONOMOUS_TRANSIT_PIPELINE.md stale-claim expiry
MAX_ACTIVE_CLAIMS = 3       # per-agent concurrent live claims
MARKER_PREFIX = "<!-- atomic-claim:"

MARKER_RE = re.compile(
    r"^<!-- atomic-claim:issue=(?P<issue>-?\d+),agent=(?P<agent>[A-Za-z0-9_.:-]+),"
    r"ts=(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z),ttl=(?P<ttl>\d+m) -->$"
)


class ClaimError(Exception):
    """Terminal-safe error; codes mirror the spec section 5 table."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


# --- Decisions (normative, spec section 3) ---------------------------------
GRANT_NEW = "GRANT_NEW"
NOOP_SELF = "NOOP_SELF"
GRANT_RENEW = "GRANT_RENEW"
CONFLICT_OTHER = "CONFLICT_OTHER"
GRANT_TAKEOVER = "GRANT_TAKEOVER"


@dataclass(frozen=True)
class Claim:
    issue: int
    agent: str
    ts: datetime
    ttl_minutes: int = TTL_MINUTES

    @property
    def expires_at(self) -> datetime:
        return self.ts + timedelta(minutes=self.ttl_minutes)

    def is_live(self, now: datetime) -> bool:
        return now < self.expires_at


def build_marker(issue: int, agent: str, ts: datetime, ttl_minutes: int = TTL_MINUTES) -> str:
    """Render the single-line marker comment. Fail-closed on bad input."""
    if issue <= 0:
        raise ClaimError("ISSUE_NOT_FOUND", "issue number must be positive")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", agent or ""):
        raise ClaimError("INVALID_AGENT", "agent id empty or has forbidden characters")
    ts_text = ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"<!-- atomic-claim:issue={issue},agent={agent},ts={ts_text},ttl={ttl_minutes}m -->"


def parse_marker(text: str) -> Optional[Claim]:
    """Parse a marker comment. Unescape-only parsing, never tag-stripping.

    Returns None for any non-marker or malformed input (fail-closed:
    garbage can never be mistaken for a live claim).
    """
    if not text or MARKER_PREFIX not in text:
        return None
    candidate = text.strip()
    m = MARKER_RE.match(candidate)
    if not m:
        return None
    ts = datetime.strptime(m.group("ts"), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return Claim(
        issue=int(m.group("issue")),
        agent=m.group("agent"),
        ts=ts,
        ttl_minutes=int(m.group("ttl").rstrip("m")),
    )


def latest_claim(comments: List[str]) -> Optional[Claim]:
    """Newest well-formed marker wins; malformed markers are ignored."""
    best: Optional[Claim] = None
    for text in comments:
        c = parse_marker(text or "")
        if c is not None and (best is None or c.ts > best.ts):
            best = c
    return best


def evaluate_claim(
    current: Optional[Claim],
    issue_number: int,
    agent_id: str,
    now: datetime,
) -> str:
    """Decision matrix (spec section 3). Pure; raises terminal errors."""
    if issue_number <= 0:
        raise ClaimError("ISSUE_NOT_FOUND")
    if now.tzinfo is None:
        raise ClaimError("INVALID_CLOCK", "now must be timezone-aware")
    if current is None:
        return GRANT_NEW
    if current.issue != issue_number:
        return GRANT_NEW  # marker for a different issue is not a claim here
    if current.agent == agent_id:
        return NOOP_SELF if current.is_live(now) else GRANT_RENEW
    return CONFLICT_OTHER if current.is_live(now) else GRANT_TAKEOVER


# --- Adapter seam: the tower GitHub App implements this ---------------------
class TowerAdapter(Protocol):
    def get_issue(self, number: int) -> Dict[str, object]: ...
    def list_comments(self, number: int) -> List[str]: ...
    def add_label(self, number: int, label: str) -> None: ...
    def remove_label(self, number: int, label: str) -> None: ...
    def post_comment(self, number: int, body: str) -> None: ...
    def append_audit(self, entry: str) -> None: ...


@dataclass
class SimulatedAdapter:
    """In-memory tower stand-in for offline tests and local dry-runs."""

    issues: Dict[int, Dict[str, object]] = field(default_factory=dict)
    comments: Dict[int, List[str]] = field(default_factory=dict)
    audit: List[str] = field(default_factory=list)
    fail_label: bool = False       # inject step-2 failure (atomicity drill)
    fail_comment: bool = False     # inject step-3 failure (rollback drill)

    def get_issue(self, number: int) -> Dict[str, object]:
        if number not in self.issues:
            raise ClaimError("ISSUE_NOT_FOUND")
        return self.issues[number]

    def list_comments(self, number: int) -> List[str]:
        return list(self.comments.get(number, []))

    def add_label(self, number: int, label: str) -> None:
        if self.fail_label:
            raise ClaimError("LABEL_WRITE_FAILED")
        labels = set(self.issues[number].get("labels", []))  # type: ignore[arg-type]
        labels.add(label)
        self.issues[number]["labels"] = sorted(labels)

    def remove_label(self, number: int, label: str) -> None:
        labels = set(self.issues[number].get("labels", []))  # type: ignore[arg-type]
        labels.discard(label)
        self.issues[number]["labels"] = sorted(labels)

    def post_comment(self, number: int, body: str) -> None:
        if self.fail_comment:
            raise ClaimError("COMMENT_WRITE_FAILED")
        self.comments.setdefault(number, []).append(body)

    def append_audit(self, entry: str) -> None:
        self.audit.append(entry)


def work_claim(adapter: TowerAdapter, issue_number: int, agent_id: str, now: datetime) -> str:
    """The atomic transaction (spec section 2). All-or-nothing by rollback.

    Raises ClaimError with a spec-section-5 code on every terminal path.
    """
    issue = adapter.get_issue(issue_number)  # may raise ISSUE_NOT_FOUND
    if str(issue.get("state", "open")) == "closed":
        raise ClaimError("ISSUE_CLOSED")
    current = latest_claim(adapter.list_comments(issue_number))
    decision = evaluate_claim(current, issue_number, agent_id, now)
    if decision == CONFLICT_OTHER:
        raise ClaimError("CLAIM_CONFLICT_OTHER")
    marker = build_marker(issue_number, agent_id, now)
    had_label = "status:claimed" in set(issue.get("labels", []))  # type: ignore[arg-type]
    adapter.add_label(issue_number, "status:claimed")            # step 2
    try:
        adapter.post_comment(issue_number, marker)               # step 3
    except ClaimError:
        if not had_label:                                        # rollback
            adapter.remove_label(issue_number, "status:claimed")
        raise
    if "status:unclaimed" in set(issue.get("labels", [])):       # step 4
        adapter.remove_label(issue_number, "status:unclaimed")
    adapter.append_audit(f"claim:{decision}:{issue_number}:{agent_id}:{now.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    return decision


def main(argv: List[str]) -> int:
    """Dry-run CLI: simulate the decision matrix without any network I/O."""
    usage = (
        "usage: work_claim_reference.py demo\n"
        "Runs a scripted simulation: claim, idempotent re-claim, conflict, "
        "TTL takeover. Useful for reviewing the contract without a tower."
    )
    if not argv or argv[0] != "demo":
        sys.stderr.write(usage + "\n")
        return 2
    ad = SimulatedAdapter()
    ad.issues[456] = {"state": "open", "labels": ["status:unclaimed"]}
    t0 = datetime(2026, 10, 17, 2, 40, 52, tzinfo=timezone.utc)
    t_mid = t0 + timedelta(minutes=10)
    t_late = t0 + timedelta(minutes=TTL_MINUTES + 1)
    print("t0      claim   ->", work_claim(ad, 456, "zai-agent", t0))
    print("t+10m   reclaim ->", work_claim(ad, 456, "zai-agent", t_mid), "(idempotent)")
    try:
        work_claim(ad, 456, "other-bot", t_mid)
    except ClaimError as exc:
        print("t+10m   other   ->", exc.code, "(protected)")
    t_takeover = t_mid + timedelta(minutes=TTL_MINUTES + 1)
    print("t+41m   takeover->", work_claim(ad, 456, "other-bot", t_takeover))
    print("audit  :", "; ".join(ad.audit))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
