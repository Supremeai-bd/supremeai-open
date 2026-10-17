#!/usr/bin/env python3
"""Rule 9 (AUTONOMOUS_TRANSIT_PIPELINE.md): 30-minute stale claim expiry.

Releases atomic claims that produced no push or PR within the 30-minute
lease. Pure-stdlib, deterministic, offline-testable reference
implementation for the self-healing board (#470).

Design invariants:
- Fail-closed: malformed snapshots raise ValueError, never guess.
- Deterministic: same snapshot + now -> same plan, always.
- Data-only output: returns a plan; callers execute against GitHub.
- Claim identity: parses S0.1 atomic-claim marker comments
  (<!-- atomic-claim:issue=N,agent=A,ts=T,ttl=Xm -->) and plain
  <!-- atomic-claim --> markers.

Self-test: python3 stale_claim_releaser.py --self-test
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone

TTL_MINUTES_DEFAULT = 30

_MARKER_TYPED = re.compile(
    r"<!--\s*atomic-claim:issue=(?P<issue>\d+),agent=(?P<agent>[^,]+),"
    r"ts=(?P<ts>[^,]+),ttl=(?P<ttl>\S+?)\s*-->")
_MARKER_PLAIN = re.compile(r"<!--\s*atomic-claim\s*-->")
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


def parse_atomic_claims(comments: list) -> list:
    """Extract S0.1 atomic-claim events from a comment list (oldest first)."""
    claims = []
    for c in comments or []:
        body = c.get("body") or ""
        m = _MARKER_TYPED.search(body)
        if m:
            ttl_raw = m.group("ttl")
            minutes = TTL_MINUTES_DEFAULT
            tm = re.fullmatch(r"(\d+)m", ttl_raw)
            if tm:
                minutes = int(tm.group(1))
            claims.append({
                "issue": int(m.group("issue")),
                "agent": m.group("agent"),
                "ts": parse_ts(m.group("ts")),
                "ttl_minutes": minutes,
                "marker": "typed",
            })
            continue
        if _MARKER_PLAIN.search(body) and c.get("ts"):
            claims.append({
                "issue": None,
                "agent": c.get("agent") or "unknown",
                "ts": parse_ts(c["ts"]),
                "ttl_minutes": TTL_MINUTES_DEFAULT,
                "marker": "plain",
            })
    return claims


def is_stale(claimed_at: datetime, now: datetime, ttl_minutes: int = TTL_MINUTES_DEFAULT) -> bool:
    """Rule 9: strict-greater comparison; exactly-TTL is NOT stale."""
    if now < claimed_at:
        raise ValueError("clock skew: now earlier than claim time")
    return (now - claimed_at) > timedelta(minutes=ttl_minutes)


def _latest_activity(issue: dict) -> datetime | None:
    stamps = []
    for key in ("last_push_at", "pr_opened_at"):
        v = issue.get(key)
        if v:
            stamps.append(parse_ts(v))
    return max(stamps) if stamps else None


def release_plan(snapshot: dict, now: datetime) -> dict:
    """Compute the Rule 9 release plan for a board snapshot.

    Snapshot shape (fail-closed on missing keys):
    {"issues": [{"number": int, "labels": [str], "comments": [{"ts", "body", "agent"?}],
                 "last_push_at": iso|null, "pr_opened_at": iso|null}]}
    """
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("issues"), list):
        raise ValueError("snapshot must be {\"issues\": [...]}")
    releases, keeps = [], []
    for issue in snapshot["issues"]:
        number = issue.get("number")
        if not isinstance(number, int) or number <= 0:
            raise ValueError(f"bad issue number: {number!r}")
        labels = issue.get("labels") or []
        if "status:claimed" not in labels:
            continue
        claims = parse_atomic_claims(issue.get("comments") or [])
        if not claims:
            # Label-plane claim without marker: treat label timestamp if present.
            lt = issue.get("label_claimed_at")
            if not lt:
                keeps.append({"issue": number, "reason": "no_claim_marker"})
                continue
            claims = [{"agent": "unknown", "ts": parse_ts(lt),
                       "ttl_minutes": TTL_MINUTES_DEFAULT, "marker": "label"}]
        claim = max(claims, key=lambda c: c["ts"])
        activity = _latest_activity(issue)
        if activity is not None and activity > claim["ts"]:
            keeps.append({"issue": number, "agent": claim["agent"],
                          "reason": "activity_after_claim"})
            continue
        if is_stale(claim["ts"], now, claim["ttl_minutes"]):
            releases.append({
                "issue": number,
                "agent": claim["agent"],
                "claimed_at": claim["ts"].strftime(_ISO_S),
                "action": "release",
                "reason": "stale_lease_expired",
                "lease_minutes": claim["ttl_minutes"],
            })
        else:
            keeps.append({"issue": number, "agent": claim["agent"],
                          "reason": "lease_active"})
    return {"releases": releases, "keeps": keeps,
            "computed_at": now.strftime(_ISO_S)}


def _self_test() -> int:
    t0 = parse_ts("2026-10-17T05:00:00Z")
    cases = [
        ("2026-10-17T05:00:00Z", "2026-10-17T05:29:59Z", 30, False),
        ("2026-10-17T05:00:00Z", "2026-10-17T05:30:00Z", 30, False),
        ("2026-10-17T05:00:00Z", "2026-10-17T05:30:01Z", 30, True),
    ]
    for claimed, now, ttl, want in cases:
        got = is_stale(parse_ts(claimed), parse_ts(now), ttl)
        assert got is want, f"is_stale({claimed},{now},{ttl}) = {got}, want {want}"
    assert parse_atomic_claims([
        {"ts": "2026-10-17T05:00:00Z",
         "body": "<!-- atomic-claim:issue=470,agent=z,ts=2026-10-17T05:00:00Z,ttl=30m -->"}
    ])[0]["agent"] == "z"
    snap = {"issues": [{
        "number": 1, "labels": ["status:claimed"],
        "comments": [{"ts": "2026-10-17T05:00:00Z",
                      "body": "<!-- atomic-claim:issue=1,agent=a,ts=2026-10-17T05:00:00Z,ttl=30m -->"}],
        "last_push_at": None, "pr_opened_at": None}]}
    plan = release_plan(snap, parse_ts("2026-10-17T05:31:00Z"))
    assert len(plan["releases"]) == 1 and plan["releases"][0]["agent"] == "a"
    plan2 = release_plan(snap, parse_ts("2026-10-17T05:29:00Z"))
    assert not plan2["releases"] and plan2["keeps"][0]["reason"] == "lease_active"
    try:
        release_plan({"issues": [{"number": "x"}]}, t0)
        raise AssertionError("expected ValueError for bad number")
    except ValueError:
        pass
    print("self-test OK: stale_claim_releaser")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    if len(sys.argv) == 3 and sys.argv[1] == "--run":
        with open(sys.argv[2], encoding="utf-8") as fh:
            snap = json.load(fh)
        print(json.dumps(release_plan(snap, datetime.now(timezone.utc)), indent=2))
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
