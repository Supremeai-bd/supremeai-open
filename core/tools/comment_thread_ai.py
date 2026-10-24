"""
CommentThreadAI — Real Implementation
Handles GitHub PR/issue comment threads:
1. Auto-summarize long threads
2. Propose code fix from reviewer comment
3. Post AI reply back to GitHub
4. Detect stale/blocked PRs
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from core.config import settings
from core.logging_config import logger

router = APIRouter(prefix="/comment-ai", tags=["comment-thread-ai"])

GITHUB_API = "https://api.github.com"
_GITHUB_TOKEN = getattr(settings, "github_token", "")


# ── Pydantic models ───────────────────────────────────────────────────────────


class PRCommentPayload(BaseModel):
    repo_full_name: str  # e.g. "owner/repo"
    pr_number: int
    comment_body: str
    file_path: str | None = None
    line_number: int | None = None
    comment_id: int | None = None
    auto_reply: bool = True  # post reply to GitHub?


class ThreadSummaryRequest(BaseModel):
    repo_full_name: str
    pr_number: int | None = None
    issue_number: int | None = None


class CommentThreadAI:
    def __init__(self, github_token: str | None = None):
        self.token = github_token or _GITHUB_TOKEN
        self._headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        logger.info(
            f"CommentThreadAI initialized (GitHub token: {'set' if self.token else 'MISSING'})"
        )

    # ── LLM call ─────────────────────────────────────────────────────────────
    async def _llm(self, prompt: str, task_type: str = "coding", max_cost: float = 0.02) -> str:
        try:
            from brain.model_router import ModelRouter

            r = ModelRouter()
            result = await r.async_route_and_generate(
                prompt, task_type=task_type, max_cost=max_cost
            )
            return result.get("text", "") if isinstance(result, dict) else str(result)
        except Exception as exc:
            logger.error(f"LLM call failed: {exc}")
            return ""

    # ── GitHub API helpers ────────────────────────────────────────────────────
    async def _gh_get(self, path: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{GITHUB_API}{path}", headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    async def _gh_post(self, path: str, body: dict) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{GITHUB_API}{path}", headers=self._headers, json=body)
        resp.raise_for_status()
        return resp.json()

    async def _get_pr_comments(self, repo: str, pr_number: int) -> list[dict]:
        """Fetch all review + issue comments on a PR."""
        comments = []
        try:
            # Review comments (line-level)
            review = await self._gh_get(f"/repos/{repo}/pulls/{pr_number}/comments")
            comments.extend(review if isinstance(review, list) else [])
        except Exception as e:
            logger.error(f"Failed to get PR review comments for {repo}#{pr_number}: {e}")
        try:
            # Issue comments (general PR comments)
            issue = await self._gh_get(f"/repos/{repo}/issues/{pr_number}/comments")
            comments.extend(issue if isinstance(issue, list) else [])
        except Exception as e:
            logger.error(f"Failed to get PR issue comments for {repo}#{pr_number}: {e}")
        return comments

    async def _get_pr_files(self, repo: str, pr_number: int) -> list[dict]:
        try:
            return await self._gh_get(f"/repos/{repo}/pulls/{pr_number}/files")  # type: ignore
        except Exception as e:
            logger.error(f"Failed to get PR files for {repo}#{pr_number}: {e}")
            return []

    async def _post_pr_comment(self, repo: str, pr_number: int, body: str) -> dict[str, Any]:
        """Post a general comment on a PR."""
        if not self.token:
            return {"status": "skipped", "reason": "No GitHub token"}
        try:
            result = await self._gh_post(
                f"/repos/{repo}/issues/{pr_number}/comments", {"body": body}
            )
            logger.info(f"Posted comment on {repo}#{pr_number}")
            return {"status": "success", "comment_url": result.get("html_url")}
        except Exception as exc:
            logger.error(f"GitHub post comment failed: {exc}")
            return {"status": "error", "error": str(exc)}

    async def _reply_to_review_comment(
        self, repo: str, pr_number: int, comment_id: int, body: str
    ) -> dict[str, Any]:
        """Reply to a specific review comment thread."""
        if not self.token:
            return {"status": "skipped", "reason": "No GitHub token"}
        try:
            result = await self._gh_post(
                f"/repos/{repo}/pulls/{pr_number}/comments/{comment_id}/replies",
                {"body": body},
            )
            return {"status": "success", "reply_url": result.get("html_url")}
        except Exception as exc:
            logger.error(f"Reply to review comment failed: {exc}")
            return {"status": "error", "error": str(exc)}

    # ── Core functions ────────────────────────────────────────────────────────

    async def handle_pr_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        comment_body: str,
        file_path: str | None = None,
        line_number: int | None = None,
        comment_id: int | None = None,
        auto_reply: bool = True,
    ) -> dict[str, Any]:
        """
        Process a PR review comment:
        1. Generate a code fix
        2. Explain the reasoning
        3. Optionally post reply to GitHub
        """
        logger.info(
            f"Handling PR comment: {repo_full_name}#{pr_number} file={file_path}:{line_number}"
        )

        location = ""
        if file_path:
            location = f"\nFile: {file_path}"
            if line_number:
                location += f", Line {line_number}"

        prompt = (
            "You are a senior software engineer responding to a code review comment. "
            "Your job is:\n"
            "1. Understand what the reviewer is asking\n"
            "2. Propose a minimal, correct code fix\n"
            "3. Briefly explain WHY this change is needed\n\n"
            f"Repository: {repo_full_name}\n"
            f"PR: #{pr_number}{location}\n"
            f"Reviewer Comment: {comment_body}\n\n"
            "Format your response as:\n"
            "**Fix:**\n```\n<replacement code>\n```\n\n"
            "**Reason:** <one-line explanation>\n\n"
            "Keep it concise and professional."
        )

        ai_response = await self._llm(prompt, task_type="coding", max_cost=0.03)
        if not ai_response:
            return {"status": "error", "error": "LLM returned empty response"}

        result: dict[str, Any] = {
            "status": "success",
            "repo": repo_full_name,
            "pr_number": pr_number,
            "action": "code_fix_proposed",
            "proposed_fix": ai_response,
            "comment_posted": False,
        }

        if auto_reply and self.token:
            reply_body = f"🤖 **SupremeAI Auto-Response**\n\n{ai_response}\n\n---\n*Generated by SupremeAI. Please review before applying.*"
            if comment_id:
                post_result = await self._reply_to_review_comment(
                    repo_full_name, pr_number, comment_id, reply_body
                )
            else:
                post_result = await self._post_pr_comment(repo_full_name, pr_number, reply_body)

            result["comment_posted"] = post_result.get("status") == "success"
            result["comment_url"] = post_result.get("comment_url") or post_result.get("reply_url")

        return result

    async def summarize_thread(
        self,
        repo_full_name: str,
        pr_number: int | None = None,
        issue_number: int | None = None,
    ) -> dict[str, Any]:
        """Fetch all comments and produce an AI summary of the discussion."""
        target_number = pr_number or issue_number
        if not target_number:
            return {"status": "error", "error": "Provide pr_number or issue_number"}

        try:
            comments = await self._get_pr_comments(repo_full_name, target_number)
        except Exception as exc:
            return {"status": "error", "error": f"GitHub API failed: {exc}"}

        if not comments:
            return {
                "status": "success",
                "summary": "No comments found on this PR/issue.",
            }

        thread_text = "\n\n".join(
            [
                f"[{c.get('user', {}).get('login', 'unknown')}]: {c.get('body', '')[:500]}"
                for c in comments[:30]  # cap at 30 comments
            ]
        )

        prompt = (
            f"Summarize this GitHub PR/issue discussion thread.\n"
            f"Repository: {repo_full_name}, #: {target_number}\n\n"
            f"Thread:\n{thread_text}\n\n"
            "Provide:\n"
            "1. **Main topic** (1 sentence)\n"
            "2. **Key concerns raised** (bullet points)\n"
            "3. **Current status** (resolved / blocked / in-progress)\n"
            "4. **Recommended next action** (1 sentence)\n"
            "Be concise."
        )

        summary = await self._llm(prompt, task_type="reasoning", max_cost=0.03)
        return {
            "status": "success",
            "repo": repo_full_name,
            "target": f"#{target_number}",
            "comment_count": len(comments),
            "summary": summary,
        }

    async def detect_stale_prs(
        self, repo_full_name: str, days_threshold: int = 7
    ) -> dict[str, Any]:
        """Find PRs with no activity in N days."""
        try:
            prs = await self._gh_get(f"/repos/{repo_full_name}/pulls?state=open&per_page=50")
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

        import datetime

        now = datetime.datetime.now(datetime.UTC)
        stale = []
        for pr in prs if isinstance(prs, list) else []:
            updated = pr.get("updated_at", "")
            if updated:
                try:
                    dt = datetime.datetime.strptime(updated, "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=datetime.UTC
                    )
                    days_idle = (now - dt).days
                    if days_idle >= days_threshold:
                        stale.append(
                            {
                                "number": pr["number"],
                                "title": pr.get("title", ""),
                                "author": pr.get("user", {}).get("login", ""),
                                "days_idle": days_idle,
                                "url": pr.get("html_url", ""),
                            }
                        )
                except Exception as e:
                    try:
                        import loguru

                        loguru.logger.error(f"Tool execution error: {e}")
                    except Exception as e:
                        logger.warning(f"Exception suppressed: {e}")
                    pass

        return {
            "status": "success",
            "repo": repo_full_name,
            "stale_threshold_days": days_threshold,
            "stale_pr_count": len(stale),
            "stale_prs": sorted(stale, key=lambda x: x["days_idle"], reverse=True),
        }

    async def handle_github_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Process GitHub webhook events for PR comments."""
        action = payload.get("action", "")
        (
            "pr_review_comment"
            if "pull_request_review_comment" in str(payload.keys())
            else "issue_comment"
        )

        if action not in ("created", "edited"):
            return {"status": "ignored", "action": action}

        comment = payload.get("comment", {})
        comment_body = comment.get("body", "")

        # Only respond if comment mentions @supremeai or contains trigger keywords
        triggers = [
            "@supremeai",
            "fix this",
            "suggest a fix",
            "auto-fix",
            "what should",
        ]
        should_respond = any(t.lower() in comment_body.lower() for t in triggers)

        if not should_respond:
            return {"status": "ignored", "reason": "No trigger keyword found"}

        repo = payload.get("repository", {}).get("full_name", "")
        pr = payload.get("pull_request", {}) or payload.get("issue", {})
        pr_number = pr.get("number")

        if not repo or not pr_number:
            return {"status": "error", "error": "Missing repo or PR number in webhook"}

        file_path = comment.get("path")
        line_number = comment.get("line") or comment.get("original_line")
        comment_id = comment.get("id")

        return await self.handle_pr_comment(
            repo_full_name=repo,
            pr_number=pr_number,
            comment_body=comment_body,
            file_path=file_path,
            line_number=line_number,
            comment_id=comment_id,
            auto_reply=True,
        )


