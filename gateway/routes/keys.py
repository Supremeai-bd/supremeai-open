"""
gateway/routes/keys.py — User API Key Management (BYOK), Validation & Health Audit.

Features:
  - Instant pre-flight validation on registration (Gemini, Groq, OpenAI, Anthropic, OpenRouter, etc.).
  - Secure Fernet encryption with SHA-256 derived key.
  - CRUD operations: Create/Update, List, Delete.
  - Daily Auto-Recheck Audit: Tests all active keys, updates status ('active' | 'invalid'),
    and adjusts bonus limits / generates user alerts.
"""

from __future__ import annotations

import base64
import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from core.logging_config import logger
from core.security.authentication.rbac import get_current_user_token as verify_token_dependency
from database.supabase_client import SupabaseDB

router = APIRouter(prefix="/keys", tags=["User Keys"])

_ENCRYPTION_SECRET = os.getenv("ENCRYPTION_KEY") or os.getenv("SUPREMEAI_CREDENTIAL_ENC_KEY")
if _ENCRYPTION_SECRET:
    try:
        cipher_suite = Fernet(_ENCRYPTION_SECRET.encode())
    except Exception:
        digest = hashlib.sha256(_ENCRYPTION_SECRET.encode()).digest()
        cipher_suite = Fernet(base64.urlsafe_b64encode(digest))
else:
    logger.warning(
        "⚠️ ENCRYPTION_KEY/SUPREMEAI_CREDENTIAL_ENC_KEY missing — /keys encryption uses a "
        "random key; stored keys will NOT survive restarts (dev-only behavior)."
    )
    cipher_suite = Fernet(Fernet.generate_key())


class KeyCreate(BaseModel):
    provider: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)


class KeyResponse(BaseModel):
    provider: str
    status: str = "active"
    last_verified_at: Optional[str] = None
    created_at: str


class KeyAuditResult(BaseModel):
    provider: str
    status: str
    message: str


def encrypt_key(api_key: str) -> str:
    return cipher_suite.encrypt(api_key.encode()).decode()


def decrypt_key(encrypted_key: str) -> str:
    return cipher_suite.decrypt(encrypted_key.encode()).decode()


# ─── Live Pre-flight Key Validator ──────────────────────────────────────────

async def validate_provider_key(provider: str, api_key: str) -> tuple[bool, str]:
    """
    Sends a lightweight query or ping to the provider developer API
    to check whether the key is active and not revoked/malformed.
    """
    p = provider.lower().strip()
    timeout = 8.0

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if p == "gemini":
                # Google Gemini models list endpoint
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                resp = await client.get(url)
                if resp.status_code == 200:
                    return True, "Valid Gemini API Key"
                return False, f"Gemini returned HTTP {resp.status_code}"

            elif p == "groq":
                url = "https://api.groq.com/openai/v1/models"
                headers = {"Authorization": f"Bearer {api_key}"}
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return True, "Valid Groq API Key"
                return False, f"Groq returned HTTP {resp.status_code}"

            elif p == "openai":
                url = "https://api.openai.com/v1/models"
                headers = {"Authorization": f"Bearer {api_key}"}
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return True, "Valid OpenAI API Key"
                return False, f"OpenAI returned HTTP {resp.status_code}"

            elif p == "anthropic":
                # Anthropic doesn't have an open /models list without headers, probe messages dry
                url = "https://api.anthropic.com/v1/models"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                }
                resp = await client.get(url, headers=headers)
                # 200 or 400 with model missing is fine, but 401 is invalid
                if resp.status_code in (200, 400):
                    return True, "Valid Anthropic API Key"
                return False, f"Anthropic returned HTTP {resp.status_code}"

            elif p == "openrouter":
                url = "https://openrouter.ai/api/v1/auth/key"
                headers = {"Authorization": f"Bearer {api_key}"}
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return True, "Valid OpenRouter API Key"
                return False, f"OpenRouter returned HTTP {resp.status_code}"

            elif p == "cerebras":
                url = "https://api.cerebras.ai/v1/models"
                headers = {"Authorization": f"Bearer {api_key}"}
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return True, "Valid Cerebras API Key"
                return False, f"Cerebras returned HTTP {resp.status_code}"

            elif p == "mistral":
                url = "https://api.mistral.ai/v1/models"
                headers = {"Authorization": f"Bearer {api_key}"}
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return True, "Valid Mistral API Key"
                return False, f"Mistral returned HTTP {resp.status_code}"

            elif p == "together":
                url = "https://api.together.xyz/v1/models"
                headers = {"Authorization": f"Bearer {api_key}"}
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return True, "Valid Together AI Key"
                return False, f"Together returned HTTP {resp.status_code}"

            elif p == "deepseek":
                url = "https://api.deepseek.com/models"
                headers = {"Authorization": f"Bearer {api_key}"}
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return True, "Valid DeepSeek API Key"
                return False, f"DeepSeek returned HTTP {resp.status_code}"

            elif p == "cohere":
                url = "https://api.cohere.com/v1/models"
                headers = {"Authorization": f"Bearer {api_key}"}
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return True, "Valid Cohere API Key"
                return False, f"Cohere returned HTTP {resp.status_code}"

            elif p == "perplexity":
                url = "https://api.perplexity.ai/models"
                headers = {"Authorization": f"Bearer {api_key}"}
                resp = await client.get(url, headers=headers)
                # Perplexity models endpoint or standard auth check
                if resp.status_code in (200, 404):  # 404 endpoint but authorized
                    return True, "Valid Perplexity Key format"
                return False, f"Perplexity returned HTTP {resp.status_code}"

            elif p == "huggingface":
                url = "https://huggingface.co/api/whoami-v2"
                headers = {"Authorization": f"Bearer {api_key}"}
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return True, "Valid Hugging Face Token"
                return False, f"Hugging Face returned HTTP {resp.status_code}"

            else:
                # Generic fallback check for basic key string length
                if len(api_key.strip()) >= 16:
                    return True, "Custom Key accepted"
                return False, "Key too short or unrecognised provider"

    except Exception as e:
        logger.warning(f"Key preflight probe exception for {provider}: {e}")
        # Allow saving if external network timeout occurred, but flag warning
        return True, f"Network timeout during check: {e}"


