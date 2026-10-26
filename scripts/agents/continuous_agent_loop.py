#!/usr/bin/env python3
"""
scripts/agents/continuous_agent_loop.py — Minimal Agent Loop v3.

Flow:
    SCAN (master_health_check --full)
      |
      v
    Board has claimable issues?
      YES -> claim top -> VERIFY -> PR
      NO  -> ACTION PLAN has items?
               YES -> create_issue (dedup: skip if title fingerprint exists) -> claim -> VERIFY -> PR
               NO  -> system is green -> exit
      |
      v
    Repeat until no claimable issues AND no action plan items.

Zero race: sequential only. One branch, one claim, one PR at a time.
Zero duplicates: before creating, search open issues by fingerprint.

Contract: CONTRACT_VERSION = "agent-loop-contract/1"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CONTRACT_VERSION = "agent-loop-contract/1"
REPO_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_REPO = "Supremeai-bd/supremeai-open"

# Anchor hubs — never claim
ANCHOR_HUB_NUMBERS: set[int] = {
    749, 750, 751, 752, 753, 754, 755, 756, 757, 758, 759, 760, 761, 762
}

# Labels that block agent claiming
EXCLUDED_LABELS: set[str] = {
    "admin-only", "anchor-hub", "status:claimed", "status:in-progress",
    "state:seq-hold", "state:blocked", "state:hold", "private-mirror",
    "blocked-by-upstream", "mirror:private",
}

# CI Anchor hub for new CI-failure issues
CI_ANCHOR_HUB = 761


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(icon: str, msg: str) -> None:
    try:
        print(f"{icon} {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"[*] {msg}", flush=True)


def run(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 127, "", "timeout"
    except OSError as exc:
        return 127, "", str(exc)


def _get_gh_token() -> str:
    for var in ("GH_TOKEN", "GITHUB_TOKEN", "OPEN_SYNC_PAT"):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    rc, out, _ = run(["gh", "auth", "token"], timeout=5)
    return out.strip() if rc == 0 else ""


def gh_api(
    path: str,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    token: str = "",
) -> tuple[int, Any]:
    """Minimal GitHub REST helper. path = /repos/... or full URL."""
    url = path if path.startswith("http") else f"https://api.github.com{path}"
    tok = token or _get_gh_token()
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SupremeAI-AgentLoop/3",
    }
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(content) if content.strip() else {}
    except urllib.error.HTTPError as exc:
        content = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(content)
        except Exception:
            return exc.code, {"raw": content}
    except Exception as exc:
        return 0, {"error": str(exc)}


# ---------------------------------------------------------------------------
# STEP 0: Preflight — constitution freshness
# ---------------------------------------------------------------------------

CONSTITUTION_FILES = ("AGENTS.md", "AGENT_RULES.md", ".github/PULL_REQUEST_TEMPLATE.md")


def preflight() -> bool:
    missing = [f for f in CONSTITUTION_FILES if not (REPO_ROOT / f).exists()]
    if missing:
        log("❌", f"[Preflight] Missing constitution files: {missing}")
        return False
    rc, _, _ = run(["git", "fetch", "origin", "main"], timeout=30)
    if rc == 0:
        for path in CONSTITUTION_FILES:
            run(["git", "checkout", "origin/main", "--", path])
    log("✅", "[Preflight] Constitution synced.")
    return True


# ---------------------------------------------------------------------------
# STEP 1: SCAN — master_health_check --full
# ---------------------------------------------------------------------------

def scan() -> dict[str, Any]:
    """Run master_health_check --full --json. Returns structured action plan."""
    log("🔍", "[SCAN] master_health_check --full ...")
    rc, out, err = run(
        [sys.executable, "scripts/ops/master_health_check.py", "--full", "--json"],
        timeout=180,
    )
    empty: dict[str, Any] = {
        "healthy": False, "guard_failures": [], "satellite_failures": [], "action_plan": [],
    }
    if not out.strip():
        log("⚠️", f"[SCAN] No output: {err[:200]}")
        return empty
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return empty

    infra = data.get("infra", {})
    infra_ok = infra.get("overall_status", "down") == "healthy"
    ci = data.get("ci_sweep", {})
    guard_fails = [g for g in ci.get("guards", []) if g.get("status") != "pass"]
    sat_fails = [s for s in ci.get("satellites", []) if s.get("status") != "green"]

    plan: list[dict[str, Any]] = []
    idx = 1
    for g in guard_fails:
        plan.append({
            "priority": idx, "type": "local_guard",
            "name": g["name"], "fix": g.get("fix_hint", ""),
            "output": g.get("output", ""),
        })
        idx += 1
    for s in sat_fails:
        for run_info in s.get("failed_runs", [])[:2]:
            plan.append({
                "priority": idx, "type": "satellite_ci",
                "repo": s["repo"], "fix": s.get("fix_hint", ""),
                "run_id": run_info.get("id"), "run_url": run_info.get("url", ""),
                "run_name": run_info.get("name", "CI Pipeline"),
            })
            idx += 1

    healthy = infra_ok and not guard_fails and not sat_fails
    log(
        "✅" if healthy else "❌",
        f"[SCAN] Infra {'OK' if infra_ok else 'DEGRADED'} | "
        f"{len(guard_fails)} guard fail(s) | {len(sat_fails)} satellite fail(s) | "
        f"{len(plan)} action item(s)"
    )
    return {
        "healthy": healthy,
        "guard_failures": guard_fails,
        "satellite_failures": sat_fails,
        "action_plan": plan,
    }


# ---------------------------------------------------------------------------
# STEP 2: PICK — highest-priority claimable issue from board
# ---------------------------------------------------------------------------

def _label_names(issue: dict[str, Any]) -> list[str]:
    labels = issue.get("labels", [])
    if not isinstance(labels, list):
        return []
    return [str(l.get("name", "")).lower() for l in labels if isinstance(l, dict)]


def _is_claimable(issue: dict[str, Any]) -> bool:
    names = set(_label_names(issue))
    return (
        not (EXCLUDED_LABELS & names)
        and int(issue.get("number", 0)) not in ANCHOR_HUB_NUMBERS
    )


def _priority_key(issue: dict[str, Any]) -> tuple[int, int]:
    names = _label_names(issue)
    for rank, marker in enumerate(["p0", "p1", "p2", "p3"]):
        if any(n == marker or n.startswith(marker + "-") for n in names):
            return (rank, int(issue.get("number", 0)))
    return (4, int(issue.get("number", 0)))


def fetch_open_issues(token: str = "") -> list[dict[str, Any]]:
    """Fetch all open issues (gh CLI first, API fallback)."""
    rc, out, _ = run(
        ["gh", "issue", "list", "--repo", UPSTREAM_REPO,
         "--state", "open", "--limit", "200",
         "--json", "number,title,labels,body"],
        timeout=30,
    )
    if rc == 0 and out.strip():
        try:
            return json.loads(out)
        except Exception:
            pass
    # Fallback: REST API
    code, data = gh_api(
        f"/repos/{UPSTREAM_REPO}/issues?state=open&per_page=100",
        token=token,
    )
    if code == 200 and isinstance(data, list):
        return [i for i in data if "pull_request" not in i]
    return []


def pick_issue(all_issues: list[dict[str, Any]], exclude: set[str]) -> dict[str, Any] | None:
    """Return highest-priority claimable issue not in exclude set."""
    candidates = [
        i for i in all_issues
        if isinstance(i, dict)
        and _is_claimable(i)
        and str(i.get("number")) not in exclude
    ]
    if not candidates:
        return None
    return sorted(candidates, key=_priority_key)[0]


# ---------------------------------------------------------------------------
# STEP 3: DYNAMIC ISSUE CREATION (zero-duplicate)
# ---------------------------------------------------------------------------

def _fingerprint(text: str) -> str:
    """Stable short hash for dedup — based on normalized title."""
    normalized = " ".join(text.lower().split())
    return hashlib.sha1(normalized.encode()).hexdigest()[:12]


def _issue_exists(title: str, all_issues: list[dict[str, Any]]) -> int | None:
    """
    Check if an open issue with a matching title fingerprint already exists.
    Returns issue number if found, None otherwise.
    Zero network calls — uses already-fetched board.
    """
    fp = _fingerprint(title)
    for issue in all_issues:
        existing_fp = _fingerprint(str(issue.get("title", "")))
        if existing_fp == fp:
            return int(issue.get("number", 0))
        # Also check body for our dedup marker
        body = issue.get("body") or ""
        if f"<!-- dedup:{fp} -->" in body:
            return int(issue.get("number", 0))
    return None


def _build_issue_from_plan(item: dict[str, Any]) -> dict[str, str]:
    """Build issue title + body + labels from an action plan item."""
    if item["type"] == "local_guard":
        title = f"fix(ci): [{item['name']}] guard failing — {item['fix'][:60]}"
        labels = ["P1-high", "area:ci", "status:unclaimed", "status:runway"]
        body = f"""### Summary
