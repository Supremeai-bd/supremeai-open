#!/usr/bin/env python3
"""Bridge Opener Hardening reference — S08 "Mistake Immunity" (task #485).

Eliminates the 4 operational friction points from autonomous intake:
1. Claim hoarding (cross-checks task #479's single-active-claim quota).
2. Brittle punctuation check: has_reflection_evidence must accept
   colon, em-dash, en-dash, and hyphen after "Reflection".
3. Lossy PR body generation: the opener must carry the WO's
   Test Evidence / Reflection Evidence sections VERBATIM into the PR
   body (why + alternatives_rejected) so Knowledge Sharing Guard #392
   passes first-shot.
4. Stale base drift: compare-status verdicts + deterministic rebase
   plans prevent false-positive Stale-Base Guard (#161) blocks.

This module is the offline-testable reference for the exact hunks in
docs/S08_MISTAKE_IMMUNITY_SPEC.md (the production edits land in
scripts/ci/auto_bridge_pr_opener.py and tests/test_ci_guards.py).
Pure functions only; network adapters stay in the opener.

Self-test: python3 bridge_opener_hardening_reference.py --self-test
"""

from __future__ import annotations

import re
import sys

# --- Single sources of truth (imported by the test suite; never copy) ------
REFLECTION_RE = re.compile(r"Reflection\s*[:\u2014\u2013-]\s*\S", re.IGNORECASE)
EVIDENCE_HEADINGS = ("## Test Evidence", "## Reflection Evidence")
FRESH_COMPARE_STATUSES = ("ahead", "identical")
MAX_ACTIVE_CLAIMS = 1  # task #479 normative; detector cross-check


def has_reflection_evidence(wo_body: str) -> bool:
    """Robust typography parser (#485 fix 2): colon, em/en-dash, hyphen.

    Case-insensitive; empty/None body -> False (fail-closed, unchanged).
    """
    return bool(REFLECTION_RE.search(wo_body or ""))


def extract_evidence_sections(wo_body: str) -> str:
    """Lossless evidence transfer (#485 fix 3).

    Returns the verbatim "## Test Evidence" and "## Reflection Evidence"
    sections (each ending before the next "## " heading), joined by a
    blank line, ready to append to the PR body. Missing sections yield
    an empty string — the PR body then keeps its original shape.
    """
    sections: list[str] = []
    lines = (wo_body or "").splitlines()
    for heading in EVIDENCE_HEADINGS:
        capture = False
        buf: list[str] = []
        for line in lines:
            stripped = line.strip()
            # Prefix match: real WOs use "## Reflection Evidence (why +
            # alternatives_rejected)" — the suffix must survive verbatim.
            if stripped.startswith(heading):
                capture = True
                buf.append(line)
                continue
            if capture and stripped.startswith("## "):
                break
            if capture:
                buf.append(line)
        if buf:
            sections.append("\n".join(buf).strip())
    return "\n\n".join(sections)


def fresh_base_verdict(compare_status: str | None) -> str:
    """Map a GitHub compare (main...branch) status to a base verdict.

    ahead/identical -> "fresh"; behind/diverged -> "stale";
    unknown/None/error -> "unknown" (fail-closed: treat as stale for
    planning, never silently open a doomed PR).
    """
    if compare_status in FRESH_COMPARE_STATUSES:
        return "fresh"
    if compare_status in ("behind", "diverged"):
        return "stale"
    return "unknown"


def rebase_plan(branch: str, verdict: str, clean: bool | None) -> dict[str, object]:
    """Deterministic stale-base plan (#485 fix 4). Data-only output.

    fresh            -> {"action": "none"}
    stale + clean    -> {"action": "rebase_and_push"}
    stale + conflict -> {"action": "skip", "reason": "stale-base-conflict"}
    unknown          -> {"action": "rebase_and_push"} only when a clean
                        dry-run is proven (clean=True); else skip.
    """
    if verdict == "fresh":
        return {"branch": branch, "action": "none"}
    if clean is True:
        return {
            "branch": branch,
            "action": "rebase_and_push",
            "commands": [
                "git fetch origin main",
                f"git rebase origin/main {branch}",
                "git push --force-with-lease origin {branch}",
            ],
        }
    return {
        "branch": branch,
        "action": "skip",
        "reason": "stale-base-conflict" if clean is False else "base-unknown",
    }


def detect_concurrent_claims(
    claim_events: list[dict], now_iso: str, max_active: int = MAX_ACTIVE_CLAIMS
) -> list[dict]:
    """Flag agents exceeding the active-claim quota (#485 test bullet 3,
    enforcing #479). Events: {agent, issue, ts, expires_at}. An event is
    active when ts <= now < expires_at. Deterministic output, ascending
    agent ids. TTL-expired and closed-issue events do not count.
    """
    if not isinstance(now_iso, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", now_iso or ""
    ):
        raise ValueError("now_iso must be an ISO-8601 Z timestamp")
    counts: dict[str, list[int]] = {}
    for ev in claim_events or []:
        agent = ev.get("agent")
        issue = ev.get("issue")
        if not agent or not isinstance(issue, int):
            raise ValueError("claim events need agent + integer issue")
        if ev.get("state") == "closed":
            continue
        if ev.get("ts", "") <= now_iso < ev.get("expires_at", ""):
            counts.setdefault(agent, []).append(issue)
    flagged = []
    for agent in sorted(counts):
        issues = sorted(set(counts[agent]))
        if len(issues) > max_active:
            flagged.append(
                {"agent": agent, "active_claims": issues, "limit": max_active}
            )
    return flagged


