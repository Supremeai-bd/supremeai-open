import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from core.config import settings
from core.errors.error_bus import with_error_bus
from core.logging_config import logger

router = APIRouter(prefix="/cdc", tags=["cdc"])

SUPABASE_WEBHOOK_SECRET = getattr(settings, "supabase_webhook_secret", "")
PINECONE_API_KEY = getattr(settings, "pinecone_api_key", "")
PINECONE_HOST = getattr(settings, "pinecone_host", "")


class CDCEvent(BaseModel):
    type: str
    table: str
    record: dict[str, Any]
    old_record: dict[str, Any] | None = None


async def _verify_webhook_signature(request: Request, body: bytes) -> bool:
    # বাংলা মন্তব্য: Webhook secret configure না থাকলে fail-closed নীতি অনুসরণ করা হচ্ছে
    # আগে এই ফাংশন True রিটার্ন করত, যার ফলে সব webhook accept হতো
    if not SUPABASE_WEBHOOK_SECRET:
        logger.warning(
            "SUPABASE_WEBHOOK_SECRET is not configured. "
            "Rejecting all CDC webhooks under fail-closed policy."
        )
        return False
    signature = request.headers.get("x-supabase-signature", "")
    if not signature:
        logger.warning("CDC webhook rejected: missing x-supabase-signature header")
        return False
    expected = hmac.new(
        SUPABASE_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    # বাংলা মন্তব্য: Supabase x-supabase-signature header-এ সাধারণত শুধু hex digest থাকে
    # যদি header-এ "sha256=" prefix থাকে, তবে সেটি strip করে compare করা হচ্ছে
    sig_value = signature
    if sig_value.startswith("sha256="):
        sig_value = sig_value[7:]
    if not hmac.compare_digest(expected, sig_value):
        logger.warning("CDC webhook rejected: invalid signature")
        return False
    return True


async def _delete_from_vector_db(user_id: str, doc_id: str | None = None) -> None:
    if not PINECONE_API_KEY or not PINECONE_HOST:
        return
    try:
        import httpx

        vector_id = f"{user_id}:{doc_id}" if doc_id else user_id

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.request(
                "DELETE",
                f"https://{PINECONE_HOST}/vectors/delete",
                headers={"Api-Key": PINECONE_API_KEY},
                json={"ids": [vector_id]},
            )
        logger.info(f"CDC: Deleted vector {vector_id} from Pinecone")
    except Exception as e:
        logger.error(f"CDC vector deletion failed: {e}")


@router.post("/webhook")
@with_error_bus("handle_cdc_webhook")
async def handle_cdc_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()

    if not await _verify_webhook_signature(request, body):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        import json

        event = json.loads(body)
    except Exception:
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from None

    event_type = event.get("type")
    table = event.get("table")
    record = event.get("record", {})
    old_record = event.get("old_record", {})

    logger.info(f"CDC Event received: {event_type} on {table}")

    if event_type in ("DELETE", "INSERT", "UPDATE"):
        user_id = record.get("user_id") or old_record.get("user_id")
        doc_id = record.get("id") or old_record.get("id")

        background_tasks.add_task(_delete_from_vector_db, user_id, doc_id)

    return {"status": "accepted"}


@router.get("/health")
async def cdc_health():
    return {
        "status": "ok",
        "events_processed": "active",
        "vector_sync": "enabled" if PINECONE_API_KEY else "disabled",
    }
