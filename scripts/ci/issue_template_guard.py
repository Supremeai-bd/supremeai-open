#!/usr/bin/env python3
"""Fail-Closed Issue Template & Contract Guard (#473).

Validates issues on supremeai-open at intake so blank, placeholder, or
malformed entries never enter the queue. Zero-dependency, stdlib-only,
deterministic, offline-testable reference implementation.

Contract (from #473):
- Conventional title: ^(feat|fix|plan|chore|docs|ops|refactor|test|ci|perf)
  (\\(scope\\))?: <text>  OR carries a priority bracket [P0..P3].
  Placeholder titles (test, asdf, bug, untitled, ...) are rejected.
- Structured body: >= 50 chars and includes a markdown header or one of
  the required section markers (Context / Summary / Task Contract /
  Acceptance Criteria / Steps).
- Fail-closed auto-rejection: invalid -> explanatory comment, label
  `invalid`, close reason not_planned. Unparseable input NEVER passes.
- Auto-labeling on success: status:unclaimed + bridge:queued so manual
  labeling is never required.
- Bot bypass: known automation authors (dependabot, github-actions,
  renovate) pass through without labels or rejection.

Data-only: returns a plan; the pipeline job executes GitHub operations.
Pipeline integration (issues: [opened, edited] + issue-contract-guard
job) is delivered as a doc appendix hunk because .github/ is a
protected path for the bridge lane.

Self-test: python3 issue_template_guard.py --self-test
"""

from __future__ import annotations

import json
import re
import sys

CONVENTIONAL_TITLE = re.compile(
    r"^(?P<type>feat|fix|plan|chore|docs|ops|refactor|test|ci|perf)"
    r"(\((?P<scope>[a-zA-Z0-9_\-.\/]+)\))?:\s+(?P<subject>\S.+)$"
)
PRIORITY_BRACKET = re.compile(r"\[(?:P0|P1|P2|P3)\]")
SECTION_MARKER = re.compile(
    r"(?im)^(?:#{1,6}\s+.*|.*\b(context|summary|task contract|"
    r"acceptance criteria|steps)\b.*$)"
)
MIN_BODY_CHARS = 50

ROUTINE_GREEN_SENTRY = re.compile(
    r"^(?:\[P[0-3]\]\s*)?(?:guard\([^)]*\):\s*(?:provider\s+)?sentry\s+pass|sentry:).*(?:all[- ]green|[0-9]+/[0-9]+\s+alive)",
    re.IGNORECASE,
)

PLACEHOLDER_TITLES = {
    "test",
    "tests",
    "asdf",
    "asdfgh",
    "bug",
    "bugfix",
    "untitled",
    "wip",
    "tmp",
    "temp",
    "misc",
    "stuff",
    "issue",
    "fix",
    "update",
    "hello",
    "sample",
    "example",
    "t",
    "x",
    "n/a",
    "na",
    "none",
}
BOT_AUTHORS = {
    "dependabot[bot]",
    "github-actions[bot]",
    "renovate[bot]",
    "copilot-pull-request-reviewer[bot]",
    "renovate-release[bot]",
}

LABEL_PASS = ["status:unclaimed", "bridge:queued"]
LABEL_REJECT = ["invalid"]


def _reject(reasons: list, issue_number, title: str) -> dict:
    bullet = "; ".join(reasons)
    comment = (
        "## Issue Contract Guard — REJECTED (fail-closed)\n\n"
        f"Reasons: {bullet}\n\n"
        "**Remediation:** use the official issue templates "
        "(`.github/ISSUE_TEMPLATE/`). Title must be conventional "
        "(e.g. `feat(gateway): ...`) or carry a priority bracket "
        "(`[P0]`..`[P3]`); body needs >= "
        f"{MIN_BODY_CHARS} chars with sections such as Context, "
        "Summary, Task Contract, Acceptance Criteria, or Steps.\n\n"
        "This issue is closed as not_planned. Please reopen a "
        "well-formed issue."
    )
    return {
        "verdict": "reject",
        "issue": issue_number,
        "title": title,
        "reasons": reasons,
        "labels_to_add": list(LABEL_REJECT),
        "comment": comment,
        "close": {"state": "closed", "reason": "not_planned"},
    }


def _pass(
    issue_number, title: str, note: str | None = None, add_labels: bool = True
) -> dict:
    return {
        "verdict": "pass",
        "issue": issue_number,
        "title": title,
        "reasons": [note] if note else [],
        "labels_to_add": list(LABEL_PASS) if add_labels else [],
        "comment": None,
        "close": None,
    }


