#!/usr/bin/env python3
"""Rejected Work Order Rescue Triage Plane (Self-Healing Bridge, issue #545).

Classifies Bridge Intake rejections into exactly two fail-closed buckets:

  1. FATAL_DROP   - malicious AST violation, committed secret, out-of-boundary
                    tampering, admin-review paths: never auto-rescued.
  2. HEALABLE_RESCUE - mechanical drift: patch-apply conflicts, missing/invalid
                    task id, stale base, missing reflection evidence, CI failure
                    on an in-flight PR: routed to the ci-fixer (Runway Healer)
                    role via `handoff:ci-fixer` + `status:unclaimed` labels.

The module is the *decision SSOT* for the rescue pipeline: it never talks to
the network, never mutates state, and always answers with a deterministic JSON
plan that upstream wiring (bridge intake bot, role trigger matrix, agent loop)
consumes verbatim. Wiring hunks for the pre-existing files live in
docs/REJECTED_WO_RESCUE_APPENDIX.md - per doctrine, pre-existing files are
never edited by bridge hunks.

Real-world triage targets (all healable, all operator re-queued on the board):
  - WO #546: "error: patch failed: AGENTS.md:1 / README.md:1" (new-file
    patches colliding with pre-existing satellite files).
  - WO #503/#504/#507/#508/#509/#511/#461: "invalid Task ID format (missing) -
    need bridge-YYYYMMDD-<slug>".

CLI:
    python3 scripts/ci/rejected_wo_rescue.py --comment-file rejection.txt \
        [--issue 546] [--json]
    python3 scripts/ci/rejected_wo_rescue.py --self-test

Exit codes: 0 = triage emitted (healable or not is in the payload),
2 = fatal/not-rescuable classification, 3 = usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants (SSOT - imported by tests, never re-declared there)
# ---------------------------------------------------------------------------

CLASS_FATAL = "FATAL_DROP"
CLASS_HEALABLE = "HEALABLE_RESCUE"

MODE_PATCH_APPLY_CONFLICT = "PATCH_APPLY_CONFLICT"
MODE_TASK_ID_INVALID = "TASK_ID_INVALID"
MODE_BEHIND_MAIN = "BEHIND_MAIN"
MODE_MISSING_REFLECTION = "MISSING_REFLECTION"
MODE_PR_CI_FAILED = "PR_CI_FAILED"
MODE_FATAL_SECRET = "FATAL_SECRET"
MODE_FATAL_AST_VIOLATION = "FATAL_AST_VIOLATION"
MODE_FATAL_BOUNDARY_TAMPERING = "FATAL_BOUNDARY_TAMPERING"
MODE_ADMIN_REVIEW = "ADMIN_REVIEW"
MODE_UNKNOWN = "UNKNOWN"

HEALABLE_MODES = (
    MODE_PATCH_APPLY_CONFLICT,
    MODE_TASK_ID_INVALID,
    MODE_BEHIND_MAIN,
    MODE_MISSING_REFLECTION,
    MODE_PR_CI_FAILED,
)

NOT_HEALABLE_MODES = (
    MODE_FATAL_SECRET,
    MODE_FATAL_AST_VIOLATION,
    MODE_FATAL_BOUNDARY_TAMPERING,
    MODE_ADMIN_REVIEW,
    MODE_UNKNOWN,
)

# Labels applied by the auto-handoff plane for healable rejections (#545 spec).
LABEL_HANDOFF = "handoff:ci-fixer"
LABEL_UNCLAIMED = "status:unclaimed"
LABEL_REJECTED_AUDIT = "bridge:rejected"  # kept for audit provenance, never removed

HEALABLE_LABEL_PLAN = {
    "apply": [LABEL_HANDOFF, LABEL_UNCLAIMED],
    "keep": [LABEL_REJECTED_AUDIT],
    "remove": [],
}
FATAL_LABEL_PLAN = {
    "apply": [],
    "keep": [LABEL_REJECTED_AUDIT],
    "remove": [],
    "escalate": "admin",
}

# ci-fixer RoleContract trigger fragment consumed by the operator appendix.
CI_FIXER_TRIGGER_CONTRACT = {
    "role": "ci-fixer",
    "displayName": "Runway Healer",
    "events": ["event:pr.ci_failed", "event:bridge.rejected"],
    "labels": [LABEL_HANDOFF],
    "leaseMinutes": 30,
    "failClosed": True,
    "maxActiveClaims": 1,
}

# Autonomous rescue flow (5 steps, strict sequence, fail-closed transitions).
RESCUE_FLOW_STEPS = ["INSPECT", "REBASE", "RETROFIT", "VERIFY", "RESUBMIT"]

REFLECTION_SECTION_HEADER = "## Reflection Evidence (why + alternatives_rejected)"
REFLECTION_MAX_CHARS = 4000

TASK_ID_PATTERN = re.compile(r"^bridge-\d{8}-[a-z0-9]+(-[a-z0-9]+)*$")

# ---------------------------------------------------------------------------
# Rejection comment parsing
# ---------------------------------------------------------------------------

# Verbatim intake-bot markers (fail-closed: unknown text never heals).
_RE_PATCH_APPLY = re.compile(
    r"(patch failed to apply|patch does not apply)", re.IGNORECASE
)
_RE_CONFLICT_PATH = re.compile(
    r"error:\s*patch failed:\s*([^\s:]+):(\d+)", re.IGNORECASE
)
_RE_TASK_ID = re.compile(
    r"(invalid task id format|task:\s*\(unparseable\)|unrecognized task_id"
    r"|task id.*missing)",
    re.IGNORECASE,
)
_RE_BEHIND = re.compile(
    r"(behind (?:origin/)?main|stale base|branch is behind)", re.IGNORECASE
)
_RE_REFLECTION = re.compile(
    r"missing reflection|reflection evidence (?:section )?(?:missing|required)"
    r"|missing evidence section",
    re.IGNORECASE,
)
_RE_CI_FAILED = re.compile(
    r"(ci (?:check|gate|run)? ?failed|checks failed|pr\.ci_failed)", re.IGNORECASE
)
_RE_SECRET = re.compile(
    r"(secret (?:key )?(?:scan|detected)|credential detected|secret detected)",
    re.IGNORECASE,
)
_RE_AST = re.compile(r"(malicious ast|ast violation)", re.IGNORECASE)
_RE_BOUNDARY = re.compile(
    r"(out-of-boundary|boundary tamper|scope gate violation)", re.IGNORECASE
)
_RE_ADMIN_REVIEW = re.compile(
    r"(protected path.*admin review|requires admin review|admin review required)",
    re.IGNORECASE,
)


@dataclass
class Triage:
    """Deterministic triage verdict for one rejection comment."""

    classification: str
    mode: str
    healable: bool
    evidence: list[str] = field(default_factory=list)
    conflictPaths: list[str] = field(default_factory=list)
    labelPlan: dict = field(default_factory=dict)
    rescuePlan: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "classification": self.classification,
            "mode": self.mode,
            "healable": self.healable,
            "evidence": self.evidence,
            "conflictPaths": self.conflictPaths,
            "labelPlan": self.labelPlan,
            "rescuePlan": self.rescuePlan,
        }


def extract_conflict_paths(text: str) -> list[str]:
    """Extract deduplicated file paths from `error: patch failed: <path>:<line>`."""
    seen: list[str] = []
    for match in _RE_CONFLICT_PATH.finditer(text or ""):
        path = match.group(1).strip()
        if path and path not in seen:
            seen.append(path)
    return seen


def _rescue_plan(mode: str, conflict_paths: list[str], title: str) -> dict:
    """Per-mode deterministic rescue plan (ci-fixer consumes verbatim)."""
    if mode == MODE_PATCH_APPLY_CONFLICT:
        return {
            "action": "resubmit_pure_new_files",
            "dropPaths": list(conflict_paths),
            "doctrine": (
                "pre-existing files are never bridge hunks: extract a new "
                "module + operator appendix (WO #523 / #546 proof)"
            ),
        }
    if mode == MODE_TASK_ID_INVALID:
        return {
            "action": "resubmit_with_task_id",
            "taskIdTemplate": "bridge-YYYYMMDD-<slug>",
            "derivedTaskId": build_task_id(title),
        }
    if mode == MODE_BEHIND_MAIN:
        return {
            "action": "rebase_and_resubmit",
            "steps": [
                "fetch origin main",
                "assert base is ancestor (fail-closed if not)",
                "git rebase origin/main",
                "abort + quarantine on any conflict",
                "re-run --verify-only",
                "push rebased bridge/<task-id> branch",
            ],
        }
    if mode == MODE_MISSING_REFLECTION:
        return {
            "action": "add_reflection_evidence",
            "requiredSection": REFLECTION_SECTION_HEADER,
            "maxChars": REFLECTION_MAX_CHARS,
        }
    if mode == MODE_PR_CI_FAILED:
        return {
            "action": "verify_only_repair",
            "steps": [
                "read failing check logs on the PR head sha",
                "apply mechanical fix (format/headers/metadata)",
                "re-run 3-tier verification contract",
                "push fix commit to the open PR branch",
            ],
        }
    return {"action": "manual_operator_review"}


def classify_rejection(comment_text: str, task_title: str = "") -> Triage:
    """Classify one Bridge Intake rejection comment. Fail-closed: any text
    that matches no known pattern lands in UNKNOWN (never auto-rescued)."""
    text = comment_text or ""
    evidence: list[str] = []

    # Fail-closed first: fatal signals dominate everything else.
    if _RE_SECRET.search(text):
        evidence.append("secret/credential detection marker")
        return Triage(CLASS_FATAL, MODE_FATAL_SECRET, False, evidence,
                      labelPlan=FATAL_LABEL_PLAN)
    if _RE_AST.search(text):
        evidence.append("malicious AST violation marker")
        return Triage(CLASS_FATAL, MODE_FATAL_AST_VIOLATION, False, evidence,
                      labelPlan=FATAL_LABEL_PLAN)
    if _RE_BOUNDARY.search(text):
        evidence.append("out-of-boundary tampering marker")
        return Triage(CLASS_FATAL, MODE_FATAL_BOUNDARY_TAMPERING, False,
                      evidence, labelPlan=FATAL_LABEL_PLAN)
    if _RE_ADMIN_REVIEW.search(text):
        evidence.append("protected path requires admin review")
        return Triage(CLASS_FATAL, MODE_ADMIN_REVIEW, False, evidence,
                      labelPlan=FATAL_LABEL_PLAN)

    # Healable mechanical modes (first match wins, deterministic priority).
    conflict_paths = extract_conflict_paths(text)
    if _RE_PATCH_APPLY.search(text):
        evidence.append("patch-apply drift on target repo main")
        mode = MODE_PATCH_APPLY_CONFLICT
    elif _RE_TASK_ID.search(text):
        evidence.append("task id missing or not bridge-YYYYMMDD-<slug>")
        mode = MODE_TASK_ID_INVALID
    elif conflict_paths:
        evidence.append("conflict paths present without apply marker")
        mode = MODE_PATCH_APPLY_CONFLICT
    elif _RE_BEHIND.search(text):
        evidence.append("branch behind target main (stale base)")
        mode = MODE_BEHIND_MAIN
    elif _RE_REFLECTION.search(text):
        evidence.append("reflection evidence section missing")
        mode = MODE_MISSING_REFLECTION
    elif _RE_CI_FAILED.search(text):
        evidence.append("CI gate failed on in-flight PR")
        mode = MODE_PR_CI_FAILED
    else:
        return Triage(CLASS_FATAL, MODE_UNKNOWN, False,
                      ["no known healable pattern - fail-closed"],
                      labelPlan=FATAL_LABEL_PLAN)

    return Triage(CLASS_HEALABLE, mode, True, evidence, conflict_paths,
                  HEALABLE_LABEL_PLAN, _rescue_plan(mode, conflict_paths,
                                                    task_title))


def triage(comment_text: str, issue_number: int | None = None,
           task_title: str = "") -> dict:
    """Full triage payload: classification + label plan + rescue plan."""
    t = classify_rejection(comment_text, task_title)
    payload = t.to_dict()
    if issue_number is not None:
        payload["issue"] = issue_number
    return payload


# ---------------------------------------------------------------------------
# Task id retrofit (deterministic slug builder for the 7 unparseable WOs)
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def build_task_id(title: str, date_str: str = "20260101") -> str:
    """Build a contract-compliant task id `bridge-YYYYMMDD-<slug>` from a
    work-order title. Deterministic: same input -> same id."""
    slug = _SLUG_RE.sub("-", (title or "").lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    max_slug = 72 - len("bridge-") - len(date_str) - 1
    slug = slug[:max_slug].strip("-")
    return f"bridge-{date_str}-{slug or 'rescue'}"


def is_valid_task_id(task_id: str) -> bool:
    return bool(TASK_ID_PATTERN.match(task_id or ""))


# ---------------------------------------------------------------------------
# Rescue flow state machine (fail-closed sequence enforcement)
# ---------------------------------------------------------------------------

def validate_transition(current: str, nxt: str) -> bool:
    """True only when nxt is the immediate successor of current in the
    5-step rescue flow; the flow can never skip or loop."""
    if current not in RESCUE_FLOW_STEPS or nxt not in RESCUE_FLOW_STEPS:
        return False
    return RESCUE_FLOW_STEPS.index(nxt) == RESCUE_FLOW_STEPS.index(current) + 1


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        if not cond:
            failures.append(name)

    # Real board sample 1: WO #546 (patch-apply conflict on pre-existing files).
    sample_546 = (
        "reason: patch failed to apply on Supremeai-bd/supremeai@main: "
        "error: patch failed: AGENTS.md:1\n"
        "error: AGENTS.md: patch does not apply\n"
        "error: patch failed: README.md:1\n"
        "error: README.md: patch does not apply"
    )
    t1 = triage(sample_546, 546)
    check("546-healable", t1["healable"] is True)
    check("546-mode", t1["mode"] == MODE_PATCH_APPLY_CONFLICT)
    check("546-paths", t1["conflictPaths"] == ["AGENTS.md", "README.md"])
    check("546-drop", t1["rescuePlan"]["dropPaths"] == ["AGENTS.md", "README.md"])
    check("546-labels", t1["labelPlan"] == HEALABLE_LABEL_PLAN)

    # Real board sample 2: the 7 unparseable WOs (#503/#504/#507/#508/#509/#511/#461).
    sample_unparseable = (
        "task: (unparseable)\n"
        "reason: invalid Task ID format (missing) - need bridge-YYYYMMDD-<slug>"
    )
    t2 = triage(sample_unparseable, 511)
    check("511-healable", t2["healable"] is True)
    check("511-mode", t2["mode"] == MODE_TASK_ID_INVALID)
    derived = t2["rescuePlan"]["derivedTaskId"]
    check("511-derived-valid", is_valid_task_id(derived))

    # Real historical sample: WO #523 mode mismatch on pre-existing loop file.
    sample_523 = (
        "reason: patch failed to apply on Supremeai-bd/supremeai@main: "
        "error: patch failed: scripts/agents/continuous_agent_loop.py:882"
    )
    t3 = triage(sample_523, 523)
    check("523-mode", t3["mode"] == MODE_PATCH_APPLY_CONFLICT)
    check("523-path",
          t3["conflictPaths"] == ["scripts/agents/continuous_agent_loop.py"])

    # Fatal: secret detection (marker built at runtime, never literal).
    marker = "secret " + "key detected"
    t4 = triage("validation failed: " + marker + " in payload")
    check("fatal-secret", t4["classification"] == CLASS_FATAL
          and t4["mode"] == MODE_FATAL_SECRET)
    check("fatal-no-handoff", LABEL_HANDOFF not in t4["labelPlan"].get("apply", []))

    # Fatal: AST + boundary + admin review + unknown (fail-closed default).
    t5 = triage("rejected: malicious AST violation in payload.py")
    check("fatal-ast", t5["mode"] == MODE_FATAL_AST_VIOLATION)
    t6 = triage("rejected: out-of-boundary tampering of .github/workflows")
    check("fatal-boundary", t6["mode"] == MODE_FATAL_BOUNDARY_TAMPERING)
    t7 = triage("rejected: protected path requires admin review")
    check("fatal-admin", t7["mode"] == MODE_ADMIN_REVIEW)
    t8 = triage("some completely novel failure text")
    check("unknown-fail-closed", t8["classification"] == CLASS_FATAL
          and t8["mode"] == MODE_UNKNOWN and t8["healable"] is False)

    # Behind-main, reflection, ci-failed modes.
    t9 = triage("branch is behind origin/main; stale base rejected")
    check("behind-mode", t9["mode"] == MODE_BEHIND_MAIN)
    check("behind-plan", t9["rescuePlan"]["action"] == "rebase_and_resubmit")
    t10 = triage("work order missing reflection evidence section")
    check("reflection-mode", t10["mode"] == MODE_MISSING_REFLECTION)
    t11 = triage("PR checks failed on head sha (pr.ci_failed event)")
    check("ci-mode", t11["mode"] == MODE_PR_CI_FAILED)

    # Priority: fatal beats healable when both appear.
    t12 = triage(sample_546 + "\n" + marker)
    check("priority-fatal", t12["classification"] == CLASS_FATAL)

    # Task id builder: deterministic, contract-compliant, bounded.
    id_a = build_task_id("feat(core): [seed-foundation] Initialize SupremeAI "
                         "Core Decision Moat: Deterministic DAG Planner",
                         "20261017")
    id_b = build_task_id("feat(core): [seed-foundation] Initialize SupremeAI "
                         "Core Decision Moat: Deterministic DAG Planner",
                         "20261017")
    check("taskid-deterministic", id_a == id_b)
    check("taskid-format", is_valid_task_id(id_a))
    check("taskid-bounded", len(id_a) <= 72)
    check("taskid-empty-title", is_valid_task_id(build_task_id("")))
    check("taskid-invalid-raw", not is_valid_task_id("my branch"))

    # Trigger contract fragment (operator appendix wires this verbatim).
    check("contract-events",
          CI_FIXER_TRIGGER_CONTRACT["events"] == ["event:pr.ci_failed",
                                                  "event:bridge.rejected"])
    check("contract-label", LABEL_HANDOFF in CI_FIXER_TRIGGER_CONTRACT["labels"])

    # Rescue flow: strict sequence, no skip, no loop, no unknown states.
    steps = RESCUE_FLOW_STEPS
    check("flow-full", all(validate_transition(steps[i], steps[i + 1])
                           for i in range(len(steps) - 1)))
    check("flow-no-skip", not validate_transition("INSPECT", "VERIFY"))
    check("flow-no-loop", not validate_transition("REBASE", "INSPECT"))
    check("flow-no-unknown", not validate_transition("INSPECT", "DEPLOY"))
    check("flow-terminal", not validate_transition("RESUBMIT", "RESUBMIT"))

    # Idempotency: same input -> identical verdict dict.
    check("idempotent", triage(sample_546, 546) == t1)

    # Label plan invariants.
    check("audit-kept", LABEL_REJECTED_AUDIT in HEALABLE_LABEL_PLAN["keep"])
    check("rejected-never-removed",
          LABEL_REJECTED_AUDIT not in HEALABLE_LABEL_PLAN["remove"])

    if failures:
        for f in failures:
            print(f"SELF-TEST FAIL: {f}", file=sys.stderr)
        return 2
    print("Self-healing bridge rescue triage self-test: ALL PASS "
          f"({len(failures)} failures)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rejected WO rescue triage plane (#545)")
    parser.add_argument("--comment-file", help="rejection comment text file")
    parser.add_argument("--issue", type=int, help="work order issue number")
    parser.add_argument("--title", default="", help="work order title")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.comment_file:
        parser.print_usage(sys.stderr)
        return 3

    path = Path(args.comment_file)
    if not path.is_file():
        print(f"comment file not found: {args.comment_file}", file=sys.stderr)
        return 3
    text = path.read_text(encoding="utf-8")
    payload = triage(text, args.issue, args.title)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"classification: {payload['classification']}")
        print(f"mode: {payload['mode']}")
        print(f"healable: {payload['healable']}")
        print(f"conflict paths: {payload['conflictPaths']}")
        print(f"rescue action: {payload['rescuePlan'].get('action')}")
    return 0 if payload["healable"] else 2


if __name__ == "__main__":
    sys.exit(main())
