import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_token, get_tenant_db
from core.logging_config import logger
from database.session import get_db_session
from services import global_http_client  # FIX: reuse shared connection pool
from tools.devops.github_agent import GitHubAgent, get_user_github_token
from tools.repo_discovery_agent import RepoDiscoveryAgent

# Lazy/optional firebase_admin import — only needed for type hints.
# The actual firestore.Client is only used at runtime if db is a Firestore client.
if TYPE_CHECKING:
    from firebase_admin import firestore
else:
    try:
        from firebase_admin import firestore
    except ImportError:
        firestore = None  # type: ignore[assignment]

router = APIRouter(prefix="/github", tags=["github"])
repo_discovery_agent = RepoDiscoveryAgent()


def _resolve_repo(payload_repo: str | None, db) -> str:
    repo = payload_repo
    if not repo or not repo.strip():
        profile = db.get_tenant_profile() or {}
        repo = profile.get("github_repo")
    if not repo or not repo.strip():
        raise HTTPException(
            status_code=400,
            detail="Repository not connected. Please connect your GitHub repository or provide one in the request.",
        )
    return repo.strip()


@asynccontextmanager
async def handle_github_errors(operation_name: str, repo: str | None = None):
    try:
        yield
    except HTTPException:
        raise
    except Exception as e:
        error_id = uuid.uuid4().hex[:8]
        repo_info = f" for repo={repo}" if repo else ""
        logger.error(f"[{error_id}] github/{operation_name} failed{repo_info}: {e}")
        raise HTTPException(
            status_code=502, detail=f"GitHub operation failed (ref: {error_id})"
        ) from e


async def _get_agent(user: dict, sql_db: AsyncSession) -> GitHubAgent:
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = await get_user_github_token(user_id, sql_db)
    if not token:
        raise HTTPException(
            status_code=403, detail="GitHub integration not connected or token invalid."
        )
    return GitHubAgent(token=token)


class ConnectRequest(BaseModel):
    installation_id: str | None = None
    repo_owner: str
    repo_name: str


class ImproveRequest(BaseModel):
    repo: str | None = None
    branch: str
    improvement_type: str


class PushRequest(BaseModel):
    repo: str | None = None
    branch: str = "main"
    commit_message: str = "AI: Automated improvements"
    # গ্যাপ ফিক্স: আগে শুধু ফাইলের নাম (files_changed: list[str]) নেওয়া হতো এবং প্রতিটি ফাইলের
    # আসল কনটেন্ট না জেনেই "Optimized content placeholder" স্ট্রিং কমিট করে দেওয়া হতো — অর্থাৎ
    # এই এন্ডপয়েন্ট ইউজারের রিয়েল GitHub রিপোর প্রতিটি টার্গেট ফাইল ওভাররাইট করে ডেটা নষ্ট করত।
    # এখন কলারকে (real, reviewed) কনটেন্ট সরবরাহ করতেই হবে; খালি/অনুপস্থিত হলে ৪০০ এরর দিয়ে
    # fail-fast করা হয়, যাতে কখনোই fabricated কনটেন্ট রিয়েল রিপোতে কমিট না হয়।
    file_contents: dict[str, str]


class DiscoverRequest(BaseModel):
    requirement: str
    tech_stack: list[str]
    criteria: dict


class ImplementRequest(BaseModel):
    repo_url: str
    integration_method: str
    target_project: str


@router.post("/connect")
async def connect_repo(
    payload: ConnectRequest,
    db=Depends(get_tenant_db),
    user=Depends(get_current_user_token),
    sql_db=Depends(get_db_session),
):
    async with handle_github_errors("connect", f"{payload.repo_owner}/{payload.repo_name}"):
        agent = await _get_agent(user, sql_db)
        inst_id = payload.installation_id if payload.installation_id is not None else ""
        await agent.connect_repo(payload.repo_owner, payload.repo_name, inst_id)
        tenant_ref = db.tenant_root
        tenant_ref.set({"github_repo": f"{payload.repo_owner}/{payload.repo_name}"}, merge=True)
        return {
            "status": "success",
            "message": f"Connected to {payload.repo_owner}/{payload.repo_name}",
        }


@router.post("/improve")
async def improve_repo(
    payload: ImproveRequest,
    db=Depends(get_tenant_db),
    user=Depends(get_current_user_token),
    sql_db=Depends(get_db_session),
):
    async with handle_github_errors("improve", payload.repo):
        repo = _resolve_repo(payload.repo, db)
        agent = await _get_agent(user, sql_db)
        analysis = await agent.analyze_repo(repo)
        return {"status": "success", "analysis": analysis}


