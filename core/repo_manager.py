"""SupremeAI 2.0 - Dynamic Repository & Workspace Manager.

Handles dynamic cloning, branch checkout, pulling, and scope-safe workspace isolation
for autonomous agents across 100+ platforms.

Key Capabilities:
- Workspace Isolation: Clones target repos into isolated directory structure.
- Scope Guard: Enforces READ_ONLY vs FULL_CONTROL permissions before executing git mutations.
- Multi-Repo Support: Manages parallel worktrees/workspaces for different target entities.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from core.config import settings
from core.logging_config import logger
from core.target_registry import TargetEntity, target_registry


class PermissionDeniedError(PermissionError):
    """READ_ONLY স্কোপে মডিফিকেশন বা রাইট চেষ্টা করা হলে এই এরর রেইজ হবে।"""

    pass


class DynamicRepoManager:
    """স্বায়ত্ত্বশাসিত এআই এজেন্টদের জন্য ডাইনামিক রেপো ও ওয়ার্কস্পেস ম্যানেজার।"""

    def __init__(self, workspace_base: Path | None = None) -> None:
        self.base_dir = workspace_base or Path(settings.workspace_base_dir)
        # বাংলা মন্তব্য: ওয়ার্কস্পেস গন্তব্য তৈরি নিশ্চিত করা
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def prepare_workspace(self, target: TargetEntity) -> Path:
        """টার্গেট রেপোর জন্য আইসোলেটেড ওয়ার্কস্পেস প্রস্তুত ও আপডেট করে।"""
        target_dir = self.base_dir / target.id
        target_dir.mkdir(parents=True, exist_ok=True)

        if not target.url or target.url.startswith("origin/"):
            # Local or main repository reference
            logger.info(f"Target '{target.id}' using local workspace: {target_dir}")
            return target_dir

        # Git clone or pull for remote targets
        if not (target_dir / ".git").exists():
            logger.info(f"Cloning target repository '{target.name}' to {target_dir}")
            clone_url = target.url
            if target.credentials_token and "https://" in clone_url:
                clone_url = clone_url.replace("https://", f"https://{target.credentials_token}@")

            cmd = ["git", "clone", "-b", target.branch, clone_url, str(target_dir)]
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
        else:
            logger.info(f"Updating workspace for target '{target.id}' ({target.branch})")
            subprocess.run(
                ["git", "-C", str(target_dir), "fetch", "origin"],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            subprocess.run(
                ["git", "-C", str(target_dir), "checkout", target.branch],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )

        return target_dir

    def execute_git_commit(self, target_id: str, commit_message: str) -> str:
        """পারমিশন স্কোপ ভ্যালিডেট করার পর টার্গেট ওয়ার্কস্পেসে Commit নির্বাহ করে।"""
        target = target_registry.get_target(target_id)
        if not target:
            raise KeyError(f"Target '{target_id}' not found")

        # বাংলা মন্তব্য: READ_ONLY স্কোপে কোনো প্রকার Commit নিষিদ্ধ
        if target.is_read_only():
            raise PermissionDeniedError(
                f"Cannot commit to target '{target_id}' because it has READ_ONLY permission scope."
            )

        target_dir = self.base_dir / target_id
        if not target_dir.exists():
            raise FileNotFoundError(f"Workspace for target '{target_id}' does not exist.")

        logger.info(f"Executing git commit on FULL_CONTROL target '{target_id}'")
        subprocess.run(
            ["git", "-C", str(target_dir), "add", "."],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        res = subprocess.run(
            ["git", "-C", str(target_dir), "commit", "-m", commit_message],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return res.stdout


# Singleton instance
repo_manager = DynamicRepoManager()
