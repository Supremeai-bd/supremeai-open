"""supremeai — official Python client for the SupremeAI Unified Gateway.

Lightweight sync and async clients (stdlib only; httpx optional), with
SSE streaming, bearer signing, and exponential-backoff retry on
transient gateway failures.
"""

from .client import AsyncSupremeAIClient, SupremeAIClient
from .errors import GatewayError
from .sse_listener import SSEListener, StreamEvent

__version__ = "0.1.0"

__all__ = [
    "AsyncSupremeAIClient",
    "SupremeAIClient",
    "GatewayError",
    "SSEListener",
    "StreamEvent",
    "__version__",
]
