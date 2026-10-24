from typing import Any

from pydantic import BaseModel


class MessageEvent(BaseModel):
    """Represents a message to be sent via the Messaging Layer."""

    recipient: str
    subject: str | None = None
    body: str
    metadata: dict[str, Any] | None = None


class MessageResult(BaseModel):
    """Standard response from messaging operations."""

    success: bool
    message_id: str | None = None
    provider: str
    error: str | None = None
