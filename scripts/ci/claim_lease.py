#!/usr/bin/env python3
"""claim_lease.py — 2-Stage Graduated Claim Lease: hermetic drop-in core.

Pure, offline, dependency-free core of the stale-claim release state machine
(#375 Phase 2a: labels + native assignees are the claim SSOT). This module is
a drop-in for the operator-side ``stale_claim_releaser.py``: all I/O (gh
calls, event fetch, plan execution, comment posting) stays with the caller;
this module exposes only deterministic, injectable logic.

Claim state machine:
  - A claim exists iff the issue carries a claimed label
    (``status:claimed`` / ``status:in-progress``) OR has native assignees.
  - The lease clock is the latest lease-relevant event timestamp from the
    issue event timeline (``labeled`` with a claimed label, ``assigned``) —
    precise, and immune to unrelated issue activity.
  - When the event timeline is unavailable or carries no lease-relevant
    event, the clock falls back to the issue ``updatedAt`` and the stale
    record is tagged ``clock_source: "updatedAt-fallback"``. LIMITATION
    (documented, honest): ``updatedAt`` is refreshed by ANY issue activity,
    so a fallback clock may under-report staleness. It never over-releases.
  - A claim with no resolvable clock is never released (fail-conservative:
    you cannot date a lease, you cannot break it).
  - Legacy comment-regex claim detection is DEPRECATED: available only via
    ``legacy_comments=True`` for the migration window. Removal trigger: when
    ``continuous_agent_loop.py`` writes claim labels (#375 Phase 2b), delete
    the flag and ``CLAIM_PATTERNS`` entirely.
  - Release write-side vocabulary: remove claimed labels, ADD
    ``status:unclaimed`` (target state per #375 §2), clear agent assignees
    (``--keep-assignees`` opt-out handled by the caller). The release plan is
    built by a pure function.

Stage windows (graduated lease):
  Stage 1 (Claim -> Branch): 10 minutes — a claim with no matching remote
  branch after 10 minutes is stale (agent failed to start).
  Stage 2 (Branch -> PR): 30 more minutes — a branch with no open PR after
  40 minutes total is stale (agent stuck/abandoned).

Principles:
  - Hermetic: ZERO static imports beyond stdlib, zero I/O, zero environment
    reads, zero subprocess. Every input is injected; ``now`` is a parameter.
  - Structural types mirror GitHub REST shapes (dicts), so the module cannot
    drift against either mirror's private copies.
  - Fail-conservative over fail-loud here by design: the caller owns I/O
    failure policy; this core only refuses to release what it cannot date.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional, Set, Tuple

# ---- Vocabulary (SSOT per #375 Phase 2a) ---------------------------------

CLAIMED_LABELS = {"status:claimed", "status:in-progress"}
UNCLAIMED_LABEL = "status:unclaimed"
EXCLUDED_LABELS = {"state:seq-hold", "blocked-by-upstream", "mirror:private"}

STAGE_1_CLAIM_TO_BRANCH_MINUTES = 10.0
STAGE_2_BRANCH_TO_PR_MINUTES = 30.0

# LEGACY claim detection (deprecated; see module docstring).
CLAIM_PATTERNS = [
    re.compile(r"(?:🎯|🤖)?\s*\**\bclaim(?:ing|ed)?\b\**", re.IGNORECASE),
    re.compile(r"claiming this issue", re.IGNORECASE),
    re.compile(r"agent claim", re.IGNORECASE),
]


def _parse_iso(value: Any) -> Optional[datetime.datetime]:
    """Parse an ISO-8601 timestamp ('Z' or offset). None when unreadable."""
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _label_names(issue: Dict[str, Any]) -> List[str]:
    """Lower-cased label names of an issue (structural, drift-proof)."""
    return [
        str(l.get("name", "")).lower()
        for l in (issue.get("labels") or [])
        if isinstance(l, dict)
    ]


def _assignee_logins(issue: Dict[str, Any]) -> List[str]:
    logins = [
        str(a.get("login", ""))
        for a in (issue.get("assignees") or [])
        if isinstance(a, dict)
    ]
    return [x for x in logins if x]


# ---- LEGACY (deprecated) comment-regex claim detection --------------------

def is_claim_comment(body: str) -> bool:
    """Check if comment text represents an agent task claim (LEGACY mode only)."""
    if not body:
        return False
    return any(p.search(body) for p in CLAIM_PATTERNS)


def extract_claim_timestamp(issue: Dict[str, Any]) -> Optional[datetime.datetime]:
    """LEGACY clock: latest claim comment timestamp, else claimed-label updatedAt.

    Kept byte-compatible with the pre-#375-Phase-2a behavior; used only when
    ``legacy_comments=True`` or by external callers that predate the
    labels+assignees SSOT.
    """
    comments = issue.get("comments", []) or []
    latest_claim_dt: Optional[datetime.datetime] = None

    for c in comments:
        if not isinstance(c, dict):
            continue
        if is_claim_comment(c.get("body", "")):
            c_dt = _parse_iso(c.get("createdAt"))
            if c_dt is not None and (latest_claim_dt is None or c_dt > latest_claim_dt):
                latest_claim_dt = c_dt

    if latest_claim_dt is not None:
        return latest_claim_dt

    if any(l in CLAIMED_LABELS for l in _label_names(issue)):
        return _parse_iso(issue.get("updatedAt"))

    return None


# ---- SSOT lease clock ------------------------------------------------------

def parse_lease_events(
    events: Optional[List[Dict[str, Any]]]
) -> Tuple[List[Tuple[datetime.datetime, str]], int]:
    """Parse an issue event timeline into lease-relevant (timestamp, kind) pairs.

    Lease-relevant events: ``labeled`` with a claimed label, ``assigned``.
    Malformed events (not a dict, unreadable timestamp) are skipped AND
    counted — one bad event never blinds the clock (P6: corrupt record
    skip-and-count). Unrelated event types are ignored by design (not
    malformed).
    """
    parsed: List[Tuple[datetime.datetime, str]] = []
    malformed = 0
    for ev in events or []:
        if not isinstance(ev, dict):
            malformed += 1
            continue
        etype = str(ev.get("event", "") or ev.get("type", ""))
        dt = _parse_iso(ev.get("created_at") or ev.get("createdAt"))
        if dt is None:
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
      1. Latest lease-relevant event timestamp (precise; immune to unrelated
         activity).
      2. Issue ``updatedAt`` fallback — tagged ``updatedAt-fallback`` (coarse:
         any activity refreshes it; may under-report staleness, never
         over-releases).
    Returns (None, None) when no clock can be resolved — caller must NOT
    release (fail-conservative).
    """
    parsed, _malformed = parse_lease_events(events)
    if parsed:
        latest_dt = max(dt for dt, _kind in parsed)
        return latest_dt, "events"

    if has_claimed_label or assignees:
        dt = _parse_iso(issue.get("updatedAt"))
        if dt is not None:
            return dt, "updatedAt-fallback"
    return None, None


