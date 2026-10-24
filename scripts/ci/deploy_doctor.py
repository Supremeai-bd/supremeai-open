#!/usr/bin/env python3
"""
Deploy Doctor — Autonomous Render Deployment Failure Detective
==============================================================
Render-এর সব service-এর recent deploys poll করে, failed deploy খুঁজে বের করে,
root cause analyze করে, এবং স্বয়ংক্রিয়ভাবে GitHub issue খুলে ফিক্স টিমের দৃষ্টি আনে।

মূল কাজ:
  1. Render API → GET /v1/services/{id}/deploys (last 10)
  2. শুধু failed deploys filter করে (last 15 min window — যাতে একই failure বারবার issue না খোলে)
  3. deploy log fetch করে error খুঁজে বের করে
  4. failure classify করে: build_error | runtime_error | config_error | quota_exceeded | unknown
  5. যদি একই SHA-তে ইতিমধ্যে issue খোলা না থাকে → নতুন issue খোলে "deploy-doctor" label সহ
  6. যদি আগের issue আছে → শুধু comment করে (duplicate প্রতিরোধ)

Run:
  python scripts/ci/deploy_doctor.py            # check সব 4 service
  python scripts/ci/deploy_doctor.py --dry-run  # শুধু দেখাবে, issue খুলবে না

GitHub Actions env:
  GITHUB_TOKEN, GH_REPO (gh CLI-র জন্য)
  RENDER_API_KEY, RENDER_API_KEY_1..4 (Render API কলের জন্য)
  RENDER_PRIMARY_SVC_ID, RENDER_WORKER_SVC_ID, RENDER_SCRAPER_SVC_ID, RENDER_MCP_SVC_ID
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# Service registry — Render-এ আমাদের 4টি production service
# (#1852 P1: hardcoded service IDs removed — secrets-only with skip-if-missing;
#  set RENDER_*_SVC_ID secrets or the service is skipped with a warning)
# ──────────────────────────────────────────────────────────────────────────
SERVICES = [
    {
        "role": "Core",
        "name": "supremeai-primary-node",
        "key_env": "RENDER_API_KEY_1",
        "fallback_key_env": "RENDER_API_KEY",
        "svc_env": "RENDER_PRIMARY_SVC_ID",
        "url": "https://supremeai-primary-node.onrender.com",
    },
    {
        "role": "Worker",
        "name": "supremeai-worker-node",
        "key_env": "RENDER_API_KEY_2",
        "fallback_key_env": None,
        "svc_env": "RENDER_WORKER_SVC_ID",
        "url": "https://supremeai-worker-node.onrender.com",
    },
    {
        "role": "Scraper",
        "name": "supremeai-scraper-node",
        "key_env": "RENDER_API_KEY_3",
        "fallback_key_env": None,
        "svc_env": "RENDER_SCRAPER_SVC_ID",
        "url": "https://supremeai-scraper-node.onrender.com",
    },
    {
        "role": "MCP",
        "name": "supremeai-mcp-tower",
        "key_env": "RENDER_API_KEY_4",
        "fallback_key_env": None,
        "svc_env": "RENDER_MCP_SVC_ID",
        "url": "https://supremeai-mcp-tower.onrender.com",
    },
]

FAILURE_WINDOW_MINUTES = 15  # শুধু গত 15 মিনিটের failed deploys দেখবে (cron 5min-এর জন্য safe)
RENDER_API_BASE = "https://api.render.com/v1"


def get_env(name: str | None) -> str:
    if not name:
        return ""
    return os.environ.get(name, "").strip()


def resolve_service_creds(svc: dict[str, Any]) -> tuple[str, str]:
    """Resolve API key + service ID with proper fallback chain."""
    api_key = get_env(svc["key_env"]) or get_env(svc.get("fallback_key_env"))
    service_id = get_env(svc["svc_env"])
    return api_key, service_id


def render_api_get(path: str, api_key: str, timeout: int = 15) -> tuple[int, Any]:
    """Call Render API GET endpoint. Returns (status_code, parsed_json_or_raw_text)."""
    url = f"{RENDER_API_BASE}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "deploy-doctor/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception as exc:
            # বডি পড়া না গেলেও status code দিয়েই ডাক্তার সিদ্ধান্ত নিতে পারে — তবে কারণটা stderr-এ থাকবে।
            print(f"  ⚠️ could not read Render HTTPError body: {exc}", file=sys.stderr)
        return e.code, body
    except (urllib.error.URLError, TimeoutError) as e:
        return 0, str(e)


def list_recent_deploys(api_key: str, service_id: str, limit: int = 10) -> list[dict]:
    """GET /v1/services/{id}/deploys — last N deploys (Render returns list of {deploy, commit})."""
    status, data = render_api_get(f"/services/{service_id}/deploys?limit={limit}", api_key)
    if status != 200:
        print(f"  ⚠️ Render API GET /deploys failed: HTTP {status} — {str(data)[:200]}")
        return []
    if isinstance(data, list):
        return data
    return []


def get_deploy_detail(api_key: str, service_id: str, deploy_id: str) -> dict:
    """GET /v1/services/{id}/deploys/{deployId} — full deploy record.
    Note: Render API returns deploy metadata here; logs are a SEPARATE endpoint."""
    status, data = render_api_get(f"/services/{service_id}/deploys/{deploy_id}", api_key, timeout=30)
    if status != 200:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def get_deploy_logs(api_key: str, service_id: str, deploy_id: str) -> str:
    """GET /v1/services/{id}/deploys/{deployId}/logs — raw deploy build/runtime log.
    Returns plain text (not JSON). Empty string on failure."""
    # Render API: GET /v1/services/{serviceId}/deploys/{deployId}/logs
    # Returns text/plain with the raw log output.
    url = f"{RENDER_API_BASE}/services/{service_id}/deploys/{deploy_id}/logs"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "text/plain, */*",
            "User-Agent": "deploy-doctor/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return body
    except urllib.error.HTTPError as e:
        # 404 common for deploys that never started building
        if e.code != 404:
            print(f"  ⚠️ logs fetch HTTP {e.code} for deploy {deploy_id}")
        return ""
    except (urllib.error.URLError, TimeoutError):
        return ""


# ──────────────────────────────────────────────────────────────────────────
# Failure classifier — error message → category + root cause hint
# ──────────────────────────────────────────────────────────────────────────
FAILURE_PATTERNS = [
    # Build-time errors (Docker/poetry/install phase)
    (r"ModuleNotFoundError:\s*No module named ['\"]?([\w.]+)", "build_error",
     "Missing Python module: {1}. Check pyproject.toml / poetry.lock pinning."),
    (r"ImportError:\s*cannot import name ['\"]?(\w+)", "build_error",
     "Import error: {1}. Symbol removed or renamed in source."),
    (r"SyntaxError:\s*(.+)", "build_error",
     "Python syntax error: {1}"),
    (r"poetry.*(?:failed|error)|Could not find a version|locked version constraint",
     "build_error", "Poetry dependency resolution failed. Check poetry.lock."),
    (r"docker build.*failed|COPY.*failed|No such file or directory",
     "build_error", "Dockerfile build step failed."),
    # Runtime errors (app started but crashed)
    (r"Traceback \(most recent call last\).*?(\w+Error):\s*(.+)",
     "runtime_error", "Runtime {1}: {2}"),
    (r"ConnectionRefusedError|connection refused|ECONNREFUSED",
     "runtime_error", "Service can't reach a dependency (DB/Redis/API)."),
    (r"OperationalError|database connection|could not connect to server",
     "config_error", "Database connection failed. Check DB env vars."),
    # Config / secret errors
    (r"KeyError:\s*['\"]?(\w+)['\"]?", "config_error",
     "Missing config key: {1}"),
    (r"ValidationError|pydantic.*error|field required",
     "config_error", "Pydantic validation failed — env var missing or invalid."),
    # Quota / rate limit
    (r"free.*plan.*limit|build.*minute.*exceeded|usage.*limit|quota",
     "quota_exceeded", "Render free-tier quota exceeded."),
    (r"api-deployments-free-per-day|rate.?limit",
     "quota_exceeded", "Provider daily rate-limit hit."),
]


def classify_failure(log_text: str) -> tuple[str, str, str | None]:
    """Returns (category, summary, root_cause_hint)."""
    if not log_text:
        return "unknown", "No deploy log available", None
    for pattern, category, hint_template in FAILURE_PATTERNS:
        m = re.search(pattern, log_text, re.IGNORECASE | re.DOTALL)
        if m:
            groups = [m.group(i) if m.group(i) else "" for i in range(m.lastindex + 1)]
            try:
                hint = hint_template.format(*groups) if "{" in hint_template else hint_template
            except (IndexError, KeyError):
                hint = hint_template
            summary = m.group(0)[:200]
            return category, summary, hint
    # Fallback — last 200 chars of log
    return "unknown", log_text[-200:] if len(log_text) > 200 else log_text, None


# ──────────────────────────────────────────────────────────────────────────
# GitHub issue operations (via gh CLI)
# ──────────────────────────────────────────────────────────────────────────
def gh_cli(args: list[str], input_text: str | None = None) -> tuple[int, str]:
    """Run gh CLI with args, return (exit_code, stdout)."""
    import subprocess
    cmd = ["gh"] + args
    try:
        r = subprocess.run(cmd, input=input_text, capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout + r.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return 1, str(e)


def find_existing_issue(commit_sha: str, service_name: str) -> int | None:
    """Search open issues with deploy-doctor label for this SHA+service.
    Uses gh issue list + local filter (more reliable than gh search issues)."""
    if not commit_sha:
        return None
    # Get all open deploy-doctor issues (limit 50 — enough for our case)
    code, out = gh_cli(["issue", "list", "--label", "deploy-doctor", "--state", "open",
                        "--json", "number,body", "--limit", "50"])
    if code != 0:
        return None
    try:
        issues = json.loads(out)
    except json.JSONDecodeError:
        return None
    # Look for this exact SHA + service in body
    for issue in issues:
        body = issue.get("body", "") or ""
        if commit_sha in body and service_name in body:
            return issue["number"]
    return None


def open_issue(service: dict, deploy: dict, commit_sha: str, category: str,
               summary: str, hint: str | None, log_url: str | None,
               log_snippet: str | None) -> int | None:
    """Open a GitHub issue for the failed deploy."""
    title = f"🔴 Deploy Doctor: {service['name']} ({service['role']}) deploy failed — {category}"
    body = f"""## 🔴 Render Deploy Failure Detected