def validate_issue(payload: dict) -> dict:
    """Validate one issue payload. Fail-closed on malformed input.

    Payload: {"number": int, "title": str, "body": str, "author": str}
    """
    if not isinstance(payload, dict):
        return _reject(["payload is not an object"], None, "")
    number = payload.get("number")
    title = payload.get("title")
    body = payload.get("body")
    author = payload.get("author") or ""
    if not isinstance(title, str) or not isinstance(body, str):
        return _reject(["missing or non-string title/body"], number, str(title))

    if author in BOT_AUTHORS:
        return _pass(number, title, note=f"bot_bypass:{author}", add_labels=False)

    reasons = []
    stripped = title.strip()
    conv = CONVENTIONAL_TITLE.match(stripped)
    has_priority = bool(PRIORITY_BRACKET.search(stripped))
    if not conv and not has_priority:
        reasons.append(
            "title is neither conventional (type(scope): subject) "
            "nor priority-bracketed [P0..P3]"
        )
    elif conv and conv.group("subject").strip().lower() in PLACEHOLDER_TITLES:
        reasons.append(f"placeholder title subject: {conv.group('subject').strip()!r}")
    elif (
        not conv
        and has_priority
        and stripped.strip("[]0123456789Pp ").lower() in PLACEHOLDER_TITLES
    ):
        reasons.append(f"placeholder title: {stripped!r}")

    if ROUTINE_GREEN_SENTRY.search(stripped):
        reasons.append(
            "routine green sentry telemetry passes must not open new issues "
            "(record routine success in run worklogs or memory plane)"
        )
    if len(body) < MIN_BODY_CHARS:
        reasons.append(f"body too short ({len(body)} < {MIN_BODY_CHARS} chars)")
    elif not SECTION_MARKER.search(body):
        reasons.append(
            "body lacks markdown headers or required section "
            "markers (Context/Summary/Task Contract/"
            "Acceptance Criteria/Steps)"
        )

    if reasons:
        return _reject(reasons, number, title)
    return _pass(number, title)


def _self_test() -> int:
    good = {
        "number": 1,
        "author": "someone",
        "title": "feat(gateway): [P1] unified shield",
        "body": "## Context\nNeed one-key SSOT across the federation "
        "gateway and downstream apps.\n## Acceptance Criteria\n"
        "OpenAPI valid; tests pass.",
    }
    v = validate_issue(good)
    assert v["verdict"] == "pass", v
    assert v["labels_to_add"] == ["status:unclaimed", "bridge:queued"]

    v2 = validate_issue({**good, "title": "feat: [P0] shield"})
    assert v2["verdict"] == "pass", v2

    # Priority bracket alone still passes when subject is real.
    v3 = validate_issue({**good, "title": "[P2] refund flow"})
    assert v3["verdict"] == "pass", v3

    # Invalid cases.
    r1 = validate_issue({**good, "title": "asdf"})
    assert r1["verdict"] == "reject" and any(
        "neither conventional" in r for r in r1["reasons"]
    ), r1
    r2 = validate_issue({**good, "title": "fix: asdf"})
    assert r2["verdict"] == "reject" and any(
        "placeholder" in r for r in r2["reasons"]
    ), r2
    r3 = validate_issue({**good, "body": "short"})
    assert r3["verdict"] == "reject" and any("too short" in r for r in r3["reasons"]), (
        r3
    )
    long_unstructured = "x" * 60
    r4 = validate_issue({**good, "body": long_unstructured})
    assert r4["verdict"] == "reject" and any("lacks" in r for r in r4["reasons"]), r4
    # Reject plan shape: label + close not_planned + comment.
    assert r1["close"] == {"state": "closed", "reason": "not_planned"}
    assert r1["labels_to_add"] == ["invalid"] and r1["comment"]

    # Bot bypass passes without labels.
    b = validate_issue({**good, "title": "asdf", "author": "dependabot[bot]"})
    assert (
        b["verdict"] == "pass"
        and b["labels_to_add"] == []
        and b["reasons"] == ["bot_bypass:dependabot[bot]"]
    ), b

    # Fail-closed on malformed payloads.
    for bad in (None, {}, {"number": 1}, {"title": 7, "body": "x"}):
        out = validate_issue(bad)
        assert out["verdict"] == "reject", (bad, out)

    # Section markers recognized case-insensitively.
    v4 = validate_issue(
        {**good, "body": "task contract: deliver the guard plus offline self-tests."}
    )
    assert v4["verdict"] == "pass", v4
    # Routine green sentry rejected
    sentry_rej = validate_issue({**good, "title": "[P2] guard(platform): sentry pass 12:00Z — 7/8 alive"})
    assert sentry_rej["verdict"] == "reject" and any("routine green sentry" in r for r in sentry_rej["reasons"]), sentry_rej
    print("self-test OK: issue_template_guard")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    if len(sys.argv) == 3 and sys.argv[1] == "--validate":
        with open(sys.argv[2], encoding="utf-8") as fh:
            plan = validate_issue(json.load(fh))
        print(json.dumps(plan, indent=2))
        sys.exit(0 if plan["verdict"] == "pass" else 2)
    print(__doc__)
    sys.exit(2)
