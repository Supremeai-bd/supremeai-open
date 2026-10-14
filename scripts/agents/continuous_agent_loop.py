#!/usr/bin/env python3
"""Continuous Autonomous Agent Loop — Open Contributor Edition.

Target: External and autonomous agents contributing to SupremeAI Open Foundation
Repository: Supremeai-bd/supremeai-open

This loop automates the 8-step cycle defined in AGENTS.md §0:
  Step 1: Understand — fetch task issue / requirements
  Step 2: Rules      — load governing AGENT_RULES.md policies
  Step 3: Inspect    — check open PRs & local git status
  Step 4: Branch     — create clean contributor branch (contributor/issue-<id>)
  Step 5: Work       — guide minimal safe change within declared scope
  Step 6: Verify     — 3-tier checks: syntax, smoke, tests
  Step 7: Record     — generate PR with Universal PR Template & test evidence
  Step 8: Return     — fresh-board check & loop back

Zero-Credential Guarantees:
  - Requires NO private tokens or credentials.
  - Can run autonomously via `gh` CLI (if installed) or interactively.
  - Seamlessly bridges changes to SupremeAI Private Monorepo via CI Guardian.
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

# Configure UTF-8 for cross-platform stability
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from typing import Any

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
    group: str = "open",
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
                "3-tier test output", "diff check", "board freshness re-poll"
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


try:
    import yaml
except ImportError:
    yaml = None


def step_1_understand(issue_id: str | None = None, allow_adhoc: bool = False) -> dict[str, str] | None:
    """Step 1: Fetch and display task contract / issue context."""
    log("📖", "[Step 1/8: Understand] Loading task contract...")
    
    if issue_id:
        code, out, _ = run_cmd(["gh", "issue", "view", str(issue_id), "--repo", UPSTREAM_REPO, "--json", "number,title,body,state"])
        if code == 0:
            try:
                data = json.loads(out)
                state = data.get("state", "OPEN").upper()
                if state == "CLOSED":
                    log("❌", f"[Fail-Closed] Issue #{data.get('number')} is CLOSED. Autonomous work on closed tasks is rejected.")
                    return None
                log("✅", f"Loaded Issue #{data.get('number')} ({state}): {data.get('title')}")
                return {
                    "id": str(data.get("number")),
                    "title": data.get("title", ""),
                    "body": data.get("body", ""),
                    "state": state,
                }
            except Exception as e:
                log("⚠️", f"Failed to parse issue JSON: {e}")
        else:
            log("ℹ️", f"Could not fetch issue #{issue_id} via gh CLI. Proceeding with offline task contract for #{issue_id}.")
            return {
                "id": str(issue_id),
                "title": f"Task #{issue_id}",
                "body": f"Implement smallest safe change for #{issue_id}.",
                "state": "OFFLINE",
            }

    if not allow_adhoc:
        log("❌", "[Fail-Closed Gate] No --issue specified! Multi-agent mode requires a specific issue contract.")
        log("ℹ️", "Please provide --issue <number> or pass --allow-adhoc explicitly for local testing.")
        return None

    # Fallback to interactive or default manual task
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


def step_4_branch(task: dict[str, str]) -> str:
    """Step 4: Create atomic branch for task with collision avoidance."""
    issue_num = task.get("id", "adhoc")
    target_branch = f"contributor/issue-{issue_num}" if issue_num != "adhoc" else f"contributor/work-{int(time.time())}"
    log("🌿", f"[Step 4/8: Branch] Ensuring branch '{target_branch}'...")
    
    # Check if branch exists
    code, _, _ = run_cmd(["git", "rev-parse", "--verify", target_branch])
    if code == 0:
        _, curr_branch, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if curr_branch == target_branch:
            log("✅", f"Already on active branch '{target_branch}'")
            return target_branch
        
        checkout_code, _, _ = run_cmd(["git", "checkout", target_branch])
        if checkout_code != 0:
            target_branch = f"contributor/issue-{issue_num}-{int(time.time())}"
            log("🌿", f"Switched to isolated collision-safe branch '{target_branch}'")
            run_cmd(["git", "checkout", "-b", target_branch])
    else:
        run_cmd(["git", "checkout", "-b", target_branch])

    log("✅", f"Active on branch '{target_branch}'")
    return target_branch


def step_5_work_notice() -> None:
    """Step 5: Scope boundary guidance."""
    log("🔨", "[Step 5/8: Work] Execution Phase")
    print("   -> Keep changes atomic and minimal within declared scope.")
    print("   -> Follow contracts in api-schemas/ and examples/.")
    print("   -> Make your edits now before running verification.")


def step_6_verify() -> bool:
    """Step 6: Run 3-tier verification (syntax, schemas, tests)."""
    log("🧪", "[Step 6/8: Verify] Running 3-Tier Verification Contract...")
    
    # 1. Python Syntax / Compile smoke
    py_files = list(REPO_ROOT.glob("**/*.py"))
    for py in py_files:
        if "venv" in str(py) or ".git" in str(py):
            continue
        code, _, err = run_cmd([sys.executable, "-m", "py_compile", str(py)])
        if code != 0:
            log("❌", f"Syntax error in {py.name}: {err}")
            return False

    # 2. JSON Schema validation
    json_files = list(REPO_ROOT.glob("**/*.json"))
    for jf in json_files:
        if "node_modules" in str(jf) or ".git" in str(jf):
            continue
        try:
            with open(jf, "r", encoding="utf-8") as f:
                json.load(f)
        except Exception as e:
            log("❌", f"Invalid JSON in {jf.name}: {e}")
            return False

    # 3. YAML & OpenAPI Schema validation
    if yaml is not None:
        yaml_files = list(REPO_ROOT.glob("**/*.yaml")) + list(REPO_ROOT.glob("**/*.yml"))
        for yf in yaml_files:
            if ".git" in str(yf) or "node_modules" in str(yf):
                continue
            try:
                with open(yf, "r", encoding="utf-8") as f:
                    yaml.safe_load(f)
            except Exception as e:
                log("❌", f"Invalid YAML in {yf.name}: {e}")
                return False

    # 4. Self-test smoke checks (P6 validation)
    try:
        res_code, _, _ = run_cmd(["__test_nonexistent_binary_xyz_123__"])
        if res_code != 127:
            log("❌", f"run_cmd missing binary expected exit 127, got {res_code}")
            return False

        try:
            build_task_contract("test", task_type="INVALID_TYPE")
            log("❌", "build_task_contract failed to reject invalid task_type")
            return False
        except ValueError:
            pass  # Expected fail-closed
    except Exception as e:
        log("❌", f"Self-test verification failed: {e}")
        return False

    log("✅", "3-tier checks passed! Syntax, JSON/YAML schemas, and contracts are verified.")
    return True


def step_7_record(
    task: dict[str, str],
    branch: str,
    contract: dict[str, Any] | None = None,
    auto_pr: bool = False,
) -> bool:
    """Step 7: Prepare PR body and submit PR."""
    log("📝", "[Step 7/8: Record] Generating Universal PR Template...")
    issue_num = task.get("id", "adhoc")
    
    contract_yaml_snippet = ""
    if contract and "task_contract" in contract:
        tc = contract["task_contract"]
        contract_yaml_snippet = f"""
