#!/usr/bin/env python3
"""
stale_claim_releaser.py — 2-Stage Graduated Lease & Orphan Claim Auto-Release Gate.

Mission & Architecture:
  Enforces the 2-Stage Dynamic Agent Lease Contract:

  Stage 1 (Claim -> Branch Creation): 10 Minutes Max
    When an issue is claimed by an agent, the work branch must be created/pushed
    within 10 minutes. If no remote branch matching the issue appears in 10 minutes,
    the claiming agent is considered disconnected/failed-to-start.
    -> The claim marker is released immediately back to the pool.

  Stage 2 (Branch -> Pull Request): 30 Minutes Max
    Once a branch exists, the agent has 30 minutes to complete the 3-tier
    verification and open an active Pull Request. If 30 minutes elapse with a branch
    active but zero open PR submitted, the agent is considered stuck/abandoned.
    -> The claim marker is released back to the pool.

Claim state machine (issue #375 Phase 2a — labels + native assignees are SSOT):
  - A claim exists iff the issue carries a claimed label
    (``status:claimed`` / ``status:in-progress``) OR has native assignees.
  - The lease clock is the latest lease-relevant event timestamp from the issue
    event timeline (``labeled`` with a claimed label, ``assigned``) — precise,
    and immune to unrelated issue activity.
  - When the event timeline is unavailable or carries no lease-relevant event,
    the clock falls back to the issue ``updatedAt`` and the stale record is
    tagged ``clock_source: "updatedAt-fallback"``. LIMITATION (documented,
    honest): ``updatedAt`` is refreshed by ANY issue activity, so a fallback
    clock may under-report staleness. It never over-releases.
  - A claim with no resolvable clock is never released (fail-conservative:
    you cannot date a lease, you cannot break it).
  - Legacy comment-regex claim detection is DEPRECATED: available only behind
    ``--legacy-comments`` for the migration window. Removal trigger: when
    ``continuous_agent_loop.py`` writes claim labels (#375 Phase 2b), delete
    the flag and ``CLAIM_PATTERNS`` entirely.
  - Release write-side vocabulary: remove claimed labels, ADD
    ``status:unclaimed`` (target state per #375 §2), clear agent assignees
    (``--keep-assignees`` opt-out). The release plan is built by a pure
    function and asserted offline by ``--self-test``.

Principles:
  - Stdlib-only: zero external dependencies, runs in public GitHub Actions and offline.
  - Fail-closed: invalid inputs or unreadable data produce non-zero exits, never silent skips.
  - Fast: ls-remote and gh queries execute in ~1-2 seconds; event fetch is bounded
    to claimed-prefiltered candidates only (first page, per_page=100 — claims are recent;
    older events degrade to the documented updatedAt fallback, never to a wrong release).
  - Testable: includes --self-test with offline fixtures covering both claim modes.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UPSTREAM_REPO = os.environ.get("GH_REPO", "Supremeai-bd/supremeai-open")
CLAIMED_LABELS = {"status:claimed", "status:in-progress"}
UNCLAIMED_LABEL = "status:unclaimed"
EXCLUDED_LABELS = {"state:seq-hold", "blocked-by-upstream", "mirror:private"}

CLAIM_PATTERNS = [
    re.compile(r"(?:🎯|🤖)?\s*\**\bclaim(?:ing|ed)?\b\**", re.IGNORECASE),
    re.compile(r"claiming this issue", re.IGNORECASE),
    re.compile(r"agent claim", re.IGNORECASE),
]

STAGE_1_CLAIM_TO_BRANCH_MINUTES = 10.0
STAGE_2_BRANCH_TO_PR_MINUTES = 30.0


def run_cmd(args: List[str]) -> Tuple[int, str, str]:
    """Execute a CLI command with UTF-8 encoding."""
    try:
        res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=False)
        return res.returncode, res.stdout, res.stderr
    except Exception as exc:
        return 1, "", str(exc)


def is_claim_comment(body: str) -> bool:
    """Check if comment text represents an agent task claim (LEGACY mode only)."""
    if not body:
        return False
    return any(p.search(body) for p in CLAIM_PATTERNS)


def extract_claim_timestamp(issue: Dict[str, Any]) -> Optional[datetime.datetime]:
    """LEGACY clock: latest claim comment timestamp, else claimed-label updatedAt.

    Kept byte-compatible with the pre-#375-Phase-2a behavior; used only when
    ``--legacy-comments`` is active or by external callers that predate the
    labels+assignees SSOT.
    """
    comments = issue.get("comments", []) or []
    latest_claim_dt: Optional[datetime.datetime] = None

    for c in comments:
        c_body = c.get("body", "")
        if is_claim_comment(c_body):
            c_time_str = c.get("createdAt")
            if c_time_str:
                try:
                    c_dt = datetime.datetime.fromisoformat(c_time_str.replace("Z", "+00:00"))
                    if latest_claim_dt is None or c_dt > latest_claim_dt:
                        latest_claim_dt = c_dt
                except Exception:
                    pass

    if latest_claim_dt is not None:
        return latest_claim_dt

    labels = [str(l.get("name", "")).lower() for l in issue.get("labels", []) if isinstance(l, dict)]
    if any(l in CLAIMED_LABELS for l in labels):
        up_str = issue.get("updatedAt")
        if up_str:
            try:
                return datetime.datetime.fromisoformat(up_str.replace("Z", "+00:00"))
            except Exception:
                pass

    return None


def parse_lease_events(events: Optional[List[Dict[str, Any]]]) -> Tuple[List[Tuple[datetime.datetime, str]], int]:
    """Parse an issue event timeline into lease-relevant (timestamp, kind) pairs.

    Lease-relevant events: ``labeled`` with a claimed label, ``assigned``.
    Malformed events (not a dict, unreadable timestamp) are skipped AND counted —
    one bad event never blinds the clock (P6: corrupt record skip-and-count).
    Unrelated event types are ignored by design (not malformed).
    """
    parsed: List[Tuple[datetime.datetime, str]] = []
    malformed = 0
    for ev in events or []:
        if not isinstance(ev, dict):
            malformed += 1
            continue
        etype = str(ev.get("event", "") or ev.get("type", ""))
        ts = ev.get("created_at") or ev.get("createdAt")
        try:
            dt = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            malformed += 1
            continue
        if etype == "labeled":
            lbl = str((ev.get("label") or {}).get("name", "")).lower()
            if lbl in CLAIMED_LABELS:
                parsed.append((dt, "labeled"))
        elif etype == "assigned":
            parsed.append((dt, "assigned"))
    return parsed, malformed


def resolve_lease_clock(
    issue: Dict[str, Any],
    events: Optional[List[Dict[str, Any]]],
    has_claimed_label: bool,
    assignees: List[str],
) -> Tuple[Optional[datetime.datetime], Optional[str]]:
    """SSOT lease clock (labels + native assignees).

    Priority:
      1. Latest lease-relevant event timestamp (precise; immune to unrelated activity).
      2. Issue ``updatedAt`` fallback — tagged ``updatedAt-fallback`` (coarse:
         any activity refreshes it; may under-report staleness, never over-releases).
    Returns (None, None) when no clock can be resolved — caller must NOT release.
    """
    parsed, _malformed = parse_lease_events(events)
    if parsed:
        latest_dt = max(dt for dt, _kind in parsed)
        return latest_dt, "events"

    if has_claimed_label or assignees:
        up_str = issue.get("updatedAt")
        if up_str:
            try:
                return (
                    datetime.datetime.fromisoformat(str(up_str).replace("Z", "+00:00")),
                    "updatedAt-fallback",
                )
            except Exception:
                pass
    return None, None


def fetch_lease_events(repo: str, issue_numbers: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    """Fetch event timelines for claimed-prefiltered candidates only (bounded cost).

    Fail-open per issue: a failed or unparseable fetch yields ``[]`` for that
    issue and the evaluator falls back to ``updatedAt`` with an honest
    ``clock_source`` marker. One unreachable issue never blinds the sweep.
    """
    out: Dict[int, List[Dict[str, Any]]] = {}
    for num in issue_numbers:
        code, body, _err = run_cmd(["gh", "api", f"repos/{repo}/issues/{num}/events?per_page=100"])
        if code != 0 or not body.strip():
            out[num] = []
            continue
        try:
            data = json.loads(body)
            out[num] = data if isinstance(data, list) else []
        except Exception:
            out[num] = []
    return out


def get_remote_branches(repo: str) -> List[str]:
    """Fetch remote branch refnames from origin."""
    code, out, _ = run_cmd(["git", "ls-remote", "--heads", "origin"])
    if code != 0 or not out.strip():
        # Fallback to gh api
        code, out, _ = run_cmd(["gh", "api", f"repos/{repo}/branches", "--jq", ".[].name"])
        if code == 0 and out.strip():
            return [b.strip() for b in out.strip().split("\n") if b.strip()]
        return []

    branches = []
    for line in out.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].startswith("refs/heads/"):
            branches.append(parts[1].replace("refs/heads/", "").strip())
    return branches


def issue_has_remote_branch(issue_number: int, branch_names: List[str]) -> Tuple[bool, Optional[str]]:
    """Determine if any remote branch targets this issue number."""
    # Matches /123, -123-, -123, issue-123, issue123
    num_str = str(issue_number)
    pattern = re.compile(rf"(^|/|-|_)({num_str})($|/|-|_)", re.IGNORECASE)

    for b in branch_names:
        if pattern.search(b) or f"issue-{num_str}" in b.lower() or f"issue{num_str}" in b.lower():
            return True, b
    return False, None


def get_open_pr_issue_references(repo: str) -> Set[int]:
    """Fetch all issue numbers currently referenced by open PRs."""
    code, out, _ = run_cmd([
        "gh", "pr", "list",
        "--repo", repo,
        "--state", "open",
        "--limit", "200",
        "--json", "number,title,body,headRefName"
    ])
    if code != 0 or not out.strip():
        return set()

    try:
        prs = json.loads(out)
    except Exception:
        return set()

    referenced_issues: Set[int] = set()
    for pr in prs:
        text = f"{pr.get('title', '')} {pr.get('body', '')} {pr.get('headRefName', '')}"
        matches = re.findall(r"#(\d+)|(?:issue[-_](\d+))", text, re.IGNORECASE)
        for m in matches:
            for num_str in m:
                if num_str:
                    referenced_issues.add(int(num_str))

    return referenced_issues


def evaluate_graduated_claims(
    issues: List[Dict[str, Any]],
    open_pr_refs: Set[int],
    remote_branches: List[str],
    claim_to_branch_min: float = STAGE_1_CLAIM_TO_BRANCH_MINUTES,
    branch_to_pr_min: float = STAGE_2_BRANCH_TO_PR_MINUTES,
    now: Optional[datetime.datetime] = None,
    events_by_issue: Optional[Dict[int, List[Dict[str, Any]]]] = None,
    legacy_comments: bool = False,
) -> List[Dict[str, Any]]:
    """Evaluate 2-stage graduated lease: 10m to branch, 30m branch to PR.

    Claim sources:
      - Default (SSOT, #375 Phase 2a): claimed labels + native assignees;
        lease clock from the issue event timeline (resolve_lease_clock).
      - legacy_comments=True (deprecated transition): comment-regex claim
        detection with the pre-existing clock semantics (extract_claim_timestamp).

    Additive output fields (backward compatible): ``assignees`` and
    ``clock_source``. Existing fields keep their names and meaning.
    """
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)

    events_by_issue = events_by_issue or {}
    stale: List[Dict[str, Any]] = []

    for issue in issues:
        num = issue.get("number")
        if not num:
            continue

        labels = [str(l.get("name", "")).lower() for l in issue.get("labels", []) if isinstance(l, dict)]
        if any(ex in labels for ex in EXCLUDED_LABELS):
            continue
        if any(l.startswith("bridge:") for l in labels):
            continue

        title_lower = issue.get("title", "").lower()
        if title_lower.startswith("audit(") or "admin_decision" in title_lower or "bridge work order" in title_lower:
            continue

        assignees = [
            str(a.get("login", "")) for a in (issue.get("assignees") or []) if isinstance(a, dict)
        ]
        has_claimed_label = any(cl in labels for cl in CLAIMED_LABELS)

        if legacy_comments:
            claim_dt = extract_claim_timestamp(issue)
            clock_source = "legacy-comments" if claim_dt is not None else None
        else:
            claim_dt, clock_source = resolve_lease_clock(
                issue, events_by_issue.get(int(num)), has_claimed_label, assignees
            )

        is_claimed = has_claimed_label or bool(assignees) or (claim_dt is not None)
        if not is_claimed:
            continue

        # If an active open PR exists, claim is progressing cleanly
        if int(num) in open_pr_refs:
            continue

        # Fail-conservative: a claim without a resolvable clock is never released.
        if claim_dt is None:
            continue

        elapsed_min = (now - claim_dt).total_seconds() / 60.0
        has_branch, matched_branch = issue_has_remote_branch(int(num), remote_branches)

        # STAGE 1 CHECK: No branch pushed within 10 minutes of claim
        if not has_branch:
            if elapsed_min >= claim_to_branch_min:
                stale.append({
                    "number": num,
                    "title": issue.get("title", ""),
                    "stage": 1,
                    "reason": f"No branch created within {claim_to_branch_min}m of claim",
                    "elapsed_minutes": round(elapsed_min, 1),
                    "branch": None,
                    "labels": labels,
                    "assignees": assignees,
                    "clock_source": clock_source,
                })
        else:
            # STAGE 2 CHECK: Branch exists, but no PR submitted within 30 minutes
            if elapsed_min >= (claim_to_branch_min + branch_to_pr_min):
                stale.append({
                    "number": num,
                    "title": issue.get("title", ""),
                    "stage": 2,
                    "reason": f"Branch '{matched_branch}' exists but no PR created within {branch_to_pr_min}m",
                    "elapsed_minutes": round(elapsed_min, 1),
                    "branch": matched_branch,
                    "labels": labels,
                    "assignees": assignees,
                    "clock_source": clock_source,
                })

    return stale


def build_release_plan(
    labels_present: Optional[List[str]],
    assignees: Optional[List[str]] = None,
    keep_assignees: bool = False,
) -> List[Dict[str, Any]]:
    """Build the ordered release action plan (#375 Phase 2a target vocabulary).

    Pure function — asserted offline by --self-test; executed by
    execute_release_plan in live mode.

    - ``labels_present=None`` (legacy positional callers): unconditionally remove
      every claimed label (matches pre-2a behavior exactly).
    - Otherwise: remove only claimed labels actually present.
    - Always ADD ``status:unclaimed`` (the #375 §2 target vocabulary).
    - Clear assignees unless ``keep_assignees`` or none present.
    """
    if labels_present is None:
        to_remove = sorted(CLAIMED_LABELS)
    else:
        present = {str(l).lower() for l in labels_present}
        to_remove = sorted(cl for cl in CLAIMED_LABELS if cl in present)

    plan: List[Dict[str, Any]] = [{"op": "remove_label", "label": lbl} for lbl in to_remove]
    plan.append({"op": "add_label", "label": UNCLAIMED_LABEL})
    logins = [str(a) for a in (assignees or []) if str(a)]
    if logins and not keep_assignees:
        plan.append({"op": "remove_assignees", "assignees": logins})
    return plan


def execute_release_plan(repo: str, issue_number: int, plan: List[Dict[str, Any]]) -> bool:
    """Execute a release plan. One gh call for labels, one for assignees."""
    remove_labels = [p["label"] for p in plan if p["op"] == "remove_label"]
    add_labels = [p["label"] for p in plan if p["op"] == "add_label"]
    remove_assignees: List[str] = []
    for p in plan:
        if p["op"] == "remove_assignees":
            remove_assignees.extend(p.get("assignees", []))

    ok = True
    if remove_labels or add_labels:
        cmd = ["gh", "issue", "edit", str(issue_number), "--repo", repo]
        for lbl in remove_labels:
            cmd.extend(["--remove-label", lbl])
        for lbl in add_labels:
            cmd.extend(["--add-label", lbl])
        l_code, _, _ = run_cmd(cmd)
        ok = ok and l_code == 0

    if remove_assignees:
        cmd = ["gh", "issue", "edit", str(issue_number), "--repo", repo]
        for login in remove_assignees:
            cmd.extend(["--remove-assignee", login])
        a_code, _, _ = run_cmd(cmd)
        ok = ok and a_code == 0

    return ok


def release_issue_claim(
    repo: str,
    issue_number: int,
    stage: int,
    reason: str,
    elapsed_min: float,
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
    keep_assignees: bool = False,
) -> bool:
    """Post release comment and execute the label/assignee release plan.

    Backward compatible: the original positional signature is preserved; when
    ``labels``/``assignees`` are omitted the plan degrades to unconditional
    claimed-label removal + ``status:unclaimed`` (no assignee writes).
    """
    clearing = "" if keep_assignees else ", clearing agent assignees"
    comment = (
        f"⏰ **Graduated Lease Auto-Release (Stage {stage})**\n\n"
        f"- **Trigger:** {reason} (elapsed: {elapsed_min}m)\n"
        f"- **Heartbeat Policy:** Claim-to-branch TTL is 10 min; branch-to-PR TTL is 30 min.\n"
        f"- **Action:** Releasing claim marker back to the public pool — removing claimed labels, "
        f"adding `status:unclaimed`{clearing}.\n\n"
        f"Task is immediately available for `--pick-next` dispatch."
    )
    # Post audit comment
    run_cmd(["gh", "issue", "comment", str(issue_number), "--repo", repo, "--body", comment])

    plan = build_release_plan(labels, assignees, keep_assignees)
    return execute_release_plan(repo, issue_number, plan)


def claimed_candidate_numbers(issues: List[Dict[str, Any]]) -> List[int]:
    """Prefilter: issue numbers that carry a claimed label or any assignee.

    Bounds the per-issue event fetch to actual claim candidates (fail-open
    elsewhere; exclusions are re-applied inside the evaluator).
    """
    out: List[int] = []
    for issue in issues:
        num = issue.get("number")
        if not num:
            continue
        labels = [str(l.get("name", "")).lower() for l in issue.get("labels", []) if isinstance(l, dict)]
        assignees = issue.get("assignees") or []
        if any(cl in labels for cl in CLAIMED_LABELS) or assignees:
            out.append(int(num))
    return out


def run_self_test() -> int:
    """Offline test of the 2-stage graduated lease (SSOT + legacy modes)."""
    print("Running 2-stage graduated lease self-test...")
    base_time = datetime.datetime(2026, 10, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)

    def iso(minute: int, hour: int = 11) -> str:
        return f"2026-10-15T{hour:02d}:{minute:02d}:00Z"

    # ---- Fixtures (1-7 preserved from the pre-2a suite; comment-based claims) ----
    # Issue 1: Claimed 5 min ago, no branch -> NOT stale (within 10 min window)
    iss1 = {
        "number": 1,
        "title": "task 1",
        "labels": [{"name": "P1-high"}],
        "comments": [{"body": "🎯 Claiming issue", "createdAt": iso(55)}],
    }

    # Issue 2: Claimed 15 min ago, NO branch -> STALE (Stage 1 trigger: >10m no branch)
    iss2 = {
        "number": 2,
        "title": "task 2",
        "labels": [{"name": "P1-high"}],
        "comments": [{"body": "🎯 Claiming issue", "createdAt": iso(45)}],
    }

    # Issue 3: Claimed 25 min ago, branch exists -> NOT stale (within 40 min total)
    iss3 = {
        "number": 3,
        "title": "task 3",
        "labels": [{"name": "P1-high"}],
        "comments": [{"body": "🎯 Claiming issue", "createdAt": iso(35)}],
    }

    # Issue 4: Claimed 45 min ago, branch exists but NO PR -> STALE (Stage 2 trigger: >40m)
    iss4 = {
        "number": 4,
        "title": "task 4",
        "labels": [{"name": "P1-high"}],
        "comments": [{"body": "🎯 Claiming issue", "createdAt": iso(15)}],
    }

    # Issue 5: Claimed 50 min ago, PR exists -> NOT stale (PR active)
    iss5 = {
        "number": 5,
        "title": "task 5",
        "labels": [{"name": "P1-high"}],
        "comments": [{"body": "🎯 Claiming issue", "createdAt": iso(10)}],
    }

    # Issue 6: claimed LABEL but NO claim comment, 120m old -> STAGE 1 STALE.
    # Regression (#222 fallout): extract_claim_timestamp() crashed with
    # NameError: CLAIMABLE_LABEL on exactly this input, killing the whole
    # releaser (and with it the agent-loop cron step) on any such issue.
    iss6 = {
        "number": 6,
        "title": "task 6",
        "labels": [{"name": "status:claimed"}],
        "comments": [],
        "updatedAt": "2026-10-15T10:00:00Z",
    }

    # Issue 7: plain unclaimed issue (no claim markers, no comments) — must
    # NOT be treated as claimed under the implicit claimable lifecycle.
    iss7 = {
        "number": 7,
        "title": "task 7",
        "labels": [{"name": "P2-medium"}],
        "comments": [],
        "updatedAt": "2026-10-15T10:00:00Z",
    }

    branches = ["feat/issue-3-contract", "fix/issue-4-repair", "fix/issue-5-patch"]
    open_prs = {5}

    # ---- SSOT mode (default): comment-only claims are INVISIBLE (T-C) ----
    stale = evaluate_graduated_claims(
        [iss1, iss2, iss3, iss4, iss5, iss6, iss7],
        open_prs,
        branches,
        now=base_time,
        events_by_issue={},
        legacy_comments=False,
    )
    assert [s["number"] for s in stale] == [6], f"SSOT mode: expected only #6, got {stale}"
    assert stale[0]["stage"] == 1 and stale[0]["clock_source"] == "updatedAt-fallback", stale[0]
    assert stale[0]["assignees"] == [], stale[0]

    # ---- T-A: events clock beats a manipulated fresh updatedAt ----
    # Labeled 15m ago per events; updatedAt refreshed 1m ago by unrelated
    # activity. Pre-2a fallback clock would see 1m (lease survives forever
    # under activity — the zombie-lease defect). Events clock must expire it.
    iss8 = {
        "number": 8,
        "title": "task 8 zombie lease",
        "labels": [{"name": "status:claimed"}],
        "comments": [],
        "updatedAt": "2026-10-15T11:59:00Z",
    }
    events8 = [
        {"event": "labeled", "label": {"name": "status:claimed"}, "created_at": iso(45)},
        {"event": "commented", "created_at": "2026-10-15T11:59:30Z"},
    ]
    stale8 = evaluate_graduated_claims(
        [iss8], set(), [], now=base_time, events_by_issue={8: events8}, legacy_comments=False
    )
    assert len(stale8) == 1 and stale8[0]["number"] == 8, f"T-A failed: {stale8}"
    assert stale8[0]["clock_source"] == "events", stale8[0]

    # ---- T-B: assignee-only claim via 'assigned' event, Stage 2 ----
    iss9 = {
        "number": 9,
        "title": "task 9 assignee claim",
        "labels": [{"name": "P1-high"}],
        "assignees": [{"login": "bot-agent-1"}],
        "comments": [],
        "updatedAt": "2026-10-15T11:59:00Z",
    }
    events9 = [{"event": "assigned", "assignee": {"login": "bot-agent-1"}, "created_at": iso(15)}]
    stale9 = evaluate_graduated_claims(
        [iss9], set(), branches + ["fix/issue-9-repair"], now=base_time,
        events_by_issue={9: events9}, legacy_comments=False
    )
    assert len(stale9) == 1 and stale9[0]["number"] == 9 and stale9[0]["stage"] == 2, f"T-B failed: {stale9}"
    assert stale9[0]["clock_source"] == "events" and stale9[0]["assignees"] == ["bot-agent-1"], stale9[0]

    # ---- T-F: malformed events skipped AND counted, good ones still used ----
    events10 = [
        "not-a-dict",
        {"event": "labeled", "label": {"name": "status:claimed"}, "created_at": "not-a-timestamp"},
        {"event": "labeled", "label": {"name": "status:claimed"}, "created_at": iso(45)},
    ]
    parsed, malformed = parse_lease_events(events10)
    assert malformed == 2, f"T-F malformed count: {malformed}"
    assert len(parsed) == 1 and parsed[0][1] == "labeled", parsed

    # ---- T-G: excluded + bridge: labels still skip in SSOT mode ----
    iss11 = {
        "number": 11,
        "title": "task 11 excluded",
        "labels": [{"name": "status:claimed"}, {"name": "state:seq-hold"}],
        "updatedAt": "2026-10-15T09:00:00Z",
    }
    iss12 = {
        "number": 12,
        "title": "Bridge Work Order — anything",
        "labels": [{"name": "bridge:queued"}, {"name": "status:claimed"}],
        "updatedAt": "2026-10-15T09:00:00Z",
    }
    stale_g = evaluate_graduated_claims(
        [iss11, iss12], set(), [], now=base_time, events_by_issue={}, legacy_comments=False
    )
    assert stale_g == [], f"T-G failed: {stale_g}"

    # ---- LEGACY mode (deprecated transition flag): original suite semantics ----
    stale_legacy = evaluate_graduated_claims(
        [iss1, iss2, iss3, iss4, iss5, iss6, iss7],
        open_prs,
        branches,
        now=base_time,
        events_by_issue={},
        legacy_comments=True,
    )
    assert len(stale_legacy) == 3, f"Legacy mode: expected 3 stale issues, got {len(stale_legacy)}"
    assert stale_legacy[0]["number"] == 2 and stale_legacy[0]["stage"] == 1, stale_legacy[0]
    assert stale_legacy[1]["number"] == 4 and stale_legacy[1]["stage"] == 2, stale_legacy[1]
    assert stale_legacy[2]["number"] == 6 and stale_legacy[2]["stage"] == 1, stale_legacy[2]
    assert all(s["number"] != 7 for s in stale_legacy), "Unlabeled issue must not be treated as claimed"
    assert all(s["clock_source"] == "legacy-comments" for s in stale_legacy if s["number"] in (2, 4)), \
        "comment-derived claims must be tagged legacy-comments"
    # iss5 (active PR) and iss3 (fresh branch) untouched in legacy mode
    assert all(s["number"] not in (3, 5) for s in stale_legacy), stale_legacy

    # ---- T-E: release plan builder (pure, ordered, target vocabulary) ----
    # Explicit labels: remove only present claimed labels, add status:unclaimed,
    # clear assignees.
    plan = build_release_plan(
        ["status:claimed", "P1-high", "status:in-progress"], ["bot-agent-1", "bot-agent-2"]
    )
    assert plan[0] == {"op": "remove_label", "label": "status:claimed"}, plan
    assert plan[1] == {"op": "remove_label", "label": "status:in-progress"}, plan
    assert plan[2] == {"op": "add_label", "label": "status:unclaimed"}, plan
    assert plan[3] == {"op": "remove_assignees", "assignees": ["bot-agent-1", "bot-agent-2"]}, plan
    # keep_assignees=True: no assignee op
    plan2 = build_release_plan(["status:claimed"], ["bot-agent-1"], keep_assignees=True)
    assert all(p["op"] != "remove_assignees" for p in plan2), plan2
    # Legacy positional callers (labels=None): unconditional claimed-label removal
    plan3 = build_release_plan(None)
    assert [p["label"] for p in plan3 if p["op"] == "remove_label"] == sorted(CLAIMED_LABELS), plan3
    assert any(p["op"] == "add_label" and p["label"] == "status:unclaimed" for p in plan3), plan3
    assert all(p["op"] != "remove_assignees" for p in plan3), plan3
    # No claimed labels present: nothing to remove, still adds status:unclaimed
    plan4 = build_release_plan(["P1-high"], [])
    assert all(p["op"] != "remove_label" for p in plan4), plan4
    assert plan4[0] == {"op": "add_label", "label": "status:unclaimed"}, plan4

    print("✅ 2-Stage graduated lease self-test passed cleanly (SSOT + legacy modes, release plans).")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="2-Stage Graduated Claim Lease Gate")
    parser.add_argument("--repo", default=UPSTREAM_REPO, help="GitHub repository (owner/repo)")
    parser.add_argument("--claim-to-branch-min", type=float, default=STAGE_1_CLAIM_TO_BRANCH_MINUTES,
                        help="Minutes allowed from claim to branch push (default: 10)")
    parser.add_argument("--branch-to-pr-min", type=float, default=STAGE_2_BRANCH_TO_PR_MINUTES,
                        help="Minutes allowed from branch to PR creation (default: 30)")
    parser.add_argument("--auto-release", action="store_true", help="Automatically release claims on GitHub")
    parser.add_argument("--legacy-comments", action="store_true",
                        help="DEPRECATED transition mode: detect claims via legacy comment regex "
                             "(#375 Phase 2a default is labels+assignees SSOT). Removal trigger: "
                             "Phase 2b (loop writes claim labels).")
    parser.add_argument("--keep-assignees", action="store_true",
                        help="Do not clear native assignees when releasing a claim")
    parser.add_argument("--no-fetch-events", action="store_true",
                        help="Skip the per-candidate event timeline fetch; lease clock falls back "
                             "to issue updatedAt (coarse, may under-report staleness — tagged in output)")
    parser.add_argument("--self-test", action="store_true", help="Run offline self-test and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    print(f"🔍 Checking 2-stage graduated claim leases on {args.repo}...")
    print(f"   Stage 1: {args.claim_to_branch_min}m (Claim -> Branch) | Stage 2: {args.branch_to_pr_min}m (Branch -> PR)")
    print(f"   Claim SSOT: {'legacy comment regex (DEPRECATED)' if args.legacy_comments else 'labels + native assignees'}")

    code, out, err = run_cmd([
        "gh", "issue", "list",
        "--repo", args.repo,
        "--state", "open",
        "--limit", "200",
        "--json", "number,title,labels,assignees,comments,updatedAt,createdAt"
    ])
    if code != 0:
        print(f"❌ Failed to fetch issues: {err}", file=sys.stderr)
        return 1

    try:
        issues = json.loads(out)
    except Exception as exc:
        print(f"❌ Failed to parse issues JSON: {exc}", file=sys.stderr)
        return 1

    open_prs = get_open_pr_issue_references(args.repo)
    remote_branches = get_remote_branches(args.repo)

    events_by_issue: Dict[int, List[Dict[str, Any]]] = {}
    if not args.legacy_comments and not args.no_fetch_events:
        candidates = claimed_candidate_numbers(issues)
        if candidates:
            print(f"   Fetching lease events for {len(candidates)} claimed candidate(s)...")
            events_by_issue = fetch_lease_events(args.repo, candidates)
            empty = sum(1 for v in events_by_issue.values() if not v)
            if empty:
                print(f"   ⚠️ {empty} candidate(s) returned no usable events — "
                      f"their clocks fall back to updatedAt (tagged in output).")

    stale_issues = evaluate_graduated_claims(
        issues,
        open_prs,
        remote_branches,
        claim_to_branch_min=args.claim_to_branch_min,
        branch_to_pr_min=args.branch_to_pr_min,
        events_by_issue=events_by_issue,
        legacy_comments=args.legacy_comments,
    )

    if not stale_issues:
        print(f"✅ Clean: Zero orphaned claims detected across {len(issues)} open issues.")
        return 0

    print(f"⚠️ Found {len(stale_issues)} orphaned claim(s):")
    for s in stale_issues:
        clock = s.get("clock_source") or "none"
        print(f"  - Issue #{s['number']} [Stage {s['stage']}]: '{s['title']}' "
              f"({s['reason']}, elapsed: {s['elapsed_minutes']}m, clock: {clock})")
        if args.auto_release:
            print(f"    🔄 Releasing claim for #{s['number']}...")
            ok = release_issue_claim(
                args.repo,
                s["number"],
                s["stage"],
                s["reason"],
                s["elapsed_minutes"],
                labels=s["labels"],
                assignees=s.get("assignees") or [],
                keep_assignees=args.keep_assignees,
            )
            if ok:
                print(f"    ✅ Issue #{s['number']} successfully released back to the open pool.")
            else:
                print(f"    ❌ Failed to release #{s['number']}.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
