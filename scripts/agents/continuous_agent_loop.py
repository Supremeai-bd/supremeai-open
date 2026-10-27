#!/usr/bin/env python3
"""SupremeAI — Minimal Autonomous Agent Loop (Unified Rules & Roles Dispatcher).

Traffic-police logic:
1. Always display the 4 Universal Invariant Pillars (Common Rules).
2. If unclaimed issues exist -> Unlimited Solvers allowed: prompt agent with solver mandate & status:claimed rule.
3. If no open issues exist -> Reset/zero cadence timers so scheduled roles can run immediately.
4. Scheduled roles -> Exactly 1 agent at a time per role (active lock / immediate state advance).
5. Problematic/stuck issues -> Agents autonomously decide and handle them.
"""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CADENCE_FILE = REPO_ROOT / "scripts" / "agents" / "agent_cadence.json"
STATE_FILE = REPO_ROOT / "scripts" / "agents" / "agent_cadence_state.json"

ROLE_RULES: dict[str, str] = {
    "solver": "Unlimited concurrent solvers allowed. Mandatory rule: Label 'status:claimed' on the issue before branching. Solve root cause, verify boundary, submit PR.",
    "ecosystem-scout": "Scan federation for new expansion opportunities and file sub-issues under 8 Anchor Hubs (no code edits).",
    "auditor": "Audit codebase for dead code, compliance drifts, and propose automated CI gates.",
    "human-eye": "Inspect user-facing public funnel speed (FCP < 1.0s) and responsive UI performance.",
    "rules-breaker": "Probe security boundaries, enforce zero-leak invariant, and report vulnerabilities.",
    "platform-guardian": "Verify all connected service dependencies and alert if any service is degraded or quota-blocked.",
}

COMMON_RULES = """=== UNIVERSAL INVARIANTS (ALL ROLES MUST FOLLOW) ===
1. Dual-Rebase: Rebase origin/main at work-start AND pre-push (0 behind).
2. Boundary: Zero satellite code in repo root (src/*, service/*, packages/*).
3. Superior Replacement: Discard broken legacy code/tests; never hack new code to appease past errors.
4. Verification: No direct push to protected branches; all PRs require local proof."""

def main() -> int:
    cmd = ["gh", "issue", "list", "--json", "number,labels", "--state", "open", "--limit", "100"]
    p = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, errors="replace")
    raw = json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip() else []
    skip = {"status:claimed", "status:in-progress", "anchor-hub", "admin-only"}
    unclaimed = [i for i in raw if not any(l.get("name") in skip for l in i.get("labels", []))]

    print(COMMON_RULES)
    print("=" * 52)

    # 1. Unclaimed issues -> Unlimited Solvers allowed (Atomic claim with status:claimed)
    if unclaimed:
        print(f"ASSIGNED ROLE: solver (Unlimited concurrency allowed)\nROLE MANDATE: {ROLE_RULES['solver']}")
        print("ACTION: Unclaimed issues found. Apply 'status:claimed' label, pick an issue, and solve it.")
        return 0

    # 2. No open issues -> Reset cadence timers to 0 so routine roles trigger immediately
    cadence = json.loads(CADENCE_FILE.read_text(encoding="utf-8")).get("cadences_hours", {}) if CADENCE_FILE.exists() else {}
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    now = time.time()

    # 3. Scheduled roles: Only 1 at a time (immediately record run timestamp to lock out others)
    for role, hours in cadence.items():
        if now - state.get(role, 0) >= hours * 3600:
            state[role] = now
            STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
            mandate = ROLE_RULES.get(role, "Execute role objectives strictly.")
            print(f"ASSIGNED ROLE: {role} (Single-runner role lock)\nROLE MANDATE: {mandate}")
            print(f"ACTION: Time expired for {role}. Act as {role} now.")
            return 0

    print("ACTION: System is clean and up to date.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
