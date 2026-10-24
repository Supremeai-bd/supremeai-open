import os
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from .interfaces import StorageProvider
from .models import StorageFile, StorageResult


class LocalStorageAdapter:
    """A local filesystem implementation of StorageProvider."""

    def __init__(self, base_path: str = "data/storage"):
        # Resolve to backend/data/storage
        self.base_dir = Path(__file__).resolve().parent.parent.parent / base_path
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, bucket: str, key: str) -> Path:
        bucket_dir = self.base_dir / bucket
        bucket_dir.mkdir(parents=True, exist_ok=True)
        # Prevent directory traversal attacks
        safe_key = key.lstrip("/").replace("../", "")
        return bucket_dir / safe_key

    async def put(
        self, bucket: str, key: str, file: BinaryIO, content_type: str = "application/octet-stream"
    ) -> StorageResult:
        try:
            path = self._get_file_path(bucket, key)
            path.parent.mkdir(parents=True, exist_ok=True)

            content = file.read()
            with open(path, "wb") as f:
                f.write(content)

            return StorageResult(
                success=True,
                bucket=bucket,
                key=key,
                url=await self.get_url(bucket, key),
                size_bytes=len(content),
                content_type=content_type,
            )
        except Exception as e:
            return StorageResult(success=False, bucket=bucket, key=key, error=str(e))

    async def get(self, bucket: str, key: str) -> StorageFile | None:
        path = self._get_file_path(bucket, key)
        if not path.exists():
            return None

        try:
            stat = path.stat()
            # Note: in a real async environment, we should use aiofiles,
            # but for this fallback adapter, standard open is fine for mock return.
            # Returning an open file handle means the caller needs to close it.
            import io

            with open(path, "rb") as f:
                content = f.read()
            return StorageFile(
                bucket=bucket,
                key=key,
                content=io.BytesIO(content),
                content_type="application/octet-stream",  # Best guess for local
                size_bytes=stat.st_size,
                last_modified=datetime.fromtimestamp(stat.st_mtime),
            )
        except Exception:
            return None

    async def delete(self, bucket: str, key: str) -> bool:
        path = self._get_file_path(bucket, key)
        if path.exists():
            try:
                path.unlink()
                return True
            except Exception:
                return False
        return False

    async def get_url(self, bucket: str, key: str) -> str:
        # In local dev, we might serve this via a FastAPI StaticFiles route
        # For now, return a logical internal URL
        return f"/local-storage/{bucket}/{key}"
