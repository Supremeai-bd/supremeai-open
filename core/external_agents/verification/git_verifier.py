"""
backend/external_agents/verification/git_verifier.py
====================================================
ISSUE-1575 (Part 6): the Git Verifier.

* Checks out an ISOLATED ``git worktree`` for the task branch — the main
  working directory is never touched by verification.
* Runs local automated checks (pytest / linters / type checks — the default
  set is pytest + ruff, extensible via ``checks``).
* On failure, packages everything into a structured :class:`FailureContext`
  and feeds it to the coder repair callback — BOUNDED at
  ``max_repair_rounds`` (3) so the loop can never run away.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from external_agents.contracts.code_artifact import CodeArtifact

__all__ = ["CheckResult", "FailureContext", "GitVerifier", "VerificationReport", "default_checks"]

RepairFn = Callable[["FailureContext"], Any]
CheckFn = Callable[[Path], "CheckResult"]
MAX_REPAIR_ROUNDS = 3


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CheckResult(BaseModel):
    name: str
    passed: bool
    exit_code: int = 0
    output: str = ""


class FailureContext(BaseModel):
    """Structured feedback handed back to the coder agent for repair."""

    task_id: str
    attempt: int
    stage: Literal["tests", "lint", "types", "boundary", "setup"]
    failed_check: str
    command: str = ""
    exit_code: int = 0
    summary: str
    output_tail: str = Field(default="", description="Last chunk of failing output")
    created_at: datetime = Field(default_factory=_utcnow)


class VerificationReport(BaseModel):
    task_id: str
    branch: str
    status: Literal["PASS", "FAILED", "BOUNDARY_FAILED"]
    rounds_used: int
    checks: list[CheckResult] = Field(default_factory=list)
    failure_contexts: list[FailureContext] = Field(default_factory=list)
    worktree_path: str | None = None
    finished_at: datetime = Field(default_factory=_utcnow)


def _run(cmd: list[str], cwd: Path, timeout: int = 600) -> CheckResult:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return CheckResult(
            name=cmd[0] if cmd else "check",
            passed=proc.returncode == 0,
            exit_code=proc.returncode,
            output=(proc.stdout + proc.stderr)[-40_000:],
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name=cmd[0] if cmd else "check", passed=False, exit_code=-1, output="timeout"
        )


def default_checks(python: str | None = None) -> list[CheckFn]:
    """Default automated check set: pytest (fast, no cov) + ruff static gate."""
    py = python or sys.executable

    def pytest_check(worktree: Path) -> CheckResult:
        return _run([py, "-m", "pytest", "-q", "--no-cov", "-p", "no:cacheprovider"], worktree)

    def ruff_check(worktree: Path) -> CheckResult:
        result = _run(
            [py, "-m", "ruff", "check", "backend", "--select", "E9,F821,F822,F823"],
            worktree,
        )
        result.name = "ruff"
        return result

    return [pytest_check, ruff_check]


class GitVerifier:
    """Worktree-isolated, bounded-repair verification of a task changeset."""

    def __init__(
        self,
        repo_root: Path | str | None = None,
        worktree_parent: Path | str | None = None,
        checks: list[CheckFn] | None = None,
        max_repair_rounds: int = MAX_REPAIR_ROUNDS,
        boundary_roots: list[str] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()
        self.worktree_parent = (
            Path(worktree_parent) if worktree_parent else Path(tempfile.gettempdir())
        )
        self.checks = checks or default_checks()
        self.max_repair_rounds = max_repair_rounds
        self.boundary_roots = boundary_roots

    # ------------------------------------------------------------------
    # Worktree lifecycle — isolation from the main working directory
    # ------------------------------------------------------------------
    def _create_worktree(self, branch: str) -> Path:
        path = self.worktree_parent / f"verify-{uuid.uuid4().hex[:10]}"
        result = subprocess.run(
            ["git", "-C", str(self.repo_root), "worktree", "add", str(path), branch],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"worktree add failed for '{branch}': {result.stderr.strip()}")
        return path

    def _cleanup_worktree(self, path: Path) -> None:
        subprocess.run(
            ["git", "-C", str(self.repo_root), "worktree", "remove", "--force", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        shutil.rmtree(path, ignore_errors=True)  # belt & braces — no leftovers

    # ------------------------------------------------------------------
    def verify(
        self, artifact: CodeArtifact, repair_fn: RepairFn | None = None
    ) -> VerificationReport:
        """Verify ``artifact`` in an isolated worktree with bounded repair.

        ``repair_fn`` receives the :class:`FailureContext` and applies fixes
        (the coder agent's self-healing callback). The loop is HARD-BOUNDED
        at ``max_repair_rounds``.
        """
        worktree: Path | None = None
        failure_contexts: list[FailureContext] = []
        all_checks: list[CheckResult] = []
        rounds_used = 0
        status: Literal["PASS", "FAILED", "BOUNDARY_FAILED"] = "FAILED"

        # Boundary validation happens BEFORE any check runs (fail fast).
        if self.boundary_roots:
            from external_agents.verification.artifact_bridge import ArtifactBridge

            report = ArtifactBridge(self.repo_root).validate_boundaries(
                artifact, self.boundary_roots
            )
            if not report.ok:
                return VerificationReport(
                    task_id=artifact.task_id,
                    branch=artifact.branch,
                    status="BOUNDARY_FAILED",
                    rounds_used=0,
                    failure_contexts=[
                        FailureContext(
                            task_id=artifact.task_id,
                            attempt=0,
                            stage="boundary",
                            failed_check="resource_boundary",
                            summary=report.reason,
                            output_tail="\n".join(report.offending_files),
                        )
                    ],
                )

        try:
            worktree = self._create_worktree(artifact.branch)
            max_attempts = 1 + self.max_repair_rounds  # initial + bounded repairs
            for attempt in range(1, max_attempts + 1):
                rounds_used = attempt
                round_checks = [check(worktree) for check in self.checks]
                all_checks.extend(round_checks)
                failed = next((c for c in round_checks if not c.passed), None)
                if failed is None:
                    status = "PASS"
                    break
                context = FailureContext(
                    task_id=artifact.task_id,
                    attempt=attempt,
                    stage="tests" if failed.name.startswith("pytest") else "lint",
                    failed_check=failed.name,
                    exit_code=failed.exit_code,
                    summary=f"check '{failed.name}' failed (attempt {attempt}/{max_attempts})",
                    output_tail=failed.output[-8_000:],
                )
                failure_contexts.append(context)
                if attempt == max_attempts:
                    status = "FAILED"  # bounded — no runaway retries
                    break
                if repair_fn is not None:
                    # The coder repairs INSIDE the isolated worktree.
                    repair_fn(context)
                else:
                    status = "FAILED"
                    break
            else:  # pragma: no cover - loop always breaks above
                status = "FAILED"
        except Exception as exc:
            failure_contexts.append(
                FailureContext(
                    task_id=artifact.task_id,
                    attempt=rounds_used,
                    stage="setup",
                    failed_check="worktree",
                    summary=str(exc),
                )
            )
            status = "FAILED"
        finally:
            if worktree is not None:
                self._cleanup_worktree(worktree)

        return VerificationReport(
            task_id=artifact.task_id,
            branch=artifact.branch,
            status=status,
            rounds_used=rounds_used,
            checks=all_checks,
            failure_contexts=failure_contexts,
        )
