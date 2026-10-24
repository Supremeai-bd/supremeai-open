"""
backend/external_agents/contracts/code_artifact.py
==================================================
ISSUE-1572 (Part 3): changeset metadata schema — what a coder agent claims
to have produced (branch, commit, files, diff), consumed by the verification
layer (#1575 artifact bridge).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["ChangedFile", "CodeArtifact"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ChangedFile(BaseModel):
    path: str
    change_type: str = Field(description="added | modified | deleted | renamed")
    additions: int = 0
    deletions: int = 0


class CodeArtifact(BaseModel):
    """Changeset metadata for a completed coder job."""

    task_id: str
    branch: str = Field(min_length=1)
    commit_sha: str = Field(min_length=1)
    base_branch: str = "main"
    changed_files: list[ChangedFile] = Field(default_factory=list)
    diff: str = Field(default="", description="Unified diff of the changeset")
    provider: str | None = None
    run_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    extra: dict[str, Any] = Field(default_factory=dict)

    def touched_paths(self) -> list[str]:
        return [f.path for f in self.changed_files]

    def violates_scope(self, allowed_roots: list[str]) -> list[str]:
        """Files outside the declared task scope (artifact bridge #1575 uses this)."""
        if not allowed_roots:
            return []
        normalised_roots = [r.rstrip("/") for r in allowed_roots if r]
        offending: list[str] = []
        for path in self.touched_paths():
            if not any(path == root or path.startswith(root + "/") for root in normalised_roots):
                offending.append(path)
        return offending
