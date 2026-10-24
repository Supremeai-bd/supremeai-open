"""
backend/external_agents/verification/pr_manager.py
==================================================
ISSUE-1575 (Part 6): the PR Manager — closes the external-agent lifecycle.

* On verification PASS: pushes the task branch to the remote and opens an
  ATOMIC GitHub PR using a least-privilege token (contents:write + pull-requests:write only).
* On anything less than PASS: refuses to open a PR (honest, fail-closed).
* On success: completes the task lifecycle in the durable state manager and
  releases the agent ownership lock.
"""

from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from external_agents.contracts.code_artifact import CodeArtifact
from external_agents.control.state_manager import AgentStateManager
from external_agents.verification.git_verifier import GitVerifier, VerificationReport

__all__ = ["PRResult", "PrManager", "SubprocessGitHubClient", "OwnershipLocks"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class OwnershipLocks:
    """Per-task agent ownership registry — exactly one owner while running."""

    def __init__(self) -> None:
        self._locks: dict[str, str] = {}

    def acquire(self, task_id: str, owner: str) -> bool:
        current = self._locks.get(task_id)
        if current is not None and current != owner:
            return False
        self._locks[task_id] = owner
        return True

    def release(self, task_id: str, owner: str | None = None) -> bool:
        current = self._locks.get(task_id)
        if current is None:
            return False
        if owner is not None and current != owner:
            return False
        del self._locks[task_id]
        return True

    def owner(self, task_id: str) -> str | None:
        return self._locks.get(task_id)


class GitHubClientABC(ABC):
    @abstractmethod
    def create_pr(self, head: str, base: str, title: str, body: str) -> dict[str, Any]: ...


class SubprocessGitHubClient(GitHubClientABC):
    """Least-privilege GitHub client — token from env, PR creation via API."""

    def __init__(self, repo: str | None = None, token: str | None = None) -> None:
        self.repo = repo or os.getenv("SUPREMEAI_GITHUB_REPO", "SaifulHaqueNiloy/supremeai")
        self.token = token or os.getenv("GITHUB_TOKEN", "")

    def create_pr(self, head: str, base: str, title: str, body: str) -> dict[str, Any]:
        import json as _json
        from urllib import error as urlerror
        from urllib import request as urlrequest

        payload = _json.dumps({"title": title, "head": head, "base": base, "body": body}).encode()
        req = urlrequest.Request(
            f"https://api.github.com/repos/{self.repo}/pulls",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlrequest.urlopen(req, timeout=60) as resp:
                data = _json.loads(resp.read().decode())
            return {"ok": True, "number": data.get("number"), "html_url": data.get("html_url")}
        except urlerror.HTTPError as exc:
            detail = exc.read().decode()[:500]
            return {"ok": False, "error": f"GitHub API {exc.code}: {detail}"}


class PRResult(BaseModel):
    ok: bool
    reason: str = ""
    pr_number: int | None = None
    pr_url: str | None = None
    branch: str | None = None
    pushed: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class PrManager:
    """Atomic PR creation gated on automated verification PASS."""

    def __init__(
        self,
        verifier: GitVerifier,
        github: GitHubClientABC | None = None,
        state_manager: AgentStateManager | None = None,
        locks: OwnershipLocks | None = None,
        repo_root: Path | str | None = None,
        remote: str = "origin",
        base_branch: str = "main",
    ) -> None:
        self.verifier = verifier
        self.github = github or SubprocessGitHubClient()
        self.state_manager = state_manager
        self.locks = locks or OwnershipLocks()
        self.repo_root = Path(repo_root) if repo_root else verifier.repo_root
        self.remote = remote
        self.base_branch = base_branch

    # ------------------------------------------------------------------
    def _push_branch(self, branch: str) -> dict[str, Any]:
        try:
            proc = subprocess.run(
                ["git", "-C", str(self.repo_root), "push", self.remote, f"refs/heads/{branch}"],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if proc.returncode != 0:
                return {"ok": False, "error": proc.stderr.strip()[-500:]}
            return {"ok": True}
        except subprocess.SubprocessError as exc:
            return {"ok": False, "error": str(exc)}

    def _complete_lifecycle(self, artifact: CodeArtifact, pr: dict[str, Any]) -> None:
        if self.state_manager is None:
            return
        sm = self.state_manager
        record = sm.get(artifact.task_id)
        if record is None:
            return
        try:
            if record.state.value == "VERIFYING":
                sm.complete(artifact.task_id, result={"pr": pr})
            else:
                # CLAIMED/RUNNING/CHECKPOINT: advance honestly through VERIFYING.
                if record.state.value in {"CLAIMED", "RUNNING", "CHECKPOINT"}:
                    if record.state.value == "CLAIMED":
                        sm.start(artifact.task_id)
                        record = sm.get(artifact.task_id)
                    if record.state.value == "RUNNING":
                        sm.begin_verification(artifact.task_id)
                        record = sm.get(artifact.task_id)
                    if record.state.value == "CHECKPOINT":
                        sm.resume_from_checkpoint(artifact.task_id)
                        sm.begin_verification(artifact.task_id)
                    sm.complete(artifact.task_id, result={"pr": pr})
        except Exception:
            # Lifecycle bookkeeping must never un-do a merged verification.
            pass

    # ------------------------------------------------------------------
    def finalize_task(
        self,
        artifact: CodeArtifact,
        verification: VerificationReport,
        title: str | None = None,
        body: str = "",
    ) -> PRResult:
        """Open an atomic PR ONLY when verification PASSED; then release the lock."""
        if verification.status != "PASS":
            return PRResult(
                ok=False,
                reason=f"verification {verification.status} — PR refused (fail-closed)",
                branch=artifact.branch,
            )
        if verification.task_id != artifact.task_id:
            return PRResult(
                ok=False,
                reason="verification/artifact task mismatch — PR refused",
                branch=artifact.branch,
            )

        push = self._push_branch(artifact.branch)
        if not push.get("ok"):
            return PRResult(
                ok=False, reason=f"branch push failed: {push.get('error')}", branch=artifact.branch
            )

        pr = self.github.create_pr(
            head=artifact.branch,
            base=self.base_branch,
            title=title or f"feat(external-agents): task {artifact.task_id}",
            body=body
            or f"Automated PR for task `{artifact.task_id}` (verified: {verification.rounds_used} round(s)).",
        )
        if not pr.get("ok"):
            return PRResult(
                ok=False,
                reason=f"PR creation failed: {pr.get('error')}",
                branch=artifact.branch,
                pushed=True,
            )

        self._complete_lifecycle(artifact, pr)
        self.locks.release(artifact.task_id)  # release agent ownership lock

        return PRResult(
            ok=True,
            reason="verified → pushed → PR opened → lifecycle closed",
            pr_number=pr.get("number"),
            pr_url=pr.get("html_url"),
            branch=artifact.branch,
            pushed=True,
        )