**Service:** `{service['name']}` ({service['role']})
**Service URL:** {service['url']}
**Commit:** `{commit_sha[:8]}` (full: `{commit_sha}`)
**Detected at:** {datetime.now(timezone.utc).isoformat()}
**Failure category:** `{category}`

### Summary
```
{summary}
```

### Root Cause Hint
{hint or '_No pattern matched — manual log review needed._'}

### Deploy Metadata
- Deploy ID: `{deploy.get('id', 'unknown')}`
- Status: `{deploy.get('status', 'unknown')}`
- Created at: `{deploy.get('createdAt', 'unknown')}`
- Finished at: `{deploy.get('finishedAt', 'unknown')}`
- Render Dashboard: {log_url or '_not provided_'}

### Log Snippet (last 800 chars)
```
{(log_snippet or 'No log available')[-800:]}
```

### What Deploy Doctor thinks
{_doctor_advice(category)}

### Action Required
- [ ] Review the deploy log (link above)
- [ ] Identify if this is a code regression or env/config issue
- [ ] If code: open a fix PR (PR Helper will auto-merge if pure-improvement)
- [ ] If env: update Render dashboard env vars

### Tracking
- Commit SHA: `{commit_sha}`
- Service: `{service['name']}`
- Label: `deploy-doctor`
"""
    code, out = gh_cli(["issue", "create", "--title", title, "--body", body,
                        "--label", "deploy-doctor"])
    if code == 0:
        # gh issue create returns URL like https://github.com/owner/repo/issues/123
        m = re.search(r"/issues/(\d+)", out)
        if m:
            return int(m.group(1))
    print(f"  ⚠️ gh issue create failed (code={code}): {out[:200]}")
    return None


def comment_on_issue(issue_number: int, deploy: dict, commit_sha: str,
                     category: str, summary: str) -> bool:
    """Add a comment to an existing issue (for repeat failures)."""
    body = f"""### 🔄 Repeat failure detected

