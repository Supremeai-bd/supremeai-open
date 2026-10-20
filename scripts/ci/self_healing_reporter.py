#!/usr/bin/env python3
"""Rules 16 + 26 (AUTONOMOUS_TRANSIT_PIPELINE.md): self-healing board reporter.

Rule 16 — any CI failure / merge conflict / dead link / runtime probe alert
across federation repositories becomes a dedup-guarded issue on
supremeai-open: identical events never open duplicate issues.

Rule 26 — 3-strike quarantine: an issue that triggers 3 consecutive CI
failures or unclaims locks into status:quarantine, halting agent retries
until admin triage. A pass resets the strike counter.

Pure-stdlib, deterministic, offline-testable reference implementation
for #470. Data-only output: returns plans; callers execute against GitHub.

Self-test: python3 self_healing_reporter.py --self-test
"""

from __future__ import annotations

import hashlib
import json
import re
import sys

QUARANTINE_THRESHOLD = 3
FP_MARKER = "heal-fp"
_FP_IN_BODY = re.compile(r"<!--\s*heal-fp:([0-9a-f]{16})\s*-->")
_KINDS = ("ci_failure", "merge_conflict", "dead_link", "probe_alert", "unclaim")


def fingerprint_event(event: dict) -> str:
    """Deterministic 16-hex dedup fingerprint for a healing event.

    Identity = (repo, kind, key). Volatile fields (ts, run ids, counts)
    are excluded so repeated failures dedup onto one issue.
    """
    if not isinstance(event, dict):
        raise ValueError("event must be a dict")  # noqa: TRY004
    repo, kind, key = event.get("repo"), event.get("kind"), event.get("key")
    if not repo or not isinstance(repo, str):
        raise ValueError("event.repo (str) required")
    if kind not in _KINDS:
        raise ValueError(f"event.kind must be one of {_KINDS}")
    if not key or not isinstance(key, str):
        raise ValueError("event.key (str) required")
    basis = json.dumps([repo, kind, key], separators=(",", ":"))
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def event_title(event: dict) -> str:
    """Deterministic issue title for a healing event (<=80 chars)."""
    return f"self-heal [{event['kind']}]: {event['repo']} :: {event['key']}"[:80]


def _open_fingerprints(existing_issues: list) -> dict:
    """Map fingerprint -> issue number for open issues carrying heal-fp markers."""
    out = {}
    for it in existing_issues or []:
        if "closed" in (it.get("state") or ""):
            continue
        for m in _FP_IN_BODY.finditer(it.get("body") or ""):
            out.setdefault(m.group(1), it.get("number"))
    return out


def dedup_guard(new_events: list, existing_issues: list) -> dict:
    """Rule 16: split new events into to_open vs suppressed (dedup)."""
    seen = _open_fingerprints(existing_issues)
    to_open, suppressed = [], []
    for ev in new_events or []:
        fp = fingerprint_event(ev)
        if fp in seen:
            suppressed.append(
                {
                    "fingerprint": fp,
                    "issue": seen[fp],
                    "key": ev["key"],
                    "reason": "duplicate_of_open_issue",
                }
            )
        else:
            to_open.append(
                {
                    "fingerprint": fp,
                    "title": event_title(ev),
                    "kind": ev["kind"],
                    "repo": ev["repo"],
                    "key": ev["key"],
                    "body_marker": f"<!-- {FP_MARKER}:{fp} -->",
                }
            )
            seen[fp] = None  # same-fingerprint duplicates inside one batch also dedup
    return {"to_open": to_open, "suppressed": suppressed}