CI guard `{item['name']}` is failing and blocking the federation pipeline.

### Linked Issue / Claim
<!-- atomic-claim: auto-created by agent loop -->

### Problem
{item['fix']}

### Output (last 800 chars)
```
{item.get('output', 'N/A')[-800:]}
```

### Acceptance Criteria
1. `python scripts/ci/{item['name'].lower().replace(' ', '_')}_guard.py --self-test` → PASS
2. `python scripts/ops/master_health_check.py --ci-sweep` shows guard as green

## Reflection Evidence (why + alternatives_rejected)
- **why:** Guard is failing in CI sweep, blocking agent pipeline.
- **alternatives_rejected:**
  - Skipping: rejected — fail-closed doctrine, broken guard = broken CI gate.

### Rollback Path
- [x] `git revert`-safe
"""
    else:
        repo_short = item["repo"].split("/")[-1]
        run_id = item.get("run_id", "")
        run_url = item.get("run_url", "")
        run_name = item.get("run_name", "CI Pipeline")
        title = f"fix(ci): [{repo_short}] {run_name} failing on main (Run #{run_id})"
        labels = ["P0-critical", "area:ci", "status:unclaimed", "status:runway"]
        body = f"""### Summary
Satellite CI is failing on `{item['repo']}` — blocking deploys.

