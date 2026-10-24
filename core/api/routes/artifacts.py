"""Feature S3: Artifacts Panel (Claude-style).

Manages code artifacts that can be live-previewed in iframes.
Supports HTML, React, SVG, Mermaid, and generic code artifacts.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from api.deps import get_current_user_token
from core.logging_config import logger
from database.supabase_client import SupabaseDB

router = APIRouter(
    prefix="/api/artifacts",
    tags=["Artifacts"],
    dependencies=[Depends(get_current_user_token)],
)

# Mapping from artifact type to Content-Type for iframe preview
_ARTIFACT_CONTENT_TYPES: dict[str, str] = {
    "html": "text/html; charset=utf-8",
    "react": "text/html; charset=utf-8",
    "svg": "image/svg+xml",
    "mermaid": "text/html; charset=utf-8",
    "code": "text/plain; charset=utf-8",
}

# ---------- Pydantic Schemas ----------


class ArtifactType(StrEnum):
    """Allowed artifact types using proper Enum to avoid MRO conflicts."""

    HTML = "html"
    REACT = "react"
    SVG = "svg"
    MERMAID = "mermaid"
    CODE = "code"

    @classmethod
    def values(cls) -> list[str]:
        """Return list of valid artifact type values."""
        return [item.value for item in cls]


class ArtifactCreate(BaseModel):
    title: str = Field(default="Untitled", max_length=256)
    artifact_type: str = Field(default="code", description="Type of artifact for preview rendering")
    content: str = Field(..., min_length=1, description="The artifact content")
    conversation_id: str | None = Field(default=None, description="Optional linked conversation")

    @field_validator("artifact_type")
    @classmethod
    def validate_artifact_type(cls, v: str) -> str:
        """Validate artifact_type against allowed Enum values."""
        allowed = ArtifactType.values()
        if v not in allowed:
            raise ValueError(f"Invalid artifact_type '{v}'. Must be one of: {allowed}")
        return v


class ArtifactUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=256)
    content: str | None = Field(default=None, min_length=1)
    artifact_type: str | None = None
    is_pinned: bool | None = None

    @field_validator("artifact_type")
    @classmethod
    def validate_artifact_type_optional(cls, v: str | None) -> str | None:
        """Validate optional artifact_type against allowed Enum values."""
        if v is not None:
            allowed = ArtifactType.values()
            if v not in allowed:
                raise ValueError(f"Invalid artifact_type '{v}'. Must be one of: {allowed}")
        return v


class ArtifactResponse(BaseModel):
    id: str
    conversation_id: str | None
    user_id: str
    title: str
    artifact_type: str
    content: str
    version: int
    is_pinned: bool
    created_at: str
    updated_at: str


class ArtifactListItem(BaseModel):
    id: str
    conversation_id: str | None
    title: str
    artifact_type: str
    version: int
    is_pinned: bool
    created_at: str
    updated_at: str


class ArtifactDeleteResponse(BaseModel):
    status: str
    artifact_id: str


# ---------- Routes ----------


@router.post("/", response_model=ArtifactResponse)
async def create_artifact(
    payload: ArtifactCreate,
    user: dict = Depends(get_current_user_token),
):
    """Create a new artifact.

    Stores the artifact in the ``artifacts`` table. If a ``conversation_id``
    is provided the artifact is linked to that conversation.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()

    try:
        row = {
            "user_id": user_id,
            "title": payload.title,
            "artifact_type": payload.artifact_type,
            "content": payload.content,
            "conversation_id": payload.conversation_id,
        }

        response = await db.client.table("artifacts").insert(row).execute()

        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create artifact")

        logger.info(f"Artifact created: {response.data[0]['id']} (type={payload.artifact_type})")

        return ArtifactResponse(**response.data[0])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create artifact: {e}")
        raise HTTPException(status_code=500, detail="Failed to create artifact") from e


