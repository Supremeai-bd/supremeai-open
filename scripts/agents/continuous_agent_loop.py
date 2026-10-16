#!/usr/bin/env python3
"""Continuous Autonomous Agent Loop — Lazy Team Leader & Safety Dispatcher.

Target: External and autonomous agents contributing to SupremeAI Open Foundation
Repository: Supremeai-bd/supremeai-open

Pathway 2 (fork-based) support: pass --fork-owner <owner> (or set
SUPREMEAI_FORK_OWNER) so step 7 pushes the session branch to that fork and
opens the PR with head "<owner>:<branch>" against the upstream repository.

This loop operates as the "Lazy Team Leader":
  - Inspects open issues and task queues.
  - Classifies the task and selects the specialized agent role (Coder, Auditor, CI Fixer, etc.).
  - Builds a contract-bound, scoped prompt with strict file boundaries.
  - Executes isolated branch and workspace setup.
  - Enforces strict multi-tier automated safety gates (tier-count SSOT: docs/AGENT_LOOP_SPEC.md §4).
  - Records dynamic, verified test evidence in PRs.
  - Performs fresh-board checks before looping to the next task.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Configure UTF-8 for cross-platform stability
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_REPO = "Supremeai-bd/supremeai-open"
AGENTS_MD_PATH = REPO_ROOT / "AGENTS.md"
AGENT_RULES_PATH = REPO_ROOT / "AGENT_RULES.md"

VALID_TASK_TYPES = {
    "AUDIT", "PLAN", "IMPLEMENT", "FIX_CI", "REVIEW",
    "SECURITY_AUDIT", "DISCOVERY", "MERGE", "ADMIN_DECISION",
}
VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}
VALID_ADMIN_GATE_STATUSES = {"NOT_REQUIRED", "WAITING", "APPROVED", "REJECTED"}

# Canonical group taxonomy (#63): agents CANNOT invent arbitrary group names.
# Fail-closed: build_task_contract() / resolve_group() reject any group not
# listed here. The .github/ISSUE_TEMPLATE/agent-task.yml dropdown must stay
# aligned with this registry.
VALID_GROUPS = frozenset({
    "agent-orchestration",  # continuous loop, agent dispatch, roles, envelopes, lifecycle
    "mcp-tower",            # MCP Control Plane tools, health probes, bridge adapters, endpoints
    "core-engine",          # federation business logic, state machines, models
    "schemas-contracts",    # OpenAPI schemas, contract definitions, protocol envelopes
    "infra-ops",            # deploy configs, CI actions, cloud runtime configuration
})
DEFAULT_GROUP = "agent-orchestration"
ENVELOPE_VERSION = 1  # task-envelope-v1 (#63)
# #67 parity marker: BOTH copies of this program (public supremeai-open and
# the private Supremeai-bd/supremeai mirror) MUST print this exact string as
# the final stdout line of `--verify-only`. Copies that disagree on flag
# behaviour must not claim the same CONTRACT_VERSION — bump both sides
# together (see docs/AGENT_LOOP_SPEC.md §4b).
CONTRACT_VERSION = "agent-loop-contract/1"

# The 7 Specialist Agent Roles
ROLES: dict[str, str] = {
    "coder": "Implementation specialist (features, bug fixes, refactoring)",
    "auditor": "Review & validation specialist (code audit, security review)",
    "ci-fixer": "Pipeline & test repair specialist (GitHub Actions, build smoke)",
    "security-breaker": "Security boundary & fail-closed validation specialist",
    "browser-qa": "End-to-end integration & UI flow specialist",
    "planner": "Architecture, contracts, and ADR specification specialist",
    "watcher": "Telemetry, heartbeat health, and ecosystem drift specialist",
}


def log(icon: str, msg: str) -> None:
    print(f"{icon} {msg}")


def run_cmd(cmd: list[str], cwd: Path = REPO_ROOT, check: bool = False) -> tuple[int, str, str]:
    """Execute command safely and return (returncode, stdout, stderr).

    Returns exit code 127 fail-honestly when binary is not found, preventing
    unhandled FileNotFoundError on zero-credential environments without gh/git.
    """
    try:
        p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout = p.stdout.decode("utf-8", errors="replace").strip()
        stderr = p.stderr.decode("utf-8", errors="replace").strip()
        if check and p.returncode != 0:
            raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(cmd)}\n{stderr}")
        return p.returncode, stdout, stderr
    except FileNotFoundError as exc:
        binary = cmd[0] if cmd else "unknown"
        err = f"Binary not found: '{binary}'. Please install it or proceed in zero-credential offline mode."
        if check:
            raise RuntimeError(err) from exc
        return 127, "", err
    except Exception as exc:
        err = f"Execution error for {' '.join(cmd)}: {exc}"
        if check:
            raise RuntimeError(err) from exc
        return 1, "", err


def build_task_contract(
    task_id: str,
    issue: str | int | None = None,
    task_type: str = "IMPLEMENT",
    group: str = DEFAULT_GROUP,
    priority: str = "P2",
    objective: str = "",
    touching_files: list[str] | None = None,
    forbidden_paths: list[str] | None = None,
    dependencies: list[str] | None = None,
    predecessor: str | int | None = None,
    admin_gate_required: bool = False,
    admin_gate_status: str = "NOT_REQUIRED",
    role_policy: str = "contributor",
    required_evidence: list[str] | None = None,
    verification: list[str] | None = None,
    acceptance: list[str] | None = None,
    stop_conditions: list[str] | None = None,
    output_format: str = "structured",
) -> dict[str, Any]:
    """Standard Task Contract builder adhering to AGENT_RULES.md §7."""
    task_type_upper = task_type.upper()
    if task_type_upper not in VALID_TASK_TYPES:
        raise ValueError(
            f"Invalid task_type: '{task_type}'. Must be one of: {sorted(VALID_TASK_TYPES)}"
        )

    priority_upper = priority.upper()
    if priority_upper not in VALID_PRIORITIES:
        raise ValueError(
            f"Invalid priority: '{priority}'. Must be one of: {sorted(VALID_PRIORITIES)}"
        )

    gate_status_upper = admin_gate_status.upper()
    if gate_status_upper not in VALID_ADMIN_GATE_STATUSES:
        raise ValueError(
            f"Invalid admin_gate_status: '{admin_gate_status}'. Must be one of: {sorted(VALID_ADMIN_GATE_STATUSES)}"
        )

    # #63 fail-closed gate: arbitrary/invented group names are rejected here —
    # invalid contracts can no longer travel downstream to private CI.
    if group not in VALID_GROUPS:
        raise ValueError(
            f"Invalid group: '{group}'. Must be one of the canonical registry: {sorted(VALID_GROUPS)}"
        )

    return {
        "task_contract": {
            "version": 1,
            "task_id": str(task_id),
            "issue": str(issue) if issue is not None else None,
            "task_type": task_type_upper,
            "group": group,
            "priority": priority_upper,
            "sequence": None,
            "objective": objective or f"Task #{task_id}",
            "scope": {
                "touching_files": touching_files or [],
                "forbidden_paths": forbidden_paths or [
                    ".env*", "secrets/**", "credentials/**", "vault/**"
                ],
            },
            "dependencies": dependencies or [],
            "predecessor": str(predecessor) if predecessor is not None else None,
            "admin_gate": {
                "required": admin_gate_required,
                "status": gate_status_upper,
            },
            "role_policy": role_policy,
            "required_evidence": required_evidence or [
                "verification tier output", "diff check", "board freshness re-poll"
            ],
            "verification": verification or [
                "py_compile", "json schema parse", "smoke validation"
            ],
            "acceptance": acceptance or [
                "Passes local validation tests", "Zero unhandled crashes"
            ],
            "stop_conditions": stop_conditions or [
                "Security boundary hit", "Out of declared scope"
            ],
            "output_format": output_format,
        }
    }


def classify_task_role(title: str, labels: list[str], body: str) -> str:
    """Intelligently map issue context to one of the 7 specialist roles."""
    combined = f"{title} {' '.join(labels)} {body}".lower()
    if any(k in combined for k in ["sec", "security", "secret", "gitleaks", "credential", "vulnerability"]):
        return "security-breaker"
    if any(k in combined for k in ["ci", "workflow", "action", "pipeline", "matrix"]):
        return "ci-fixer"
    if any(k in combined for k in ["audit", "review", "parity", "drift", "readiness"]):
        return "auditor"
    if any(k in combined for k in ["plan", "adr", "architecture", "rfc", "contract"]):
        return "planner"
    if any(k in combined for k in ["browser", "e2e", "ui", "frontend", "playwright"]):
        return "browser-qa"
    if any(k in combined for k in ["telemetry", "heartbeat", "health", "watcher", "monitor"]):
        return "watcher"
    return "coder"


def build_agent_prompt(task: dict[str, Any], role: str, contract: dict[str, Any]) -> str:
    """Build a deterministic, contract-bound scoped prompt for the specialist agent."""
    tc = contract.get("task_contract", {})
    touching_files = tc.get("scope", {}).get("touching_files", [])
    forbidden_paths = tc.get("scope", {}).get("forbidden_paths", [])

    return f"""### 🤖 SupremeAI Task Assignment: {role.upper()}
