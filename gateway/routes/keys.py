import base64
import hashlib
import os
import uuid

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.logging_config import logger
from core.security.authentication.rbac import get_current_user_token as verify_token_dependency
from database.supabase_client import SupabaseDB

router = APIRouter(prefix="/keys", tags=["User Keys"])

# বাংলা (স্থায়িত্ব সংশোধন): আগে ENCRYPTION_KEY অ-ফার্নেট (non-base64) হলে বা না থাকলে
# প্রতি রিস্টার্টে নতুন random Fernet key তৈরি হতো — ফলে /keys রুটে সংরক্ষিত ইউজার
# API key গুলো প্রতিটি deploy-এর পর আর decrypt করা যেত না (silent data loss)।
# এখন secure_credential_store.RotatingFernet ও byoc/cloud_connector.py-এর প্রতিষ্ঠিত
# প্যাটার্ন অনুযায়ী sha256 → urlsafe-base64 দিয়ে ডেরাইভ করা হয় — একই সিক্রেট
# থেকে সবসময় একই Fernet key, রিস্টার্টেও সংরক্ষিত ডেটা অক্ষত থাকে।
_ENCRYPTION_SECRET = os.getenv("ENCRYPTION_KEY") or os.getenv("SUPREMEAI_CREDENTIAL_ENC_KEY")
if _ENCRYPTION_SECRET:
    try:
        cipher_suite = Fernet(_ENCRYPTION_SECRET.encode())
    except Exception:
        # প্রতিষ্ঠিত ডেরাইভেশন প্যাটার্ন: arbitrary-strength সিক্রেট → বৈধ Fernet key
        digest = hashlib.sha256(_ENCRYPTION_SECRET.encode()).digest()
        cipher_suite = Fernet(base64.urlsafe_b64encode(digest))
else:
    # কোনো সিক্রেট না থাকলেই কেবল random fallback (keys restart-এ হারাবে — dev-only)
    logger.warning(
        "⚠️ ENCRYPTION_KEY/SUPREMEAI_CREDENTIAL_ENC_KEY missing — /keys encryption uses a "
        "random key; stored keys will NOT survive restarts (dev-only behavior)."
    )
    cipher_suite = Fernet(Fernet.generate_key())


class KeyCreate(BaseModel):
    provider: str
    api_key: str


class KeyResponse(BaseModel):
    provider: str
    created_at: str


def encrypt_key(api_key: str) -> str:
    return cipher_suite.encrypt(api_key.encode()).decode()


def decrypt_key(encrypted_key: str) -> str:
    return cipher_suite.decrypt(encrypted_key.encode()).decode()


@router.post("/", response_model=KeyResponse)
async def create_or_update_key(key_data: KeyCreate, user: dict = Depends(verify_token_dependency)):
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    encrypted_key = encrypt_key(key_data.api_key)

    db = SupabaseDB()
    # Assuming upsert via Supabase RPC or direct table access
    # We will use direct table access here
    try:
        response = (
            await db.client.table("user_keys")
            .upsert(
                {"user_id": user_id, "provider": key_data.provider, "encrypted_key": encrypted_key},
                on_conflict="user_id,provider",
            )
            .execute()
        )

        data = response.data[0]
        return KeyResponse(provider=data["provider"], created_at=data["created_at"])
    except Exception as e:
        # AUD-2.9 follow-up (MANUAL_STEPS 7.4): never echo raw exception text —
        # internal errors (DSN, SQL, provider payloads) must not reach clients.
        correlation_id = uuid.uuid4().hex[:12]
        logger.exception(f"key upsert failed correlation_id={correlation_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (correlation_id: {correlation_id})",
        ) from e


@router.get("/", response_model=list[KeyResponse])
async def list_keys(user: dict = Depends(verify_token_dependency)):
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()
    try:
        response = (
            await db.client.table("user_keys")
            .select("provider, created_at")
            .eq("user_id", user_id)
            .execute()
        )
        return [
            KeyResponse(provider=row["provider"], created_at=row["created_at"])
            for row in response.data
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
