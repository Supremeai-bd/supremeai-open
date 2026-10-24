from typing import BinaryIO

from core.config import settings
from core.logging_config import logger

from .interfaces import StorageProvider
from .models import StorageFile, StorageResult


class StorageDispatcher:
    """Routes storage operations to the configured StorageProvider."""

    _instance = None
    _provider: StorageProvider | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_provider()
        return cls._instance

    def _initialize_provider(self) -> None:
        if getattr(settings, "appwrite_enabled", False):
            try:
                from core.providers.appwrite.adapter import AppwriteStorageAdapter

                self._provider = AppwriteStorageAdapter()
                logger.info("StorageDispatcher initialized with AppwriteStorageAdapter.")
                return
            except ImportError as e:
                logger.warning(f"Could not load AppwriteStorageAdapter: {e}")

        # Fallback to local storage
        from .local_adapter import LocalStorageAdapter

        self._provider = LocalStorageAdapter()
        logger.info("StorageDispatcher initialized with LocalStorageAdapter.")

    async def put(
        self, bucket: str, key: str, file: BinaryIO, content_type: str = "application/octet-stream"
    ) -> StorageResult:
        if not self._provider:
            return StorageResult(
                success=False, bucket=bucket, key=key, error="No storage provider configured"
            )
        return await self._provider.put(bucket, key, file, content_type)

    async def get(self, bucket: str, key: str) -> StorageFile | None:
        if not self._provider:
            return None
        return await self._provider.get(bucket, key)

    async def delete(self, bucket: str, key: str) -> bool:
        if not self._provider:
            return False
        return await self._provider.delete(bucket, key)

    async def get_url(self, bucket: str, key: str) -> str:
        if not self._provider:
            return ""
        return await self._provider.get_url(bucket, key)


storage_dispatcher = StorageDispatcher()
