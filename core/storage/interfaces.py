from typing import BinaryIO, Protocol

from .models import StorageFile, StorageResult


class StorageProvider(Protocol):
    """Protocol defining the interface for standard storage operations."""

    async def put(
        self, bucket: str, key: str, file: BinaryIO, content_type: str = "application/octet-stream"
    ) -> StorageResult:
        """Upload a file to storage."""
        ...

    async def get(self, bucket: str, key: str) -> StorageFile | None:
        """Retrieve a file from storage."""
        ...

    async def delete(self, bucket: str, key: str) -> bool:
        """Delete a file from storage."""
        ...

    async def get_url(self, bucket: str, key: str) -> str:
        """Get a publicly accessible or signed URL for a file."""
        ...
