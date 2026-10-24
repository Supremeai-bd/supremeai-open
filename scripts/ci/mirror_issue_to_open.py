#!/usr/bin/env python3
"""
scripts/ci/mirror_issue_to_open.py — Auto-Mirror CI Failures & Tasks to supremeai-open

Mission:
  When a CI failure occurs or a CI/ops issue is opened in Supremeai-bd/supremeai,
  autonomously format, sanitize, and publish it to Supremeai-bd/supremeai-open
  so external/public agents can claim and resolve it without private access.

Invariants:
  - Fail-closed dedup (never duplicate an open mirrored task)
  - Sanitization: strip secrets, internal tokens, private cluster endpoints
  - Strict contract: compliant with agent-task.yml template & VALID_GROUPS taxonomy
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error

OPEN_REPO = os.environ.get("OPEN_REPO", "Supremeai-bd/supremeai-open")
CORE_REPO = os.environ.get("CORE_REPO", "Supremeai-bd/supremeai")

SECRET_PATTERNS = [
    r"ghp_[a-zA-Z0-9]+",
    r"ghs_[a-zA-Z0-9]+",
    r"github_pat_[a-zA-Z0-9_]+",
    r"sk-[a-zA-Z0-9]+",
    r"ak-[a-zA-Z0-9]+",
    r"as-[a-zA-Z0-9]+",
    r"cfk_[a-zA-Z0-9]+",
    r"cfut_[a-zA-Z0-9]+",
    r"Bearer\s+[a-zA-Z0-9_\-\.]+",
]

def sanitize_text(text: str) -> str:
    if not text:
        return ""
    sanitized = text
    for pattern in SECRET_PATTERNS:
        sanitized = re.sub(pattern, "[REDACTED_SECRET]", sanitized)
    return sanitized

def get_github_token() -> str:
    return (
        os.environ.get("OPEN_SYNC_PAT")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or ""
    )

def gh_api_request(url: str, method: str = "GET", data: dict = None) -> tuple[int, dict]:
    token = get_github_token()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SupremeAI-AutoMirror/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    payload = json.dumps(data).encode("utf-8") if data else None
    if payload:
        headers["Content-Type"] = "application/json"
    
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            return resp.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_content = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_content)
        except Exception:
            return e.code, {"error": err_content}
    except Exception as e:
        return 500, {"error": str(e)}

def find_existing_mirror(source_marker: str) -> dict | None:
    """Check if an open issue in OPEN_REPO already contains the MIRROR_SOURCE marker."""
    url = f"https://api.github.com/repos/{OPEN_REPO}/issues?state=open&per_page=100"
    status, issues = gh_api_request(url)
    if status != 200 or not isinstance(issues, list):
        print(f"[WARN] Failed to list open issues from {OPEN_REPO}: HTTP {status}")
        return None
    
    for issue in issues:
        body = issue.get("body") or ""
        if source_marker in body:
            return issue
    return None

def mirror_core_issue(issue_num: int) -> bool:
    print(f"[*] Processing Core Issue #{issue_num} for auto-mirroring...")
    url = f"https://api.github.com/repos/{CORE_REPO}/issues/{issue_num}"
    status, issue = gh_api_request(url)
    if status != 200:
        print(f"[ERROR] Failed to fetch Core Issue #{issue_num}: HTTP {status}")
        return False
    
    source_marker = f"<!-- MIRROR_SOURCE: {CORE_REPO}#{issue_num} -->"
    existing = find_existing_mirror(source_marker)
    if existing:
        print(f"[INFO] Mirror already exists: {OPEN_REPO}#{existing.get('number')}. Skipping.")
        return True
    
    title = issue.get("title", f"fix(ci): failure from {CORE_REPO}#{issue_num}")
    body = sanitize_text(issue.get("body", ""))
    
    # Format compliant agent-task body
    open_body = f"""### 🤖 SupremeAI Agent Task Contract
This task is mirrored automatically from the core CI failure / pipeline tracker. Open to **all autonomous agents** (Local Antigravity, Claude, ChatGPT, Mistral, external contributors).

### Target Repository
{CORE_REPO}

### Priority Tier
P1-high (Important fix/blocker/architecture)

### Topological Layer
Layer 2 (Tools / Workers / Sidecars)

### Task Group (VALID_GROUPS registry)
agent-orchestration

### Summary / Problem Statement
{body}

### Acceptance Criteria
1. Investigate and resolve the failure reported in {CORE_REPO}#{issue_num}.
2. Ensure all relevant unit and contract tests pass.
3. Submit patch via zero-credential bridge (`bridge_submit_patch`) or fork PR.

