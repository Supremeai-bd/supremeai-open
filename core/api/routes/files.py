# backend/api/routes/files.py
# বাংলা মন্তব্য: AUDIT-018 — frontend-এর useSupremeStore.saveFile() PUT /api/files/{path}
# কল করে, কিন্তু এই route কখনো backend-এ implement হয়নি (raw file-write-by-path
# endpoint বিনা path-traversal protection-এ বানানো নিরাপদ না, তাই আগে flag করে
# রাখা হয়েছিল)। এখানে microvm_sandbox.py-র প্রতিষ্ঠিত pattern অনুসরণ করে
# (whitelist root + resolved-path containment check) নিরাপদভাবে implement করা হলো।
#
# Design decisions:
#  ১. প্রতিটা tenant/user-এর নিজস্ব isolated sub-directory (settings.workspace_base_dir
#     এর অধীনে ide/{tenant_id}/) — cross-tenant file access সম্ভব না।
#  ২. path traversal (../, absolute path override, symlink escape) — সব resolved
#     Path.resolve() করে root-এর ভিতরে আছে কিনা কড়াভাবে যাচাই করা হয়।
#  ৩. Authentication required (get_current_user_token) — unauthenticated write বন্ধ।
#  ৪. File size cap ও extension allowlist — arbitrary binary/অতিরিক্ত বড় ফাইল রুখতে।
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_token
from core.config import settings
from core.logging_config import logger

router = APIRouter(prefix="/files", tags=["Workspace Files"])

# বাংলা মন্তব্য: শুধু টেক্সট/কোড ফাইল edit করার জন্য এই endpoint — binary/executable
# extension এখানে blocklist করা হলো যাতে কেউ .sh/.exe আপলোড করে পরে চালানোর
# চেষ্টা না করতে পারে।
_BLOCKED_EXTENSIONS: frozenset[str] = frozenset(
    {".exe", ".sh", ".bash", ".bat", ".cmd", ".ps1", ".dll", ".so", ".dylib"}
)

# বাংলা মন্তব্য: 2MB — editor দিয়ে সাধারণ কোড/টেক্সট ফাইল edit করার জন্য যথেষ্ট,
# অথচ disk-fill DoS ঠেকাতে যথেষ্ট ছোট।
_MAX_FILE_BYTES = 2 * 1024 * 1024

# বাংলা মন্তব্য: tenant_id নিজেই path component হিসেবে ব্যবহার হবে, তাই এটাও
# strictly validate করা দরকার (JWT sub claim সাধারণত নিরাপদ, কিন্তু defense-in-depth)।
_TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_.@-]{1,128}$")


class FileWriteRequest(BaseModel):
    content: str = Field(..., description="Full file content to write")


class FileWriteResponse(BaseModel):
    path: str = Field(..., description="Relative file path within workspace")
    bytes_written: int = Field(..., description="Number of bytes written")
    status: str = Field("saved", description="Operation status")


class FileReadResponse(BaseModel):
    path: str = Field(..., description="Relative file path within workspace")
    content: str = Field(..., description="Decoded UTF-8 content of the file")


def _get_tenant_root(tenant_id: str) -> Path:
    """তেনান্টের জন্য isolated workspace root বানায় ও রিটার্ন করে।"""
    if not _TENANT_ID_PATTERN.match(tenant_id):
        # বাংলা মন্তব্য: এটা normally ঘটবে না (JWT sub থেকে আসে), কিন্তু ঘটলে
        # অবশ্যই silently allow করা যাবে না।
        raise HTTPException(status_code=400, detail="Invalid tenant identifier")

    base = Path(settings.workspace_base_dir).resolve()
    root = (base / "ide" / tenant_id).resolve()

    # বাংলা মন্তব্য: root নিজেই base-এর ভিতরে আছে কিনা যাচাই (defense-in-depth,
    # tenant_id regex already এটা guarantee করে, কিন্তু double-check ক্ষতিকর না)
    if base not in root.parents and root != base:
        raise HTTPException(status_code=400, detail="Invalid workspace root")

    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_safe_path(root: Path, relative_path: str) -> Path:
    """
    বাংলা মন্তব্য: এই ফাংশনটাই এই endpoint-এর মূল নিরাপত্তা boundary।
    - কোনো absolute path override না (leading '/' বা 'C:\\' জাতীয় কিছু)
    - '..' দিয়ে root-এর বাইরে যাওয়া যাবে না
    - symlink দিয়ে root-এর বাইরে বের হওয়া গেলেও resolve()-এর পর ধরা পড়বে
    """
    if not relative_path or relative_path.strip() in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid file path")

    # বাংলা মন্তব্য: null byte injection ঠেকানো
    if "\x00" in relative_path:
        raise HTTPException(status_code=400, detail="Invalid file path")

    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise HTTPException(status_code=400, detail="Absolute paths are not allowed")

    resolved = (root / candidate).resolve()

    # বাংলা মন্তব্য: মূল নিরাপত্তা চেক — resolved path অবশ্যই root-এর ভিতরে থাকতে হবে।
    # os.path.commonpath এর বদলে pathlib-এর is_relative_to (py3.9+) ব্যবহার করা হলো,
    # কারণ এটা string-prefix bug-প্রবণ (যেমন "/root2" শুরু হয় "/root" দিয়ে) এড়ায়।
    if not resolved.is_relative_to(root):
        logger.warning(
            f"🚨 Path traversal attempt blocked: '{relative_path}' resolved outside workspace root"
        )
        raise HTTPException(status_code=400, detail="Path escapes workspace root")

    if resolved.suffix.lower() in _BLOCKED_EXTENSIONS:
        raise HTTPException(
            status_code=400, detail=f"File extension '{resolved.suffix}' is not allowed"
        )

    return resolved


@router.put("/{file_path:path}", response_model=FileWriteResponse)
async def write_file(
    file_path: str, payload: FileWriteRequest, token: dict = Depends(get_current_user_token)
):
    """
    বাংলা মন্তব্য: IDE editor থেকে save — শুধুমাত্র caller-এর নিজের tenant-scoped
    workspace-এ, path-traversal protection সহ।
    """
    tenant_id = token.get("sub") or token.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    content_bytes = payload.content.encode("utf-8")
    if len(content_bytes) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413, detail=f"File exceeds {_MAX_FILE_BYTES // (1024 * 1024)}MB limit"
        )

    root = _get_tenant_root(str(tenant_id))
    target = _resolve_safe_path(root, file_path)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content_bytes)
    except OSError as e:
        logger.error(f"Failed to write workspace file '{file_path}' for tenant '{tenant_id}': {e}")
        raise HTTPException(status_code=500, detail="Failed to write file") from e

    return FileWriteResponse(path=file_path, bytes_written=len(content_bytes), status="saved")


@router.get("/{file_path:path}", response_model=FileReadResponse)
async def read_file(file_path: str, token: dict = Depends(get_current_user_token)):
    """বাংলা মন্তব্য: write_file-এর সঙ্গী GET — একই safety boundary পুনর্ব্যবহার করে।"""
    tenant_id = token.get("sub") or token.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    root = _get_tenant_root(str(tenant_id))
    target = _resolve_safe_path(root, file_path)

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=415, detail="File is not valid UTF-8 text") from e
    except OSError as e:
        logger.error(f"Failed to read workspace file '{file_path}' for tenant '{tenant_id}': {e}")
        raise HTTPException(status_code=500, detail="Failed to read file") from e

    return FileReadResponse(path=file_path, content=content)
