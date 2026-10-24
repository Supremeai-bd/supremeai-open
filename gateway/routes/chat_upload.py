import asyncio
import json
import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.deps import get_current_user_token
from core.logging_config import logger
from database.supabase_client import SupabaseDB

router = APIRouter(
    prefix="/api/chat/upload",
    tags=["Chat Upload"],
    dependencies=[Depends(get_current_user_token)],
)

# Upload directory — relative to the backend root
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Allowed MIME types and their file extensions
ALLOWED_MIME_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/avif": ".avif",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# In-memory registry of uploaded files (attachment_id -> metadata)
# Audit B-10 fix (2026-09-17): bounded — entries are removed via explicit
# DELETE, but the dict itself used to grow without limit per process.
# Sidecar metadata files persist on disk regardless, so eviction here only
# drops the in-memory mirror of the oldest entries.
_MAX_UPLOAD_ENTRIES = 500
_uploads: dict[str, dict] = {}


def _prune_uploads() -> None:
    while len(_uploads) > _MAX_UPLOAD_ENTRIES:
        oldest = next(iter(_uploads))
        _uploads.pop(oldest, None)


# ---------- Pydantic Schemas ----------


class AttachmentResponse(BaseModel):
    attachment_id: str
    url: str
    name: str
    size: int
    mime_type: str


# ---------- Helpers ----------


def _mime_to_ext(mime: str) -> str | None:
    """Return the canonical file extension for a MIME type, or None."""
    return ALLOWED_MIME_TYPES.get(mime)


def _get_attachment_url(attachment_id: str) -> str:
    """Return the API URL to serve the uploaded file."""
    return f"/api/chat/upload/{attachment_id}"


