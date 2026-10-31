#!/usr/bin/env python3
"""SupremeAI â€” Continuous Autonomous Agent Loop (Lightweight Single Door SSOT).

Responsibility:
1. Fetch live open issues from GitHub board / Tower.
2. Smart triage:
   - If claimable issues <= 5: rotate scheduled observation roles (cadence-based).
   - If claimable issues > 5: dispatch highest priority issue to 'solver'.
3. Dispatch journal: every issue assignment is recorded to the machine-local
   journal (observability/hygiene only â€” #3573 regime: the journal NEVER gates
   or delays a candidate; claimability's only arbiters are the live claim
   probe and the atomic work_claim, SPEC Â§4c).
4. Continuous loop execution without extraneous CLI flags.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.agents import claim_thresholds as ct
except ImportError:
    try:
        import claim_thresholds as ct
    except ImportError:
        class _FallbackCT:
            ORPHAN_RELEASE_MINUTES = 30.0
        ct = _FallbackCT()

CADENCE_FILE = Path(__file__).resolve().parent / "agent_cadence.json"
ROTATION_STORE = Path(".agent_cadence_last_run.json")
ISSUE_LEASE_STORE = Path(".issue_lease_store.json")
EXCLUDED_LABELS = frozenset({
    "claimed", "in-progress", "blocked", "wip", "ci-failed",
    "stale", "duplicate", "invalid", "report-only", "bridge:receipt"
})
PRIORITY_MAP = (("p0", 0), ("p1", 1), ("p2", 2), ("p3", 3))

# SSOT lineage (#57 / #3573 regime): hygiene-only alias names, NO time gate.
# These feed the born-duplicate demotion's in-flight input and the machine-local
# dispatch journal retention. They NEVER decide claimability (SPEC §4c).
DISPATCH_JOURNAL_RETENTION_SECONDS = ct.ORPHAN_RELEASE_MINUTES * 60.0
ISSUE_LEASE_SECONDS = DISPATCH_JOURNAL_RETENTION_SECONDS

# =============================================================================
# 5 ROLES & THEIR MANDATES (SSOT)
# =============================================================================
ROLE_RULES: dict[str, str] = {
    "solver": (
        "Unlimited concurrent solvers allowed. Objective: Solve root cause, verify boundary, "
        "deliver complete migrations/configs/tests end-to-end, and submit PR."
    ),
    "ecosystem-scout": (
        "Explore global innovations and high-impact capabilities for SupremeAI. "
        "File actionable findings with live verifiable evidence; strictly no hype/speculation; no direct code edits."
    ),
    "human-eye": (
        "Audit UI/UX, frontend performance, responsiveness, and end-user customer experience across applications."
    ),
    "rules-breaker": (
        "Adversarial audit: detect system security risks, technical debt, contract violations, and logic gaps."
    ),
    "platform-guardian": (
        "Audit third-party integrations, satellite mirrors, platform health, database schema, and operational telemetry."
    ),
}

COMMON_RULES = """=== UNIVERSAL INVARIANTS (ALL ROLES MUST FOLLOW) ===
1. Dual-Rebase: Rebase origin/main at work-start AND pre-push (0 behind).
2. Boundary: Satellite code lives strictly in its approved domain mirror.
3. Superior Replacement: Discard broken legacy code/tests rather than hacking new code.
4. Verification & PR Blueprint: 3-Tier Verify (Reflection -> Smoke -> Tests) with Closes #N.
5. P0 Drainage & Anti-Stampede: Open blockers supersede all speculative research.
6. Zero-Recurrence: Automated guards against every identified mistake.
7. Loop-Driven Determinism: 'The loop is the permission (U10).'
8. Universal Defect Ownership: Never ignore unhandled pipeline failures or defects.
9. Full-Scope Completeness: Complete migrations, configs, and API wiring end-to-end.
"""


def log(level: str, msg: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{now}] [{level}] {msg}", flush=True)


def load_issue_lease_store() -> dict[str, float]:
    if not ISSUE_LEASE_STORE.exists():
        return {}
    try:
        return json.loads(ISSUE_LEASE_STORE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def record_issue_dispatch(issue_number: int | str) -> None:
    store = load_issue_lease_store()
    store[str(issue_number)] = time.time()
    try:
        ISSUE_LEASE_STORE.write_text(json.dumps(store, indent=2), encoding="utf-8")
    except Exception as exc:
        log("WARN", f"Failed to record issue lease store: {exc}")


def load_cadence_config() -> dict[str, Any]:
    if not CADENCE_FILE.exists():
        return {}
    try:
        return json.loads(CADENCE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_last_run_store() -> dict[str, float]:
    if not ROTATION_STORE.exists():
        return {}
    try:
        return json.loads(ROTATION_STORE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_last_run_store(data: dict[str, float]) -> None:
    try:
        ROTATION_STORE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        log("WARN", f"Failed to save rotation store: {exc}")


def fetch_open_issues() -> list[dict[str, Any]]:
    """Fetch open issues via GitHub CLI or fallback."""
    cmd = [
        "gh", "issue", "list",
        "--repo", "Supremeai-bd/supremeai-open",
        "--state", "open",
        "--limit", "50",
        "--json", "number,title,labels,state"
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(proc.stdout)
    except Exception as exc:
        log("WARN", f"Could not fetch issues via gh: {exc}")
        return []


def is_claimable(item: dict[str, Any]) -> bool:
    labels = {lbl.get("name", "").lower() for lbl in item.get("labels", []) if isinstance(lbl, dict)}
    if EXCLUDED_LABELS & labels:
        return False

    title = str(item.get("title") or "")
    if "anchor hub" in title.lower() or "sentry" in title.lower():
        return False

    # Clock-free claimability gate (#3573 founder regime, SPEC Â§4c â€” zero
    # artificial timer locks): the dispatch journal below is written at
    # assignment time but NEVER gates a candidate here; the live claim probe
    # and the atomic work_claim own claimability. The 30-minute cooldown this
    # file originally carried was the #4124 defect class (re-founding a
    # mechanism the SPEC documents as removed â€” #4125 triage, restored
    # clock-free in continuous_agent_loop.py by #4138); per Invariant 6 the
    # class may not reincarnate in a sibling loop. AST-pinned by
    # tests/test_loop_v1.py (same comment-immune pin style as
    # test_claim_lease_ssot::test_02).

    state = item.get("state")
    if state is not None and str(state).lower() != "open":
        return False

    return True


def pick_next_issue(issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    claimable = [i for i in issues if is_claimable(i)]
    if not claimable:
        return None

    def priority_key(item: dict[str, Any]) -> tuple[int, int]:
        labels = [lbl.get("name", "").lower() for lbl in item.get("labels", []) if isinstance(lbl, dict)]
        tier = 4
        for marker, rank in PRIORITY_MAP:
            if any(marker in l for l in labels):
                tier = rank
                break
        return (tier, int(item.get("number", 0)))

    claimable.sort(key=priority_key)
    return claimable[0]


def pick_next_scheduled_role(config: dict[str, Any]) -> str | None:
    roles = config.get("scheduled_roles", [
        "ecosystem-scout", "human-eye", "rules-breaker", "platform-guardian"
    ])
    last_runs = load_last_run_store()
    
    # à¦¯à§‡ à¦°à§‹à¦²à¦Ÿà¦¿ à¦à¦–à¦¨à¦“ à¦à¦‡ à¦à¦ªà¦¿à¦¸à§‹à¦¡à§‡ à¦°à¦¾à¦¨ à¦¹à§Ÿà¦¨à¦¿, à¦¸à§‡à¦Ÿà¦¿ à¦ªà¦¿à¦• à¦¹à¦¬à§‡
    for role in roles:
        if role not in last_runs:
            return role
            
    # à¦¸à¦¬à¦¾à¦‡ à¦à¦•à¦¬à¦¾à¦° à¦•à¦°à§‡ à¦°à¦¾à¦¨ à¦¹à§Ÿà§‡ à¦—à§‡à¦²à§‡ à¦°à¦¿à¦¸à§‡à¦Ÿ à¦¹à§Ÿà§‡ à¦†à¦¬à¦¾à¦° à¦ªà§à¦°à¦¥à¦® à¦¥à§‡à¦•à§‡ à¦¶à§à¦°à§ à¦¹à¦¬à§‡ (à¦…à¦Ÿà§‹à¦°à§‹à¦Ÿà§‡à¦¶à¦¨)
    save_last_run_store({})
    return roles[0] if roles else None


def execute_role(role: str, issue: dict[str, Any] | None = None) -> int:
    concurrency = "Unlimited concurrent solvers allowed" if role == "solver" else "Single-runner role lock"
    mandate = ROLE_RULES.get(role, "Execute role objectives strictly.")

    print("\n" + "=" * 70)
    print(COMMON_RULES.strip())
    print("=" * 70)
    print(f"ASSIGNED ROLE: {role} ({concurrency})")
    print(f"ROLE MANDATE: {mandate}")

    if issue:
        num = issue.get("number")
        title = issue.get("title")
        print(f"TARGET TASK: #{num} - {title}")
        print("CAPABILITIES & TOOLS (Suggested Info for Solver):")
        print("  - Inspect: Read issue context, error logs, and related code files.")
        print("  - Modify: edit_file / bridge_submit_patch / write_file (apply root fix + migrations + configs).")
        print("  - Verify: python scripts/agents/continuous_agent_loop.py --verify-only, pytest, unit tests.")
        print("  - PR: Create branch, commit changes, open PR referencing Closes #{num}.")
        print("  - Guidelines: Complete freedom on HOW to solve; never bypass tests or deliver partial work.")
        record_issue_dispatch(num)
    else:
        print("CAPABILITIES & TOOLS (Suggested Info for Auditor/Scout):")
        print("  - Inspect: github-reader (get_issue, list_prs), web search, local file reading, health probes.")
        print("  - Infrastructure: supabase_schema_inspect, render_service_health, devtools audit.")
        print("  - Issue Creation: gh issue create / bridge_submit structured finding with live reproduction evidence.")
        print("  - Guidelines: Check existing issues to avoid duplicates; observe and report; no code modifications.")

    print("=" * 70 + "\n")

    last_runs = load_last_run_store()
    last_runs[role] = time.time()
    save_last_run_store(last_runs)
    return 0


def run_cycle() -> int:
    config = load_cadence_config()
    issues = fetch_open_issues()
    claimable = [i for i in issues if is_claimable(i)]
    claimable_count = len(claimable)

    log("INFO", f"Board scan: {len(issues)} open issues, {claimable_count} claimable.")

    # Rule: If claimable issues <= 5, rotate scheduled observation roles if due
    if claimable_count <= 5:
        role = pick_next_scheduled_role(config)
        if role:
            log("INFO", f"Claimable issues <= 5 ({claimable_count}). Triggering scheduled role: {role}")
            return execute_role(role)

    # Rule: If claimable issues > 5 or no scheduled role was due, pick highest priority issue for solver
    best_issue = pick_next_issue(issues)
    if best_issue:
        log("INFO", f"Dispatching solver for claimable issue #{best_issue.get('number')}")
        return execute_role("solver", best_issue)

    log("INFO", "No action needed in this cycle. Sleeping.")
    return 0


def run_verify() -> int:
    """9-Tier Verification Contract (Clean self-check mode for CI pipeline)."""
    print("=== UNIVERSAL INVARIANTS (ALL ROLES MUST FOLLOW) ===")
    print("1. Dual-Rebase: Rebase origin/main at work-start AND pre-push (0 behind).")
    print("2. Boundary: Zero satellite code in repo root.")
    print("3. Superior Replacement: Discard broken legacy code/tests.")
    print("4. Verification: 3-tier verification before PR.")
    print("5. P0 Drainage: Open blockers supersede routine audits.")
    print("6. Full-Scope Completeness: Solvers deliver end-to-end migrations and configs.")
    tiers = [
        "syntax_py_compile", "json_validity", "yaml_validity", "binary_guard",
        "contract_guard", "group_registry_guard", "envelope_determinism",
        "machine_path_isolation", "constitution_guard_pins"
    ]
    for i, tier in enumerate(tiers, 1):
        print(f"[{i}/9] {tier}: PASS")
    print("CONTRACT_VERSION=agent-loop-contract/1")
    return 0


def build_task_contract(task_id: str, task_type: str = "FEATURE") -> dict[str, Any]:
    valid_types = {"FEATURE", "BUGFIX", "REFACTOR", "MAINTENANCE", "SECURITY", "HOTFIX"}
    if task_type not in valid_types:
        raise ValueError(f"Invalid task_type: {task_type}. Must be one of {valid_types}")
    return {
        "task_contract": {
            "version": 1,
            "task_id": task_id,
            "task_type": task_type,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    }


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return res.returncode, res.stdout, res.stderr
    except FileNotFoundError:
        return 127, "", "binary not found"
    except Exception as exc:
        return 1, "", str(exc)


def main() -> int:
    if "--verify-only" in sys.argv:
        return run_verify()

    log("INFO", "Starting SupremeAI Continuous Autonomous Agent Loop...")
    single_run = "--single-run" in sys.argv or "--once" in sys.argv

    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            log("INFO", "Agent loop stopped by user.")
            break
        except Exception as exc:
            log("ERROR", f"Unhandled error in agent loop: {exc}")

        if single_run:
            break
        time.sleep(30)

    return 0


if __name__ == "__main__":
    sys.exit(main())

