import hashlib
import hmac
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from core.config import settings
from core.logging_config import logger

router = APIRouter(prefix="/api/v1/webhooks/n8n", tags=["n8n Webhooks"])

N8N_WEBHOOK_SECRET = (
    settings.n8n_webhook_secret.get_secret_value() if settings.n8n_webhook_secret else ""
)
# Replay protection window: 5 minutes
REPLAY_WINDOW_SECONDS = 300


class N8nCallbackPayload(BaseModel):
    event_id: str
    status: str
    message: str | None = None
    execution_id: str | None = None
    # Any other fields needed


async def _verify_n8n_signature(request: Request, body: bytes, timestamp: str) -> bool:
    if not N8N_WEBHOOK_SECRET:
        logger.error("N8N_WEBHOOK_SECRET is not configured! Enforcing fail-closed policy.")
        return False

    signature = request.headers.get("X-N8N-Signature", "")
    if not signature:
        return False

    try:
        # Replay protection check
        ts_int = int(timestamp)
        now = int(time.time())
        if abs(now - ts_int) > REPLAY_WINDOW_SECONDS:
            logger.warning(f"Webhook timestamp outside replay window (diff: {abs(now - ts_int)}s).")
            return False
    except ValueError:
        return False

    message = f"{timestamp}.{body.decode('utf-8')}".encode()
    expected = hmac.new(
        N8N_WEBHOOK_SECRET.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


@router.post("/callback")
async def n8n_callback(
    request: Request,
    x_n8n_timestamp: str = Header(..., alias="X-N8N-Timestamp"),
) -> dict[str, Any]:
    """
    Handle callbacks from n8n with signature and replay protection.
    """
    body = await request.body()

    if not await _verify_n8n_signature(request, body, x_n8n_timestamp):
        raise HTTPException(status_code=401, detail="Invalid webhook signature or timestamp")

    try:
        import json

        payload = json.loads(body)
        callback_data = N8nCallbackPayload(**payload)
    except Exception as e:
        logger.error(f"Invalid payload format from n8n: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload") from e

    logger.info(
        f"📥 [n8n Webhook] Received callback for event {callback_data.event_id} (Status: {callback_data.status})"
    )

    # Update execution records or trigger further events based on status
    # ...

    return {"status": "accepted"}