# ---- Board geometry (pure helpers over caller-fetched data) ----------------

def issue_has_remote_branch(
    issue_number: int, branch_names: List[str]
) -> Tuple[bool, Optional[str]]:
    """Determine if any remote branch targets this issue number.

    Matches /123, -123-, -123, issue-123, issue123 style branch names.

    BEHAVIOR DELTA vs the pre-2a operator matcher (documented, tested): the
    legacy ``issue-<n>``/``issue<n>`` substring checks are boundary-guarded —
    an issue-12 claim no longer false-matches an issue-123 branch (numeric
    substring collision). The collision caused Stage 2 (40m) instead of
    Stage 1 (10m) for branchless claims — an under-release contract
    violation. Fail direction here stays conservative: only true orphans
    expire at Stage 1.
    """
    num_str = str(issue_number)
    pattern = re.compile(rf"(^|/|-|_)({num_str})($|/|-|_)", re.IGNORECASE)
    legacy = re.compile(rf"issue-?{num_str}(?:$|/|-|_)", re.IGNORECASE)

    for b in branch_names:
        if pattern.search(b) or legacy.search(b):
            return True, b
    return False, None


def claimed_candidate_numbers(issues: List[Dict[str, Any]]) -> List[int]:
    """Prefilter: issue numbers that carry a claimed label or any assignee.

    Bounds the per-issue event fetch (caller-side) to actual claim
    candidates; exclusions are re-applied inside the evaluator.
    """
    out: List[int] = []
    for issue in issues:
        num = issue.get("number")
        if not num:
            continue
        labels = _label_names(issue)
        assignees = issue.get("assignees") or []
        if any(cl in labels for cl in CLAIMED_LABELS) or assignees:
            out.append(int(num))
    return out


