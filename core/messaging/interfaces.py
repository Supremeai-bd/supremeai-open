from typing import Protocol

from .models import MessageEvent, MessageResult


class MessagingProvider(Protocol):
    """Protocol defining the interface for standard messaging operations."""

    async def send(self, event: MessageEvent) -> MessageResult:
        """Send a message to a recipient."""
        ...
