"""
SupremeAI Core Exception Hierarchy.

This module provides a unified, structured exception framework across the entire
SupremeAI backend. All custom exceptions inherit from `SupremeAIException` to ensure
consistent error logging, status codes, and structured JSON client responses.
"""

from __future__ import annotations

from typing import Any


class SupremeAIException(Exception):
    """
    Base exception class for all SupremeAI domain errors.
    """

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        self.original_error = original_error

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": False,
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
            },
        }


class AuthenticationError(SupremeAIException):
    """Raised when authentication credentials are missing, invalid, or expired."""

    def __init__(
        self, message: str = "Authentication failed", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message, error_code="AUTHENTICATION_FAILED", status_code=401, details=details
        )


class AuthorizationError(SupremeAIException):
    """Raised when an authenticated user/agent lacks permissions for a resource."""

    def __init__(
        self, message: str = "Permission denied", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message, error_code="PERMISSION_DENIED", status_code=403, details=details
        )


class ResourceNotFoundError(SupremeAIException):
    """Raised when a requested resource (thread, task, agent, model) is not found."""

    def __init__(
        self, message: str = "Resource not found", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message, error_code="RESOURCE_NOT_FOUND", status_code=404, details=details
        )


class ValidationError(SupremeAIException):
    """Raised when input payloads or schemas fail validation."""

    def __init__(
        self, message: str = "Invalid input payload", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message, error_code="VALIDATION_ERROR", status_code=422, details=details
        )


class ExecutionError(SupremeAIException):
    """Raised when an autonomous agent, workflow step, or sandbox command execution fails."""

    def __init__(
        self,
        message: str = "Execution failed",
        error_code: str = "EXECUTION_FAILED",
        details: dict[str, Any] | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=500,
            details=details,
            original_error=original_error,
        )


class RateLimitError(SupremeAIException):
    """Raised when client or agent rate limits are exceeded."""

    def __init__(
        self, message: str = "Rate limit exceeded", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message, error_code="RATE_LIMIT_EXCEEDED", status_code=429, details=details
        )


class ThirdPartyServiceError(SupremeAIException):
    """Raised when an external/fallback provider returns an unexpected error."""

    def __init__(
        self, message: str = "External provider unavailable", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message, error_code="UPSTREAM_SERVICE_ERROR", status_code=502, details=details
        )


# Backward-compatible aliases for legacy imports
SupremeAIError = SupremeAIException


class ProviderExhaustedError(SupremeAIException):
    """Raised when all fallback AI providers fail or are exhausted."""

    def __init__(
        self, message: str = "All AI providers exhausted", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message, error_code="PROVIDER_EXHAUSTED", status_code=503, details=details
        )


class LLMProviderError(SupremeAIException):
    """Legacy alias: Raised when an LLM provider request fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message, error_code="LLM_PROVIDER_ERROR", status_code=502, details=details
        )


class QuotaExceededError(SupremeAIException):
    """Legacy alias: Raised when LLM rate limit or budget quota is exceeded."""

    def __init__(self, message: str = "LLM Provider Rate Limit or Budget Quota Exceeded.") -> None:
        super().__init__(message=message, error_code="QUOTA_EXCEEDED", status_code=429)
