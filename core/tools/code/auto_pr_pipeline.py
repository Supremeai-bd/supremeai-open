# backend/tools/code/auto_pr_pipeline.py
"""
SupremeAI Automated GitHub Pull Request (PR) Pipeline
বাংলা মন্তব্য: Guardian AI দিয়ে patch code যাচাই করে, isolated Git branch তৈরি করে,
এবং GitHubAgent-এর মাধ্যমে আসল GitHub Pull Request খোলে।
আগে hash(branch_name) % 1000 দিয়ে fake PR number তৈরি হতো — কোনো API call ছিল না।
এখন GitHubAgent সম্পূর্ণ real GitHub REST API call করে।
"""

import os
from typing import Any

from core.logging_config import logger
from core.security.intelligence.guardian_ai import guardian_ai


class AutoPRPipeline:
    """
    Automated PR generation pipeline for AI self-healing patches.
    বাংলা মন্তব্য: GitHubAgent-এর উপর নির্ভরশীল — duplicate code নেই।
    """

    def __init__(self, github_token: str | None = None, repo_name: str | None = None):
        # বাংলা মন্তব্য: আগে "mock-token" ছিল fallback — এখন token না থাকলে প্রোডাকশনে ব্যর্থ হবে
        self.github_token = github_token or os.getenv("GITHUB_TOKEN", "")
        self.repo_name = repo_name or os.getenv("GITHUB_REPOSITORY", "paykaribazaronline/supremeai")

    async def create_patch_pr(
        self,
        branch_name: str,
        file_path: str,
        patch_code: str,
        pr_title: str,
        pr_description: str,
    ) -> dict[str, Any]:
        """
        Guardian AI দিয়ে patch code যাচাই করে এবং real GitHub PR তৈরি করে।
        বাংলা মন্তব্য: আগে hash(branch_name) % 1000 দিয়ে fake PR URL তৈরি হতো।
        এখন GitHubAgent-এর real create_pr() এবং commit_changes() ব্যবহার করা হয়।
        """
        logger.info(
            f"🛡️ [Auto PR] Validating patch safety for '{file_path}' on branch '{branch_name}'..."
        )

        if not self.github_token:
            logger.error("AutoPRPipeline: No GitHub token configured. Set GITHUB_TOKEN.")
            return {
                "status": "failed",
                "reason": "GitHub token not configured. Set GITHUB_TOKEN environment variable.",
                "pr_url": None,
            }

        # ── 1. Guardian AI Safety Check ─────────────────────────────────────
        validation_result = await guardian_ai.scan_code(patch_code)
        if not validation_result.get("is_safe", True):
            reason = validation_result.get("reason", "Unknown safety violation")
            logger.error(f"❌ [Auto PR] Guardian AI rejected patch for '{branch_name}': {reason}")
            return {
                "status": "failed",
                "reason": f"Guardian AI rejected patch: {reason}",
                "pr_url": None,
            }

        # ── 2. Real GitHub PR via GitHubAgent ────────────────────────────────
        logger.info(
            f"🚀 [Auto PR] Creating real branch '{branch_name}' and PR on '{self.repo_name}'..."
        )
        try:
            from tools.devops.github_agent import GitHubAgent

            agent = GitHubAgent(token=self.github_token)

            # বাংলা মন্তব্য: ফাইল কমিট করা হচ্ছে নতুন branch-এ
            files_to_commit = {file_path: patch_code}
            commit_msg = f"fix: {pr_title}"
            await agent.commit_changes(self.repo_name, files_to_commit, commit_msg, branch_name)

            # বাংলা মন্তব্য: আসল PR তৈরি করা হচ্ছে GitHub API-এ
            pr_result = await agent.create_pr(
                repo_name=self.repo_name,
                title=pr_title,
                body=pr_description,
                head_branch=branch_name,
            )

            pr_url = pr_result.get("pr_url")
            pr_number = pr_result.get("pr_number")

            logger.info(f"✅ [Auto PR] PR #{pr_number} created: {pr_url}")
            return {
                "status": "success",
                "branch_name": branch_name,
                "pr_number": pr_number,
                "pr_url": pr_url,
                "title": pr_title,
                "target_file": file_path,
            }

        except Exception as exc:
            logger.error(f"❌ [Auto PR] GitHub PR creation failed: {exc}")
            return {
                "status": "failed",
                "reason": str(exc),
                "pr_url": None,
            }
