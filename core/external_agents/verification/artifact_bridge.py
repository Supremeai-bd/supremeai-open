"""
backend/external_agents/verification/artifact_bridge.py
=======================================================
ISSUE-1575 (Part 6): the Artifact Bridge — translates completed coder agent
jobs into verifiable git changesets.

* Extracts branch references, commit SHAs, patch diffs and changed-file
  lists from the repository (real git data, never agent claims).
* Enforces RESOURCE BOUNDARY validation: every touched file must live
  inside the declared task scope — anything outside fails the report.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from external_agents.contracts.code_artifact import ChangedFile, CodeArtifact

__all__ = ["ArtifactBridge", "BoundaryReport"]


class BoundaryReport(BaseModel):
    ok: bool
    allowed_roots: list[str] = Field(default_factory=list)
    offending_files: list[str] = Field(default_factory=list)
    reason: str = ""


class ArtifactBridge:
    """Extracts REAL git changesets and validates task-scope boundaries."""

    def __init__(self, repo_root: Path | str | None = None) -> None:
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()

    # ------------------------------------------------------------------
    def _git(self, *args: str, check: bool = True) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo_root), *args],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout

    # ------------------------------------------------------------------
    def extract_artifact(
        self,
        task_id: str,
        branch: str,
        base: str = "main",
        allowed_roots: list[str] | None = None,
        provider: str | None = None,
    ) -> CodeArtifact:
        """Read the REAL changeset for ``branch`` vs ``base`` from git."""
        commit_sha = self._git("rev-parse", "--verify", branch).strip()  # raises if missing
        merge_base = self._git("merge-base", base, branch).strip()

        name_status = self._git("diff", "--name-status", merge_base, branch)
        numstat = self._git("diff", "--numstat", merge_base, branch)
        diff = self._git("diff", merge_base, branch)

        changed: dict[str, ChangedFile] = {}
        for line in name_status.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            status_code = parts[0][0]
            path = parts[-1]
            changed[path] = ChangedFile(path=path, change_type=status_code)

        for line in numstat.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue  # e.g. malformed line
            adds, dels, path = parts[0], parts[1], "\t".join(parts[2:])
            if path in changed:
                # binary files show "-" — treat as 0
                changed[path].additions = int(adds) if adds.isdigit() else 0
                changed[path].deletions = int(dels) if dels.isdigit() else 0

        artifact = CodeArtifact(
            task_id=task_id,
            branch=branch,
            commit_sha=commit_sha,
            base_branch=base,
            changed_files=sorted(changed.values(), key=lambda f: f.path),
            diff=diff[-500_000:],
            provider=provider,
        )
        if allowed_roots is not None:
            report = self.validate_boundaries(artifact, allowed_roots)
            artifact.extra["boundary_ok"] = report.ok
            artifact.extra["boundary_offenders"] = report.offending_files
        return artifact

    # ------------------------------------------------------------------
    def validate_boundaries(
        self, artifact: CodeArtifact, allowed_roots: list[str]
    ) -> BoundaryReport:
        """Fail-closed resource boundary validation (issue scope item 2)."""
        if not allowed_roots:
            return BoundaryReport(
                ok=True, allowed_roots=[], reason="no scope declared (unrestricted)"
            )
        offending = artifact.violates_scope(allowed_roots)
        if offending:
            return BoundaryReport(
                ok=False,
                allowed_roots=allowed_roots,
                offending_files=offending,
                reason=f"{len(offending)} file(s) outside the declared task scope",
            )
        return BoundaryReport(
            ok=True, allowed_roots=allowed_roots, reason="all files within declared scope"
        )