def _validate_image_header(content: bytes, mime_type: str) -> bool:
    """Basic image header validation to reject non-image payloads disguised with image MIME types."""
    if len(content) < 4:
        return False
    header = content[:8]
    if mime_type == "image/png" and header[:4] == b"\x89PNG":
        return True
    if mime_type == "image/jpeg" and header[:2] == b"\xff\xd8":
        return True
    if mime_type == "image/gif" and header[:6] in (b"GIF87a", b"GIF89a"):
        return True
    if mime_type == "image/webp" and header[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return True
    if mime_type == "image/svg+xml":
        try:
            try:
                import defusedxml.ElementTree as ET
            except ImportError:
                import xml.etree.ElementTree as ET

            tree = ET.fromstring(content)
            for elem in list(tree.iter()):
                tag_name = elem.tag.split("}")[-1].lower() if "}" in elem.tag else elem.tag.lower()
                if tag_name in ("script", "foreignobject"):
                    return False
                for attr in list(elem.attrib.keys()):
                    attr_name = attr.split("}")[-1].lower() if "}" in attr else attr.lower()
                    if attr_name.startswith("on"):
                        return False
            return True
        except Exception:
            return False
    # BMP starts with "BM"
    if mime_type == "image/bmp" and header[:2] == b"BM":
        return True
    # For AVIF and TIFF we skip deep validation and trust the MIME
    if mime_type in ("image/avif", "image/tiff"):
        return True
    # If unrecognized header, still allow (some formats vary)
    return True


# ---------- Routes ----------


@router.post("/", response_model=AttachmentResponse)
async def upload_chat_image(
    file: UploadFile = File(..., description="Image file to upload (max 10MB)"),
    user: dict = Depends(get_current_user_token),
):
    """Upload an image file for use in chat messages.

    Validates file type and size, stores to local disk, and returns
    metadata that can be included in chat message payloads.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Validate MIME type
    mime_type = file.content_type or ""
    ext = _mime_to_ext(mime_type)
    if ext is None:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {mime_type}. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES.keys()))}",
        )

    # Read and validate size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content)} bytes). Maximum allowed: {MAX_FILE_SIZE} bytes (10MB).",
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Validate image header to catch disguised files
    if not _validate_image_header(content, mime_type):
        raise HTTPException(
            status_code=400,
            detail="File content does not match the declared MIME type.",
        )

    # Generate a unique ID and filename
    attachment_id = uuid.uuid4().hex
    original_name = file.filename or f"upload{ext}"
    safe_name = f"{attachment_id}{ext}"
    user_dir = os.path.join(UPLOAD_DIR, user_id[:8])
    os.makedirs(user_dir, exist_ok=True)
    file_path = os.path.join(user_dir, safe_name)

    # Write file to disk
    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except OSError as e:
        logger.error(f"Failed to write upload file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file") from e

    # ERR-B02 (defect register 2026-09-15): persist original metadata next to the
    # file so the /files explorer's LIST endpoint survives process restarts (the
    # in-memory `_uploads` registry does not). Sidecar: <attachment_id>.meta.json
    try:
        with open(os.path.join(user_dir, f"{attachment_id}.meta.json"), "w") as meta_fh:
            json.dump(
                {
                    "name": original_name,
                    "mime_type": mime_type,
                    "size": len(content),
                    "user_id": user_id,
                    "created_at": datetime.now(UTC).isoformat(),
                },
                meta_fh,
            )
    except OSError as meta_err:
        logger.warning(f"Sidecar metadata write failed (non-critical): {meta_err}")

    url = _get_attachment_url(attachment_id)

    metadata = {
        "attachment_id": attachment_id,
        "url": url,
        "name": original_name,
        "size": len(content),
        "mime_type": mime_type,
        "file_path": file_path,
        "user_id": user_id,
        "created_at": datetime.now(UTC).isoformat(),
    }

    _uploads[attachment_id] = metadata
    _prune_uploads()

    # Persist reference in DB
    try:
        db = SupabaseDB()
        await (
            db.client.table("chat_attachments")
            .insert(
                {
                    "id": attachment_id,
                    "user_id": user_id,
                    "file_name": original_name,
                    "file_path": file_path,
                    "mime_type": mime_type,
                    "file_size": len(content),
                }
            )
            .execute()
        )
    except Exception as db_err:
        logger.warning(f"DB insert for attachment failed (non-critical): {db_err}")

    # Optionally run vision analysis
    try:
        from services.vision_service import VisionService

        vision_svc = VisionService()
        analysis = await vision_svc.analyze_image(content, query="Describe this image briefly")
        metadata["vision_analysis"] = analysis
    except Exception as vision_err:
        logger.debug(f"Vision analysis skipped: {vision_err}")

    logger.info(f"Chat image uploaded: {attachment_id} ({mime_type}, {len(content)} bytes)")

    return AttachmentResponse(
        attachment_id=attachment_id,
        url=url,
        name=original_name,
        size=len(content),
        mime_type=mime_type,
    )


# Reverse MIME map for disk-derived listing fallback
_EXT_TO_MIME = {v: k for k, v in ALLOWED_MIME_TYPES.items()}


@router.get("")
async def list_uploads(user: dict = Depends(get_current_user_token)):
    """ERR-B02: list the current user's uploaded files for the /files explorer.

    বাংলা: ডিস্ক থেকে user-এর ডিরেক্টরি স্ক্যান করে লিস্ট — প্রসেস রিস্টার্টেও
    ফাইল এক্সপ্লোরার ঠিক থাকে। মেটাডেটা priority: in-memory registry →
    sidecar .meta.json → disk-derived (stat + ext→mime)।
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_dir = os.path.join(UPLOAD_DIR, user_id[:8])
    items: list[dict] = []
    if os.path.isdir(user_dir):
        for fname in sorted(os.listdir(user_dir)):
            if fname.endswith(".meta.json"):
                continue  # sidecar, not a real attachment
            fpath = os.path.join(user_dir, fname)
            if not os.path.isfile(fpath):
                continue
            attachment_id = os.path.splitext(fname)[0]
            meta = _uploads.get(attachment_id) or {}
            if not meta:
                sidecar_path = os.path.join(user_dir, f"{attachment_id}.meta.json")
                if os.path.isfile(sidecar_path):
                    try:
                        with open(sidecar_path) as meta_fh:
                            meta = json.load(meta_fh)
                    except (OSError, ValueError):
                        meta = {}
            ext = os.path.splitext(fname)[1]
            try:
                stat = os.stat(fpath)
            except OSError:
                continue
            items.append(
                {
                    "attachment_id": attachment_id,
                    "url": _get_attachment_url(attachment_id),
                    "name": meta.get("name") or meta.get("file_name") or fname,
                    "size": meta.get("size", stat.st_size),
                    "mime_type": meta.get("mime_type")
                    or _EXT_TO_MIME.get(ext, "application/octet-stream"),
                    "created_at": meta.get("created_at")
                    or datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                }
            )
    items.sort(key=lambda item: item["created_at"] or "", reverse=True)
    return {"items": items, "total": len(items)}


@router.get("/{attachment_id}")
async def serve_upload(
    attachment_id: str,
    user: dict = Depends(get_current_user_token),
):
    """Serve an uploaded file by its attachment ID.

    Returns the file with the appropriate Content-Type header.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Look up in-memory registry first
    metadata = _uploads.get(attachment_id)

    if metadata is None:
        # Try loading from database
        try:
            db = SupabaseDB()
            resp = (
                await db.client.table("chat_attachments")
                .select("*")
                .eq("id", attachment_id)
                .execute()
            )
            if resp.data:
                metadata = resp.data[0]
                _uploads[attachment_id] = metadata
        except asyncio.CancelledError:
            raise
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception(f"Silenced error: {e}")

    if metadata is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # AUD-2.5 (object-level authorization): the GET route previously served any
    # attachment by ID alone, letting any authenticated user download another
    # user's uploads. Enforce ownership now (404, mirroring the DELETE route).
    if metadata.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Attachment not found")

    file_path = metadata["file_path"]
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Attachment file not found on disk")

    mime_type = metadata.get("mime_type", "application/octet-stream")
    file_name = metadata.get("file_name", "download")

    return FileResponse(
        path=file_path,
        media_type=mime_type,
        filename=file_name,
        headers={
            "Cache-Control": "private, max-age=86400",
        },
    )


@router.delete("/{attachment_id}")
async def delete_upload(
    attachment_id: str,
    user: dict = Depends(get_current_user_token),
):
    """Delete an uploaded attachment.

    Only the owner can delete their own attachments.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    metadata = _uploads.get(attachment_id)
    if metadata is None:
        try:
            db = SupabaseDB()
            resp = (
                await db.client.table("chat_attachments")
                .select("*")
                .eq("id", attachment_id)
                .execute()
            )
            if resp.data:
                metadata = resp.data[0]
        except asyncio.CancelledError:
            raise
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception(f"Silenced error: {e}")

    if metadata is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    if metadata.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="You do not own this attachment")

    # Delete from disk (file + sidecar metadata)
    file_path = metadata.get("file_path", "")
    if file_path and os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except OSError as e:
            logger.warning(f"Failed to delete file from disk: {e}")
    try:
        sidecar_path = os.path.join(UPLOAD_DIR, user_id[:8], f"{attachment_id}.meta.json")
        if os.path.isfile(sidecar_path):
            os.remove(sidecar_path)
    except OSError as sidecar_err:
        logger.warning(f"Failed to delete sidecar metadata: {sidecar_err}")

    # Delete from DB
    try:
        db = SupabaseDB()
        await db.client.table("chat_attachments").delete().eq("id", attachment_id).execute()
    except Exception as db_err:
        logger.warning(f"Failed to delete attachment from DB: {db_err}")

    # Remove from memory
    _uploads.pop(attachment_id, None)

    return {"status": "deleted", "attachment_id": attachment_id}
