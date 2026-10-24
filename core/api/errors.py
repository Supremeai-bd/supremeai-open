# backend/api/errors.py
"""Standardized API error response layer.

Every route must raise HTTPException — never return raw error dicts.
This module provides shared error models and a centralized handler.
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus


class APIErrorDetail(BaseModel):
    """Structured error payload returned to clients."""

    title: str
    detail: str
    instance: str
    code: str | None = None
    trace_id: str | None = None


class ErrorResponse(BaseModel):
    """Top-level error envelope."""

    error: APIErrorDetail


@with_error_bus("api_error_handler")
async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler — replaces bare `except Exception: print(e)`."""
    error_event_bus.emit(
        ErrorEvent(
            module="api_error_handler",
            error_type=type(exc).__name__,
            message=str(exc)[:500],
            severity="ERROR",
            structured_context=ErrorContext(module="api_error_handler"),
            context={"path": request.url.path, "method": request.method},
        ),
    )
    logger.error(f"Unhandled exception on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=getattr(exc, "status_code", 500),
        content={
            "error": {
                "title": getattr(exc, "title", "Internal Server Error"),
                "detail": str(exc),
                "instance": request.url.path,
            },
        },
    )


def raise_bad_request(detail: str, *, code: str | None = None) -> None:
    raise HTTPException(status_code=400, detail=detail)


def raise_unauthorized(
    detail: str = "Missing or invalid authentication token",
) -> None:
    raise HTTPException(status_code=401, detail=detail)


def raise_forbidden(detail: str = "Insufficient permissions") -> None:
    raise HTTPException(status_code=403, detail=detail)


def raise_not_found(detail: str = "Resource not found") -> None:
    raise HTTPException(status_code=404, detail=detail)


def raise_conflict(detail: str) -> None:
    raise HTTPException(status_code=409, detail=detail)


def raise_internal(detail: str) -> None:
    raise HTTPException(status_code=500, detail=detail)
