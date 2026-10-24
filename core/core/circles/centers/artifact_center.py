"""Artifact Circle Center — artifact and asset lookup.

Owns (per FCC plan, artifact domain): artifacts and projects.
Domain adapter: ``storage.asset_manager.AssetManager`` (lazy import).
"""

from __future__ import annotations

from core.circles.centers.base import CircleCenter, ExecutionEnvelope, LocalCapability
from core.circles.contracts import CircleName, RiskLevel


class ArtifactCenter(CircleCenter):
    circle = CircleName.ARTIFACT
    display_name = "Artifacts and projects"
    owner = "backend/storage"

    def __init__(self) -> None:
        super().__init__()
        self.register(
            LocalCapability(
                name="artifact.url",
                description="Resolve a signed URL for a stored artifact path",
                risk_level=RiskLevel.LOW,
                timeout_ms=15_000,
                cache_ttl_ms=30_000,
            ),
            self._url,
        )

    def local_permission(self, envelope: ExecutionEnvelope) -> str | None:
        if (
            envelope.capability == "artifact.url"
            and not str(envelope.payload.get("path", "")).strip()
        ):
            return "path is required for artifact.url"
        return None

    def resolve_adapter(self, envelope: ExecutionEnvelope):  # noqa: ANN201
        from storage.asset_manager import AssetManager

        return AssetManager()

    async def _url(self, request) -> dict:
        manager = self.resolve_adapter(request)
        url = manager.get_asset_url(
            str(request.payload.get("path", "")),
            expires_in=int(request.payload.get("expires_in", 3600)),
        )
        if not url:
            raise LookupError("artifact_not_found")
        return {"path": request.payload.get("path"), "url": url}


__all__ = ["ArtifactCenter"]