You are assigned as the **{role.upper()}** specialist by the SupremeAI Continuous Loop Team Leader.

**1. Mission Objective:**
{tc.get('objective')}

**2. Task Context & Problem Statement:**
Issue #{task.get('id')}: {task.get('title')}
{task.get('body')}

**3. Scope Boundary (STRICT):**
- Authorized Touching Files: {touching_files if touching_files else 'Keep to smallest safe minimal set (1-5 files)'}
- Forbidden Paths: {forbidden_paths}

**4. Role Policy Contract ({role}):**
{ROLES.get(role, '')}

**5. Execution Instructions:**
- Implement the smallest safe change strictly inside declared scope.
- Maintain documentation and code comments integrity.
- Do NOT hallucinate private credentials or internal monorepo scripts.
- Satisfy the 3-Tier Verification Contract before handoff.
"""


def resolve_group(explicit: str | None, task: dict[str, Any] | None = None) -> str:
    """Deterministic group resolution (#63): --group flag > issue body/label scan > canonical default.

    Fail-closed: an unknown explicit group raises ValueError — agents cannot
    invent arbitrary group names outside the VALID_GROUPS registry.
    """
    if explicit:
        group = explicit.strip().lower()
        if group not in VALID_GROUPS:
            raise ValueError(
                f"Invalid group: '{explicit}'. Must be one of the canonical registry: {sorted(VALID_GROUPS)}"
            )
        return group
    if task:
        haystack = " ".join(task.get("labels", []) or []).lower() + "\n" + str(task.get("body") or "").lower()
        for group in sorted(VALID_GROUPS):
            if group in haystack:
                return group
    return DEFAULT_GROUP


def build_pr_body(
    task: dict[str, Any],
    contract: dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> str:
    """Single construction site for the PR submission record (#114).

    One builder, two renderings of the SAME skeleton (same sections, same
    order):
      - ``build_pr_body(task, contract)`` — the envelope's ``submission.pr_body_template``
        (four static section headers; no contract snippet, no evidence block).
      - ``build_pr_body(task, contract, evidence)`` — the exact body
        ``--auto-pr`` submits via ``gh pr create --body`` (adds the Task
        Contract YAML snippet and the Dynamic Test Evidence block between
        Type of Change and Rollback Path).

    Closing-keyword doctrine (U8, #219, #220): the Merge Gate overrides the
    squash commit subject, so ``Closes #N`` must ride in the PR body (and in
    the branch commit message) to survive into the final squash commit
    message — ``Refs #N`` alone can never auto-close the linked issue.
    """
    tc = (contract or {}).get("task_contract", {})
    issue_ref = tc.get("issue") or task.get("id")
    # Emit `Closes #N` only for a real board issue — "adhoc" tasks carry no
    # closing intent (no board issue exists to close).
    closing_line = (
        f"Closes #{issue_ref}\n"
        if issue_ref and str(issue_ref).strip() and str(issue_ref).lower() != "adhoc"
        else ""
    )

    contract_yaml_snippet = ""
    if contract and evidence is not None:
        contract_yaml_snippet = f"""
### Task Contract Snapshot (reproducibility & governance)
```yaml
task_contract:
  task_id: {tc.get('task_id')}
  task_type: {tc.get('task_type')}
  group: {tc.get('group')}
  priority: {tc.get('priority')}
  role: {tc.get('role_policy')}
  scope:
    touching_files: {json.dumps(tc.get('scope', {}).get('touching_files', []))}
    forbidden_paths: {json.dumps(tc.get('scope', {}).get('forbidden_paths', []))}
  admin_gate:
    required: {str(tc.get('admin_gate', {}).get('required', False)).lower()}
    status: {tc.get('admin_gate', {}).get('status', 'NOT_REQUIRED')}
  role_policy: {tc.get('role_policy')}
```
"""

    evidence_block = ""
    if evidence is not None:
        evidence_lines = []
        for ev in (evidence or []):
            status_icon = "✅" if ev.get("passed") else "❌"
            extra = f" ({ev.get('count')} files verified)" if "count" in ev else ""
            verdict = "PASS" if ev.get("passed") else "FAIL"
            if not ev.get("passed") and ev.get("reason"):
                extra = f"{extra} (skipped: {ev['reason']})" if ev.get("skipped") else f"{extra} ({ev['reason']})"
            evidence_lines.append(f"- {status_icon} **{ev.get('name')}:** {verdict}{extra}")
        evidence_content = "\n".join(evidence_lines) if evidence_lines else "- ✅ All verification tiers passed."
        evidence_block = f"""
## Dynamic Test Evidence (verification tiers — SSOT: docs/AGENT_LOOP_SPEC.md §4)
{evidence_content}
"""

    return f"""## Summary
Autonomous contribution for issue #{issue_ref}: {task.get('title')}.

## Linked Issue / Claim
{closing_line}Refs #{issue_ref}

## Type of Change
- [x] `feat` / `fix` / `docs` — Open contributor change
{contract_yaml_snippet}{evidence_block}
## Rollback Path
- [x] `git revert`-safe (no private state dependencies)
"""


def build_task_envelope(task: dict[str, Any], role: str, contract: dict[str, Any]) -> dict[str, Any]:
    """Build the Single Deterministic Task Envelope (#63).

    One canonical JSON payload that replaces the four legacy output formats:
      1. multi-step console logs   -> problem_statement + objective fields
      2. --emit-prompt markdown    -> specialist_prompt field
      3. --emit-contract raw JSON  -> embedded contract fields (group/scope/admin_gate)
      4. .pr_template_draft.md     -> submission.pr_body_template field
    """
    tc = contract["task_contract"]
    pr_body_template = build_pr_body(task, contract=contract)
    return {
        "task_envelope": {
            "envelope_version": ENVELOPE_VERSION,
            "output_format": "task-envelope-v1",
            "task_id": tc.get("task_id"),
            "issue": tc.get("issue"),
            "task_type": tc.get("task_type"),
            "group": tc.get("group"),
            "priority": tc.get("priority"),
            "objective": tc.get("objective"),
            "problem_statement": {
                "id": task.get("id"),
                "title": task.get("title"),
                "body": task.get("body"),
                "labels": task.get("labels", []),
                "state": task.get("state"),
            },
            "role": role,
            "role_policy": tc.get("role_policy"),
            "role_description": ROLES.get(role, ""),
            "scope": tc.get("scope", {}),
            "acceptance": tc.get("acceptance", []),
            "verification": tc.get("verification", []),
            "required_evidence": tc.get("required_evidence", []),
            "stop_conditions": tc.get("stop_conditions", []),
            "admin_gate": tc.get("admin_gate", {}),
            "specialist_prompt": build_agent_prompt(task, role, contract),
            "submission": {
                "pathway": "bridge_submit_patch | pull_request",
                "reference": "AGENTS.md §2.1 Pathway 1 + §8 (bridge_submit_patch)",
                "base_branch": "main",
                "pr_title_prefix": "feat(open):",
                "issue_reference_required": True,
                "branch_convention": (
                    "^(feat|fix|docs|chore|test|refactor|perf|bridge|group|contributor|"
                    "hotfix|release|copilot|agent)/<slug> — enforced by pipeline.yml"
                ),
                "pr_body_template": pr_body_template,
            },
        }
    }


def emit_task_envelope(args: argparse.Namespace) -> int:
    """Emit the Single Deterministic Task Envelope (#63) — read-only, fail-closed."""
    issue_id = args.issue
    task: dict[str, Any] | None = None
    if issue_id:
        task = step_1_understand(issue_id)  # fail-closed: missing/closed issue -> None
        if not task:
            return 1
    elif args.allow_adhoc:
        task = {
            "id": "adhoc",
            "title": "Autonomous Contribution Task",
            "body": "Implement smallest safe change adhering to AGENTS.md contracts.",
            "state": "ADHOC",
            "labels": [],
        }
    else:
        log("❌", "[Fail-Closed Gate] --task-envelope requires --issue <number> (or --allow-adhoc for offline testing).")
        return 1

    try:
        group = resolve_group(args.group, task)
    except ValueError as exc:
        log("❌", f"[Group Registry Fail-Closed Gate] {exc}")
        return 2

    try:
        contract = build_task_contract(
            task_id=f"task-{task['id']}",
            issue=task["id"] if task["id"] != "adhoc" else None,
            task_type=args.task_type,
            group=group,
            priority=args.priority,
            objective=task.get("title") or f"Resolve issue #{task['id']}",
            touching_files=[f.strip() for f in args.touching_files.split(",")] if args.touching_files else [],
        )
    except ValueError as exc:
        log("❌", f"[Task Contract Fail-Closed Gate] {exc}")
        return 2

    role = args.role or classify_task_role(
        task.get("title", ""), task.get("labels", []), task.get("body", "")
    )
    envelope = build_task_envelope(task, role, contract)
    print(json.dumps(envelope, indent=2))
    return 0


def pick_next_issue(exclude: set[str] | list[str] | None = None) -> str | None:
    """Fetch the highest priority claimable open issue from GitHub.

    Selection policy (#88):
      - Claim-gated: any open issue is claimable by default unless it carries
        an active claim (status:claimed, status:in-progress), hold, blocked, or
        private-mirror exclusion marker.
      - Whole-board scope: pagination limit high enough that truncation cannot
        starve old issues (verified: board regularly holds 35+ open issues).
      - Explicit priority map on LABELS only (P0>P1>P2>P3>unlabeled) — prose in
        titles can no longer outrank a real priority label; age (lowest issue
        number) breaks ties per AGENT_RULES.md §5.
      - exclude: issue numbers already dispatched in this session. Prevents
        session-local re-picks while GitHub search API index updates.
    """
    code, out, _ = run_cmd([
        "gh", "issue", "list",
        "--repo", UPSTREAM_REPO,
        "--state", "open",
        "--limit", "200",
        "--json", "number,title,labels",
    ])
    if code != 0 or not out.strip():
        return None
    try:
        issues = json.loads(out)

        # Claim-gated (#88): open issues are available unless claimed or held.
        # Removing explicit status:unclaimed eliminates label desynchronization.
        EXCLUDED_LABELS = {
            "status:claimed",
            "status:in-progress",
            "state:seq-hold",
            "blocked-by-upstream",
            "mirror:private",
        }

        def label_names(item: dict[str, Any]) -> list[str]:
            labels = item.get("labels")
            if not isinstance(labels, list):
                return []
            return [str(l.get("name", "")).lower() for l in labels if isinstance(l, dict)]

        def is_claimable(item: dict[str, Any]) -> bool:
            names = label_names(item)
            return not (EXCLUDED_LABELS & set(names))

        # Explicit priority map — LABELS ONLY (title prose must not influence).
        PRIORITY_MAP = (("p0", 0), ("p1", 1), ("p2", 2), ("p3", 3))

        def priority_key(item: dict[str, Any]) -> tuple[int, int]:
            names = label_names(item)
            tier = 4  # unlabeled sorts last
            for marker, rank in PRIORITY_MAP:
                if any(name == marker or name.startswith(marker + "-") or name.startswith(marker + " ") for name in names):
                    tier = rank
                    break
            return (tier, int(item.get("number", 0)))  # number ASC = oldest first

        candidates = [i for i in issues if isinstance(i, dict) and is_claimable(i)]
        if exclude:
            excluded_set = {str(e) for e in exclude}
            candidates = [i for i in candidates if str(i.get("number")) not in excluded_set]
        sorted_issues = sorted(candidates, key=priority_key)
        if sorted_issues:
            return str(sorted_issues[0].get("number"))
    except Exception:
        pass
    return None


try:
    import yaml
except ImportError:
    yaml = None


def step_1_understand(issue_id: str | None = None, allow_adhoc: bool = False) -> dict[str, Any] | None:
    """Step 1: Fetch and validate task contract / issue context fail-closed."""
    log("📖", "[Step 1/8: Understand] Loading task contract...")
    
    if issue_id:
        code, out, err = run_cmd(["gh", "issue", "view", str(issue_id), "--repo", UPSTREAM_REPO, "--json", "number,title,body,state,labels"])
        if code != 0:
            log("❌", f"[Fail-Closed Gate] Could not fetch issue #{issue_id} from {UPSTREAM_REPO}: {err or out}")
            log("❌", "Cannot verify issue validity or acceptance criteria. Aborting task.")
            return None
        try:
            data = json.loads(out)
            state = data.get("state", "OPEN").upper()
            if state == "CLOSED":
                log("❌", f"[Fail-Closed Gate] Issue #{data.get('number')} is CLOSED. Autonomous work on closed tasks is rejected.")
                return None

            # Duplicate work check: look for open PRs
            pr_code, pr_out, _ = run_cmd(["gh", "pr", "list", "--repo", UPSTREAM_REPO, "--state", "open", "--json", "number,title,headRefName"])
            if pr_code == 0 and pr_out.strip():
                try:
                    open_prs = json.loads(pr_out)
                    for pr in open_prs:
                        pr_head = pr.get("headRefName", "")
                        pr_title = pr.get("title", "")
                        if f"issue-{issue_id}" in pr_head or f"#{issue_id}" in pr_title or f"task-{issue_id}" in pr_head:
                            log("⚠️", f"Existing open PR found for issue #{issue_id}: PR #{pr.get('number')} ({pr_head}).")
                            log("❌", "[Fail-Closed Gate] Duplicate PR work rejected. Coordinate or review existing PR first.")
                            return None
                except Exception:
                    pass

            labels_list = [l.get("name", "") for l in data.get("labels", [])] if isinstance(data.get("labels"), list) else []
            log("✅", f"Loaded Issue #{data.get('number')} ({state}): {data.get('title')}")
            return {
                "id": str(data.get("number")),
                "title": data.get("title", ""),
                "body": data.get("body", ""),
                "state": state,
                "labels": labels_list,
            }
        except Exception as e:
            log("❌", f"[Fail-Closed Gate] Failed to parse issue JSON for #{issue_id}: {e}")
            return None

    if not allow_adhoc:
        log("❌", "[Fail-Closed Gate] No --issue specified! Multi-agent mode requires a specific issue contract.")
        log("ℹ️", "Please provide --issue <number>, use --pick-next, or pass --allow-adhoc explicitly for local offline testing.")
        return None

    log("ℹ️", f"Checking active issues on {UPSTREAM_REPO}...")
    code, out, _ = run_cmd(["gh", "issue", "list", "--repo", UPSTREAM_REPO, "--limit", "5", "--json", "number,title"])
    if code == 0 and out.strip() != "[]":
        try:
            issues = json.loads(out)
            log("📋", "Recent Open Issues:")
            for it in issues:
                print(f"   #{it.get('number')}: {it.get('title')}")
        except Exception:
            pass

    return {
        "id": "adhoc",
        "title": "Autonomous Contribution Task",
        "body": "Implement smallest safe change adhering to AGENTS.md contracts.",
        "state": "ADHOC",
        "labels": [],
    }


def step_2_rules() -> bool:
    """Step 2: Verify and display governing constitution rules."""
    log("⚖️", "[Step 2/8: Rules] Loading constitution rules...")
    if not AGENTS_MD_PATH.exists() or not AGENT_RULES_PATH.exists():
        log("⚠️", "AGENTS.md or AGENT_RULES.md missing from repository root!")
        return False
    log("✅", "AGENTS.md and AGENT_RULES.md validated. Zero-Admin & Scope rules active.")
    return True


def step_3_inspect_state(force: bool = False) -> dict[str, str]:
    """Step 3: Inspect local git status, branch, and active remote."""
    log("🔍", "[Step 3/8: Inspect State] Checking git repository status...")
    _, status, _ = run_cmd(["git", "status", "--porcelain"])
    _, branch, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    
    dirty = bool(status.strip())
    if dirty:
        log("⚠️", f"Current branch: {branch} (uncommitted changes: YES)")
        if not force:
            log("❌", "[Fail-Closed Workspace Isolation] Working tree has uncommitted modifications!")
            log("❌", "Running multi-agent loop on a dirty workspace risks cross-contaminating agent sessions.")
            log("ℹ️", "Commit or stash uncommitted changes before continuing, or run with --force.")
            return {"branch": branch, "dirty": "True", "clean": "False"}
    else:
        log("ℹ️", f"Current branch: {branch} (uncommitted changes: NO)")
    return {"branch": branch, "dirty": str(dirty), "clean": str(not dirty)}


def step_4_branch(task: dict[str, Any]) -> str | None:
    """Step 4: Create atomic branch for task with strict error checking."""
    issue_num = task.get("id", "adhoc")
    target_branch = f"contributor/issue-{issue_num}" if issue_num != "adhoc" else f"contributor/work-{int(time.time())}"
    log("🌿", f"[Step 4/8: Branch] Ensuring branch '{target_branch}'...")
    
    code, _, _ = run_cmd(["git", "rev-parse", "--verify", target_branch])
    if code == 0:
        _, curr_branch, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if curr_branch == target_branch:
            log("✅", f"Already on active branch '{target_branch}'")
            return target_branch
        
        checkout_code, _, checkout_err = run_cmd(["git", "checkout", target_branch])
        if checkout_code != 0:
            target_branch = f"contributor/issue-{issue_num}-{int(time.time())}"
            log("🌿", f"Switching to isolated session branch '{target_branch}'")
            create_code, _, create_err = run_cmd(["git", "checkout", "-b", target_branch])
            if create_code != 0:
                log("❌", f"Failed to create isolated branch '{target_branch}': {create_err}")
                return None
    else:
        create_code, _, create_err = run_cmd(["git", "checkout", "-b", target_branch])
        if create_code != 0:
            log("❌", f"Failed to create branch '{target_branch}': {create_err}")
            return None

    _, active_branch, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if active_branch != target_branch:
        log("❌", f"Branch checkout verification failed! Expected '{target_branch}', got '{active_branch}'.")
        return None

    log("✅", f"Active on verified branch '{target_branch}'")
    # Mark issue as claimed on upstream board (honest degradation if guest/offline)
    if issue_num != "adhoc":
        run_cmd(["gh", "issue", "edit", str(issue_num), "--repo", UPSTREAM_REPO, "--add-label", "status:claimed"])
    return target_branch


def step_5_work_notice(role: str, prompt: str) -> None:
    """Step 5: Scope boundary guidance and specialized prompt dispatch."""
    log("🔨", f"[Step 5/8: Work] Dispatch Phase (Role: {role.upper()})")
    print("----------------------------------------------------------------------")
    print(f"Role: {role} ({ROLES.get(role, '')})")
    print("Specialist Agent Prompt Prepared.")
    print("   -> Keep changes atomic and minimal within declared scope.")
    print("   -> Follow contracts in api-schemas/ and examples/.")
    print("----------------------------------------------------------------------")


def step_6_verify() -> tuple[bool, list[dict[str, Any]]]:
    """Step 6: Run the verification tiers and collect dynamic evidence."""
    log("🧪", "[Step 6/8: Verify] Running the verification contract (tier-count SSOT: docs/AGENT_LOOP_SPEC.md §4)...")
    evidence: list[dict[str, Any]] = []

    # 1. Python Syntax / Compile smoke
    py_files = [p for p in REPO_ROOT.glob("**/*.py") if "venv" not in str(p) and ".git" not in str(p)]
    py_errors = []
    for py in py_files:
        code, _, err = run_cmd([sys.executable, "-m", "py_compile", str(py)])
        if code != 0:
            py_errors.append(f"{py.name}: {err}")
    if py_errors:
        log("❌", f"Python syntax errors in {len(py_errors)} files: {py_errors[0]}")
        evidence.append({"tier": 1, "name": "Python Syntax Compile", "passed": False, "count": len(py_files), "errors": py_errors})
        return False, evidence
    evidence.append({"tier": 1, "name": "Python Syntax Compile", "passed": True, "count": len(py_files)})

    # 2. JSON Schema validation
    json_files = [j for j in REPO_ROOT.glob("**/*.json") if "node_modules" not in str(j) and ".git" not in str(j)]
    json_errors = []
    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                json.load(f)
        except Exception as e:
            json_errors.append(f"{jf.name}: {e}")
    if json_errors:
        log("❌", f"Invalid JSON in {len(json_errors)} files: {json_errors[0]}")
        evidence.append({"tier": 2, "name": "JSON Schema Parse", "passed": False, "count": len(json_files), "errors": json_errors})
        return False, evidence
    evidence.append({"tier": 2, "name": "JSON Schema Parse", "passed": True, "count": len(json_files)})

    # 3. YAML & OpenAPI Schema validation
    if yaml is not None:
        yaml_files = [y for y in list(REPO_ROOT.glob("**/*.yaml")) + list(REPO_ROOT.glob("**/*.yml")) if ".git" not in str(y) and "node_modules" not in str(y)]
        yaml_errors = []
        for yf in yaml_files:
            try:
                with open(yf, "r", encoding="utf-8") as f:
                    yaml.safe_load(f)
            except Exception as e:
                yaml_errors.append(f"{yf.name}: {e}")
        if yaml_errors:
            log("❌", f"Invalid YAML in {len(yaml_errors)} files: {yaml_errors[0]}")
            evidence.append({"tier": 3, "name": "YAML/OpenAPI Safe Load", "passed": False, "count": len(yaml_files), "errors": yaml_errors})
            return False, evidence
        evidence.append({"tier": 3, "name": "YAML/OpenAPI Safe Load", "passed": True, "count": len(yaml_files)})
    else:
        evidence.append({"tier": 3, "name": "YAML/OpenAPI Safe Load", "passed": False, "skipped": True, "reason": "PyYAML not installed"})

    # 4. Self-test smoke checks (P6 validation)
    try:
        res_code, _, _ = run_cmd(["__test_nonexistent_binary_xyz_123__"])
        if res_code != 127:
            evidence.append({"tier": 4, "name": "Missing Binary Fail-Honest Guard", "passed": False, "exit_code": res_code})
            return False, evidence
        evidence.append({"tier": 4, "name": "Missing Binary Fail-Honest Guard (Code 127)", "passed": True})

        try:
            build_task_contract("test", task_type="INVALID_TYPE")
            evidence.append({"tier": 5, "name": "Task Contract Fail-Closed Guard", "passed": False})
            return False, evidence
        except ValueError:
            evidence.append({"tier": 5, "name": "Task Contract Fail-Closed Guard (ValueError)", "passed": True})

        # Tier 6 (#63): group registry fail-closed guard — invented group names rejected
        try:
            build_task_contract("group-guard-test", group="not-a-canonical-group")
            evidence.append({"tier": 6, "name": "Group Registry Fail-Closed Guard", "passed": False})
            return False, evidence
        except ValueError:
            evidence.append({"tier": 6, "name": "Group Registry Fail-Closed Guard (ValueError)", "passed": True})

        # Tier 7 (#63): envelope determinism — identical inputs produce byte-identical contracts
        _c1 = build_task_contract("env-test", issue="0", group=DEFAULT_GROUP)
        _c2 = build_task_contract("env-test", issue="0", group=DEFAULT_GROUP)
        if json.dumps(_c1, sort_keys=True) != json.dumps(_c2, sort_keys=True):
            evidence.append({"tier": 7, "name": "Envelope Determinism", "passed": False})
            return False, evidence
        evidence.append({"tier": 7, "name": "Envelope Determinism (byte-identical rebuild)", "passed": True})

        # Tier 8: Hardcoded Machine Path Guard (P6 Defect Class Prevention)
        # Rejects absolute host drive paths (e.g. F:/, C:/, \Users\) hardcoded into operational source
        machine_path_pattern = re.compile(r'["\'](?:[A-Za-z]:[\\/]|\\\\Users\\\\)')
        path_violations = []
        scan_targets = [
            f for f in REPO_ROOT.glob("**/*")
            if f.suffix in {".py", ".ts", ".js"}
            and "node_modules" not in f.parts
            and ".git" not in f.parts
            and "dist" not in f.parts
        ]
        for target in scan_targets:
            try:
                content = target.read_text(encoding="utf-8", errors="ignore")
                for line_idx, line in enumerate(content.splitlines(), start=1):
                    stripped = line.strip()
                    if stripped.startswith(("#", "//", "/*", "*")):
                        continue
                    if machine_path_pattern.search(line):
                        path_violations.append(f"{target.relative_to(REPO_ROOT)}:{line_idx}")
            except Exception:
                pass

        if path_violations:
            log("❌", f"Hardcoded machine paths detected in source: {path_violations[:3]}")
            evidence.append({"tier": 8, "name": "Machine Path Isolation Guard", "passed": False, "violations": path_violations})
            return False, evidence
        evidence.append({"tier": 8, "name": "Machine Path Isolation Guard", "passed": True, "files_scanned": len(scan_targets)})
    except Exception as e:
        log("❌", f"Self-test verification failed: {e}")
        return False, evidence

    tier_count = len({e["tier"] for e in evidence})
    log("✅", f"{tier_count}-tier checks passed! Syntax, JSON/YAML schemas, and contracts are verified.")
    return True, evidence


def push_branch_to_fork(fork_owner: str, branch: str) -> tuple[bool, str]:
    """Pathway 2 (AGENTS.md §2.1): ensure the fork exists and push the session branch.

    Idempotent: `gh repo fork` is a no-op when the fork already exists; the push
    is force-with-lease safe for a session-scoped contributor branch.
    """
    fork_code, fork_out, fork_err = run_cmd(
        ["gh", "repo", "fork", UPSTREAM_REPO, "--clone=false"],
        check=False,
    )
    if fork_code != 0:
        return False, f"fork ensure failed ({fork_code}): {fork_err or fork_out}"
    push_code, push_out, push_err = run_cmd(
        ["git", "push", "--force-with-lease",
         f"https://github.com/{fork_owner}/{UPSTREAM_REPO.split('/')[-1]}.git",
         f"{branch}:{branch}"],
        check=False,
    )
    if push_code != 0:
        return False, f"fork push failed ({push_code}): {push_err or push_out}"
    return True, f"pushed {branch} to {fork_owner}/{UPSTREAM_REPO.split('/')[-1]}"


def step_7_record(
    task: dict[str, Any],
    branch: str,
    contract: dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    auto_pr: bool = False,
    fork_owner: str | None = None,
) -> bool:
    """Step 7: Prepare PR body with dynamic test evidence and submit PR."""
    log("📝", "[Step 7/8: Record] Generating Universal PR Template...")
    # #114: single construction site — build_pr_body() renders the exact
    # skeleton the envelope's submission.pr_body_template carries, plus the
    # contract YAML snippet and the dynamic evidence block for --auto-pr.
    pr_body = build_pr_body(task, contract=contract, evidence=evidence)

    # #63: no intermediate filesystem draft — the PR body goes inline to gh,
    # and agents consuming the Task Envelope get the same template via
    # submission.pr_body_template (single source of truth).
    if auto_pr:
        head_ref = branch
        if fork_owner:
            log("🍴", f"Pathway 2: ensuring fork + pushing branch to {fork_owner}...")
            pushed, push_detail = push_branch_to_fork(fork_owner, branch)
            if not pushed:
                log("❌", f"[Fail-Closed Gate] Fork push failed: {push_detail}")
                return False
            head_ref = f"{fork_owner}:{branch}"
        log("🚀", f"Opening Pull Request against {UPSTREAM_REPO}:main (head: {head_ref})...")
        cmd = [
            "gh", "pr", "create",
            "--repo", UPSTREAM_REPO,
            "--base", "main",
            "--head", head_ref,
            "--title", f"feat(open): {task.get('title')}",
            "--body", pr_body
        ]
        code, out, err = run_cmd(cmd)
        if code == 0:
            log("🎉", f"PR Successfully Created: {out}")
            return True
        else:
            log("❌", f"PR creation via gh CLI failed ({code}): {err}")
            print(f"   Submit manually at: https://github.com/{UPSTREAM_REPO}/compare/main...{branch}")
            return False

    return True


def step_8_return() -> None:
    """Step 8: Fresh-board re-check and clean exit."""
    log("🔄", "[Step 8/8: Return] Checking board freshness & cycle completed.")
    code, out, _ = run_cmd(["gh", "pr", "list", "--repo", UPSTREAM_REPO, "--limit", "5", "--json", "number,title,headRefName"])
    if code == 0 and out.strip() != "[]":
        try:
            prs = json.loads(out)
            log("📋", "Active Open PRs on upstream board:")
            for p in prs:
                print(f"   #{p.get('number')} ({p.get('headRefName')}): {p.get('title')}")
        except Exception:
            pass
    print("----------------------------------------------------------------------")
    print(f"Cycle completed successfully. Ready for next task in {UPSTREAM_REPO}.")
    print("----------------------------------------------------------------------")


# ============================================================================
# Contributor additions: scheduled mode (AGENTS.md §0 — this extends the
# EXISTING dispatcher in place; no new loop script is introduced). All lines
# below are pure additions; upstream lines are left unmodified.
# ============================================================================

def _utc_now_stamp() -> str:
    """UTC ISO-8601 timestamp for scheduler log lines."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def cron_expression(minutes: int) -> str:
    """Best-effort translation of a start-to-start interval to crontab fields."""
    if 0 < minutes < 60 and 60 % minutes == 0:
        return f"*/{minutes} * * * *"
    if minutes >= 60 and minutes % 60 == 0:
        return f"0 */{minutes // 60} * * *"
    return f"*/{minutes} * * * *"  # approximate in cron field semantics; --schedule itself anchors start-to-start


def print_cron_entry(minutes: int) -> None:
    """Print a ready-to-paste crontab entry for the requested cadence."""
    print(f"# continuous_agent_loop.py --print-cron (generated {_utc_now_stamp()})")
    print(f"# cadence: every {minutes} min — {cron_expression(minutes)}")
    print(f"{cron_expression(minutes)} cd {REPO_ROOT} && python3 scripts/agents/continuous_agent_loop.py --schedule {minutes} >> .agent_loop_schedule.log 2>&1")


def _run_one_scheduled_tick(args: argparse.Namespace, exclude: set[str] | list[str] | None = None) -> tuple[int, str | None]:
    """One scheduled dispatch — reuses upstream's own single-cycle paths."""
    if args.verify_only:
        passed, _ = step_6_verify()
        return (0 if passed else 1), None
    issue_id = args.issue
    if args.pick_next:
        issue_id = pick_next_issue(exclude=exclude)
        if not issue_id:
            log("❌", "No eligible open issues found on board this tick!")
            return 1, None
        log("🎯", f"Auto-selected highest priority Issue #{issue_id}")
    rc = run_cycle(args, issue_id)
    return rc, issue_id


def run_scheduled_cycles(args: argparse.Namespace) -> int:
    """Cron-like scheduler anchored on cycle START (not cycle end).

    Contract:
      - cycle 1 starts immediately;
      - cycle N starts exactly ``--schedule`` minutes after cycle N-1 STARTED
        (the sleep is derived from a time.monotonic() anchor, so variable
        cycle duration never accumulates end-to-start drift);
      - if a cycle overruns the interval, the next tick runs immediately and
        logs the catch-up loudly (silent drift is worse than a loud delay);
      - a failed tick logs a warning and does NOT stop the clock — one failed
        tick is not a stalled schedule;
      - Ctrl-C stops the scheduler cleanly.
    """
    interval = args.schedule * 60
    total = args.cycles
    plan = "indefinitely (Ctrl-C to stop)" if total == 0 else f"{total} cycle(s)"
    log("⏰", f"[Scheduled Mode] dispatch every {args.schedule} min, {plan}.")
    failures = 0
    cycle_no = 0
    next_start = time.monotonic()
    dispatched: set[str] = set()
    try:
        while total == 0 or cycle_no < total:
            if cycle_no > 0:
                delay = next_start - time.monotonic()
                if delay < 0:
                    log("⚠️", f"[Scheduled Mode] overrun by {int(-delay)}s — running catch-up tick immediately (start-to-start anchor preserved).")
                elif delay > 0:
                    time.sleep(delay)
            cycle_no += 1
            next_start = time.monotonic() + interval
            label = f"{cycle_no}/{total}" if total else str(cycle_no)
            log("🚀", f"[Scheduled Mode] cycle {label} starting at {_utc_now_stamp()}.")
            rc, dispatched_id = _run_one_scheduled_tick(args, exclude=dispatched)
            if dispatched_id:
                dispatched.add(str(dispatched_id))
            if rc != 0:
                failures += 1
                log("⚠️", f"[Scheduled Mode] cycle {label} exited {rc} — one failed tick is not a stalled clock; schedule continues.")
    except KeyboardInterrupt:
        log("🛑", f"[Scheduled Mode] interrupted — clean stop after {cycle_no} cycle(s) ({failures} failed tick(s)).")
        return 130
    log("🏁", f"[Scheduled Mode] finished: {cycle_no} cycle(s), {failures} failed tick(s).")
    return 0 if failures == 0 else 1


def run_cycle(args: argparse.Namespace, issue_id: str | None) -> int:
    """Execute a single complete task dispatch cycle."""
    task = step_1_understand(issue_id, allow_adhoc=args.allow_adhoc)
    if not task:
        return 1

    if not step_2_rules():
        return 1

    state = step_3_inspect_state(force=args.force)
    if state.get("clean") != "True" and not args.force:
        return 1

    # Classify Role & Prompt
    assigned_role = args.role or classify_task_role(
        task.get("title", ""), task.get("labels", []), task.get("body", "")
    )
    log("🎯", f"Classified Task Role: '{assigned_role.upper()}' ({ROLES.get(assigned_role, '')})")

    touching_files = [f.strip() for f in args.touching_files.split(",")] if args.touching_files else []
    resolved_group = resolve_group(args.group, task)  # #63: canonical taxonomy, fail-closed
    contract = build_task_contract(
        task_id=f"task-{task.get('id', 'adhoc')}",
        issue=task.get("id"),
        task_type=args.task_type,
        group=resolved_group,
        priority=args.priority,
        objective=task.get("title", ""),
        touching_files=touching_files,
        role_policy=assigned_role,
    )

    agent_prompt = build_agent_prompt(task, assigned_role, contract)

    branch = step_4_branch(task)
    if not branch:
        return 1

    step_5_work_notice(assigned_role, agent_prompt)

    # Verification check
    passed, evidence = step_6_verify()
    if not passed:
        log("❌", "Verification failed. Please fix errors before proceeding.")
        return 1

    fork_owner = getattr(args, "fork_owner", None) or os.environ.get("SUPREMEAI_FORK_OWNER", "").strip() or None
    if not step_7_record(task, branch, contract=contract, evidence=evidence, auto_pr=args.auto_pr, fork_owner=fork_owner):
        log("❌", "Step 7 (Record) failed! Halting before completion return.")
        return 1

    step_8_return()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI Continuous Agent Loop — Lazy Team Leader & Dispatcher")
    parser.add_argument("--issue", type=str, help="Specific GitHub issue number to claim and resolve")
    parser.add_argument("--pick-next", action="store_true", help="Automatically pick highest priority open issue from upstream board")
    parser.add_argument("--loop", action="store_true", help="Continuous mode: process eligible issues sequentially")
    parser.add_argument("--max-tasks", type=int, default=5, help="Maximum number of tasks to process in loop mode (default: 5)")
    parser.add_argument("--role", type=str, help=f"Force specific agent role: {', '.join(ROLES.keys())}")
    parser.add_argument("--task-envelope", action="store_true", help="Emit the unified deterministic Task Envelope (canonical single payload, #63) and exit")
    parser.add_argument("--group", type=str, default=None, help="Canonical group from the VALID_GROUPS registry (agent-orchestration, mcp-tower, core-engine, schemas-contracts, infra-ops)")
    parser.add_argument("--emit-prompt", action="store_true", help="DEPRECATED (#63): use --task-envelope — emits the unified envelope with a deprecation warning")
    parser.add_argument("--auto-pr", action="store_true", help="Automatically submit PR via gh CLI upon test pass")
    parser.add_argument("--verify-only", action="store_true", help="Only run the verification tiers and exit")
    parser.add_argument("--emit-contract", action="store_true", help="DEPRECATED (#63): use --task-envelope — emits the unified envelope with a deprecation warning")
    parser.add_argument("--touching-files", type=str, help="Comma-separated list of touching files for declared scope")
    parser.add_argument("--task-type", type=str, default="IMPLEMENT", help="Task type (default: IMPLEMENT)")
    parser.add_argument("--priority", type=str, default="P2", help="Task priority (P0, P1, P2, P3)")
    parser.add_argument("--allow-adhoc", action="store_true", help="Allow adhoc task execution without --issue (offline testing only)")
    parser.add_argument("--force", action="store_true", help="Bypass dirty workspace isolation gate (not recommended)")
    parser.add_argument("--fork-owner", type=str, default=None,
                        help="Pathway 2: GitHub owner of your fork; step 7 pushes the branch "
                             "there and opens the PR with head '<owner>:<branch>' "
                             "(env fallback: SUPREMEAI_FORK_OWNER)")
    # --- contributor additions: scheduled mode (cron-like start-to-start loop) ---
    parser.add_argument("--schedule", type=int, nargs="?", const=30, default=None, metavar="MINUTES",
                        help="Scheduled mode: dispatch every MINUTES minutes (default: 30). Anchored on cycle START like a true cron tick, so cycle duration never accumulates drift.")
    parser.add_argument("--cycles", type=int, default=0,
                        help="Stop after N scheduled cycles (default: 0 = run indefinitely; requires --schedule).")
    parser.add_argument("--print-cron", action="store_true",
                        help="Print the equivalent crontab entry for --schedule and exit (does not run the loop).")
    args = parser.parse_args()

    banner = (
        "======================================================================\n"
        " SupremeAI — Continuous Agent Loop (Lazy Team Leader Runner) \n"
        f" Target: {UPSTREAM_REPO}\n"
        "======================================================================"
    )
    if args.task_envelope or args.emit_prompt or args.emit_contract:
        # #63: envelope mode keeps stdout PURE JSON (machine-parseable single
        # payload) — the human banner goes to stderr instead.
        print(banner, file=sys.stderr)
    else:
        print(banner)

    # --- contributor additions: scheduled-mode fail-fast guards + dispatch ---
    # Unified guards apply to every consumer of --schedule (including
    # --print-cron): zero/negative intervals and negative cycle counts are
    # configuration errors, rejected before anything runs (fail-fast).
    if args.schedule is not None and args.schedule <= 0:
        log("❌", f"--schedule must be a positive number of minutes (got {args.schedule}).")
        return 1
    if args.cycles < 0:
        log("❌", f"--cycles must be >= 0 (0 = run indefinitely; got {args.cycles}).")
        return 1
    if args.cycles > 0 and args.schedule is None:
        log("❌", "--cycles requires --schedule (scheduled mode).")
        return 1
    if args.print_cron:
        print_cron_entry(args.schedule if args.schedule is not None else 30)
        return 0
    if args.schedule is not None:
        return run_scheduled_cycles(args)

    if args.verify_only:
        passed, _ = step_6_verify()
        # #67 parity marker — final stdout line, byte-identical across the
        # public and private copies (grep target for cross-repo parity check).
        print(f"CONTRACT_VERSION={CONTRACT_VERSION}")
        return 0 if passed else 1

    if args.emit_prompt or args.emit_contract:
        print("⚠️  DEPRECATION WARNING (#63): --emit-prompt / --emit-contract are deprecated.", file=sys.stderr)
        print("    Use the canonical unified payload: --task-envelope", file=sys.stderr)

    if args.task_envelope or args.emit_prompt or args.emit_contract:
        return emit_task_envelope(args)

    if args.loop:
        log("🔄", f"[Continuous Loop Mode] Starting task runner (max tasks: {args.max_tasks})...")
        processed = 0
        dispatched: set[str] = set()
        while processed < args.max_tasks:
            next_issue = pick_next_issue(exclude=dispatched)
            if not next_issue:
                log("🏁", "No more eligible open issues in queue. Loop finished.")
                break
            log("🚀", f"Dispatching Task #{next_issue} ({processed + 1}/{args.max_tasks})...")
            dispatched.add(str(next_issue))
            rc = run_cycle(args, next_issue)
            if rc != 0:
                log("⚠️", f"Task #{next_issue} halted with code {rc}. Stopping continuous loop.")
                return rc
            processed += 1
            time.sleep(2)  # Short cooldown between dispatches
        log("🎉", f"Continuous loop completed {processed} task(s).")
        return 0

    issue_to_run = args.issue
    if args.pick_next:
        issue_to_run = pick_next_issue()
        if not issue_to_run:
            log("❌", "No eligible open issues found on board!")
            return 1
        log("🎯", f"Auto-selected highest priority Issue #{issue_to_run}")

    return run_cycle(args, issue_to_run)


if __name__ == "__main__":
    sys.exit(main())
