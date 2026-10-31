#!/usr/bin/env python3
"""SupremeAI — Continuous Autonomous Agent Loop (Lightweight Single Door SSOT).

Responsibility:
1. Fetch live open issues from GitHub board / Tower.
2. Smart triage:
   - If claimable issues <= 5: rotate scheduled observation roles (cadence-based).
   - If claimable issues > 5: dispatch highest priority issue to 'solver'.
3. 30-minute cooldown: once an issue is dispatched, skip it for 30 minutes;
   if still unresolved after 30 minutes, re-evaluate by priority.
4. Continuous loop execution without extraneous CLI flags.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROTATION_STORE = Path(".agent_cadence_last_run.json")
ISSUE_LEASE_STORE = Path(".issue_lease_store.json")
EXCLUDED_LABELS = frozenset({
    "claimed", "in-progress", "blocked", "wip", "ci-failed",
    "stale", "duplicate", "invalid", "report-only", "bridge:receipt",
    "status:claimed", "status:in-progress", "state:seq-hold",
    "blocked-by-upstream", "mirror:private", "anchor-hub", "admin-only",
    "bridge:idempotent-noop", "bridge:in-gates", "bridge:pr-opened",
    "bridge:queued", "bridge:rejected"
})
PRIORITY_MAP = (("p0", 0), ("p1", 1), ("p2", 2), ("p3", 3))

# =============================================================================
# 5 ROLES & THEIR MANDATES (SSOT)
# =============================================================================
ROLE_RULES: dict[str, str] = {
    "solver": (
        "Unlimited concurrent solvers allowed. Solve root cause, verify boundary, "
        "write all required migrations/configs/tests end-to-end (no partial work), and submit PR."
    ),
    "ecosystem-scout": (
        "সারা বিশ্বের যেকোনো জায়গা থেকে SupremeAI-এর জন্য সবচেয়ে লাভজনক ও উপকারী "
        "হবে এমন জিনিস ও ইনোভেশন খুঁজে আনা। শুধুমাত্র লাইভ প্রমাণসহ কংক্রিট, "
        "বাস্তবায়নযোগ্য ফাইন্ডিং ফাইল করা যাবে; অনুমাননির্ভর/হাইপ টিকেট কঠোরভাবে নিষিদ্ধ; কোড এডিট নয়।"
    ),
    "human-eye": (
        "আমাদের কাস্টমার যেন সর্বোত্তম ও শ্রেষ্ঠ এক্সপেরিয়েন্স পায় তার জন্য "
        "প্রয়োজনীয় সমস্ত UI/UX ও পারফরম্যান্স নিশ্চিত করা।"
    ),
    "rules-breaker": (
        "আমাদের সম্পূর্ণ সিস্টেমের সিকিউরিটি, টেকনিক্যাল ডেট এবং লজিক্যাল "
        "গ্যাপের সমস্ত দুর্বলতা খুঁজে বের করে রিপোর্ট করা।"
    ),
    "platform-guardian": (
        "প্রজেক্টের সাথে যুক্ত অন্যান্য সমস্ত থার্ড-পার্টি প্ল্যাটফর্ম ও "
        "সার্ভিসের সার্বক্ষণিক তদারকি, অডিট ও নজরদারি নিশ্চিত করা (absorbed auditor duties)।"
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
    return {
        "scheduled_roles": [
            "ecosystem-scout", "human-eye", "rules-breaker", "platform-guardian"
        ]
    }


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

    # 30-minute cooldown
    num = str(item.get("number", ""))
    if num:
        lease_store = load_issue_lease_store()
        if num in lease_store:
            try:
                last_ts = float(lease_store[num])
                if (time.time() - last_ts) < 1800.0:
                    return False
            except Exception:
                pass

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
    
    # যে রোলটি এখনও এই এপিসোডে রান হয়নি, সেটি পিক হবে
    for role in roles:
        if role not in last_runs:
            return role
            
    # সবাই একবার করে রান হয়ে গেলে রিসেট হয়ে আবার প্রথম থেকে শুরু হবে (অটোরোটেশন)
    save_last_run_store({})
    return roles[0] if roles else None


def sanitize_branch_name(issue_num: int | str, title: str) -> str:
    """Create deterministic and compliant branch name from issue number and title."""
    # Prefix detection (fix, feat, chore, etc.)
    prefix = "feat"
    lower_title = title.lower()
    for p in ("fix", "feat", "chore", "docs", "refactor", "test", "perf"):
        if lower_title.startswith(f"{p}:") or lower_title.startswith(f"{p}("):
            prefix = p
            break

    # Strip prefixes and non-alphanumeric characters
    clean_title = re.sub(r'^(feat|fix|chore|docs|refactor|test|perf)(\([^)]+\))?:?\s*', '', title, flags=re.I)
    slug = re.sub(r'[^a-z0-9]+', '-', clean_title.lower()).strip('-')[:35]
    slug = slug.strip('-') or "task"
    return f"{prefix}/{issue_num}-{slug}"


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
        title = str(issue.get("title") or "")
        branch_name = sanitize_branch_name(num, title)
        print(f"TARGET TASK: #{num} - {title}")
        print(f"AUTOMATIC BRANCH: {branch_name}")
        
        # Automatic branch creation & checkout for the agent
        try:
            curr_branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
            if curr_branch != branch_name:
                code = subprocess.run(["git", "checkout", "-b", branch_name], capture_output=True).returncode
                if code != 0:
                    subprocess.run(["git", "checkout", branch_name], capture_output=True)
                log("INFO", f"Automatically switched to branch: {branch_name}")
        except Exception as exc:
            log("WARN", f"Could not auto-create branch: {exc}")

        print(f"ACTION INSTRUCTION: Work strictly inside satellite domain. Rebase origin/main, execute fix, verify 3-tier, submit via PR (Closes #{num}).")
        print("CI CLOSURE POLICY: Issue closes automatically upon 100% green CI + auto-landing (never close manually).")
        record_issue_dispatch(num)
    else:
        print("ACTION INSTRUCTION: Perform observation/audit scan per role mandate. File structured concrete findings with live evidence only.")

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


def main() -> int:
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