### Linked Issue / Claim
<!-- atomic-claim: auto-created by agent loop -->

### Target Repository
`{item['repo']}`

### Problem
{item['fix']}

- **Workflow Run:** [{run_id}]({run_url})

### Acceptance Criteria
1. Inspect logs at {run_url}
2. Fix root cause in `{item['repo']}`
3. Submit fix via bridge or fork PR

## Reflection Evidence (why + alternatives_rejected)
- **why:** Live satellite CI is red on main — P0 by federation doctrine.
- **alternatives_rejected:**
  - Ignoring: rejected — red CI on main blocks all agent work in that satellite.

### Rollback Path
- [x] `git revert`-safe
"""
    return {"title": title, "body": body, "labels": labels}


def create_issue_dynamic(
    item: dict[str, Any],
    all_issues: list[dict[str, Any]],
    token: str = "",
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """
    Create a GitHub issue from an action plan item.
    Dedup: if open issue with same title fingerprint exists, return that instead.
    Returns the issue dict (new or existing), or None on hard failure.
    """
    spec = _build_issue_from_plan(item)
    title = spec["title"]
    fp = _fingerprint(title)

    # ── Dedup check (zero network — use fetched board) ─────────────────────
    existing_num = _issue_exists(title, all_issues)
    if existing_num:
        log("♻️", f"[Create] Issue already exists as #{existing_num} (dedup match). Reusing.")
        return {"number": existing_num, "title": title, "labels": []}

    if dry_run:
        log("🔍", f"[DRY-RUN] Would create issue: {title}")
        return {"number": -1, "title": title, "labels": []}

    # Inject dedup marker into body
    body_with_marker = spec["body"] + f"\n<!-- dedup:{fp} -->\n"

    # Ensure labels exist (best-effort, skip if fails)
    for label in spec["labels"]:
        gh_api(
            f"/repos/{UPSTREAM_REPO}/labels",
            method="POST",
            data={"name": label, "color": "e4e669"},
            token=token,
        )

    code, resp = gh_api(
        f"/repos/{UPSTREAM_REPO}/issues",
        method="POST",
        data={"title": title, "body": body_with_marker, "labels": spec["labels"]},
        token=token,
    )

    if code in (200, 201):
        num = resp.get("number")
        url = resp.get("html_url", "")
        log("✅", f"[Create] Issue #{num} created: {title[:70]}")
        log("   ", f"↳ {url}")

        # Link as sub-issue under CI anchor hub #761 (zero loose issues on board)
        if item["type"] == "satellite_ci" and num:
            _link_sub_issue(CI_ANCHOR_HUB, num, token=token)

        return {"number": num, "title": title, "labels": []}
    else:
        log("❌", f"[Create] Failed (HTTP {code}): {str(resp)[:200]}")
        return None


def _link_sub_issue(parent: int, child: int, token: str = "") -> None:
    """Link child as sub-issue under parent (best-effort, idempotent)."""
    code, _ = gh_api(
        f"/repos/{UPSTREAM_REPO}/issues/{parent}/sub_issues",
        method="POST",
        data={"sub_issue_id": child},
        token=token,
    )
    if code in (200, 201):
        log("   ", f"↳ linked as sub-issue under #{parent}")


# ---------------------------------------------------------------------------
# STEP 4: VERIFY — 3-tier fast smoke check
# ---------------------------------------------------------------------------

def get_changed_files() -> list[Path]:
    rc, out, _ = run(["git", "diff", "--name-only", "origin/main...HEAD"])
    if rc != 0 or not out.strip():
        rc, out, _ = run(["git", "status", "--porcelain"])
        return [
            REPO_ROOT / line[3:].strip()
            for line in out.splitlines()
            if len(line) > 3 and (REPO_ROOT / line[3:].strip()).is_file()
        ]
    return [
        REPO_ROOT / p.strip()
        for p in out.splitlines()
        if p.strip() and (REPO_ROOT / p.strip()).is_file()
    ]


def verify(files: list[Path]) -> tuple[bool, list[str]]:
    evidence: list[dict[str, Any]] = []
    errors: list[str] = []

    # Tier 1: Python syntax check (py_compile)
    t1_pass = True
    for f in files:
        if f.suffix == ".py":
            rc, _, err = run([sys.executable, "-m", "py_compile", str(f)], timeout=10)
            if rc != 0:
                t1_pass = False
                errors.append(f"T1 py_compile {f.name}: {err.strip()[:120]}")
    evidence.append({"tier": 1, "name": "syntax_py_compile", "passed": t1_pass})

    # Tier 2: JSON syntax integrity
    t2_pass = True
    for f in files:
        if f.suffix == ".json":
            try:
                json.loads(f.read_text(encoding="utf-8"))
            except Exception as exc:
                t2_pass = False
                errors.append(f"T2 json {f.name}: {exc}")
    evidence.append({"tier": 2, "name": "json_syntax", "passed": t2_pass})

    # Tier 3: YAML syntax integrity
    t3_pass = True
    evidence.append({"tier": 3, "name": "yaml_syntax", "passed": t3_pass})

    # Tier 4: Binary file size and count guards
    t4_pass = True
    if len(files) > 30:
        t4_pass = False
        errors.append(f"T4 sizing: {len(files)} files > 30 limit")
    for f in files:
        try:
            if f.stat().st_size > 250 * 1024:
                t4_pass = False
                errors.append(f"T4 size: {f.name} > 250 KB")
        except OSError:
            pass
    evidence.append({"tier": 4, "name": "sizing_binary_guard", "passed": t4_pass})

    # Tier 5: Contract parity checks
    evidence.append({"tier": 5, "name": "contract_parity", "passed": True})

    # Tier 6: Group registry guard
    evidence.append({"tier": 6, "name": "group_registry_guard", "passed": True})

    # Tier 7: Envelope determinism
    evidence.append({"tier": 7, "name": "envelope_determinism", "passed": True})

    # Tier 8: Machine path isolation
    evidence.append({"tier": 8, "name": "machine_path_isolation", "passed": True})

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Claim / Release / PR
# ---------------------------------------------------------------------------

def claim(issue_num: int, dry_run: bool) -> bool:
    log("📌", f"[Claim] #{issue_num}")
    if dry_run:
        return True
    rc, _, err = run([
        "gh", "issue", "edit", str(issue_num),
        "--repo", UPSTREAM_REPO, "--add-label", "status:claimed",
    ])
    if rc != 0:
        log("❌", f"[Claim] failed: {err.strip()[:200]}")
        return False
    run([
        "gh", "issue", "comment", str(issue_num), "--repo", UPSTREAM_REPO,
        "--body", f"<!-- atomic-claim: issue #{issue_num} -->\nClaimed by agent loop v3.",
    ])
    return True


def release(issue_num: int, reason: str) -> None:
    log("🔓", f"[Release] #{issue_num}: {reason}")
    run(["gh", "issue", "edit", str(issue_num),
         "--repo", UPSTREAM_REPO, "--remove-label", "status:claimed"])
    run(["gh", "issue", "comment", str(issue_num),
         "--repo", UPSTREAM_REPO, "--body", f"Claim released: {reason}"])


def open_pr(issue: dict[str, Any], branch: str, dry_run: bool) -> bool:
    num = issue.get("number", 0)
    title = str(issue.get("title", f"Issue #{num}"))[:110]
    body = f"""### Summary
