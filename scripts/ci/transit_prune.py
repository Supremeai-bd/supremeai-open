#!/usr/bin/env python3
"""transit_prune.py — Ephemeral Transit Pipeline: auto-prune decision core.

Pure, offline, dependency-free core for issue #416 (Ephemeral Transit Pipeline
Doctrine / The Ephemeral Mailbox Model): supremeai-open's ``patches/`` folder
is a TRANSIT INBOX, not permanent storage. Once a transit patch is verified as
dispatched to its satellite target (landing.yml), it must be removed so the
public host stays pristine and zero-residue.

This module owns ONLY the fail-closed decision logic:

  - What counts as "verified dispatch" (structural evidence contract).
  - Whether a given patch is safe to prune (fail-closed: any doubt = keep).
  - The exact commit message the cleanup job must use (byte-specified by
    the doctrine: ``chore(bridge): auto-prune transit patch <task-id> after
    successful satellite dispatch``).

All I/O (reading patches/, git operations, workflow execution) stays with the
caller — typically the landing.yml post-dispatch cleanup job via a thin
wrapper, or an operator script. This module never touches the filesystem, the
network, or the environment; ``now`` is always injectable.

Fail-closed principle: a transit patch that cannot be PROVEN dispatched is
never pruned. The mailbox prefers residue over data loss (a pruned-but-
undispatched patch silently destroys the only public copy of agent work).
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional, Tuple

# ---- Vocabulary (SSOT: dispatch targets observed in .github/workflows/landing.yml) ----

DEFAULT_DISPATCH_TARGETS = frozenset({
    "Supremeai-bd/supremeai",
    "Supremeai-bd/supremeai-agents",
    "Supremeai-bd/supremeai-api",
    "Supremeai-bd/supremeai-archive",
    "Supremeai-bd/supremeai-browser",
    "Supremeai-bd/supremeai-command",
    "Supremeai-bd/supremeai-core",
    "Supremeai-bd/supremeai-infrastructure",
    "Supremeai-bd/supremeai-mcp-control-plane",
    "Supremeai-bd/supremeai-open",
    "Supremeai-bd/supremeai-sdk",
    "Supremeai-bd/supremeai-skills",
    "Supremeai-bd/supremeai-studio",
    "Supremeai-bd/supremeai-vscode",
})

PRUNE_COMMIT_MESSAGE_FMT = (
    "chore(bridge): auto-prune transit patch {task_id} after successful satellite dispatch"
)

_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
_PATCH_SUFFIX = ".patch"


def _parse_iso(value: Any) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


# ---- Task-id extraction ------------------------------------------------------

def parse_task_id(patch_ref: str) -> Tuple[Optional[str], List[str]]:
    """Extract the task-id from a transit patch reference.

    Accepts ``patches/<task-id>.patch``, ``<task-id>.patch`` (bare name), or a
    path ending in the same shape. Returns (task_id, reasons); task_id is None
    when the reference is not a well-formed transit patch name. The task-id is
    the filename stem — by bridge convention the full WO taskId, which may
    itself contain dots and dashes, so only the ``.patch`` suffix is stripped.
    """
    reasons: List[str] = []
    if not isinstance(patch_ref, str) or not patch_ref.strip():
        return None, ["empty patch reference"]
    name = patch_ref.strip().replace("\\", "/").split("/")[-1]
    if not name.endswith(_PATCH_SUFFIX):
        return None, [f"not a .patch file: {name!r}"]
    stem = name[: -len(_PATCH_SUFFIX)]
    if not stem:
        return None, ["empty task-id before .patch"]
    if stem in {".", ".."}:
        return None, [f"unsafe task-id: {stem!r}"]
    return stem, reasons


# ---- Dispatch evidence contract ----------------------------------------------

EVIDENCE_REQUIRED_KEYS = ("task_id", "target_repo", "dispatch_commit", "dispatched_at")


def validate_dispatch_evidence(
    evidence: Any,
    expected_task_id: str,
    known_targets: Optional[frozenset] = None,
) -> Tuple[bool, List[str]]:
    """Validate the structural dispatch-evidence contract. Fail-closed.

    Required keys:
      - ``task_id``: must equal the patch's own task-id (identity binding).
      - ``target_repo``: must be a known federation dispatch target.
      - ``dispatch_commit``: hex git sha (7-40 chars) of the dispatch commit
        on the target side.
      - ``dispatched_at``: ISO-8601 timestamp of the dispatch.

    Unknown or malformed fields never pass silently — every failure returns an
    explicit reason so the hold-back is auditable.
    """
    reasons: List[str] = []
    if not isinstance(evidence, dict):
        return False, ["dispatch evidence is not a mapping"]

    for key in EVIDENCE_REQUIRED_KEYS:
        if key not in evidence or evidence.get(key) in (None, ""):
            reasons.append(f"missing evidence field: {key}")

    if reasons:
        return False, reasons

    ev_task = str(evidence["task_id"])
    if ev_task != expected_task_id:
        reasons.append(
            f"task-id mismatch: evidence {ev_task!r} != patch {expected_task_id!r}"
        )

    targets = known_targets if known_targets is not None else DEFAULT_DISPATCH_TARGETS
    target = str(evidence["target_repo"])
    if target not in targets:
        reasons.append(f"unknown dispatch target: {target!r}")

    commit = str(evidence["dispatch_commit"])
    if not _COMMIT_SHA_RE.match(commit):
        reasons.append(f"dispatch_commit is not a hex sha (7-40): {commit!r}")

    if _parse_iso(evidence["dispatched_at"]) is None:
        reasons.append(f"dispatched_at is not ISO-8601: {evidence['dispatched_at']!r}")

    return (len(reasons) == 0), reasons


# ---- Prune decision ------------------------------------------------------------

def build_prune_plan(
    patch_ref: str,
    evidence: Any,
    known_targets: Optional[frozenset] = None,
    now: Optional[datetime.datetime] = None,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Decide whether a transit patch may be pruned. Fail-closed.

    Returns (plan, hold_reasons):
      - plan is None when ANY contract check fails; hold_reasons lists every
        reason (auditable, no silent keeps).
      - On success, plan = {patch, task_id, commit_message, evidence} — the
        caller executes the plan (git rm + commit + optional issue comment).
    """
    del now  # reserved for future grace-window policy; never load-bearing today
    task_id, reasons = parse_task_id(patch_ref)
    if task_id is None:
        return None, reasons

    ok, ev_reasons = validate_dispatch_evidence(evidence, task_id, known_targets)
    if not ok:
        return None, ev_reasons

    plan = {
        "patch": patch_ref,
        "task_id": task_id,
        "commit_message": build_prune_commit_message(task_id),
        "evidence": {
            "task_id": str(evidence["task_id"]),
            "target_repo": str(evidence["target_repo"]),
            "dispatch_commit": str(evidence["dispatch_commit"]),
            "dispatched_at": str(evidence["dispatched_at"]),
        },
    }
    return plan, []