@router.post("/push")
async def push_improvements(
    payload: PushRequest,
    db=Depends(get_tenant_db),
    user=Depends(get_current_user_token),
    sql_db=Depends(get_db_session),
):
    async with handle_github_errors("push", payload.repo):
        if not payload.file_contents:
            raise HTTPException(
                status_code=400,
                detail=(
                    "file_contents is required — no automatic code-generation step is wired to this endpoint yet. "
                    "Supply the real, reviewed content for each file (path -> new content) to commit."
                ),
            )
        repo = _resolve_repo(payload.repo, db)
        agent = await _get_agent(user, sql_db)

        commit_res = await agent.commit_changes(
            repo, payload.file_contents, payload.commit_message, payload.branch
        )

        pr_title = "SupremeAI: Automated Code Improvements"
        pr_body = "AI has analyzed the repository and suggested changes.\n\nNote: Customer approval is required before merging."
        pr_res = await agent.create_pr(repo, pr_title, pr_body, payload.branch)

        return {
            "status": "success",
            "branch": commit_res["branch"],
            "pr_title": pr_title,
            "pr_url": pr_res["pr_url"],
            "message": "PR created successfully. Waiting for manual approval.",
        }


@router.post("/discover")
async def discover_repos(payload: DiscoverRequest):
    async with handle_github_errors("discover"):
        repos = repo_discovery_agent.discover_repos(
            payload.requirement, payload.tech_stack, payload.criteria
        )
        return {"status": "success", "repos": repos}


@router.post("/implement")
async def implement_repo(payload: ImplementRequest):
    async with handle_github_errors("implement", payload.repo_url):
        res = repo_discovery_agent.implement_repo(
            payload.repo_url, payload.integration_method, payload.target_project
        )
        return res


@router.get("/repos")
async def list_connected_repos(
    db=Depends(get_tenant_db),
    user=Depends(get_current_user_token),
    sql_db=Depends(get_db_session),
):
    profile = db.get_tenant_profile() or {}
    repo = profile.get("github_repo")
    if not repo:
        return []

    import httpx

    GITHUB_API_BASE = "https://api.github.com"
    agent = await _get_agent(user, sql_db)

    # FIX (perf): reuse shared httpx.AsyncClient from lifespan (50 keep-alive conns)
    # CONNLEAK-001 FIX: Fallback client was never closed → FD exhaustion.
    # Now: use async with for fallback client so it's always closed.
    client = global_http_client
    _fallback_client = None
    if client is None:
        import httpx

        _fallback_client = httpx.AsyncClient(timeout=10.0)
        client = _fallback_client
    try:
        resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{repo}",
            headers={
                "Authorization": f"Bearer {agent.token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
    finally:
        if _fallback_client:
            await _fallback_client.aclose()
    return [
        {
            "id": str(data["id"]),
            "name": data["name"],
            "branch": data["default_branch"],
            "updated": data["updated_at"],
            "commits": data.get("size", 0),
        }
    ]


@router.get("/repos/{repo_id}/commits")
async def list_repo_commits(
    repo_id: str,
    limit: int = 10,
    db=Depends(get_tenant_db),
    user=Depends(get_current_user_token),
    sql_db=Depends(get_db_session),
):
    profile = db.get_tenant_profile() or {}
    repo = profile.get("github_repo")
    if not repo:
        raise HTTPException(status_code=404, detail="No repository connected.")

    import httpx

    GITHUB_API_BASE = "https://api.github.com"
    agent = await _get_agent(user, sql_db)

    # FIX (perf): reuse shared httpx.AsyncClient from lifespan (same as /repos endpoint above)
    # CONNLEAK-001 FIX: Fallback client was never closed → FD exhaustion.
    client = global_http_client
    _fallback_client = None
    if client is None:
        import httpx

        _fallback_client = httpx.AsyncClient(timeout=10.0)
        client = _fallback_client
    try:
        resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{repo}/commits?per_page={limit}",
            headers={
                "Authorization": f"Bearer {agent.token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=10.0,
        )
        resp.raise_for_status()
    finally:
        if _fallback_client:
            await _fallback_client.aclose()
    return [
        {
            "hash": c["sha"][:7],
            "message": c["commit"]["message"].split("\n")[0],
            "author": c["commit"]["author"]["name"],
            "time": c["commit"]["author"]["date"],
        }
        for c in resp.json()
    ]