def _self_test() -> int:
    # fix 2: punctuation variants all pass
    variants = [
        "Reflection: why this way",
        "Reflection \u2014 why this way",
        "Reflection\u2013 why this way",
        "Reflection- why this way",
        "reflection:  spaced",
        "REFLECTION \u2014 UPPER",
        "prefix Reflection: tail",
    ]
    for body in variants:
        assert has_reflection_evidence(body), body
    for body in (
        "",
        None,
        "no reflection here",
        "Reflections: plural noun",
        "Reflection\t\n",
    ):
        assert not has_reflection_evidence(body), repr(body)

    # fix 3: lossless section transfer
    wo = (
        "### Task ID\nbridge-x\n\n## Test Evidence\n- a: 1\n- b: 2\n\n"
        "## Reflection Evidence (why + alternatives_rejected)\n"
        "- **why:** speed\n- **alternatives_rejected:** slow path\n\n"
        "## Rollback\nrevert"
    )
    out = extract_evidence_sections(wo)
    assert "## Test Evidence" in out and "- a: 1" in out and "- b: 2" in out
    assert "## Reflection Evidence (why + alternatives_rejected)" in out
    assert "- **why:** speed" in out and "- **alternatives_rejected:** slow path" in out
    assert "## Rollback" not in out and "revert" not in out
    assert out.index("## Test Evidence") < out.index("## Reflection Evidence")
    # heading ends the previous section
    assert "\n### Task ID" not in out
    # missing sections -> empty string, PR body shape unchanged
    assert extract_evidence_sections("no sections at all") == ""
    assert extract_evidence_sections("") == ""
    assert extract_evidence_sections(None) == ""
    # evidence-first ordering also works
    wo2 = "## Reflection Evidence\n- **why:** only\n\n## Tail\nx"
    assert extract_evidence_sections(wo2) == "## Reflection Evidence\n- **why:** only"

    # fix 4: base verdicts + plans
    assert fresh_base_verdict("ahead") == "fresh"
    assert fresh_base_verdict("identical") == "fresh"
    assert fresh_base_verdict("behind") == "stale"
    assert fresh_base_verdict("diverged") == "stale"
    assert fresh_base_verdict(None) == "unknown"
    assert rebase_plan("b", "fresh", None) == {"branch": "b", "action": "none"}
    p = rebase_plan("b", "stale", True)
    assert p["action"] == "rebase_and_push" and len(p["commands"]) == 3
    assert rebase_plan("b", "stale", False)["reason"] == "stale-base-conflict"
    assert rebase_plan("b", "unknown", None)["action"] == "skip"

    # fix 1: concurrency detection (#479 enforcement cross-check)
    events = [
        {
            "agent": "a",
            "issue": 900,
            "ts": "2026-10-17T06:00:00Z",
            "expires_at": "2026-10-17T06:30:00Z",
        },
        {
            "agent": "a",
            "issue": 901,
            "ts": "2026-10-17T06:05:00Z",
            "expires_at": "2026-10-17T06:35:00Z",
        },
        {
            "agent": "b",
            "issue": 905,
            "ts": "2026-10-17T06:00:00Z",
            "expires_at": "2026-10-17T06:30:00Z",
        },
    ]
    flagged = detect_concurrent_claims(events, "2026-10-17T06:10:00Z")
    assert flagged == [{"agent": "a", "active_claims": [900, 901], "limit": 1}], flagged
    # expired lease does not count
    assert detect_concurrent_claims(events, "2026-10-17T06:40:00Z") == []
    # closed issues do not count
    closed = events + [
        {
            "agent": "c",
            "issue": 910,
            "ts": "2026-10-17T06:00:00Z",
            "expires_at": "2026-10-17T06:30:00Z",
            "state": "closed",
        }
    ]
    assert detect_concurrent_claims(closed, "2026-10-17T06:10:00Z") == flagged
    # deterministic ascending agents
    two = events + [
        {
            "agent": "b",
            "issue": 906,
            "ts": "2026-10-17T06:05:00Z",
            "expires_at": "2026-10-17T06:35:00Z",
        }
    ]
    got = [f["agent"] for f in detect_concurrent_claims(two, "2026-10-17T06:10:00Z")]
    assert got == ["a", "b"], got

    # fail-closed inputs
    for bad_now in ("", "not-a-time", None, "2026-10-17 06:00:00"):
        try:
            detect_concurrent_claims(events, bad_now)  # type: ignore[arg-type]
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
    for bad_ev in ([{"agent": "a"}], [{"issue": 1}], [{"agent": 5, "issue": "x"}]):
        try:
            detect_concurrent_claims(bad_ev, "2026-10-17T06:00:00Z")
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
    print("self-test OK: bridge_opener_hardening_reference")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    print(__doc__)
    sys.exit(2)