# ---- The evaluator (state machine) -----------------------------------------

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
        detection with the pre-existing clock semantics
        (extract_claim_timestamp).

    Board hygiene exclusions (same as the operator releaser):
      - EXCLUDED_LABELS members, and any ``bridge:``-prefixed label.
      - Titles starting with ``audit(`` or containing ``admin_decision`` or
        ``bridge work order``.

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

        labels = _label_names(issue)
        if any(ex in labels for ex in EXCLUDED_LABELS):
            continue
        if any(l.startswith("bridge:") for l in labels):
            continue

        title_lower = str(issue.get("title", "")).lower()
        if (
            title_lower.startswith("audit(")
            or "admin_decision" in title_lower
            or "bridge work order" in title_lower
        ):
            continue

        assignees = _assignee_logins(issue)
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


# ---- Release plan (pure; caller executes) -----------------------------------

def build_release_plan(
    labels_present: Optional[List[str]],
    assignees: Optional[List[str]] = None,
    keep_assignees: bool = False,
) -> List[Dict[str, Any]]:
    """Build the ordered release action plan (#375 Phase 2a target vocabulary).

    Pure function — asserted offline by the colocated test battery; executed
    by the caller (one gh call for labels, one for assignees).

    - ``labels_present=None`` (legacy positional callers): unconditionally
      remove every claimed label (matches pre-2a behavior exactly).
    - Otherwise: remove only claimed labels actually present.
    - Always ADD ``status:unclaimed`` (the #375 §2 target vocabulary).
    - Clear assignees unless ``keep_assignees`` or none present.
    """
    if labels_present is None:
        to_remove = sorted(CLAIMED_LABELS)
    else:
        present = {str(l).lower() for l in labels_present}
        to_remove = sorted(cl for cl in CLAIMED_LABELS if cl in present)

    plan: List[Dict[str, Any]] = [
        {"op": "remove_label", "label": lbl} for lbl in to_remove
    ]
    plan.append({"op": "add_label", "label": UNCLAIMED_LABEL})
    logins = [str(a) for a in (assignees or []) if str(a)]
    if logins and not keep_assignees:
        plan.append({"op": "remove_assignees", "assignees": logins})
    return plan


def build_release_comment(
    stage: int,
    reason: str,
    elapsed_min: float,
    keep_assignees: bool = False,
) -> str:
    """Pure formatter for the release audit comment (caller posts it).

    Byte-compatible with the operator releaser's historical template so the
    migration does not change what agents see on released issues.
    """
    clearing = "" if keep_assignees else ", clearing agent assignees"
    return (
        f"⏰ **Graduated Lease Auto-Release (Stage {stage})**\n\n"
        f"- **Trigger:** {reason} (elapsed: {elapsed_min}m)\n"
        f"- **Heartbeat Policy:** Claim-to-branch TTL is 10 min; branch-to-PR TTL is 30 min.\n"
        f"- **Action:** Releasing claim marker back to the public pool — removing claimed labels, "
        f"adding `status:unclaimed`{clearing}.\n\n"
        f"Task is immediately available for `--pick-next` dispatch."
    )