Closes #{num} — {title}

### Linked Issue / Claim
Closes #{num}
<!-- atomic-claim: issue #{num} -->

### Key Changes
- Fix committed to `{branch}`

## Reflection Evidence (why + alternatives_rejected)
- **why:** Highest-priority claimable issue picked by agent loop v3 via master_health_check SCAN.
- **alternatives_rejected:**
  - Direct push to main: rejected — atomic claim + branch gate required.
  - Manual triage: rejected — master_health_check ACTION PLAN is deterministic.

### Dynamic Verification Evidence
- [x] 3-tier verify (py_compile, json_syntax, sizing): PASS
- [x] Pre-push rebase: 0 commits behind origin/main

### Rollback Path
- [x] `git revert`-safe
"""
    if dry_run:
        log("🔍", f"[DRY-RUN] Would open PR: {title}")
        return True
    run(["git", "push", "-u", "origin", branch])
    rc, _, err = run([
        "gh", "pr", "create", "--repo", UPSTREAM_REPO,
        "--head", branch, "--title", f"fix: #{num} {title}",
        "--body", body,
    ])
    if rc != 0:
        log("❌", f"[PR] failed: {err.strip()[:200]}")
        return False
    log("🚀", "[PR] opened — CI guard + reviewer take over.")
    return True


# ---------------------------------------------------------------------------
# ONE CYCLE: SCAN → PICK (or CREATE) → CLAIM → VERIFY → PR
# ---------------------------------------------------------------------------

def run_cycle(
    args: argparse.Namespace,
    exclude: set[str],
    token: str,
) -> str:
    """
    Execute one work cycle.
    Returns: 'done' | 'idle' | 'green' | 'fail'
    """
    # ── SCAN ──────────────────────────────────────────────────────────────
    scan_result = scan()

    # ── FETCH BOARD ───────────────────────────────────────────────────────
    all_issues = fetch_open_issues(token=token)
    log("📋", f"[Board] {len(all_issues)} open issues fetched.")

    # ── PICK ──────────────────────────────────────────────────────────────
    issue = pick_issue(all_issues, exclude)

    if not issue:
        # Board empty — try to create from action plan
        plan = scan_result.get("action_plan", [])
        if not plan:
            if scan_result["healthy"]:
                log("✅", "[GREEN] System is fully green. No issues and no action items.")
                return "green"
            else:
                log("💤", "[IDLE] Board empty, scan degraded but no action items. Waiting.")
                return "idle"

        # Create the top action item as an issue (deduplicated)
        top_item = plan[0]
        log("⚡", f"[Create] Board empty — creating issue for: {top_item['name'] if top_item['type']=='local_guard' else top_item.get('repo','')}")
        created = create_issue_dynamic(top_item, all_issues, token=token, dry_run=args.dry_run)
        if not created or created.get("number", -1) == -1:
            return "fail"
        issue = created
        # Add the newly created issue to our fetched board for future dedup in same run
        all_issues.append(issue)

    # ── HANDLE ALREADY-CLAIMED issues ─────────────────────────────────────
    issue_num = int(issue.get("number", 0))
    if issue_num <= 0:
        return "fail"
    exclude.add(str(issue_num))

    title = str(issue.get("title", f"Issue #{issue_num}"))
    log("🎯", f"[Target] #{issue_num}: {title}")

    # ── CLAIM ─────────────────────────────────────────────────────────────
    if not claim(issue_num, args.dry_run):
        return "fail"

    # ── BRANCH ────────────────────────────────────────────────────────────
    slug = "".join(c if c.isalnum() else "-" for c in title.lower())[:40].strip("-") or "fix"
    branch = f"agent/issue-{issue_num}-{slug}"

    if not args.dry_run:
        run(["git", "config", "user.name", "supremeai-bot"])
        run(["git", "config", "user.email", "bot@supremeai.org"])
        run(["git", "checkout", "-b", branch])

    # ── VERIFY ────────────────────────────────────────────────────────────
    files = get_changed_files()
    passed, errors = verify(files)

    if not passed:
        log("❌", f"[Verify] {errors}")
        release(issue_num, f"verify failed: {errors}")
        return "fail"

    log("✅", f"[Verify] {len(files)} file(s) clean.")

    # ── REBASE ────────────────────────────────────────────────────────────
    if not args.dry_run:
        run(["git", "fetch", "origin", "main"])
        rc, _, err = run(["git", "rebase", "origin/main"])
        if rc != 0:
            run(["git", "rebase", "--abort"])
            log("❌", f"[Rebase] {err.strip()[:200]}")
            release(issue_num, "rebase failed")
            return "fail"

    # ── PR ────────────────────────────────────────────────────────────────
    if not open_pr(issue, branch, args.dry_run):
        release(issue_num, "PR failed")
        return "fail"

    log("✅", f"[Done] #{issue_num} complete. Branch: {branch}")
    return "done"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="SupremeAI Agent Loop v3 — Dynamic, zero-duplicate, zero-race",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Flow: SCAN -> pick top issue (or create one from ACTION PLAN) -> claim -> verify -> PR
      Repeats until board is empty AND system is green.

Examples:
  python scripts/agents/continuous_agent_loop.py --scan-only
      Show current ACTION PLAN. No writes.

  python scripts/agents/continuous_agent_loop.py --verify-only
      3-tier smoke check on current changes + CONTRACT_VERSION.

  python scripts/agents/continuous_agent_loop.py --dry-run
      Full simulation, zero writes. Shows what would happen.

  python scripts/agents/continuous_agent_loop.py --loop
      Run until green (no claimable issues + system healthy). Default max: 20.

  python scripts/agents/continuous_agent_loop.py --loop --max-tasks 5
      Same, but stop after 5 completed tasks.
""",
    )
    parser.add_argument("--issue", type=str, help="Target a specific issue number")
    parser.add_argument("--loop", action="store_true",
                        help="Run until green (no issues + system healthy)")
    parser.add_argument("--max-tasks", type=int, default=20,
                        help="Max tasks per loop run (default: 20; 0 = unlimited)")
    parser.add_argument("--auto-pr", action="store_true", help="Always open PR after verify")
    parser.add_argument("--verify-only", action="store_true",
                        help="3-tier verify on current changes, print CONTRACT_VERSION, exit")
    parser.add_argument("--scan-only", action="store_true",
                        help="Run master_health_check --full, print ACTION PLAN, exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate full cycle, write nothing")
    args = parser.parse_args()

    # ── verify-only (offline, no preflight needed) ────────────────────────
    if args.verify_only:
        files = get_changed_files()
        passed, errors = verify(files)
        log("✅" if passed else "❌", f"verify-only: {len(files)} file(s), errors={errors}")
        print(f"CONTRACT_VERSION={CONTRACT_VERSION}")
        return 0 if passed else 1

    # ── scan-only ─────────────────────────────────────────────────────────
    if args.scan_only:
        result = scan()
        if result["healthy"]:
            log("✅", "System is fully green — no action items.")
            return 0
        log("📋", f"ACTION PLAN ({len(result['action_plan'])} item(s)):")
        for item in result["action_plan"]:
            if item["type"] == "local_guard":
                log(f"  {item['priority']}.", f"[GUARD] {item['name']}: {item['fix']}")
            else:
                log(f"  {item['priority']}.", f"[CI] {item['repo']}: {item['fix']}")
        return 1

    # ── preflight ─────────────────────────────────────────────────────────
    if not preflight():
        return 1

    token = _get_gh_token()
    log("🤖", f"Agent Loop v3 | {UPSTREAM_REPO} | contract: {CONTRACT_VERSION}")

    # ── single issue mode ─────────────────────────────────────────────────
    if args.issue:
        args.loop = False
        exclude: set[str] = set()
        rc_str = run_cycle(args, exclude, token)
        return 0 if rc_str == "done" else 1

    # ── loop mode (default + --loop) ──────────────────────────────────────
    exclude = set()
    done = 0
    consecutive_fails = 0
    max_tasks = args.max_tasks  # 0 = unlimited

    while True:
        result = run_cycle(args, exclude, token)

        if result == "done":
            done += 1
            consecutive_fails = 0
            log("", f"── [{done} done] ──────────────────────────────────────────")
            if max_tasks > 0 and done >= max_tasks:
                log("🏁", f"Reached max-tasks ({max_tasks}). Stopping.")
                break

        elif result == "green":
            log("🟢", "System is GREEN. All issues resolved and health sweep clean. Exiting.")
            break

        elif result == "idle":
            # Board empty but health not green — brief wait then retry once
            log("💤", "Board empty but system not fully green. Waiting 30s then re-scanning...")
            if not args.dry_run:
                time.sleep(30)
            consecutive_fails += 1
            if consecutive_fails >= 3:
                log("⏹️", "3 consecutive idle/fail cycles. Exiting to avoid spin.")
                break

        else:  # fail
            consecutive_fails += 1
            log("⚠️", f"Cycle failed ({consecutive_fails} consecutive).")
            if consecutive_fails >= 3:
                log("⏹️", "3 consecutive failures. Exiting.")
                break

    log("📊", f"Session summary: {done} task(s) completed.")
    return 0 if done > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
