"""
MCP Server for GitHub CI/CD Integration in SupremeAI 2.0.

এই সার্ভারটি এজেন্টকে GitHub সার্ভারকে একিভাবে connect করে এবং
CI/CD অপারেশন (Issue, PR, Auto-fix) সরাসরে চ্যাটবক্স থেকে করার ক্ষমতা দেয়।
"""

import asyncio
import base64
import json
import os
import re
import time
from enum import StrEnum

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from core.config import settings
from core.mcp_audit import audit_tool_call

# শেয়ার্ড ইউটিলিটি — ডুপ্লিকেট কোড দূর করতে কেন্দ্রীয় মডিউল থেকে ইম্পোর্ট
from utils.environment import is_admin_authorized, is_autofix_authorized
from utils.http_client import handle_api_error
from utils.json_helpers import json_error

mcp = FastMCP("github_cicd_mcp")

CHARACTER_LIMIT = 25000
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY") or getattr(
    settings, "github_repository", "SaifulHaqueNiloy/supremeai"
)
GITHUB_API_URL = "https://api.github.com"


def _get_github_token() -> str:
    """Return only the centrally managed platform credential.

    Tenant actions must use a governed connection reference; this legacy MCP
    surface has no request-scoped tenant context, so it is platform-admin only.
    """
    if not is_admin_authorized():
        return ""
    return getattr(settings, "github_token", "") or os.environ.get("GITHUB_TOKEN", "")


class ResponseFormat(StrEnum):
    """আউটপুট ফরম্যাট।"""

    MARKDOWN = "markdown"
    JSON = "json"


class CreatePRInput(BaseModel):
    """PR তৈরির জন্য ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    title: str = Field(..., description="PR এর শিরোনাম", min_length=1, max_length=200)
    body: str = Field(..., description="PR এর বর্ণনা", min_length=1)
    head: str = Field(..., description="সূচী ব্রাঞ্চ", min_length=1)
    base: str = Field(default="main", description="লক্ষ্য ব্রাঞ্চ")


class FixIssueInput(BaseModel):
    """Issue ফিক্স করার জন্য ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    issue_number: int = Field(..., description="ফিক্স করার Issue নম্বর", ge=1)
    branch: str = Field(..., description="ফিক্স শুরু করার ব্রাঞ্চ", min_length=1)


# রিফ্যাক্টর: লোকাল _check_admin_auth, _check_autofix_auth, _handle_api_error মুছে
# শেয়ার্ড ইউটিলিটি (utils.environment, utils.http_client) ব্যবহার করা হচ্ছে।


