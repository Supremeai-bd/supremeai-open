import base64
from datetime import datetime as dt

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging_config import logger
from core.security.security_vault import decrypt_token
from models.integration import Integration


async def get_user_github_token(user_id: str, db: AsyncSession) -> str | None:
    """
    DB থেকে ইউজারের এনক্রিপ্টেড GitHub টোকেন রিট্রিভ করে ডিক্রিপ্ট করে।
    টোকেন না পেলে None রিটার্ন করে — কলারকে fail-fast করতে হবে।

    ⚠️ FIX: AsyncSession.get() শুধুমাত্র primary key নেয়, dict ফিল্টার নয়।
    আগে db.get(Integration, {"user_id": ..., "provider": ...}) দিয়ে ArgumentError
    থ্রো করত। এখন select().where() ব্যবহার করা হচ্ছে।
    """
    stmt = select(Integration).where(
        Integration.user_id == user_id,
        Integration.provider == "github",
    )
    result = await db.execute(stmt)
    integration = result.scalar_one_or_none()
    if not integration or not integration.encrypted_access_token:
        logger.warning(f"No GitHub token found for user '{user_id}'")
        return None

    try:
        access_token = decrypt_token(integration.encrypted_access_token)
        return access_token
    except Exception as exc:
        logger.error(f"Failed to decrypt GitHub token for user '{user_id}': {exc}")
        return None


async def create_autonomous_pr(
    user_id: str,
    repo_name: str,
    file_path: str,
    code_content: str,
    commit_msg: str,
    db: AsyncSession | None = None,
):
    """
    এনক্রিপ্টেড টোকেন ডিক্রিপ্ট করে গিটহাবে নতুন ব্রাঞ্চ এবং PR তৈরি করবে।
    repo_name ফরম্যাট হতে হবে: "username/repo"

    db_session বাধ্যতামূলক — না দিলে fail-fast করে, যাতে কেউ ভুলে placeholder দিয়ে ডিপ্লয় করতে না পারে।
    """
    if db is None:
        raise RuntimeError(
            "create_autonomous_pr: db_session is required. Call with an active AsyncSession to fetch the GitHub token from DB."
        )

    access_token = await get_user_github_token(user_id, db)
    if access_token is None:
        raise RuntimeError(
            f"GitHub token not found or could not be decrypted for user '{user_id}'. Please connect GitHub via /integrations/github/link first."
        )

    agent = GitHubAgent(token=access_token)

    branch_name = f"supremeai-auto-fix-{dt.now().strftime('%Y%m%d%H%M%S')}"

    # Step 1: Commit the code
    files_to_commit = {file_path: code_content}
    await agent.commit_changes(repo_name, files_to_commit, commit_msg, branch_name)

    # Step 2: Create the Pull Request
    title = f"🚀 SupremeAI Auto-Fix: {commit_msg}"
    body = "This PR was autonomously generated and verified in the SupremeAI Zero-Cost Sandbox.\n\n- ✅ Execution Verified\n- 🧠 Saved to Memory Vault"
    pr_res = await agent.create_pr(repo_name, title, body, branch_name)

    return pr_res.get("pr_url")


class GitHubAgent:
    """Thin wrapper around the GitHub REST API. No mock/simulated responses —
    every method either performs the real call or raises."""

    def __init__(self, token: str | None = None):
        self.token = token or ""
        if not self.token:
            logger.warning("GitHubAgent initialized without a token; real API calls disabled.")

    def _headers(self) -> dict:
        if not self.token:
            raise RuntimeError("GitHub token is required for real API operations.")
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    async def connect_repo(
        self, repo_owner: str, repo_name: str, installation_id: str | None = None
    ) -> dict:
        """Verifies the repo is actually reachable with this token before 'connecting'."""
        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=self._headers())
        if resp.status_code == 404:
            raise ValueError(
                f"Repository {repo_owner}/{repo_name} not found or not accessible with this token."
            )
        resp.raise_for_status()
        return {
            "status": "success",
            "repo": f"{repo_owner}/{repo_name}",
            "default_branch": resp.json().get("default_branch"),
        }

    async def analyze_repo(self, repo_url: str) -> dict:
        """Real, lightweight repo metadata pull (open issues, language, size).
        Deep static-analysis scoring is NOT implemented yet — we report that
        honestly instead of returning a fabricated score."""
        url = f"https://api.github.com/repos/{repo_url}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        return {
            "status": "success",
            "repo": repo_url,
            "open_issues": data.get("open_issues_count"),
            "primary_language": data.get("language"),
            "default_branch": data.get("default_branch"),
            "code_quality_score": None,
            "note": "Static-analysis scoring available via CodeValidator when enabled.",
        }

    async def create_pr(
        self,
        repo_name: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
    ) -> dict:
        headers = self._headers()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"https://api.github.com/repos/{repo_name}/pulls",
                headers=headers,
                json={
                    "title": title,
                    "body": body,
                    "head": head_branch,
                    "base": base_branch,
                },
            )
        if resp.status_code != 201:
            raise RuntimeError(f"GitHub PR creation failed ({resp.status_code}): {resp.text}")
        pr = resp.json()
        logger.info(f"Real PR created: {pr['html_url']}")
        return {
            "status": "success",
            "pr_url": pr["html_url"],
            "pr_number": pr["number"],
        }

    async def commit_changes(
        self,
        repo_url: str,
        files_to_commit: dict[str, str],
        commit_message: str,
        branch: str,
    ) -> dict:
        """files_to_commit: {file_path: new_content}. Creates the branch if it
        doesn't exist, then commits each file for real via the Contents API."""
        headers = self._headers()
        base_url = f"https://api.github.com/repos/{repo_url}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            repo_info = await client.get(base_url, headers=headers)
            repo_info.raise_for_status()
            default_branch = repo_info.json()["default_branch"]

            ref = await client.get(f"{base_url}/git/refs/heads/{default_branch}", headers=headers)
            ref.raise_for_status()
            base_sha = ref.json()["object"]["sha"]

            branch_res = await client.post(
                f"{base_url}/git/refs",
                headers=headers,
                json={"ref": f"refs/heads/{branch}", "sha": base_sha},
            )
            if branch_res.status_code not in (
                201,
                422,
            ):  # 422 = branch already exists, acceptable
                raise RuntimeError(f"Failed to create branch: {branch_res.text}")

            last_sha = None
            for file_path, content in files_to_commit.items():
                encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
                commit_res = await client.put(
                    f"{base_url}/contents/{file_path}",
                    headers=headers,
                    json={
                        "message": commit_message,
                        "content": encoded,
                        "branch": branch,
                    },
                )
                if commit_res.status_code not in (200, 201):
                    raise RuntimeError(f"Failed to commit {file_path}: {commit_res.text}")
                last_sha = commit_res.json()["commit"]["sha"]

        return {
            "status": "success",
            "branch": branch,
            "commit_hash": last_sha,
            "files_committed": list(files_to_commit),
        }