def compute_strikes(history: list, issue: int) -> int:
    """Rule 26: consecutive fail/unclaim runs for an issue, newest backwards.

    history: [{"issue": int, "outcome": "pass"|"fail"|"unclaim", "ts": iso}, ...]
    oldest -> newest. A pass resets the count.
    """
    if not isinstance(issue, int) or issue <= 0:
        raise ValueError("issue must be a positive int")
    runs = [h for h in (history or []) if h.get("issue") == issue]
    strikes = 0
    for h in reversed(runs):
        outcome = h.get("outcome")
        if outcome in ("fail", "unclaim"):
            strikes += 1
        elif outcome == "pass":
            break
        else:
            raise ValueError(f"bad outcome {outcome!r}")
    return strikes


def quarantine_decisions(
    history: list, quarantined: set | None = None, threshold: int = QUARANTINE_THRESHOLD
) -> dict:
    """Rule 26 plan: issues crossing the strike threshold (idempotent)."""
    locked = set(quarantined or ())
    issues = sorted({h["issue"] for h in (history or [])})
    quarantine, updates = [], []
    for n in issues:
        if n in locked:
            continue
        strikes = compute_strikes(history, n)
        updates.append({"issue": n, "strikes": strikes})
        if strikes >= threshold:
            quarantine.append(
                {
                    "issue": n,
                    "strikes": strikes,
                    "action": "lock",
                    "label": "status:quarantine",
                }
            )
    return {"quarantine": quarantine, "strike_updates": updates, "threshold": threshold}


def report_plan(
    events: list, existing_issues: list, history: list, quarantined: set | None = None
) -> dict:
    """Combined Rule 16 + Rule 26 plan (deterministic order)."""
    d16 = dedup_guard(events, existing_issues)
    d26 = quarantine_decisions(history, quarantined)
    return {
        "to_open": d16["to_open"],
        "suppressed": d16["suppressed"],
        "quarantine": d26["quarantine"],
        "strike_updates": d26["strike_updates"],
    }


def _self_test() -> int:
    ev = {"repo": "supremeai-open", "kind": "ci_failure", "key": "guard-392"}
    fp1 = fingerprint_event(ev)
    assert fp1 == fingerprint_event(dict(ev)), "fingerprint must be deterministic"
    assert fp1 != fingerprint_event({**ev, "kind": "dead_link"})
    try:
        fingerprint_event({**ev, "kind": "nope"})
        raise AssertionError("expected kind rejection")
    except ValueError:
        pass
    d = dedup_guard(
        [ev, ev],
        [{"number": 5, "state": "open", "body": f"note <!-- {FP_MARKER}:{fp1} -->"}],
    )
    assert not d["to_open"] and len(d["suppressed"]) == 2, d
    d2 = dedup_guard([ev], [])
    assert len(d2["to_open"]) == 1 and not d2["suppressed"]
    d3 = dedup_guard([ev, ev], [])
    assert len(d3["to_open"]) == 1, "in-batch duplicates must dedup"
    hist = [
        {"issue": 9, "outcome": "fail", "ts": "T1"},
        {"issue": 9, "outcome": "fail", "ts": "T2"},
        {"issue": 9, "outcome": "pass", "ts": "T3"},
        {"issue": 9, "outcome": "fail", "ts": "T4"},
    ]
    assert compute_strikes(hist, 9) == 1, "pass resets strikes"
    hist2 = hist[:2]
    assert compute_strikes(hist2, 9) == 2
    q = quarantine_decisions(
        [
            {"issue": 9, "outcome": "fail", "ts": "T1"},
            {"issue": 9, "outcome": "unclaim", "ts": "T2"},
            {"issue": 9, "outcome": "fail", "ts": "T3"},
        ]
    )
    assert len(q["quarantine"]) == 1 and q["quarantine"][0]["strikes"] == 3
    q2 = quarantine_decisions(hist2)
    assert not q2["quarantine"], "2 strikes must not quarantine"
    q3 = quarantine_decisions(hist2, quarantined={9})
    assert not q3["quarantine"], "already-quarantined must be idempotent"
    try:
        compute_strikes(hist, "x")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    print("self-test OK: self_healing_reporter")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    print(__doc__)
    sys.exit(2)