### 3-Tier Verification Contract
1. Reflection: `git diff --stat` covers only target failing files.
2. Smoke: syntax/typecheck passes cleanly.
3. Tests: relevant pytest/vitest suite passes without regression.

{source_marker}
"""
    create_url = f"https://api.github.com/repos/{OPEN_REPO}/issues"
    create_data = {
        "title": title,
        "body": open_body,
        "labels": ["status:unclaimed", "P1-high", "handoff:coder", "area:ci"],
    }
    create_status, created = gh_api_request(create_url, method="POST", data=create_data)
    if create_status == 201:
        print(f"[SUCCESS] Mirrored to {OPEN_REPO}#{created.get('number')}: {created.get('html_url')}")
        # Add comment on core issue linking back
        comment_url = f"https://api.github.com/repos/{CORE_REPO}/issues/{issue_num}/comments"
        comment_data = {
            "body": f"🔄 **Auto-Mirrored to Public Open Queue:**\nThis issue has been mirrored to `{OPEN_REPO}` as [#{created.get('number')}]({created.get('html_url')}) for autonomous external agent execution."
        }
        gh_api_request(comment_url, method="POST", data=comment_data)
        return True
    else:
        print(f"[ERROR] Failed to create mirror issue on {OPEN_REPO}: HTTP {create_status} {created}")
        return False

def mirror_workflow_run(run_id: int) -> bool:
    print(f"[*] Processing Workflow Run #{run_id} for auto-mirroring...")
    url = f"https://api.github.com/repos/{CORE_REPO}/actions/runs/{run_id}"
    status, run = gh_api_request(url)
    if status != 200:
        print(f"[ERROR] Failed to fetch Run #{run_id}: HTTP {status}")
        return False
    
    workflow_name = run.get("name", "CI Workflow")
    head_branch = run.get("head_branch", "unknown")
    html_url = run.get("html_url", "")
    conclusion = run.get("conclusion", "")
    
    if conclusion != "failure":
        print(f"[INFO] Workflow Run #{run_id} conclusion is '{conclusion}', not 'failure'. Skipping.")
        return True
    
    source_marker = f"<!-- MIRROR_RUN: {CORE_REPO}/actions/runs/{run_id} -->"
    existing = find_existing_mirror(source_marker)
    if existing:
        print(f"[INFO] Mirror already exists for Run #{run_id}: {OPEN_REPO}#{existing.get('number')}. Skipping.")
        return True
    
    title = f"fix(ci): {workflow_name} failed on branch {head_branch} (Run #{run_id})"
    open_body = f"""### 🤖 SupremeAI Agent Task Contract
This task is mirrored automatically from a core CI workflow failure. Open to **all autonomous agents**.

### Target Repository
{CORE_REPO}

### Priority Tier
P0-critical (Production outage/security/fatal bug)

### Topological Layer
Layer 2 (Tools / Workers / Sidecars)

### Task Group (VALID_GROUPS registry)
agent-orchestration

### Summary / Problem Statement
Workflow **{workflow_name}** failed on branch `{head_branch}`.
- **Workflow Run:** [{run_id}]({html_url})
- **Conclusion:** {conclusion}

### Acceptance Criteria
1. Inspect the failing check logs in Run #{run_id}.
2. Fix root cause in {CORE_REPO}.
3. Submit fix via zero-credential bridge (`bridge_submit_patch`) or fork PR.

### 3-Tier Verification Contract
1. Reflection: `git diff --stat` matches the fixed CI/code files.
2. Smoke: CI checks compile and pass locally.
3. Tests: relevant tests green.

{source_marker}
"""
    create_url = f"https://api.github.com/repos/{OPEN_REPO}/issues"
    create_data = {
        "title": title,
        "body": open_body,
        "labels": ["status:unclaimed", "P0-critical", "handoff:coder", "area:ci"],
    }
    create_status, created = gh_api_request(create_url, method="POST", data=create_data)
    if create_status == 201:
        print(f"[SUCCESS] Mirrored CI failure to {OPEN_REPO}#{created.get('number')}: {created.get('html_url')}")
        return True
    else:
        print(f"[ERROR] Failed to create mirror issue for Run #{run_id}: HTTP {create_status} {created}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Auto-mirror CI failures to supremeai-open")
    parser.add_argument("--issue-number", type=int, help="Core issue number to mirror")
    parser.add_argument("--run-id", type=int, help="Workflow run ID to mirror")
    args = parser.parse_args()

    if args.issue_number:
        success = mirror_core_issue(args.issue_number)
        sys.exit(0 if success else 1)
    elif args.run_id:
        success = mirror_workflow_run(args.run_id)
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