**Commit:** `{commit_sha[:8]}`
**Deploy ID:** `{deploy.get('id', 'unknown')}`
**Time:** {datetime.now(timezone.utc).isoformat()}
**Category:** `{category}`

```
{summary}
```

_(Deploy Doctor is tracking this — no new issue opened to avoid duplicates.)_
"""
    code, out = gh_cli(["issue", "comment", str(issue_number), "--body", body])
    return code == 0


def _doctor_advice(category: str) -> str:
    """Human-readable advice per category."""
    advice = {
        "build_error": "এটি একটি **build-time error** — commit-এ কোনো dependency/import ভেঙে গেছে। PR খুলে ফিক্স করুন।",
        "runtime_error": "এটি একটি **runtime error** — অ্যাপ শুরু হয়েছিল কিন্তু ক্র্যাশ করেছে। লগ দেখে specific error খুঁজুন।",
        "config_error": "এটি একটি **config/secret error** — Render dashboard-এ env var মিসিং বা ভুল। Render থেকেই ঠিক করা যায়, কোড PR লাগবে না।",
        "quota_exceeded": "এটি একটি **quota/rate-limit** — Render free-tier শেষ। মাস রিসেট হলে ঠিক হবে, অথবা Pro-তে আপগ্রেড করুন।",
        "unknown": "ক্যাটাগরি নির্ধারণ করা যায়নি — সম্পূর্ণ deploy log ম্যানুয়ালি পর্যালোচনা করুন।",
    }
    return advice.get(category, advice["unknown"])


# ──────────────────────────────────────────────────────────────────────────
# Main — poll all services, find failures, open/comment issues
# ──────────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy Doctor — autonomous Render deploy failure detective")
    parser.add_argument("--dry-run", action="store_true", help="শুধু দেখাবে, issue খুলবে না")
    parser.add_argument("--window-minutes", type=int, default=FAILURE_WINDOW_MINUTES,
                        help=f"গত N মিনিটের failed deploys দেখবে (default: {FAILURE_WINDOW_MINUTES})")
    args = parser.parse_args()

    # Validate gh CLI is available (required for issue ops)
    gh_available = os.system("gh --version > /dev/null 2>&1") == 0
    if not gh_available and not args.dry_run:
        print("❌ gh CLI not found — cannot open issues. Install gh or run with --dry-run.")
        return 2

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=args.window_minutes)
    print(f"🔍 Deploy Doctor — scanning {len(SERVICES)} Render services")
    print(f"   Window: {args.window_minutes} min (since {window_start.isoformat()})")
    print(f"   Dry-run: {args.dry_run}")
    print()

    total_failures = 0
    issues_opened = 0
    issues_commented = 0

    for svc in SERVICES:
        api_key, service_id = resolve_service_creds(svc)
        if not api_key:
            print(f"⏭️  {svc['name']}: no API key found (env {svc['key_env']}/{svc.get('fallback_key_env')}) — skipping")
            continue
        if not service_id:
            print(f"⏭️  {svc['name']}: {svc['svc_env']} secret not set (#1852 P1: IDs are secrets-only now) — skipping")
            continue

        print(f"🔎 {svc['name']} ({svc['role']}) — service_id={service_id[:16]}...")
        deploys = list_recent_deploys(api_key, service_id, limit=10)
        if not deploys:
            print(f"   no deploys returned (or API error)")
            continue

        # Filter: failed deploys within window
        recent_failures = []
        for item in deploys:
            deploy = item.get("deploy", item) if isinstance(item, dict) else {}
            status = deploy.get("status", "").lower()
            created_at_str = deploy.get("createdAt") or deploy.get("created_at") or ""
            try:
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            # Render-এর failure status variants: failed, build_failed, update_failed, deploy_failed, error, canceled
            is_failure = (
                status in ("failed", "error", "canceled") or
                status.endswith("_failed") or
                status.endswith("_error")
            )
            if is_failure and created_at >= window_start:
                # Get commit SHA from deploy record
                commit_sha = ""
                commit = deploy.get("commit") or {}
                if isinstance(commit, dict):
                    commit_sha = commit.get("sha") or commit.get("id") or ""
                if not commit_sha:
                    commit_sha = deploy.get("commitSha") or ""
                recent_failures.append((deploy, commit_sha, created_at))

        if not recent_failures:
            # Check latest deploy status for visibility
            latest = deploys[0].get("deploy", deploys[0]) if deploys else {}
            latest_status = latest.get("status", "unknown")
            print(f"   ✅ no failures in last {args.window_minutes} min (latest: {latest_status})")
            continue

        total_failures += len(recent_failures)
        for deploy, commit_sha, created_at in recent_failures:
            deploy_id = deploy.get("id", "unknown")
            print(f"   ❌ failed deploy {deploy_id} (sha {commit_sha[:8]}, {created_at.isoformat()})")

            # Fetch deploy logs via the SEPARATE /logs endpoint
            # (Render API: /deploys/{id} returns metadata, /deploys/{id}/logs returns text)
            log_text = get_deploy_logs(api_key, service_id, deploy_id)
            detail = get_deploy_detail(api_key, service_id, deploy_id)
            if not log_text and detail:
                # Fallback: check metadata for any embedded log fields
                log_text = (detail.get("logs") or detail.get("log")
                            or detail.get("output") or "")
                if isinstance(log_text, dict):
                    log_text = json.dumps(log_text)

            category, summary, hint = classify_failure(log_text)
            print(f"      category: {category}")
            print(f"      summary:  {summary[:120]}")
            if hint:
                print(f"      hint:     {hint[:120]}")

            if args.dry_run:
                print("      (dry-run — issue খোলে না)")
                continue

            # Check for existing issue (deduplication)
            existing = find_existing_issue(commit_sha, svc["name"])
            if existing:
                comment_on_issue(existing, deploy, commit_sha, category, summary)
                issues_commented += 1
                print(f"      💬 commented on existing issue #{existing}")
            else:
                # Render dashboard URL — service deploys page
                log_url = f"https://dashboard.render.com/web/{service_id}/deploys/{deploy_id}"
                issue_num = open_issue(svc, deploy, commit_sha, category, summary,
                                       hint, log_url, log_text)
                if issue_num:
                    issues_opened += 1
                    print(f"      📝 opened issue #{issue_num}")
                else:
                    print(f"      ⚠️ issue creation failed")

    print()
    print(f"📊 Summary: {total_failures} failures found | "
          f"{issues_opened} issues opened | {issues_commented} comments added")
    return 0 if total_failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
