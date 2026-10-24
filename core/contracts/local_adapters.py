"""Deterministic local adapters for offline contract verification."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from .adapters import Artifact, ArtifactKind, validate_artifact
from .canonical import ExecutionContext
from .security_policy import SandboxMode, validate_workspace_path


@dataclass
class LocalArtifactStore:
    artifacts: dict[str, bytes] = field(default_factory=dict)
    metadata: dict[str, Artifact] = field(default_factory=dict)

    def put(
        self, context: ExecutionContext, name: str, content: bytes, kind: ArtifactKind
    ) -> Artifact:
        content_type, size, digest = validate_artifact(name, content)
        artifact = Artifact(
            f"artifact_{uuid.uuid4().hex}", context, name, content_type, size, digest, kind
        )
        self.artifacts[artifact.artifact_id] = bytes(content)
        self.metadata[artifact.artifact_id] = artifact
        return artifact

    def get(self, context: ExecutionContext, artifact_id: str) -> bytes:
        artifact = self.metadata.get(artifact_id)
        if artifact is None or artifact.context.tenant_id != context.tenant_id:
            raise KeyError(artifact_id)
        return self.artifacts[artifact_id]


@dataclass
class LocalTaskAdapter:
    tasks: dict[str, dict] = field(default_factory=dict)

    def enqueue(self, context: ExecutionContext, task_type: str, payload: dict) -> str:
        task_id = f"task_{uuid.uuid4().hex}"
        self.tasks[task_id] = {
            "tenant_id": context.tenant_id,
            "type": task_type,
            "payload": payload,
            "state": "queued",
        }
        return task_id

    def cancel(self, context: ExecutionContext, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if task is None or task["tenant_id"] != context.tenant_id:
            raise KeyError(task_id)
        if task["state"] == "completed":
            raise ValueError("completed task cannot be cancelled")
        task["state"] = "cancelled"


@dataclass
class LocalBrowserAdapter:
    workspace: str
    sessions: dict[str, dict] = field(default_factory=dict)

    def open(
        self, context: ExecutionContext, url: str, mode: SandboxMode = SandboxMode.READ_ONLY
    ) -> str:
        from core.config import settings

        # Localhost URLs are only allowed when running in a local environment. In any
        # other environment this adapter must fail loudly instead of silently connecting
        # to a wrong host (established repo idiom: settings.env == "local" guard).
        if url.startswith("http://localhost") or url.startswith("http://127.0.0.1"):
            is_local = settings.env == "local"
            if not is_local:
                raise ValueError(
                    "browser adapter only permits localhost URLs in a local environment"
                )
        elif not url.startswith("https://"):
            raise ValueError("browser adapter only permits HTTPS or localhost URLs")
        session_id = f"browser_{uuid.uuid4().hex}"
        self.sessions[session_id] = {"tenant_id": context.tenant_id, "url": url, "mode": mode.value}
        return session_id

    def close(self, context: ExecutionContext, session_id: str) -> None:
        session = self.sessions.get(session_id)
        if session is None or session["tenant_id"] != context.tenant_id:
            raise KeyError(session_id)
        del self.sessions[session_id]
