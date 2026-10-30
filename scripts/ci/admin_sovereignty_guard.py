#!/usr/bin/env python3
"""S15 — Admin Sovereignty Guard: authority:admin-only quarantine (issue #528).

Machine-enforces the Sovereign Execution Level: issues labeled
authority:admin-only are 100% human-Admin execution territory. Autonomous
agents (continuous_agent_loop, MCP work.claim, CI claim gate, pick-next
scanners) must fail-closed reject every interaction with them.

This module is the single SSOT for the quarantine decision so the loop,
the MCP Tower and CI cannot drift. The operator wires the thin calls
listed in docs/ADMIN_SOVEREIGNTY_WIRING_APPENDIX.md (loop steps,
bridge.tools.ts, pipeline.yml, issue templates, U11 rules text, label
provisioning are operator/admin seats — protected or pre-existing).

Decision surface (all deterministic, fail-closed):

  D1  quarantine_decision(labels, issue_number) -> Decision
      DENY with CLAIM_DENIED_ADMIN_ONLY when the label is present
      (case-normalized: any casing variant denies — fail-closed).
  D2  filter_pick_next(candidates) -> (eligible, quarantined)
      pick-next candidates minus admin-only issues; malformed
      candidates are quarantined too (never silently eligible).
  D3  work_queue_marking(labels) -> {claimable, executionLane}
      bridge.work_queue contract: claimable False + admin-only lane.
  D4  ci_claim_gate(opener_is_agent, closes_issue_labels) -> (bool, msg)
      CI blocks agent-opened PRs that close admin-only issues; PRs
      opened by the Admin himself pass.

Exit codes: 0 = allow; 2 = deny (fail-closed); 3 = malformed input.

Pure stdlib. Run: python3 scripts/ci/admin_sovereignty_guard.py --self-test
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

ADMIN_ONLY_LABEL: Final = "authority:admin-only"
DENIAL_CODE: Final = "CLAIM_DENIED_ADMIN_ONLY"
DOMAIN_MISMATCH_CODE: Final = "CLAIM_DENIED_DOMAIN_MISMATCH"
GRANT_CODE: Final = "GRANT"
LANE_SWARM: Final = "swarm"
LANE_ADMIN: Final = "admin-only"
LABEL_COLOR: Final = "B60205"
LABEL_DESCRIPTION: Final = (
    "Admin manual execution only - autonomous agents strictly quarantined"
)

EXIT_ALLOW: Final = 0
EXIT_DENY: Final = 2
EXIT_MALFORMED: Final = 3


@dataclass(frozen=True)
class Decision:
    allowed: bool
    code: str  # GRANT_CODE or DENIAL_CODE
    message: str
    execution_lane: str  # LANE_SWARM or LANE_ADMIN


def _normalized(labels: Sequence[str] | None) -> set[str]:
    if not isinstance(labels, (list, tuple, set, frozenset)):
        raise ValueError("labels must be a list of strings")
    out = set()
    for label in labels:
        if not isinstance(label, str):
            raise ValueError("labels must be a list of strings")
        out.add(label.strip().lower())
    return out


def is_admin_only(labels: Sequence[str] | None) -> bool:
    """Fail-closed membership check: any casing variant of the label denies."""
    return ADMIN_ONLY_LABEL in _normalized(labels)


def extract_domain_from_labels(labels: Sequence[str] | None) -> str | None:
    """Extract a routing domain from labels (domain:* or repo:* or target_repo shorthand)."""
    if not isinstance(labels, (list, tuple, set, frozenset)):
        return None
    for label in labels:
        if not isinstance(label, str):
            continue
        low = label.strip().lower()
        for prefix in ("domain:", "repo:"):
            if low.startswith(prefix):
                return low[len(prefix) :].strip() or None
    return None


def domain_scope_decision(
    issue_domain: str | None,
    agent_allowed_domains: Sequence[str] | None,
    issue_number: int,
) -> Decision:
    """Domain-scope claim decision: agent may only claim issues in its allowed domains."""
    allowed = (
        [str(d).strip().lower() for d in agent_allowed_domains]
        if isinstance(agent_allowed_domains, (list, tuple, set, frozenset))
        else []
    )
    if not issue_domain:
        # no domain tag -> cannot verify scope -> fail-closed deny
        return Decision(
            allowed=False,
            code=DOMAIN_MISMATCH_CODE,
            message=(
                f"CLAIM_DENIED_DOMAIN_MISMATCH: Issue #{issue_number} has no "
                "domain tag; cannot verify agent scope (fail-closed)."
            ),
            execution_lane=LANE_SWARM,
        )
    dom = issue_domain.strip().lower()
    if dom not in allowed:
        return Decision(
            allowed=False,
            code=DOMAIN_MISMATCH_CODE,
            message=(
                f"CLAIM_DENIED_DOMAIN_MISMATCH: Agent scope {allowed or ['(none)']} "
                f"cannot claim domain '{dom}' (issue #{issue_number})."
            ),
            execution_lane=LANE_SWARM,
        )
    return Decision(
        allowed=True,
        code=GRANT_CODE,
        message=f"Issue #{issue_number} domain '{dom}' is within agent scope.",
        execution_lane=LANE_SWARM,
    )


def quarantine_decision(
    labels: Sequence[str] | None,
    issue_number: int,
    *,
    issue_domain: str | None = None,
    agent_allowed_domains: Sequence[str] | None = None,
) -> Decision:
    """D1: the fail-closed claim decision for one issue.

    Backward compatible: when issue_domain/agent_allowed_domains are not
    supplied, only the admin-only check runs (existing contract).
    """
    # admin-only check first (highest priority)
    if is_admin_only(labels):
        return Decision(
            allowed=False,
            code=DENIAL_CODE,
            message=(
                f"CLAIM_DENIED_ADMIN_ONLY: Issue #{issue_number} is "
                "strictly reserved for human Admin execution. "
                "Autonomous bots cannot claim."
            ),
            execution_lane=LANE_ADMIN,
        )
    # optional domain-scope check
    if issue_domain is not None or agent_allowed_domains is not None:
        dom = issue_domain
        if dom is None:
            dom = extract_domain_from_labels(labels)
        ddec = domain_scope_decision(dom, agent_allowed_domains, issue_number)
        if not ddec.allowed:
            return ddec
    return Decision(
        allowed=True,
        code=GRANT_CODE,
        message=f"Issue #{issue_number} is swarm-claimable.",
        execution_lane=LANE_SWARM,
    )


def filter_pick_next(
    candidates: Sequence[Mapping],
) -> tuple[list[Mapping], list[Mapping]]:
    """D2: pick-next candidate filter.

    Returns (eligible, quarantined). Malformed candidates (missing or
    non-list labels, non-int number) are quarantined, never eligible.
    """
    eligible: list[Mapping] = []
    quarantined: list[Mapping] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            quarantined.append({"candidate": repr(candidate), "reason": "malformed"})
            continue
        labels = candidate.get("labels")
        number = candidate.get("number")
        if (
            not isinstance(number, int)
            or isinstance(number, bool)
            or not isinstance(labels, list)
        ):
            quarantined.append({"candidate": {"number": number}, "reason": "malformed"})
            continue
        if is_admin_only(labels):
            quarantined.append(
                {"candidate": {"number": number}, "reason": ADMIN_ONLY_LABEL}
            )
            continue
        eligible.append(candidate)
    return eligible, quarantined


def work_queue_marking(labels: Sequence[str] | None) -> dict[str, object]:
    """D3: bridge.work_queue per-issue marking contract."""
    if is_admin_only(labels):
        return {"claimable": False, "executionLane": LANE_ADMIN}
    return {"claimable": True, "executionLane": LANE_SWARM}


def ci_claim_gate(
    opener_is_agent: bool,
    closes_issue_labels: Sequence[str] | None,
    issue_number: int = 0,
) -> tuple[bool, str]:
    """D4: CI claim gate for PRs that close admin-only issues."""
    labels = closes_issue_labels if closes_issue_labels is not None else []
    if opener_is_agent and is_admin_only(labels):
        suffix = f" (issue #{issue_number})" if issue_number else ""
        return False, (
            "CI CLAIM GATE: PR blocked - it closes an "
            f"authority:admin-only issue{suffix}; manual Admin "
            "approval is required before autonomous merge."
        )
    return True, "CI claim gate: allow"


def self_test() -> bool:
    admin = [ADMIN_ONLY_LABEL]
    swarm = ["enhancement", "P1-high"]

    # D1 decisions
    d = quarantine_decision(admin, 42)
    assert not d.allowed and d.code == DENIAL_CODE
    assert d.execution_lane == LANE_ADMIN
    assert d.message == (
        "CLAIM_DENIED_ADMIN_ONLY: Issue #42 is strictly "
        "reserved for human Admin execution. Autonomous "
        "bots cannot claim."
    ), d.message
    ok = quarantine_decision(swarm, 43)
    assert ok.allowed and ok.code == GRANT_CODE and ok.execution_lane == LANE_SWARM

    # Fail-closed casing variants
    for variant in (
        "Authority:Admin-Only",
        "AUTHORITY:ADMIN-ONLY",
        " authority:admin-only ",
    ):
        assert not quarantine_decision([variant], 44).allowed, variant

    # D2 pick-next filter
    queue = [
        {"number": 1, "labels": ["enhancement"]},
        {"number": 2, "labels": [ADMIN_ONLY_LABEL]},
        {"number": 3, "labels": ["Authority:Admin-Only"]},
        {"number": "bad", "labels": []},
        {"number": 4},
    ]
    eligible, quarantined = filter_pick_next(queue)
    assert [c["number"] for c in eligible] == [1]
    assert {q["candidate"]["number"] for q in quarantined} == {2, 3, "bad", 4}
    assert any(q["reason"] == ADMIN_ONLY_LABEL for q in quarantined)
    assert any(q["reason"] == "malformed" for q in quarantined)
    assert filter_pick_next([]) == ([], [])

    # D3 queue marking
    assert work_queue_marking(admin) == {
        "claimable": False,
        "executionLane": LANE_ADMIN,
    }
    assert work_queue_marking(swarm) == {"claimable": True, "executionLane": LANE_SWARM}

    # D4 CI claim gate
    blocked, msg = ci_claim_gate(True, admin, 42)
    assert not blocked and "CI CLAIM GATE" in msg and "42" in msg
    assert ci_claim_gate(False, admin, 42)[0] is True  # admin's own PR
    assert ci_claim_gate(True, swarm, 43)[0] is True  # not admin-only
    assert ci_claim_gate(True, None)[0] is True  # no labels

    # Malformed labels fail closed
    captured: list[str] = []
    for bad in ("authority:admin-only", {"a": 1}, 7):
        try:
            is_admin_only(bad)  # type: ignore[arg-type]
            assert False, bad
        except ValueError as exc:
            captured.append(str(exc))
    assert len(captured) == 3 and all("labels" in c for c in captured)

    # Domain-scope check
    dd = domain_scope_decision("studio", ["studio", "vscode"], 7)
    assert dd.allowed and dd.code == GRANT_CODE
    dd2 = domain_scope_decision("core", ["studio"], 8)
    assert not dd2.allowed and dd2.code == DOMAIN_MISMATCH_CODE
    assert domain_scope_decision(None, ["studio"], 9).code == DOMAIN_MISMATCH_CODE
    assert extract_domain_from_labels(["domain:studio", "P1-high"]) == "studio"
    assert extract_domain_from_labels(["repo:core"]) == "core"
    assert extract_domain_from_labels(["enhancement"]) is None
    return True


def _parse_labels(raw: str) -> list[str]:
    data = json.loads(raw)
    if not isinstance(data, list) or any(not isinstance(x, str) for x in data):
        raise ValueError("expected a JSON list of label strings")
    return data


def _cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--check", action="store_true", help="decide one issue: --labels-json + --issue"
    )
    parser.add_argument("--labels-json", help="JSON list of label strings")
    parser.add_argument("--issue", type=int, default=0)
    parser.add_argument("--domain", help="issue domain (e.g. studio) for scope check")
    parser.add_argument(
        "--allowed-domains",
        help="comma-separated agent allowed domains (e.g. studio,vscode)",
    )
    parser.add_argument(
        "--filter",
        action="store_true",
        help="filter a pick-next queue from --queue-json or stdin",
    )
    parser.add_argument("--queue-json", help="JSON list of {number, labels}")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("SELF-TEST OK: admin_sovereignty_guard")
        return EXIT_ALLOW
    try:
        if args.check:
            allowed_domains = None
            if args.allowed_domains:
                allowed_domains = [
                    x.strip() for x in args.allowed_domains.split(",") if x.strip()
                ]
            decision = quarantine_decision(
                _parse_labels(args.labels_json or "[]"),
                args.issue,
                issue_domain=args.domain,
                agent_allowed_domains=allowed_domains,
            )
            print(
                json.dumps(
                    {
                        "allowed": decision.allowed,
                        "code": decision.code,
                        "message": decision.message,
                        "executionLane": decision.execution_lane,
                    }
                )
            )
            return EXIT_ALLOW if decision.allowed else EXIT_DENY
        if args.filter:
            raw = args.queue_json if args.queue_json else sys.stdin.read()
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValueError("expected a JSON list of candidates")
            eligible, quarantined = filter_pick_next(data)
            print(
                json.dumps(
                    {
                        "eligible": [c.get("number") for c in eligible],
                        "quarantined": quarantined,
                    },
                    default=str,
                )
            )
            return EXIT_ALLOW
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"MALFORMED INPUT (fail-closed): {exc}")
        return EXIT_MALFORMED
    parser.print_help()
    return EXIT_MALFORMED


if __name__ == "__main__":
    raise SystemExit(_cli())