## Task Contract (§7 AGENT_RULES.md)
```yaml
task_contract:
  version: {tc.get('version', 1)}
  task_id: "{tc.get('task_id')}"
  issue: "{tc.get('issue')}"
  task_type: {tc.get('task_type')}
  group: {tc.get('group')}
  priority: {tc.get('priority')}
  objective: "{tc.get('objective')}"
  scope:
    touching_files: {json.dumps(tc.get('scope', {}).get('touching_files', []))}
    forbidden_paths: {json.dumps(tc.get('scope', {}).get('forbidden_paths', []))}
  admin_gate:
    required: {str(tc.get('admin_gate', {}).get('required', False)).lower()}
    status: {tc.get('admin_gate', {}).get('status', 'NOT_REQUIRED')}
  role_policy: {tc.get('role_policy')}
```
"""

    pr_body = f"""## Summary
Autonomous contribution for issue #{issue_num}: {task.get('title')}.

## Linked Issue / Claim
Refs #{issue_num}

## Type of Change
- [x] `feat` / `fix` / `docs` — Open contributor change
{contract_yaml_snippet}
## Test Evidence (3-Tier যাচাই-চুক্তি)
1. **Reflection Check:** Scoped to public open contracts.
2. **Syntax/Boot:** Verified with `continuous_agent_loop.py` compilation checks.
3. **Tests:** All schema and example contracts verified.