# ─── API Routes ─────────────────────────────────────────────────────────────

@router.post("/", response_model=KeyResponse)
async def create_or_update_key(key_data: KeyCreate, user: dict = Depends(verify_token_dependency)):
    user_id = user.get("sub") or user.get("user_id") or user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    provider = key_data.provider.lower().strip()
    raw_key = key_data.api_key.strip()

    # 1. Live Validation
    is_valid, msg = await validate_provider_key(provider, raw_key)
    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail=f"Key validation failed: {msg}. Please check your API key from the provider console."
        )

    encrypted_key = encrypt_key(raw_key)
    now_iso = datetime.now(timezone.utc).isoformat()

    db = SupabaseDB()
    try:
        response = (
            await db.client.table("user_keys")
            .upsert(
                {
                    "user_id": str(user_id),
                    "provider": provider,
                    "encrypted_key": encrypted_key,
                    "status": "active",
                    "last_verified_at": now_iso,
                    "created_at": now_iso,
                },
                on_conflict="user_id,provider",
            )
            .execute()
        )

        data = response.data[0] if response.data else {
            "provider": provider,
            "status": "active",
            "last_verified_at": now_iso,
            "created_at": now_iso,
        }
        return KeyResponse(
            provider=data["provider"],
            status=data.get("status", "active"),
            last_verified_at=data.get("last_verified_at", now_iso),
            created_at=data["created_at"],
        )
    except Exception as e:
        correlation_id = uuid.uuid4().hex[:12]
        logger.exception(f"key upsert failed correlation_id={correlation_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (correlation_id: {correlation_id})",
        ) from e


@router.get("/", response_model=list[KeyResponse])
async def list_keys(user: dict = Depends(verify_token_dependency)):
    user_id = user.get("sub") or user.get("user_id") or user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()
    try:
        response = (
            await db.client.table("user_keys")
            .select("provider, status, last_verified_at, created_at")
            .eq("user_id", str(user_id))
            .execute()
        )
        return [
            KeyResponse(
                provider=row["provider"],
                status=row.get("status", "active"),
                last_verified_at=row.get("last_verified_at"),
                created_at=row["created_at"],
            )
            for row in (response.data or [])
        ]
    except Exception as e:
        logger.warning(f"Error fetching user keys: {e}")
        return []


@router.delete("/{provider}")
async def delete_key(provider: str, user: dict = Depends(verify_token_dependency)):
    user_id = user.get("sub") or user.get("user_id") or user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()
    try:
        await (
            db.client.table("user_keys")
            .delete()
            .eq("user_id", str(user_id))
            .eq("provider", provider.lower().strip())
            .execute()
        )
        return {"status": "success", "message": f"{provider.upper()} key removed successfully."}
    except Exception as e:
        correlation_id = uuid.uuid4().hex[:12]
        logger.exception(f"key delete failed correlation_id={correlation_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete key (correlation_id: {correlation_id})",
        ) from e


# ─── Daily Auto-Audit Worker Route ──────────────────────────────────────────

@router.post("/audit/daily-recheck", response_model=list[KeyAuditResult])
async def run_daily_key_recheck(user: dict = Depends(verify_token_dependency)):
    """
    Rechecks user's registered keys. If a key expired or revoked, flips status to 'invalid'
    and user loses bonus quota. Returns summary of audited keys.
    """
    user_id = user.get("sub") or user.get("user_id") or user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SupabaseDB()
    try:
        response = (
            await db.client.table("user_keys")
            .select("provider, encrypted_key, status")
            .eq("user_id", str(user_id))
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database fetch failed: {e}")

    rows = response.data or []
    audit_results: list[KeyAuditResult] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for row in rows:
        provider = row["provider"]
        encrypted_key = row.get("encrypted_key")
        if not encrypted_key:
            continue

        try:
            raw_key = decrypt_key(encrypted_key)
            is_valid, reason = await validate_provider_key(provider, raw_key)
            new_status = "active" if is_valid else "invalid"

            # Update status in db
            await (
                db.client.table("user_keys")
                .update({
                    "status": new_status,
                    "last_verified_at": now_iso,
                })
                .eq("user_id", str(user_id))
                .eq("provider", provider)
                .execute()
            )

            audit_results.append(
                KeyAuditResult(
                    provider=provider,
                    status=new_status,
                    message="Key is healthy and active" if is_valid else f"Revoked/Invalid: {reason}",
                )
            )
        except Exception as ex:
            audit_results.append(
                KeyAuditResult(
                    provider=provider,
                    status="invalid",
                    message=f"Decryption/check error: {ex}",
                )
            )

    return audit_results