# ── Singleton ─────────────────────────────────────────────────────────────────
_comment_ai = CommentThreadAI()


# ── REST Endpoints ────────────────────────────────────────────────────────────


@router.post("/handle-comment")
async def handle_comment(payload: PRCommentPayload):
    """Handle a PR review comment — propose fix and optionally auto-reply."""
    return await _comment_ai.handle_pr_comment(
        repo_full_name=payload.repo_full_name,
        pr_number=payload.pr_number,
        comment_body=payload.comment_body,
        file_path=payload.file_path,
        line_number=payload.line_number,
        comment_id=payload.comment_id,
        auto_reply=payload.auto_reply,
    )


@router.post("/summarize")
async def summarize_thread(request: ThreadSummaryRequest):
    """Summarize a GitHub PR/issue comment thread with AI."""
    return await _comment_ai.summarize_thread(
        repo_full_name=request.repo_full_name,
        pr_number=request.pr_number,
        issue_number=request.issue_number,
    )


@router.get("/stale-prs/{owner}/{repo}")
async def detect_stale(owner: str, repo: str, days: int = 7):
    """Find PRs with no activity in N days."""
    return await _comment_ai.detect_stale_prs(f"{owner}/{repo}", days)


@router.post("/webhook")
async def github_webhook(request: Request, x_github_event: str = Header(default="ping")):
    """GitHub webhook receiver for PR comment events."""
    if x_github_event == "ping":
        return {"status": "pong"}
    try:
        payload = await request.json()
    except Exception as e:
        try:
            import loguru

            loguru.logger.error(f"Tool execution error: {e}")
        except Exception as e:
            logger.warning(f"Exception suppressed: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from e

    if x_github_event not in ("pull_request_review_comment", "issue_comment"):
        return {"status": "ignored", "event": x_github_event}

    return await _comment_ai.handle_github_webhook(payload)