## Rollback Path
- [x] `git revert`-safe (no private state dependencies)
"""

    pr_file = REPO_ROOT / ".pr_template_draft.md"
    pr_file.write_text(pr_body, encoding="utf-8")
    log("📄", f"PR body draft saved to {pr_file.name}")

    if auto_pr:
        log("🚀", f"Opening Pull Request against {UPSTREAM_REPO}:main...")
        cmd = [
            "gh", "pr", "create",
            "--repo", UPSTREAM_REPO,
            "--base", "main",
            "--head", branch,
            "--title", f"feat(open): {task.get('title')}",
            "--body-file", str(pr_file)
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


def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI Continuous Agent Loop — Open Contributor Edition")
    parser.add_argument("--issue", type=str, help="Specific GitHub issue number to claim and resolve")
    parser.add_argument("--auto-pr", action="store_true", help="Automatically submit PR via gh CLI upon test pass")
    parser.add_argument("--verify-only", action="store_true", help="Only run 3-tier verification and exit")
    parser.add_argument("--emit-contract", action="store_true", help="Emit JSON task contract adhering to AGENT_RULES.md §7 and exit")
    parser.add_argument("--touching-files", type=str, help="Comma-separated list of touching files for declared scope")
    parser.add_argument("--task-type", type=str, default="IMPLEMENT", help="Task type (default: IMPLEMENT)")
    parser.add_argument("--priority", type=str, default="P2", help="Task priority (P0, P1, P2, P3)")
    parser.add_argument("--allow-adhoc", action="store_true", help="Allow adhoc task execution without --issue (offline testing only)")
    parser.add_argument("--force", action="store_true", help="Bypass dirty workspace isolation gate (not recommended)")
    args = parser.parse_args()

    touching_files = [f.strip() for f in args.touching_files.split(",")] if args.touching_files else []

    if args.emit_contract:
        issue_id = args.issue or "adhoc"
        contract = build_task_contract(
            task_id=f"task-{issue_id}",
            issue=issue_id if issue_id != "adhoc" else None,
            task_type=args.task_type,
            priority=args.priority,
            objective=f"Resolve issue #{issue_id}",
            touching_files=touching_files,
        )
        print(json.dumps(contract, indent=2))
        return 0

    print("======================================================================")
    print(" SupremeAI — Continuous Agent Loop (Open Contributor Runner) ")
    print(f" Target: {UPSTREAM_REPO}")
    print("======================================================================")

    if args.verify_only:
        return 0 if step_6_verify() else 1

    task = step_1_understand(args.issue, allow_adhoc=args.allow_adhoc)
    if not task:
        return 1

    if not step_2_rules():
        return 1

    state = step_3_inspect_state(force=args.force)
    if state.get("clean") != "True" and not args.force:
        return 1

    contract = build_task_contract(
        task_id=f"task-{task.get('id', 'adhoc')}",
        issue=task.get("id"),
        task_type=args.task_type,
        priority=args.priority,
        objective=task.get("title", ""),
        touching_files=touching_files,
    )

    branch = step_4_branch(task)
    step_5_work_notice()

    # Run verification check
    if not step_6_verify():
        log("❌", "Verification failed. Please fix errors before proceeding.")
        return 1

    if not step_7_record(task, branch, contract=contract, auto_pr=args.auto_pr):
        log("❌", "Step 7 (Record) failed! Halting before completion return.")
        return 1

    step_8_return()
    return 0


if __name__ == "__main__":
    sys.exit(main())