def build_prune_commit_message(task_id: str) -> str:
    """Byte-exact cleanup commit message mandated by the doctrine (#416)."""
    return PRUNE_COMMIT_MESSAGE_FMT.format(task_id=task_id)


# ---- Sweep-level selection -------------------------------------------------------

def select_prunable_patches(
    patch_refs: List[str],
    evidence_by_task: Dict[str, Any],
    known_targets: Optional[frozenset] = None,
    now: Optional[datetime.datetime] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Partition a transit inbox into prunable vs held-back. Fail-closed.

    - ``prunable``: patches with fully valid dispatch evidence — each entry is
      a ready-to-execute prune plan.
    - ``held``: everything else, each with explicit reasons. A patch with NO
      evidence entry at all is held with reason "no dispatch evidence" (the
      honest default: absence of proof is not proof of dispatch).
    """
    prunable: List[Dict[str, Any]] = []
    held: List[Dict[str, Any]] = []

    for ref in patch_refs:
        task_id, reasons = parse_task_id(ref)
        if task_id is None:
            held.append({"patch": ref, "reasons": reasons})
            continue
        evidence = evidence_by_task.get(task_id)
        if evidence is None:
            held.append({"patch": ref, "task_id": task_id, "reasons": ["no dispatch evidence"]})
            continue
        plan, hold = build_prune_plan(ref, evidence, known_targets, now=now)
        if plan is None:
            held.append({"patch": ref, "task_id": task_id, "reasons": hold})
        else:
            prunable.append(plan)

    return {"prunable": prunable, "held": held}