@mcp.tool(
    name="github_create_pull_request",
    annotations={
        "title": "Create Pull Request",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def github_create_pull_request(params: CreatePRInput) -> str:
    """
    GitHub-এ নতুন Pull Request তৈরি করে।

    MESH-7 (#925) নীতি: PR body-তে বাধ্যতামূলকভাবে issue-link থাকতে হবে
    (যেমন `Fixes #N`, `Closes #N`, `Resolves #N`) — issue-first policy
    (env1.txt directive: 1 Issue → 1 Branch → 1 PR)।

    Args:
        params (CreatePRInput): ইনপুট প্যারামিটার সম্বলিত:
            - title (str): PR শিরোনাম
            - body (str): PR বর্ণনা (`Fixes #N` বাধ্যতামূলক)
            - head (str): সূচী ব্রাঞ্চ
            - base (str): লক্ষ্য ব্রাঞ্চ

    Returns:
        str: PR স্ট্যাটাস ও লিংক
    """
    if not is_admin_authorized():
        return json_error("Admin authorization required for PR creation")

    # MESH-7 (#925): issue-link mandatory — Fixes/Closes/Resolves #N
    if not _has_issue_link(params.body):
        _audit_write(
            "github_create_pull_request",
            "DENY",
            error="missing issue-link (Fixes/Closes/Resolves #N)",
        )
        return json_error(
            "PR body must contain an issue-link (e.g. 'Fixes #123', 'Closes #123', "
            "'Resolves #123') — issue-first policy (#925)"
        )

    github_token = _get_github_token()
    if not github_token:
        return json_error("GITHUB_TOKEN not configured")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/pulls",
                headers={
                    "Authorization": f"token {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={
                    "title": params.title,
                    "body": params.body,
                    "head": params.head,
                    "base": params.base,
                },
            )
            response.raise_for_status()
            data = response.json()

            return json.dumps(
                {
                    "success": True,
                    "pr_number": data.get("number"),
                    "pr_url": data.get("html_url"),
                    "status": data.get("state", "open"),
                    "message": f"PR #{data.get('number')} created successfully",
                },
                ensure_ascii=False,
            )

    except httpx.HTTPStatusError as e:
        return handle_api_error(e, e.response.status_code)
    except Exception as e:
        return handle_api_error(e)


@mcp.tool(
    name="github_run_auto_fix",
    annotations={
        "title": "Run CI Auto-Fix Pipeline",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def github_run_auto_fix(params: FixIssueInput) -> str:
    """
    CI অটো-ফিক্স পাইলাইন চালায়।

    এই টুলটি ci-auto-fix-v3.py ইঞ্জিনকে ট্রিগার করে এবং
    ফিল্ড টেস্ট গুলোর স্বয়ংক্রিয় ফিক্সিং সক্ষম করে।

    Args:
        params (FixIssueInput): ইনপুট প্যারামিটার সম্বলিত:
            - issue_number (int): Issue নম্বর
            - branch (str): ফিক্স ব্রাঞ্চ

    Returns:
        str: অটো-ফিক্স স্ট্যাটাস
    """
    if not is_autofix_authorized():
        return json.dumps(
            {
                "error": "Auto-fix authorization required",
                "message": "Set AUTOFIX_AUTHORIZED=true in environment",
            },
            ensure_ascii=False,
        )

    github_token = _get_github_token()
    if not github_token:
        return json_error("GITHUB_TOKEN not configured")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/actions/workflows/ci-auto-fix-v3.yml/dispatches",
                headers={
                    "Authorization": f"token {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={
                    "ref": params.branch,
                    "inputs": {"issue_number": str(params.issue_number)},
                },
            )
            response.raise_for_status()

            return json.dumps(
                {
                    "success": True,
                    "issue_number": params.issue_number,
                    "branch": params.branch,
                    "workflow": "ci-auto-fix-v3",
                    "message": f"Auto-fix workflow triggered for issue #{params.issue_number}",
                },
                ensure_ascii=False,
            )

    except httpx.HTTPStatusError as e:
        return handle_api_error(e, e.response.status_code)
    except Exception as e:
        return handle_api_error(e)


@mcp.tool(
    name="github_list_issues",
    annotations={
        "title": "List Repository Issues",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def github_list_issues(state: str = "open", labels: str | None = None) -> str:
    """
    রিপোজিটরিতে ইস্যু তালিকা দেখায়।

    Args:
        state (str): ইস্যু স্টেট ('open', 'closed', 'all')
        labels (str | None): ফিল্টার করার জন্য লেবেল

    Returns:
        str: ইস্যু তালিকা
    """
    github_token = _get_github_token()
    if not github_token:
        return json_error("GITHUB_TOKEN not configured")

    valid_states = {"open", "closed", "all"}
    if state not in valid_states:
        state = "open"

    params = {"state": state}
    if labels:
        params["labels"] = labels

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/issues",
                headers={
                    "Authorization": f"token {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                params=params,
            )
            response.raise_for_status()
            issues = response.json()

            return json.dumps(
                {
                    "issues": [
                        {
                            "number": i.get("number"),
                            "title": i.get("title"),
                            "state": i.get("state"),
                            "labels": [lbl.get("name") for lbl in i.get("labels", [])],
                            "url": i.get("html_url"),
                        }
                        for i in issues
                    ],
                    "count": len(issues),
                },
                ensure_ascii=False,
            )

    except httpx.HTTPStatusError as e:
        return handle_api_error(e, e.response.status_code)
    except Exception as e:
        return handle_api_error(e)


@mcp.tool(
    name="github_get_ci_status",
    annotations={
        "title": "Get CI/CD Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def github_get_ci_status(branch: str = "main") -> str:
    """
    শাখার CI/CD স্ট্যাটাস দেখায়।

    Args:
        branch (str): চেক করার শাখা

    Returns:
        str: CI স্ট্যাটাস ও রিজাল্ট
    """
    github_token = _get_github_token()
    if not github_token:
        return json_error("GITHUB_TOKEN not configured")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/commits/{branch}/status",
                headers={
                    "Authorization": f"token {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            response.raise_for_status()
            data = response.json()

            return json.dumps(
                {
                    "branch": branch,
                    "state": data.get("state"),
                    "statuses": data.get("statuses", []),
                    "total_count": data.get("total_count", 0),
                },
                ensure_ascii=False,
            )

    except httpx.HTTPStatusError as e:
        return handle_api_error(e, e.response.status_code)
    except Exception as e:
        return handle_api_error(e)


class GetFileContentsInput(BaseModel):
    """ফাইল কনটেন্ট পড়ার জন্য ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    path: str = Field(..., description="রিপোর মধ্যে ফাইলের পাথ", min_length=1)
    ref: str = Field(default="main", description="ব্রাঞ্চ/ট্যাগ/কমিট SHA")


class SearchCodeInput(BaseModel):
    """কোড সার্চের জন্য ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    query: str = Field(
        ..., description="সার্চ কোয়েরি (GitHub code search সিনট্যাক্স সাপোর্ট করে)", min_length=1
    )
    per_page: int = Field(default=10, description="প্রতি পেজে কতগুলো রেজাল্ট", ge=1, le=50)


@mcp.tool(
    name="github_get_file_contents",
    annotations={
        "title": "Read File From Repository",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def github_get_file_contents(params: GetFileContentsInput) -> str:
    """
    রিপো থেকে একটি ফাইলের কনটেন্ট পড়ে আনে (base64 ডিকোড সহ)।

    Args:
        params (GetFileContentsInput): path ও ref (ব্রাঞ্চ/ট্যাগ/SHA)

    Returns:
        str: ডিকোড করা ফাইলের কনটেন্ট অথবা এরর JSON
    """
    github_token = _get_github_token()
    if not github_token:
        return json_error("GITHUB_TOKEN is missing or empty")

    url = f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/contents/{params.path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"token {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                params={"ref": params.ref},
            )
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list):
                return json_error(f"Path '{params.path}' is a directory, not a file.")

            content_b64 = data.get("content", "")
            encoding = data.get("encoding", "")

            if encoding == "base64" and content_b64:
                decoded_content = base64.b64decode(content_b64).decode("utf-8", errors="replace")
            else:
                decoded_content = content_b64

            return json.dumps(
                {
                    "path": data.get("path"),
                    "sha": data.get("sha"),
                    "size": data.get("size"),
                    "encoding": encoding,
                    "content": decoded_content,
                },
                ensure_ascii=False,
            )

    except httpx.HTTPStatusError as e:
        return handle_api_error(e, e.response.status_code)
    except Exception as e:
        return handle_api_error(e)


@mcp.tool(
    name="github_search_code",
    annotations={
        "title": "Search Code In Repository",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def github_search_code(params: SearchCodeInput) -> str:
    """
    GitHub code search এপিআই ব্যবহার করে রিপোর মধ্যে কোড সার্চ করে।

    Args:
        params (SearchCodeInput): query ও per_page

    Returns:
        str: সার্চ রেজাল্টের তালিকা (ফাইলের নাম, পাথ, ম্যাচিং স্নিপেট)
    """
    github_token = _get_github_token()
    if not github_token:
        return json_error("GITHUB_TOKEN is missing or empty")

    scoped_query = f"repo:{GITHUB_REPO} {params.query}"
    url = f"{GITHUB_API_URL}/search/code"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"token {github_token}",
                    "Accept": "application/vnd.github.v3.text-match+json",
                },
                params={"q": scoped_query, "per_page": params.per_page},
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("items", []):
                matches = []
                for match in item.get("text_matches", []):
                    matches.append(match.get("fragment", ""))

                results.append(
                    {
                        "name": item.get("name"),
                        "path": item.get("path"),
                        "sha": item.get("sha"),
                        "html_url": item.get("html_url"),
                        "matches": matches,
                    }
                )

            return json.dumps(
                {
                    "total_count": data.get("total_count", 0),
                    "incomplete_results": data.get("incomplete_results", False),
                    "items": results,
                },
                ensure_ascii=False,
            )

    except httpx.HTTPStatusError as e:
        return handle_api_error(e, e.response.status_code)
    except Exception as e:
        return handle_api_error(e)


# ═══════════════════════════════════════════════════════════════════════════════
# MESH-7 (issue #962/#925): Tower GitHub Write-op completion
# Plan: docs/plans/MULTI_AGENT_MESH_MASTER_PLAN.md §৪ principle 1 —
# "GitHub PR as Universal IPC"। Tower যেন mesh flow সম্পূর্ণ করতে পারে:
# branch → commit → issue/comment → merge। প্রতিটি op:
#   1. admin-gated (is_admin_authorized)
#   2. sliding-window rate-limited (WRITE_MAX_PER_WINDOW/minute, সব write শেয়ার্ড)
#   3. audit-logged (Constitution Law #19 — observable audit trail)
#   4. fail-closed টোকেন অনুপস্থিতিতে (json_error, কোনো silent no-op নেই)
# ═══════════════════════════════════════════════════════════════════════════════

# বাংলা: CFG-001 সচেতনতা — runtime policy মান env-driven (registry ডিফল্ট সহ)
WRITE_WINDOW_SECONDS = float(os.environ.get("SUPREME_GITHUB_WRITE_WINDOW_SECONDS", "60"))
WRITE_MAX_PER_WINDOW = int(os.environ.get("SUPREME_GITHUB_WRITE_MAX_PER_WINDOW", "30"))
_write_op_times: list[float] = []
_write_op_lock = asyncio.Lock()


def _github_headers(token: str, accept: str = "application/vnd.github.v3+json") -> dict[str, str]:
    """GitHub API স্ট্যান্ডার্ড হেডার।"""
    return {"Authorization": f"token {token}", "Accept": accept}


async def _enforce_write_rate_limit() -> str | None:
    """সব GitHub write op-এর জন্য শেয়ার্ড sliding-window rate limiter।

    Returns:
        str | None: limit ছাড়িয়ে গেলে json_error পেলোড, নাহলে None।
    """
    async with _write_op_lock:
        now = time.monotonic()
        while _write_op_times and now - _write_op_times[0] > WRITE_WINDOW_SECONDS:
            _write_op_times.pop(0)
        if len(_write_op_times) >= WRITE_MAX_PER_WINDOW:
            return json_error(
                f"GitHub write rate limit exceeded "
                f"({WRITE_MAX_PER_WINDOW} ops/{int(WRITE_WINDOW_SECONDS)}s) — try again shortly"
            )
        _write_op_times.append(now)
        return None


def _audit_write(tool_name: str, outcome: str, error: str | None = None) -> None:
    """Constitution Law #19 — প্রতিটি write op-এর observable audit trail।"""
    audit_tool_call(
        tool_name,
        decision=outcome,
        risk_level="R2",
        tenant_id="platform-admin",
        error=error,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MESH-7 Phase 2 (issue #925): GitHub Write Tools completion
#   - github_commit_files (multi-file atomic commit, path allowlist)
#   - github_pr_comment (explicit PR comment tool)
#   - github_close_issue
#   - github_add_labels
#   - github_create_pull_request: now enforces `Fixes #N` issue-link mandatory
#   - github_merge_pull_request: now enforces CI-green pre-merge check (P0 policy)
# Acceptance spec: https://github.com/SaifulHaqueNiloy/supremeai/issues/925
# ═══════════════════════════════════════════════════════════════════════════════

# GitHub auto-close keywords — case-insensitive (close[sd]?|fix(es|ed)?|resolve[sd]?) + #N
# Ref: https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue
_ISSUE_LINK_PATTERN = re.compile(
    r"\b(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)\s+#\d+\b",
    re.IGNORECASE,
)

# Protected path prefixes — `allow_protected_paths=True` স্পষ্টভাবে সেট না করলে
# এই পথগুলোতে commit/write ব্লক হবে (P0 policy #925)।
PROTECTED_PATH_PREFIXES: tuple[str, ...] = ("backend/core/", ".github/")


def _has_issue_link(body: str | None) -> bool:
    """PR body-তে `Fixes #N` / `Closes #N` / `Resolves #N` লিংক আছে কিনা যাচাই করে।

    GitHub-এর auto-close কিওয়ার্ডগুলো সব সম্মান করা হয়।
    """
    return bool(_ISSUE_LINK_PATTERN.search(body or ""))


def _is_protected_path(path: str) -> bool:
    """Path-টি protected prefix (`backend/core/`, `.github/`) এর অধীনে আছে কিনা।"""
    normalized = (path or "").lstrip("/").lower()
    return any(normalized.startswith(prefix) for prefix in PROTECTED_PATH_PREFIXES)


def _find_protected_paths(paths: list[str]) -> list[str]:
    """তালিকা থেকে সব protected path বের করে (original case সংরক্ষিত)।"""
    return [p for p in paths if _is_protected_path(p)]


async def _check_pr_ci_green(
    client: httpx.AsyncClient, token: str, pr_number: int
) -> tuple[bool, str]:
    """PR-এর head SHA-তে combined CI status চেক করে।

    P0 policy (#925): merge করার আগে CI সবুজ হতে হবে।

    Returns:
        (success, message) — CI সবুজ হলে (True, head_sha), অন্যথায় (False, reason)।
    """
    pr_resp = await client.get(
        f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/pulls/{pr_number}",
        headers=_github_headers(token),
    )
    pr_resp.raise_for_status()
    pr_data = pr_resp.json()
    head_sha = (pr_data.get("head") or {}).get("sha")
    if not head_sha:
        return False, "PR head sha not found"

    status_resp = await client.get(
        f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/commits/{head_sha}/status",
        headers=_github_headers(token),
    )
    status_resp.raise_for_status()
    state = (status_resp.json() or {}).get("state", "")

    if state == "success":
        return True, head_sha
    return (
        False,
        f"CI state is '{state}' (expected 'success') — P0 policy requires green CI before merge",
    )


class CreateBranchInput(BaseModel):
    """নতুন branch তৈরির ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    branch: str = Field(
        ..., description="নতুন branch-এর নাম (যেমন mesh/task-42)", min_length=1, max_length=200
    )
    base: str = Field(default="main", description="কোন branch থেকে তৈরি হবে", min_length=1)


class PushCommitInput(BaseModel):
    """Contents API দিয়ে single-file commit পুশ করার ইনপুট (git binary ছাড়া)।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    branch: str = Field(..., description="কোন branch-এ commit হবে", min_length=1)
    path: str = Field(..., description="ফাইলের repo-relative পথ", min_length=1, max_length=400)
    content: str = Field(..., description="ফাইলের নতুন কনটেন্ট (encoding অনুযায়ী)")
    message: str = Field(..., description="commit message", min_length=1, max_length=600)
    encoding: str = Field(
        default="utf-8",
        description="utf-8 (raw text — স্বয়ংক্রিয়ভাবে base64 হবে) অথবা base64 (binary passthrough)",
        pattern="^(utf-8|base64)$",
    )


class CreateIssueInput(BaseModel):
    """নতুন Issue তৈরির ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    title: str = Field(..., description="Issue শিরোনাম", min_length=1, max_length=256)
    body: str = Field(default="", description="Issue বর্ণনা")
    labels: list[str] = Field(
        default_factory=list, description="ঐচ্ছিক labels (token-এর push scope লাগে)"
    )


class IssueCommentInput(BaseModel):
    """Issue-তে কমেন্ট যোগের ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    issue_number: int = Field(..., description="Issue নম্বর", ge=1)
    body: str = Field(..., description="কমেন্ট কনটেন্ট (markdown)", min_length=1)


class MergePRInput(BaseModel):
    """PR merge করার ইনপুট — Universal IPC লুপের শেষ ধাপ।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    pr_number: int = Field(..., description="Pull Request নম্বর", ge=1)
    merge_method: str = Field(
        default="merge",
        description="merge | squash | rebase",
        pattern="^(merge|squash|rebase)$",
    )
    commit_title: str | None = Field(
        default=None, description="ঐচ্ছিক merge commit শিরোনাম", max_length=300
    )
    commit_message: str | None = Field(default=None, description="ঐচ্ছিক merge commit বার্তা")


@mcp.tool(
    name="github_create_branch",
    annotations={
        "title": "Create Branch",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def github_create_branch(params: CreateBranchInput) -> str:
    """
    base branch-এর HEAD sha থেকে নতুন branch তৈরি করে (mesh/task-N ব্রাঞ্চিং)।

    Args:
        params (CreateBranchInput): branch নাম + base branch (default main)

    Returns:
        str: তৈরি হওয়া branch-এর নাম, base sha, লিংক
    """
    if not is_admin_authorized():
        return json_error("Admin authorization required for branch creation")
    rate_limited = await _enforce_write_rate_limit()
    if rate_limited:
        return rate_limited
    github_token = _get_github_token()
    if not github_token:
        return json_error("GITHUB_TOKEN not configured")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            ref_response = await client.get(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/git/ref/heads/{params.base}",
                headers=_github_headers(github_token),
            )
            ref_response.raise_for_status()
            base_sha = ref_response.json()["object"]["sha"]

            create_response = await client.post(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/git/refs",
                headers=_github_headers(github_token),
                json={"ref": f"refs/heads/{params.branch}", "sha": base_sha},
            )
            create_response.raise_for_status()
            data = create_response.json()

        _audit_write("github_create_branch", "ALLOW")
        return json.dumps(
            {
                "success": True,
                "branch": params.branch,
                "base": params.base,
                "base_sha": base_sha,
                "ref": data.get("ref"),
                "url": data.get("url"),
                "message": f"Branch '{params.branch}' created from {params.base}@{base_sha[:7]}",
            },
            ensure_ascii=False,
        )
    except httpx.HTTPStatusError as e:
        _audit_write("github_create_branch", "ERROR", error=str(e.response.status_code))
        return handle_api_error(e, e.response.status_code)
    except Exception as e:  # noqa: BLE001 — MCP tool boundary
        _audit_write("github_create_branch", "ERROR", error=str(e))
        return handle_api_error(e)


@mcp.tool(
    name="github_push_commit",
    annotations={
        "title": "Push Commit (single file)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def github_push_commit(params: PushCommitInput) -> str:
    """
    Contents API দিয়ে single-file commit পুশ করে — git binary ছাড়াই
    Tower-managed agents (local executors) mesh/task-N branch-এ কোড দিতে পারে।

    ফাইল আগে থাকলে update (existing sha সহ), না থাকলে নতুন ফাইল তৈরি হয়।

    Args:
        params (PushCommitInput): branch, path, content, message, encoding

    Returns:
        str: commit sha, ফাইল path, html_url
    """
    if not is_admin_authorized():
        return json_error("Admin authorization required for commit push")
    rate_limited = await _enforce_write_rate_limit()
    if rate_limited:
        return rate_limited
    github_token = _get_github_token()
    if not github_token:
        return json_error("GITHUB_TOKEN not configured")

    encoded = (
        params.content
        if params.encoding == "base64"
        else base64.b64encode(params.content.encode("utf-8")).decode("ascii")
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            existing_sha: str | None = None
            get_response = await client.get(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/contents/{params.path}",
                headers=_github_headers(github_token),
                params={"ref": params.branch},
            )
            if get_response.status_code == 200:
                existing_sha = get_response.json().get("sha")
            elif get_response.status_code != 404:
                get_response.raise_for_status()

            payload: dict[str, object] = {
                "message": params.message,
                "content": encoded,
                "branch": params.branch,
            }
            if existing_sha:
                payload["sha"] = existing_sha

            put_response = await client.put(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/contents/{params.path}",
                headers=_github_headers(github_token),
                json=payload,
            )
            put_response.raise_for_status()
            data = put_response.json()

        commit = data.get("commit", {})
        _audit_write("github_push_commit", "ALLOW")
        return json.dumps(
            {
                "success": True,
                "branch": params.branch,
                "path": params.path,
                "commit_sha": commit.get("sha"),
                "commit_url": commit.get("html_url"),
                "created": existing_sha is None,
                "message": f"{'Created' if existing_sha is None else 'Updated'} {params.path} on {params.branch}",
            },
            ensure_ascii=False,
        )
    except httpx.HTTPStatusError as e:
        _audit_write("github_push_commit", "ERROR", error=str(e.response.status_code))
        return handle_api_error(e, e.response.status_code)
    except Exception as e:  # noqa: BLE001 — MCP tool boundary
        _audit_write("github_push_commit", "ERROR", error=str(e))
        return handle_api_error(e)


@mcp.tool(
    name="github_create_issue",
    annotations={
        "title": "Create Issue",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def github_create_issue(params: CreateIssueInput) -> str:
    """
    নতুন GitHub Issue তৈরি করে — task tracking + result audit trail-এর ভিত্তি।

    Args:
        params (CreateIssueInput): title, body, labels (ঐচ্ছিক)

    Returns:
        str: issue নম্বর, লিংক, স্ট্যাটাস
    """
    if not is_admin_authorized():
        return json_error("Admin authorization required for issue creation")
    rate_limited = await _enforce_write_rate_limit()
    if rate_limited:
        return rate_limited
    github_token = _get_github_token()
    if not github_token:
        return json_error("GITHUB_TOKEN not configured")

    payload: dict[str, object] = {"title": params.title, "body": params.body}
    if params.labels:
        payload["labels"] = params.labels

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/issues",
                headers=_github_headers(github_token),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        _audit_write("github_create_issue", "ALLOW")
        return json.dumps(
            {
                "success": True,
                "issue_number": data.get("number"),
                "issue_url": data.get("html_url"),
                "status": data.get("state", "open"),
                "message": f"Issue #{data.get('number')} created successfully",
            },
            ensure_ascii=False,
        )
    except httpx.HTTPStatusError as e:
        _audit_write("github_create_issue", "ERROR", error=str(e.response.status_code))
        return handle_api_error(e, e.response.status_code)
    except Exception as e:  # noqa: BLE001 — MCP tool boundary
        _audit_write("github_create_issue", "ERROR", error=str(e))
        return handle_api_error(e)


@mcp.tool(
    name="github_add_issue_comment",
    annotations={
        "title": "Add Issue Comment",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def github_add_issue_comment(params: IssueCommentInput) -> str:
    """
    Issue-তে কমেন্ট যোগ করে — agent result/evidence পোস্ট করার চ্যানেল।

    Args:
        params (IssueCommentInput): issue_number, body

    Returns:
        str: কমেন্ট id, লিংক
    """
    if not is_admin_authorized():
        return json_error("Admin authorization required for issue comment")
    rate_limited = await _enforce_write_rate_limit()
    if rate_limited:
        return rate_limited
    github_token = _get_github_token()
    if not github_token:
        return json_error("GITHUB_TOKEN not configured")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/issues/{params.issue_number}/comments",
                headers=_github_headers(github_token),
                json={"body": params.body},
            )
            response.raise_for_status()
            data = response.json()

        _audit_write("github_add_issue_comment", "ALLOW")
        return json.dumps(
            {
                "success": True,
                "issue_number": params.issue_number,
                "comment_id": data.get("id"),
                "comment_url": data.get("html_url"),
                "message": f"Comment added to issue #{params.issue_number}",
            },
            ensure_ascii=False,
        )
    except httpx.HTTPStatusError as e:
        _audit_write("github_add_issue_comment", "ERROR", error=str(e.response.status_code))
        return handle_api_error(e, e.response.status_code)
    except Exception as e:  # noqa: BLE001 — MCP tool boundary
        _audit_write("github_add_issue_comment", "ERROR", error=str(e))
        return handle_api_error(e)


@mcp.tool(
    name="github_merge_pull_request",
    annotations={
        "title": "Merge Pull Request",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def github_merge_pull_request(params: MergePRInput) -> str:
    """
    Pull Request merge করে — "PR as Universal IPC" লুপের সমাপ্তি (Verification-এর পরে)।

    MESH-7 (#925) P0 নীতি: merge করার আগে বাধ্যতামূলকভাবে CI-green check।
    PR-এর head SHA-তে combined status `success` না হলে merge হবে না (no bypass)।

    Args:
        params (MergePRInput): pr_number, merge_method (merge|squash|rebase), ঐচ্ছিক commit title/message

    Returns:
        str: merge sha, স্ট্যাটাস
    """
    if not is_admin_authorized():
        return json_error("Admin authorization required for PR merge")
    rate_limited = await _enforce_write_rate_limit()
    if rate_limited:
        return rate_limited
    github_token = _get_github_token()
    if not github_token:
        return json_error("GITHUB_TOKEN not configured")

    payload: dict[str, object] = {"merge_method": params.merge_method}
    if params.commit_title:
        payload["commit_title"] = params.commit_title
    if params.commit_message:
        payload["commit_message"] = params.commit_message

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # MESH-7 (#925) P0 policy: CI-green বাধ্যতামূলক pre-merge gate
            ci_ok, ci_msg = await _check_pr_ci_green(client, github_token, params.pr_number)
            if not ci_ok:
                _audit_write(
                    "github_merge_pull_request",
                    "DENY",
                    error=f"CI not green: {ci_msg}",
                )
                return json_error(f"Merge blocked by P0 CI-green policy (#925): {ci_msg}")

            response = await client.put(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/pulls/{params.pr_number}/merge",
                headers=_github_headers(github_token),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        _audit_write("github_merge_pull_request", "ALLOW")
        return json.dumps(
            {
                "success": True,
                "pr_number": params.pr_number,
                "merged": data.get("merged", True),
                "merge_sha": data.get("sha"),
                "ci_head_sha": ci_msg,
                "message": data.get("message", "Pull Request successfully merged"),
            },
            ensure_ascii=False,
        )
    except httpx.HTTPStatusError as e:
        _audit_write("github_merge_pull_request", "ERROR", error=str(e.response.status_code))
        return handle_api_error(e, e.response.status_code)
    except Exception as e:  # noqa: BLE001 — MCP tool boundary
        _audit_write("github_merge_pull_request", "ERROR", error=str(e))
        return handle_api_error(e)


# ─────────────────────────────────────────────────────────────────────────────
# MESH-7 Phase 2 (#925) — নতুন write tools: commit_files, pr_comment,
# close_issue, add_labels
# ─────────────────────────────────────────────────────────────────────────────


class FileContentItem(BaseModel):
    """Commit করার ফাইলের একটি আইটেম (multi-file atomic commit-এর জন্য)।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    path: str = Field(..., description="ফাইলের repo-relative পথ", min_length=1, max_length=400)
    content: str = Field(..., description="ফাইলের কনটেন্ট (encoding অনুযায়ী)")
    encoding: str = Field(
        default="utf-8",
        description="utf-8 (raw text — স্বয়ংক্রিয়ভাবে base64 হবে) অথবা base64 (binary passthrough)",
        pattern="^(utf-8|base64)$",
    )


class CommitFilesInput(BaseModel):
    """Multi-file atomic commit — git tree+commit API দিয়ে single commit।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    branch: str = Field(..., description="কোন branch-এ commit হবে", min_length=1)
    message: str = Field(..., description="commit message", min_length=1, max_length=600)
    files: list[FileContentItem] = Field(
        ...,
        description="commit করার ফাইলের তালিকা (অন্তত ১টি, সর্বোচ্চ ১০০)",
        min_length=1,
        max_length=100,
    )
    allow_protected_paths: bool = Field(
        default=False,
        description=(
            "backend/core/** অথবা .github/** এর অধীনে লেখার সুস্পষ্ট অনুমতি "
            "(P0 policy #925 — ডিফল্ট False)"
        ),
    )


class PRCommentInput(BaseModel):
    """Pull Request-তে কমেন্ট যোগের ইনপুট (issue comment API এর সাথে একই endpoint শেয়ার করে)।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    pr_number: int = Field(..., description="Pull Request নম্বর", ge=1)
    body: str = Field(..., description="কমেন্ট কনটেন্ট (markdown)", min_length=1)


class CloseIssueInput(BaseModel):
    """Issue বন্ধ করার ইনপুট — ঐচ্ছিক close-comment ও state reason সহ।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    issue_number: int = Field(..., description="Issue নম্বর", ge=1)
    comment: str | None = Field(
        default=None,
        description="বন্ধ করার আগে পোস্ট করার ঐচ্ছিক close-comment (markdown)",
        max_length=10000,
    )
    state_reason: str | None = Field(
        default=None,
        description="বন্ধ করার কারণ: completed | not_planned | duplicate",
        pattern="^(completed|not_planned|duplicate)$",
    )


class AddLabelsInput(BaseModel):
    """Issue/PR-তে labels যোগ করার ইনপুট (PR হলেও issue endpoint ব্যবহৃত হয়)।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    issue_number: int = Field(..., description="Issue অথবা PR নম্বর", ge=1)
    labels: list[str] = Field(..., description="যোগ করার labels তালিকা (অন্তত ১টি)", min_length=1)


@mcp.tool(
    name="github_commit_files",
    annotations={
        "title": "Commit Multiple Files (atomic)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def github_commit_files(params: CommitFilesInput) -> str:
    """
    Multi-file atomic commit — git tree+commit API দিয়ে single commit।

    Path allowlist (P0 policy #925): `backend/core/**` অথবা `.github/**`
    এর অধীনে লেখা হলে `allow_protected_paths=True` স্পষ্টভাবে সেট করতে হবে।

    প্রবাহ (Git Data API):
      1. branch ref → parent commit SHA
      2. parent commit → base tree SHA
      3. প্রতিটি ফাইলের জন্য blob তৈরি
      4. base_tree + tree items → new tree
      5. message + tree + parent → new commit
      6. branch ref আপডেট → new commit SHA

    Args:
        params (CommitFilesInput): branch, message, files[], allow_protected_paths

    Returns:
        str: commit sha, parent sha, files_committed, paths[]
    """
    # Path allowlist — সব গেটের আগে (যাতে protected write কখনো audit-ছাড়া না যায়)
    requested_paths = [f.path for f in params.files]
    protected = _find_protected_paths(requested_paths)
    if protected and not params.allow_protected_paths:
        _audit_write(
            "github_commit_files",
            "DENY",
            error=f"protected path(s) without override: {protected}",
        )
        return json_error(
            f"Protected path(s) require explicit allow_protected_paths=true "
            f"(P0 policy #925): {protected}"
        )

    if not is_admin_authorized():
        return json_error("Admin authorization required for multi-file commit")
    rate_limited = await _enforce_write_rate_limit()
    if rate_limited:
        return rate_limited
    github_token = _get_github_token()
    if not github_token:
        return json_error("GITHUB_TOKEN not configured")

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            # Step 1: branch ref → parent commit SHA
            ref_resp = await client.get(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/git/ref/heads/{params.branch}",
                headers=_github_headers(github_token),
            )
            ref_resp.raise_for_status()
            parent_sha = ref_resp.json()["object"]["sha"]

            # Step 2: parent commit → base tree SHA
            parent_commit_resp = await client.get(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/git/commits/{parent_sha}",
                headers=_github_headers(github_token),
            )
            parent_commit_resp.raise_for_status()
            base_tree_sha = (parent_commit_resp.json().get("tree") or {}).get("sha")

            # Step 3: create blob per file
            tree_items: list[dict[str, str]] = []
            for f in params.files:
                encoded_content = (
                    f.content
                    if f.encoding == "base64"
                    else base64.b64encode(f.content.encode("utf-8")).decode("ascii")
                )
                blob_resp = await client.post(
                    f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/git/blobs",
                    headers=_github_headers(github_token),
                    json={"content": encoded_content, "encoding": "base64"},
                )
                blob_resp.raise_for_status()
                blob_sha = blob_resp.json()["sha"]
                tree_items.append(
                    {
                        "path": f.path.lstrip("/"),
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob_sha,
                    }
                )

            # Step 4: create new tree (base_tree + items)
            tree_payload: dict[str, object] = {"tree": tree_items}
            if base_tree_sha:
                tree_payload["base_tree"] = base_tree_sha
            tree_resp = await client.post(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/git/trees",
                headers=_github_headers(github_token),
                json=tree_payload,
            )
            tree_resp.raise_for_status()
            new_tree_sha = tree_resp.json()["sha"]

            # Step 5: create commit pointing to new tree, parent = parent_sha
            commit_resp = await client.post(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/git/commits",
                headers=_github_headers(github_token),
                json={
                    "message": params.message,
                    "tree": new_tree_sha,
                    "parents": [parent_sha],
                },
            )
            commit_resp.raise_for_status()
            new_commit_sha = commit_resp.json()["sha"]

            # Step 6: update branch ref → fast-forward (force=False)
            ref_update_resp = await client.patch(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/git/refs/heads/{params.branch}",
                headers=_github_headers(github_token),
                json={"sha": new_commit_sha, "force": False},
            )
            ref_update_resp.raise_for_status()

        _audit_write("github_commit_files", "ALLOW")
        return json.dumps(
            {
                "success": True,
                "branch": params.branch,
                "commit_sha": new_commit_sha,
                "parent_sha": parent_sha,
                "files_committed": len(params.files),
                "paths": [f.path for f in params.files],
                "protected_paths_overridden": bool(protected),
                "message": (
                    f"Committed {len(params.files)} file(s) to "
                    f"{params.branch}@{new_commit_sha[:7]} (parent {parent_sha[:7]})"
                ),
            },
            ensure_ascii=False,
        )
    except httpx.HTTPStatusError as e:
        _audit_write("github_commit_files", "ERROR", error=str(e.response.status_code))
        return handle_api_error(e, e.response.status_code)
    except Exception as e:  # noqa: BLE001 — MCP tool boundary
        _audit_write("github_commit_files", "ERROR", error=str(e))
        return handle_api_error(e)


@mcp.tool(
    name="github_pr_comment",
    annotations={
        "title": "Add PR Comment",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def github_pr_comment(params: PRCommentInput) -> str:
    """
    Pull Request-তে কমেন্ট যোগ করে।

    GitHub-এর issue comment endpoint (POST /repos/{repo}/issues/{pr_number}/comments)
    ব্যবহৃত হয় — PR-গুলো এই endpoint-এ issue হিসেবে চিহ্নিত।

    Args:
        params (PRCommentInput): pr_number, body (markdown)

    Returns:
        str: comment_id, comment_url
    """
    if not is_admin_authorized():
        return json_error("Admin authorization required for PR comment")
    rate_limited = await _enforce_write_rate_limit()
    if rate_limited:
        return rate_limited
    github_token = _get_github_token()
    if not github_token:
        return json_error("GITHUB_TOKEN not configured")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/issues/{params.pr_number}/comments",
                headers=_github_headers(github_token),
                json={"body": params.body},
            )
            response.raise_for_status()
            data = response.json()

        _audit_write("github_pr_comment", "ALLOW")
        return json.dumps(
            {
                "success": True,
                "pr_number": params.pr_number,
                "comment_id": data.get("id"),
                "comment_url": data.get("html_url"),
                "message": f"Comment added to PR #{params.pr_number}",
            },
            ensure_ascii=False,
        )
    except httpx.HTTPStatusError as e:
        _audit_write("github_pr_comment", "ERROR", error=str(e.response.status_code))
        return handle_api_error(e, e.response.status_code)
    except Exception as e:  # noqa: BLE001 — MCP tool boundary
        _audit_write("github_pr_comment", "ERROR", error=str(e))
        return handle_api_error(e)


@mcp.tool(
    name="github_close_issue",
    annotations={
        "title": "Close Issue",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def github_close_issue(params: CloseIssueInput) -> str:
    """
    Issue (অথবা PR — state transition) বন্ধ করে।

    ঐচ্ছিক `comment` দিলে বন্ধ করার আগে সেই কমেন্ট পোস্ট হয় (close-reason সহ)।
    `state_reason` দিলে GitHub সেট করে (completed | not_planned | duplicate)।

    Args:
        params (CloseIssueInput): issue_number, comment?, state_reason?

    Returns:
        str: issue_number, state, comment_id?
    """
    if not is_admin_authorized():
        return json_error("Admin authorization required for issue close")
    rate_limited = await _enforce_write_rate_limit()
    if rate_limited:
        return rate_limited
    github_token = _get_github_token()
    if not github_token:
        return json_error("GITHUB_TOKEN not configured")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            comment_id: int | None = None
            comment_url: str | None = None
            # ঐচ্ছিক close-comment — issue-তে পোস্ট করা হয় আগে
            if params.comment:
                comment_resp = await client.post(
                    f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/issues/{params.issue_number}/comments",
                    headers=_github_headers(github_token),
                    json={"body": params.comment},
                )
                comment_resp.raise_for_status()
                comment_data = comment_resp.json()
                comment_id = comment_data.get("id")
                comment_url = comment_data.get("html_url")

            # PATCH issue → state=closed
            patch_payload: dict[str, object] = {"state": "closed"}
            if params.state_reason:
                patch_payload["state_reason"] = params.state_reason
            patch_resp = await client.patch(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/issues/{params.issue_number}",
                headers=_github_headers(github_token),
                json=patch_payload,
            )
            patch_resp.raise_for_status()
            data = patch_resp.json()

        _audit_write("github_close_issue", "ALLOW")
        result: dict[str, object] = {
            "success": True,
            "issue_number": params.issue_number,
            "state": data.get("state", "closed"),
            "state_reason": data.get("state_reason"),
            "issue_url": data.get("html_url"),
            "message": f"Issue #{params.issue_number} closed",
        }
        if comment_id is not None:
            result["comment_id"] = comment_id
            result["comment_url"] = comment_url
        return json.dumps(result, ensure_ascii=False)
    except httpx.HTTPStatusError as e:
        _audit_write("github_close_issue", "ERROR", error=str(e.response.status_code))
        return handle_api_error(e, e.response.status_code)
    except Exception as e:  # noqa: BLE001 — MCP tool boundary
        _audit_write("github_close_issue", "ERROR", error=str(e))
        return handle_api_error(e)


@mcp.tool(
    name="github_add_labels",
    annotations={
        "title": "Add Labels to Issue/PR",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def github_add_labels(params: AddLabelsInput) -> str:
    """
    Issue অথবা PR-তে labels যোগ করে (PR-গুলো issue endpoint শেয়ার করে)।

    Args:
        params (AddLabelsInput): issue_number, labels[]

    Returns:
        str: issue_number, labels[] (সর্বমোট labels যা এখন issue-তে আছে)
    """
    if not is_admin_authorized():
        return json_error("Admin authorization required for adding labels")
    rate_limited = await _enforce_write_rate_limit()
    if rate_limited:
        return rate_limited
    github_token = _get_github_token()
    if not github_token:
        return json_error("GITHUB_TOKEN not configured")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/issues/{params.issue_number}/labels",
                headers=_github_headers(github_token),
                json={"labels": params.labels},
            )
            response.raise_for_status()
            data = response.json()

        # data: list of label objects — extract names
        final_labels = [(lbl.get("name") if isinstance(lbl, dict) else lbl) for lbl in (data or [])]
        _audit_write("github_add_labels", "ALLOW")
        return json.dumps(
            {
                "success": True,
                "issue_number": params.issue_number,
                "labels_added": params.labels,
                "labels_now": final_labels,
                "message": (
                    f"Added {len(params.labels)} label(s) to issue/PR #{params.issue_number}"
                ),
            },
            ensure_ascii=False,
        )
    except httpx.HTTPStatusError as e:
        _audit_write("github_add_labels", "ERROR", error=str(e.response.status_code))
        return handle_api_error(e, e.response.status_code)
    except Exception as e:  # noqa: BLE001 — MCP tool boundary
        _audit_write("github_add_labels", "ERROR", error=str(e))
        return handle_api_error(e)


if __name__ == "__main__":
    mcp.run()