@router.get("/conversation/{conversation_id}", response_model=list[ArtifactListItem])
async def list_artifacts_by_conversation(
    conversation_id: str,
    user: dict = Depends(get_current_user_token),
):
    """List all artifacts belonging to a specific conversation."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()

    try:
        response = (
            await db.client.table("artifacts")
            .select(
                "id, conversation_id, user_id, title, artifact_type, version, is_pinned, created_at, updated_at"
            )
            .eq("conversation_id", conversation_id)
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
        )

        return [ArtifactListItem(**row) for row in response.data]
    except Exception as e:
        logger.error(f"Failed to list artifacts: {e}")
        raise HTTPException(status_code=500, detail="Failed to list artifacts") from e


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: str,
    user: dict = Depends(get_current_user_token),
):
    """Retrieve a single artifact by its ID."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()

    try:
        response = (
            await db.client.table("artifacts")
            .select("*")
            .eq("id", artifact_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=404, detail="Artifact not found")

        return ArtifactResponse(**response.data[0])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve artifact: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve artifact") from e


@router.patch("/{artifact_id}", response_model=ArtifactResponse)
async def update_artifact(
    artifact_id: str,
    payload: ArtifactUpdate,
    user: dict = Depends(get_current_user_token),
):
    """Update an artifact's content, title, type, or pin status.

    Automatically increments the ``version`` counter on every update.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()

    try:
        # Verify ownership and fetch current version
        existing = (
            await db.client.table("artifacts")
            .select("id, user_id, version")
            .eq("id", artifact_id)
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=404, detail="Artifact not found")

        if existing.data[0]["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="You do not own this artifact")

        current_version = existing.data[0]["version"]

        # Build update payload (only include non-None fields)
        update_fields: dict[str, Any] = {
            "version": current_version + 1,
        }
        if payload.title is not None:
            update_fields["title"] = payload.title
        if payload.content is not None:
            update_fields["content"] = payload.content
        if payload.artifact_type is not None:
            update_fields["artifact_type"] = payload.artifact_type
        if payload.is_pinned is not None:
            update_fields["is_pinned"] = payload.is_pinned

        response = (
            await db.client.table("artifacts").update(update_fields).eq("id", artifact_id).execute()
        )

        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to update artifact")

        logger.info(f"Artifact updated: {artifact_id} -> version {current_version + 1}")

        return ArtifactResponse(**response.data[0])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update artifact: {e}")
        raise HTTPException(status_code=500, detail="Failed to update artifact") from e


@router.delete("/{artifact_id}", response_model=ArtifactDeleteResponse)
async def delete_artifact(
    artifact_id: str,
    user: dict = Depends(get_current_user_token),
):
    """Delete an artifact. Only the owner can delete their artifacts."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()

    try:
        # Verify ownership
        existing = (
            await db.client.table("artifacts").select("id, user_id").eq("id", artifact_id).execute()
        )

        if not existing.data:
            raise HTTPException(status_code=404, detail="Artifact not found")

        if existing.data[0]["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="You do not own this artifact")

        await db.client.table("artifacts").delete().eq("id", artifact_id).execute()

        logger.info(f"Artifact deleted: {artifact_id}")

        return ArtifactDeleteResponse(status="deleted", artifact_id=artifact_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete artifact: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete artifact") from e


@router.get("/{artifact_id}/preview")
async def preview_artifact(
    artifact_id: str,
    user: dict = Depends(get_current_user_token),
):
    """Return the artifact content with proper Content-Type for iframe embedding.

    For Mermaid artifacts, wraps the content in an HTML page that renders
    the diagram using the Mermaid JS library from CDN.
    For React artifacts, wraps the content in an HTML page that bootstraps
    React via a CDN script tag.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()

    try:
        response = (
            await db.client.table("artifacts")
            .select("id, user_id, artifact_type, content")
            .eq("id", artifact_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=404, detail="Artifact not found")

        artifact = response.data[0]

        if artifact["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="You do not own this artifact")

        artifact_type = artifact["artifact_type"]
        content = artifact["content"]
        content_type = _ARTIFACT_CONTENT_TYPES.get(artifact_type, "text/plain; charset=utf-8")

        # For Mermaid, wrap in an HTML page that renders the diagram
        if artifact_type == "mermaid":
            html = _build_mermaid_html(content)
            return Response(
                content=html,
                media_type="text/html; charset=utf-8",
                headers={
                    "X-Frame-Options": "SAMEORIGIN",
                    "Content-Security-Policy": "default-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net;",
                },
            )

        # For React, wrap in an HTML page that bootstraps React
        if artifact_type == "react":
            html = _build_react_html(content)
            return Response(
                content=html,
                media_type="text/html; charset=utf-8",
                headers={
                    "X-Frame-Options": "SAMEORIGIN",
                    "Content-Security-Policy": "default-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com https://cdn.jsdelivr.net;",
                },
            )

        # For HTML and SVG, serve directly
        return Response(
            content=content,
            media_type=content_type,
            headers={
                "X-Frame-Options": "SAMEORIGIN",
                "Cache-Control": "private, max-age=3600",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to preview artifact: {e}")
        raise HTTPException(status_code=500, detail="Failed to preview artifact") from e


def _build_mermaid_html(mermaid_code: str) -> str:
    """Wrap Mermaid diagram code in a self-contained HTML page."""
    escaped = mermaid_code.replace("</script>", "<" + "/script>").replace("\\", "\\\\")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mermaid Preview</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
    <style>
        body {{ margin: 0; padding: 24px; background: #fff; display: flex; justify-content: center; }}
        .mermaid {{ max-width: 100%; }}
    </style>
</head>
<body>
    <pre class="mermaid">
{escaped}
    </pre>
    <script>
        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
</body>
</html>"""


def _build_react_html(react_code: str) -> str:
    """Wrap React JSX/component code in a self-contained HTML page using CDN React."""
    escaped = react_code.replace("</script>", "<" + "/script>")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>React Preview</title>
    <script src="https://unpkg.com/react@18/umd/react.development.js" crossorigin></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js" crossorigin></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <style>
        body {{ margin: 0; padding: 24px; background: #fff; font-family: -apple-system, sans-serif; }}
    </style>
</head>
<body>
    <div id="root"></div>
    <script type="text/babel">
        try {{
            {escaped}
        }} catch(e) {{
            document.getElementById('root').innerHTML = '<pre style="color:red;">' + e.message + '</pre>';
        }}
    </script>
</body>
</html>"""
