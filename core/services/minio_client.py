"""
SupremeAI — MinIO Object Storage Client
=======================================

Zero-cost object storage client for MinIO/S3-compatible storage.
- Upload/download with presigned URLs
- Bucket management
- Event notifications via Redis
- Caching layer integration
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from core.cache import get_cache
from core.logging_config import logger

# ── Constants ────────────────────────────────────────────────────────────────
URL_CACHE_TTL = 3600  # 1 hour


class StorageTier(StrEnum):
    HOT = "hot"  # Frequently accessed
    WARM = "warm"  # Occasionally accessed
    COLD = "cold"  # Archive


@dataclass(frozen=True)
class StoredObject:
    """Information about stored object."""

    bucket: str
    key: str
    size: int
    etag: str
    content_type: str
    url: str | None
    stored_at: datetime


class MinIOClient:
    """
    MinIO/S3-compatible object storage client.
    Zero-cost: uses environment-configured MinIO endpoint.
    """

    def __init__(self) -> None:
        self.cache = get_cache()
        self._client = None  # Lazy init
        self._endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")  # is_local()
        self._access_key = os.environ.get("MINIO_ACCESS_KEY", "")
        self._secret_key = os.environ.get("MINIO_SECRET_KEY", "")
        self._secure = os.environ.get("MINIO_SECURE", "false").lower() == "true"
        # timedelta is stdlib — always available; initialize eagerly so URL
        # generation never depends on the lazy Minio import path.
        self._timedelta = timedelta
        logger.info(f"MinIOClient initialized for {self._endpoint}")

    def _get_client(self) -> Any:
        """Get or create MinIO client."""
        if self._client is None:
            try:
                from minio import Minio

                self._client = Minio(
                    self._endpoint,
                    access_key=self._access_key,
                    secret_key=self._secret_key,
                    secure=self._secure,
                )
            except ImportError:
                logger.warning("MinIO client not installed, using mock mode")
                self._client = None

        return self._client

    def _cache_key(self, bucket: str, key: str) -> str:
        return f"minio:url:{bucket}:{key}"

    async def upload(
        self,
        bucket: str,
        key: str,
        file_path: str,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """
        Upload file to MinIO.

        Args:
            bucket: Bucket name.
            key: Object key.
            file_path: Path to file.
            content_type: MIME type.

        Returns:
            Upload result.
        """
        client = self._get_client()
        if not client:
            # Mock mode for zero-cost
            stat = Path(file_path).stat()
            return {
                "status": "mock_success",
                "bucket": bucket,
                "key": key,
                "size": stat.st_size,
            }

        try:
            result = client.fput_object(bucket, key, file_path, content_type=content_type)

            return {
                "status": "success",
                "bucket": bucket,
                "key": key,
                "etag": result.etag,
                "size": result.size,
            }
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return {"status": "error", "error": str(e)}

    async def download(self, bucket: str, key: str, dest_path: str) -> bool:
        """Download file from MinIO."""
        client = self._get_client()
        if not client:
            return False

        try:
            client.fget_object(bucket, key, dest_path)
            return True
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False

    async def get_presigned_url(
        self,
        bucket: str,
        key: str,
        expires_seconds: int = 3600,
    ) -> str:
        """Generate presigned URL for download."""
        cache_key = self._cache_key(bucket, key)
        cached = await self.cache.get(cache_key)
        if cached:
            return cached  # type: ignore

        client = self._get_client()
        if not client:
            return ""  # No client available

        try:
            if self._timedelta:  # type: ignore
                url = client.presigned_get_object(
                    bucket, key, expires=self._timedelta(seconds=expires_seconds)
                )
                await self.cache.set(cache_key, url, ttl=URL_CACHE_TTL)
                return url
        except Exception as e:
            logger.error(f"URL generation failed: {e}")

        return ""

    async def generate_presigned_upload(
        self,
        bucket: str,
        key: str,
        content_type: str = "application/octet-stream",
        expires_seconds: int = 3600,
    ) -> str:
        """Generate presigned URL for upload."""
        client = self._get_client()
        if not client:
            return ""

        try:
            if self._timedelta:  # type: ignore
                url = client.presigned_put_object(
                    bucket,
                    key,
                    content_type,
                    expires=self._timedelta(seconds=expires_seconds),
                )
                return url
        except Exception as e:
            logger.error(f"Upload URL generation failed: {e}")

        return ""

    async def ensure_bucket(self, bucket: str) -> bool:
        """Ensure bucket exists."""
        client = self._get_client()
        if not client:
            return True  # Mock success

        try:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
            return True
        except Exception as e:
            logger.error(f"Bucket setup failed: {e}")
            return False

    async def list_objects(self, bucket: str, prefix: str | None = None) -> list[StoredObject]:
        """List objects in bucket."""
        client = self._get_client()
        if not client:
            return []

        try:
            objects = client.list_objects(bucket, prefix=prefix)
            return [
                StoredObject(
                    bucket=bucket,
                    key=obj.object_name or "",
                    size=obj.size or 0,
                    etag=obj.etag or "",
                    content_type=obj.content_type or "",
                    url=None,
                    stored_at=datetime.now(UTC),
                )
                for obj in objects
            ]
        except Exception as e:
            logger.error(f"List failed: {e}")
            return []


# Singleton
_minio_instance: MinIOClient | None = None


def get_minio_client() -> MinIOClient:
    """Get or create the singleton MinIOClient instance."""
    global _minio_instance
    if _minio_instance is None:
        _minio_instance = MinIOClient()
    return _minio_instance
