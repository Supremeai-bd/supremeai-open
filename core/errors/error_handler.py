from __future__ import annotations

import uuid

from fastapi import HTTPException

from core.logging_config import logger


def safe_http_error(
    exc,
    *,
    status_code=500,
    public_message="Internal error. Please try again.",
    context="",
):
    trace_id = str(uuid.uuid4())[:8]
    prefix = f"[{context}] " if context else ""
    logger.opt(exception=True).error(f"{prefix}trace_id={trace_id}: {exc}")
    return HTTPException(
        status_code=status_code,
        detail={"message": public_message, "trace_id": trace_id},
    )


def safe_error_response(exc, *, public_message="Internal error.", context=""):
    trace_id = str(uuid.uuid4())[:8]
    prefix = f"[{context}] " if context else ""
    logger.opt(exception=True).error(f"{prefix}trace_id={trace_id}: {exc}")
    return {"status": "error", "message": public_message, "trace_id": trace_id}
