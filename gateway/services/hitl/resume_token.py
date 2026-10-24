"""services/hitl/resume_token.py — M17 P-A: one-bridge-many-doors (issue #1278).

বাংলা মতবাদ (MODULE_17): "one-bridge-many-doors" — HITL approval-এর সেতু এক,
দরজা অনেক। ড্যাশবোর্ড সেশন ছাড়াও approver একটি **resume-URL token** দিয়ে
(টেলিগ্রাম/ইমেইল/মোবাইল — যে-কোনো দরজা) approve/reject করতে পারেন।

নিরাপত্তা-চুক্তি:
- টোকেন = HMAC-SHA256(json payload, jwt_secret) — জাল হয় না; raw টোকেন কখনো
  রেকর্ডে থাকে না (শুধু sha256 হ্যাশ);
- টোকেন **একবারই** খরচ হয় — consume-এর পরে `used_at` স্থায়ী হয়;
- আসল double-approve নিরাপত্তা engine-এর বিদ্যমান CAS transition-এ — রেস-এ
  দুটো consume গেলেও approve() একবারই জেতে (লুজার → 409);
- TTL মেয়াদোত্তীর্ণ টোকেন 410; ভুয়া/অজানা টোকেন 403; রেকর্ডে সর্বোচ্চ
  MAX_TOKENS_PER_RECORD টাকেন (পুরোনো আগে-ব্যবহৃতগুলো প্রত্যাহারযোগ্য)।
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from core.logging_config import logger

MAX_TOKENS_PER_RECORD = 10
DEFAULT_RESUME_TTL_SECONDS = 24 * 3600


class ResumeTokenError(ValueError):
    """Raised for invalid/forged tokens (maps to 403)."""


class ResumeTokenExpiredError(ResumeTokenError):
    """Raised when the token TTL has elapsed (maps to 410)."""


class ResumeTokenAlreadyUsedError(ResumeTokenError):
    """Raised on replay of a consumed token (maps to 409)."""


def _secret() -> bytes:
    """HMAC key — jwt_secret (fail-closed; engine-এর বাকি চুক্তির সাথে এক সত্যের উৎস)।"""
    from core.config import settings

    secret = str(getattr(settings, "jwt_secret", "") or "")
    if not secret:
        # test/CI fallback — প্রোডাকশনে jwt_secret অবশ্যই থাকে (settings validator)
        if (
            os.environ.get("ENV") in {"test", "testing", "ci"}
            or "pytest" in __import__("sys").modules
        ):
            secret = "test_only_resume_token_secret"
        else:
            raise RuntimeError("jwt_secret is required to sign HITL resume tokens (fail-closed).")
    return secret.encode("utf-8")


def _sign(payload_b64: str) -> str:
    return hmac.new(_secret(), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_resume_token(
    engine: Any,
    record_id: str,
    actor_id: str,
    *,
    ttl_seconds: int | None = None,
) -> str:
    """Mint a one-time resume token bound to (record_id, actor_id) and record its hash.

    Returns the RAW token (only place it ever exists) — the caller builds the
    resume URL and delivers it out-of-band.
    """
    if not actor_id:
        raise ResumeTokenError("actor_id is required to issue a resume token.")

    expires_at = datetime.now(UTC) + timedelta(
        seconds=ttl_seconds if ttl_seconds is not None else DEFAULT_RESUME_TTL_SECONDS
    )
    payload = {
        "rid": record_id,
        "act": actor_id,
        "exp": expires_at.isoformat(),
        "nonce": secrets.token_urlsafe(16),
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode()
    token = f"{payload_b64}.{_sign(payload_b64)}"

    doc_ref = engine.db.client.collection(engine.collection_name).document(record_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise ValueError(f"Pending approval record {record_id} not found.")

    existing = doc.to_dict().get("resume_tokens") or []
    existing = existing[-(MAX_TOKENS_PER_RECORD - 1) :]
    existing.append(
        {
            "token_hash": _token_hash(token),
            "actor_id": actor_id,
            "expires_at": expires_at.isoformat(),
            "used_at": None,
        }
    )
    doc_ref.update({"resume_tokens": existing})
    logger.info(f"[M17 P-A] resume token issued for '{record_id}' (actor={actor_id}).")
    return token


def _verify_signature(token: str) -> dict[str, Any]:
    try:
        payload_b64, sig = token.rsplit(".", 1)
    except ValueError as exc:
        raise ResumeTokenError("Malformed resume token.") from exc
    if not hmac.compare_digest(_sign(payload_b64), sig):
        raise ResumeTokenError("Invalid resume token signature.")
    try:
        return json.loads(base64.urlsafe_b64decode(payload_b64.encode()).decode())
    except Exception as exc:  # noqa: BLE001 — any decode failure = forged/malformed
        raise ResumeTokenError("Malformed resume token payload.") from exc


def consume_resume_token(engine: Any, record_id: str, token: str) -> str:
    """Validate + burn a resume token; returns the bound actor_id.

    Raises: ResumeTokenAlreadyUsedError (replay), ResumeTokenExpiredError
    (TTL), ResumeTokenError (forged/malformed), ValueError (unknown record).
    """
    payload = _verify_signature(token)
    if payload.get("rid") != record_id:
        raise ResumeTokenError("Token is not bound to this record.")

    doc_ref = engine.db.client.collection(engine.collection_name).document(record_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise ValueError(f"Pending approval record {record_id} not found.")

    entries = doc.to_dict().get("resume_tokens") or []
    target_hash = _token_hash(token)
    entry = next((e for e in entries if e.get("token_hash") == target_hash), None)
    if entry is None:
        raise ResumeTokenError("Resume token not recognized for this record.")
    if entry.get("used_at"):
        raise ResumeTokenAlreadyUsedError("Resume token has already been used.")

    exp = entry.get("expires_at")
    if exp:
        try:
            expiry = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ResumeTokenError("Corrupt token expiry.") from exc
        if expiry < datetime.now(UTC):
            raise ResumeTokenExpiredError("Resume token has expired.")

    # Burn (one-time). The REAL double-approve safety is engine approve()'s CAS —
    # a consume-race can only produce one winning decision; the loser 409s.
    doc_ref.update(
        {
            "resume_tokens": [
                {**e, "used_at": datetime.now(UTC).isoformat()} if e is entry else e
                for e in entries
            ]
        }
    )
    return str(payload.get("act") or "")


def build_resume_url(base_url: str, record_id: str, token: str) -> str:
    """Build the out-of-band resume URL (the 'door' for any channel)."""
    base = base_url.rstrip("/")
    return f"{base}/api/v1/hitl/{record_id}/resume?token={token}"
