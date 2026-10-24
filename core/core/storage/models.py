from datetime import datetime
from typing import BinaryIO

from pydantic import BaseModel, Field


class StorageResult(BaseModel):
    """Standard response from storage operations."""

    success: bool
    bucket: str
    key: str
    url: str | None = None
    error: str | None = None
    size_bytes: int | None = None
    content_type: str | None = None


class StorageFile(BaseModel):
    """Represents a file retrieved from storage."""

    bucket: str
    key: str
    content: BinaryIO
    content_type: str
    size_bytes: int
    last_modified: datetime | None = None

    class Config:
        arbitrary_types_allowed = True
