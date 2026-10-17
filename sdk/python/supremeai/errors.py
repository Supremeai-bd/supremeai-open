"""Typed gateway errors for the SupremeAI Python SDK."""

from __future__ import annotations

from typing import Any, Optional

RETRYABLE_STATUSES = frozenset({502, 503, 504})


class GatewayError(RuntimeError):
    """Raised when the gateway answers with a non-2xx response.

    Attributes mirror the gateway error contract: ``status``, ``code``,
    ``provider``, ``retryable`` and the decoded ``body`` when available.
    """

    def __init__(
        self,
        status: int,
        code: str = "GATEWAY_ERROR",
        message: str = "gateway request failed",
        provider: Optional[str] = None,
        retryable: Optional[bool] = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.provider = provider
        self.retryable = status in RETRYABLE_STATUSES if retryable is None else retryable
        self.body = body

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return "GatewayError(status=%s, code=%s, retryable=%s)" % (
            self.status,
            self.code,
            self.retryable,
        )
