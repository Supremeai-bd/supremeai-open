#!/usr/bin/env python3
"""Smart Dispatcher - 5-layer intelligence for autonomous agent routing.

5 Intelligence Layers:
1. Smart Role-Switching (CI red -> ci-fixer, security -> breaker)
2. Auto-Delegation (area:backend -> coder, area:ci -> ci-fixer)
3. Cross-Agent Knowledge Sharing (auditor findings -> coder context)
4. Predictive Priority Boosting (3+ blockers -> auto P1)
5. Auto-Escalation (3x fail -> P0 + different agent)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")

# Role capability matrix
ROLE_CAPABILITIES = {
    "auditor": ["area:backend", "area:frontend", "area:ci", "type:bug", "type:dead-code"],
    "planner": ["type:feature-proposal", "type:architecture", "area:architecture"],
    "coder": ["area:backend", "area:frontend", "type:bug", "type:feature", "type:refactor"],
    "ci-fixer": ["area:ci", "type:ci-failure", "type:merge-conflict"],
    "watcher": ["area:infrastructure", "type:platform-alert", "type:security"],
    "human-eyes": ["area:frontend", "type:ui-ux-bug", "type:accessibility"],
    "breaker": ["type:security", "type:vulnerability", "type:performance"],
}

AREA_TO_ROLE = {
    "area:backend": "coder",
    "area:frontend": "coder",
    "area:ci": "ci-fixer",
    "area:architecture": "planner",
    "area:infrastructure": "watcher",
    "area:security": "breaker",
}

TYPE_TO_ROLE = {
    "type:bug": "coder",
    "type:feature": "coder",
    "type:refactor": "coder",
    "type:ci-failure": "ci-fixer",
    "type:merge-conflict": "ci-fixer",
    "type:platform-alert": "watcher",
    "type:ui-ux-bug": "human-eyes",
    "type:vulnerability": "breaker",
    "type:feature-proposal": "planner",
    "type:dead-code": "auditor",
}


class SmartDispatcher:
    """5-layer intelligent task dispatcher for autonomous agents."""

    def __init__(self, repo: str = REPO):
        self.repo = repo
        self.gh_token = os.environ.get("GITHUB_TOKEN", os.environ.get("GH_TOKEN", ""))

    def _gh_cli(self, *args: str) -> str:
        """Run gh CLI command."""
        try:
            r = subprocess.run(
                ["gh", *args, "--repo", self.repo],
                capture_output=True, text=True, timeout=15, check=False,
            )
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""

    # === Layer 1: Smart Role-Switching ===

    def _check_ci_red(self) -> dict | None:
        """Check if CI is red on main branch.

        #3208: historical failures on obsolete SHAs are not red. Only a
        failure whose headSha equals the CURRENT main HEAD counts — otherwise
        stale failures permanently divert the coder fleet to ci-fixer
        (fleet-wide starvation while current HEAD is green).
        """
        try:
            # Resolve current main HEAD SHA first. Without it we cannot judge
            # the current HEAD's state: reporting RED from unfiltered history
            # would be an unverified claim (U2), so treat as not-red (a false
            # green only means agents keep working; a false red starves them).
            sha_r = subprocess.run(
                ["gh", "api", f"repos/{self.repo}/commits/main", "--jq", ".sha"],
                capture_output=True, text=True, timeout=15, check=False,
            )
            main_sha = sha_r.stdout.strip() if sha_r.returncode == 0 else ""
            if not main_sha:
                return None
            r = subprocess.run(
                ["gh", "run", "list", "--repo", self.repo, "--branch", "main",
                 "--status", "failure", "--limit", "30", "--json",
                 "databaseId,name,headSha,url"],
                capture_output=True, text=True, timeout=15, check=False,
            )
            if r.returncode == 0 and r.stdout.strip():
                runs = json.loads(r.stdout)
                # #3208: client-side filter — only failures on current HEAD
                runs = [run for run in runs if run.get("headSha") == main_sha]
                if runs:
                    return runs[0]
        except Exception:
            pass
        return None

    def _check_security_alerts(self) -> dict | None:
        """Check for open P0-critical security issues."""
        try:
            r = subprocess.run(
                ["gh", "issue", "list", "--repo", self.repo, "--state", "open",
                 "--label", "P0-critical", "--label", "type:security",
                 "--json", "number,title", "--limit", "3"],
                capture_output=True, text=True, timeout=15, check=False,
            )
            if r.returncode == 0 and r.stdout.strip():
                issues = json.loads(r.stdout)
                if issues:
                    return issues[0]
        except Exception:
            pass
        return None

    def _should_switch_role(self, current_role: str) -> tuple[str, str]:
        """Layer 1: decide if agent should switch role based on system state."""
        ci_fail = self._check_ci_red()
        if ci_fail and current_role != "ci-fixer":
            name = ci_fail.get("name", "?")
            sha = ci_fail.get("headSha", "?")[:8]
            return "ci-fixer", f"CI RED on main: {name} ({sha})"

        sec_alert = self._check_security_alerts()
        if sec_alert and current_role != "breaker":
            num = sec_alert.get("number")
            title = sec_alert.get("title", "?")[:50]
            return "breaker", f"Security P0: #{num} - {title}"

        return current_role, ""

    # === Layer 2: Auto-Delegation ===

    def _match_role_to_task(self, issue_labels: list[str]) -> str | None:
        """Layer 2: match task labels to best-fit role."""
        for label in issue_labels:
            if label in AREA_TO_ROLE:
                return AREA_TO_ROLE[label]
            if label in TYPE_TO_ROLE:
                return TYPE_TO_ROLE[label]
        return None

    # === Layer 3: Cross-Agent Knowledge Sharing ===

    def _fetch_relevant_knowledge(self, issue_labels: list[str]) -> list[str]:
        """Layer 3: fetch knowledge from past closed issues."""
        knowledge = []
        keywords = []
        if "area:backend" in issue_labels:
            keywords.append("backend")
        if "area:security" in issue_labels or "type:security" in issue_labels:
            keywords.append("security")
        if "type:bug" in issue_labels:
            keywords.append("bug")

        for kw in keywords[:2]:
            try:
                r = subprocess.run(
                    ["gh", "issue", "list", "--repo", self.repo, "--state", "closed",
                     "--search", f"{kw} alternatives_rejected", "--json", "number,title",
                     "--limit", "3"],
                    capture_output=True, text=True, timeout=10, check=False,
                )
                if r.returncode == 0 and r.stdout.strip():
                    results = json.loads(r.stdout)
                    for item in results:
                        num = item.get("number")
                        title = item.get("title", "?")[:60]
                        knowledge.append(f"#{num}: {title}")
            except Exception:
                pass
        return knowledge[:3]

    # === Layer 4: Predictive Priority Boosting ===

    def _count_blocking_relationships(self, issue_number: int) -> int:
        """Layer 4: count how many other issues depend on this one."""
        try:
            r = subprocess.run(
                ["gh", "issue", "list", "--repo", self.repo, "--state", "open",
                 "--search", f"#{issue_number} blocked-by", "--json", "number",
                 "--limit", "20"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if r.returncode == 0 and r.stdout.strip():
                results = json.loads(r.stdout)
                return len(results)
        except Exception:
            pass
        return 0

    def _should_boost_priority(self, issue: dict) -> tuple[bool, str]:
        """Layer 4: should this issue priority be boosted?"""
        num = issue.get("number", 0)
        labels = [l.get("name", "") if isinstance(l, dict) else str(l) for l in issue.get("labels", [])]
        if "P0-critical" in labels:
            return False, "already P0"
        blockers = self._count_blocking_relationships(num)
        if blockers >= 3 and "P1-high" not in labels:
            return True, f"blocks {blockers}+ other issues - auto-promote to P1"
        return False, ""

    # === Layer 5: Auto-Escalation ===

    def _check_fail_count(self, issue_number: int) -> int:
        """Layer 5: count how many times agents failed on this issue."""
        try:
            r = subprocess.run(
                ["gh", "issue", "view", str(issue_number), "--repo", self.repo,
                 "--json", "comments", "--jq", ".comments[].body"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if r.returncode == 0:
                fail_count = len(re.findall(r"claim failed|rc=[^0]|work command exited rc=non", r.stdout))
                return fail_count
        except Exception:
            pass
        return 0

    def _should_escalate(self, issue: dict) -> tuple[bool, str]:
        """Layer 5: should this issue be auto-escalated?"""
        num = issue.get("number", 0)
        labels = [l.get("name", "") if isinstance(l, dict) else str(l) for l in issue.get("labels", [])]
        fail_count = self._check_fail_count(num)
        if fail_count >= 3 and "P0-critical" not in labels:
            return True, f"failed {fail_count}x - auto-escalate to P0 + reassign"
        created = issue.get("createdAt", "")
        if created:
            try:
                from datetime import datetime, timezone
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                age_hours = (datetime.now(timezone.utc) - created_dt).total_seconds() / 3600
                if age_hours > 24 and "P1-high" not in labels and "P0-critical" not in labels:
                    return True, f"stale {age_hours:.0f}h - auto-escalate for human review"
            except Exception:
                pass
        return False, ""

    # === Main Decision Engine ===

    def decide(self, agent_name: str, current_role: str) -> dict:
        """Main entry point - returns the smart dispatch decision."""
        decision = {
            "role": current_role,
            "issue": None,
            "reason": "",
            "knowledge": [],
            "priority_boost": False,
            "escalation": False,
        }

        # Layer 1: Smart Role-Switching
        new_role, switch_reason = self._should_switch_role(current_role)
        if new_role != current_role:
            decision["role"] = new_role
            decision["reason"] = switch_reason
            print(f"Layer 1 (Role-Switch): {current_role} -> {new_role} - {switch_reason}")

        # Fetch open issues
        try:
            r = subprocess.run(
                ["gh", "issue", "list", "--repo", self.repo, "--state", "open",
                 "--json", "number,title,labels,createdAt", "--limit", "30"],
                capture_output=True, text=True, timeout=15, check=False,
            )
            if r.returncode != 0 or not r.stdout.strip():
                return decision
            issues = json.loads(r.stdout)
        except Exception:
            return decision

        # Layer 5: Auto-Escalation
        for issue in issues:
            should_escalate, esc_reason = self._should_escalate(issue)
            if should_escalate:
                num = issue.get("number")
                print(f"Layer 5 (Escalation): #{num} - {esc_reason}")
                self._gh_cli("issue", "edit", str(num), "--add-label", "P0-critical")
                decision["escalation"] = True

        # Layer 4: Predictive Priority Boosting
        for issue in issues:
            should_boost, boost_reason = self._should_boost_priority(issue)
            if should_boost:
                num = issue.get("number")
                print(f"Layer 4 (Priority-Boost): #{num} - {boost_reason}")
                self._gh_cli("issue", "edit", str(num), "--add-label", "P1-high")
                decision["priority_boost"] = True

        # Layer 2: Auto-Delegation - find best-fit task
        best_issue = None
        best_score = -1
        for issue in issues:
            labels = [l.get("name", "") if isinstance(l, dict) else str(l) for l in issue.get("labels", [])]
            if "has-pr" in labels or "status:in-progress" in labels:
                continue
            if "blocked" in labels:
                continue
            matched_role = self._match_role_to_task(labels)
            if matched_role == decision["role"] or matched_role is None:
                if "P0-critical" in labels:
                    score = 100
                elif "P1-high" in labels:
                    score = 80
                elif "P2-medium" in labels:
                    score = 60
                elif "P3-low" in labels:
                    score = 40
                else:
                    score = 30
                if matched_role == decision["role"]:
                    score += 20
                if score > best_score:
                    best_score = score
                    best_issue = issue

        if best_issue:
            num = best_issue.get("number")
            title = best_issue.get("title", "")
            labels = [l.get("name", "") if isinstance(l, dict) else str(l) for l in best_issue.get("labels", [])]
            if not decision["reason"]:
                decision["reason"] = f"best-fit task for role '{decision['role']}'"
            decision["issue"] = num
            decision["title"] = title
            # Layer 3: Cross-Agent Knowledge Sharing
            knowledge = self._fetch_relevant_knowledge(labels)
            if knowledge:
                decision["knowledge"] = knowledge
                print(f"Layer 3 (Knowledge): {len(knowledge)} entries from past work")
            print(f"Layer 2 (Delegation): #{num} '{title[:50]}' -> role={decision['role']} (score={best_score})")
        else:
            if not decision["reason"]:
                decision["reason"] = "no best-fit task found - fallback to normal flow"

        return decision


def main() -> int:
    """CLI entry point for testing the dispatcher."""
    import argparse
    parser = argparse.ArgumentParser(description="Smart Dispatcher (#2919)")
    parser.add_argument("--agent-name", required=True, help="Agent identifier")
    parser.add_argument("--role", required=True, help="Current role")
    args = parser.parse_args()
    dispatcher = SmartDispatcher()
    decision = dispatcher.decide(args.agent_name, args.role)
    print(json.dumps(decision, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
