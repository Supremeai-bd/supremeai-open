"""Encrypted browser credentials management (admin-guarded).

Split out of the former single-module api/routes/browser.py verbatim.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_current_user_token
from api.routes.admin_dashboard import require_admin_token
from api.routes.browser import router
from core.errors.error_bus import with_error_bus
from core.kernel.audit_logger import AuditLogger
from core.security.secure_credential_store import SecureCredentialStore


class CredentialRequest(BaseModel):
    serviceName: str | None = None  # Frontend compat
    provider: str | None = None  # Canonical schema
    username: str | None = None  # Frontend compat
    label: str | None = None  # Canonical schema
    password: str | None = None  # Frontend compat
    secret: str | None = None  # Canonical schema
    userId: str | None = "default"
    authType: str | None = None
    secret_metadata: dict[str, Any] | None = None


class CredentialUseRequest(BaseModel):
    action: str | None = "autofill"
    target_url: str | None = None


def get_audit() -> AuditLogger:
    return AuditLogger()


def get_credential_store() -> SecureCredentialStore:
    return SecureCredentialStore()


CREDENTIALS: list[dict[str, Any]] = []


@router.get("/credentials", dependencies=[Depends(require_admin_token)])
@with_error_bus("get_credentials")
def get_credentials(
    userId: str = "default",
    current_user: dict = Depends(get_current_user_token),
):
    from database.supabase_client import db

    cred_store = get_credential_store()
    effective_owner = current_user.get("sub") or userId or "default"
    user_creds = []

    # 1. Try fetching from Supabase DB
    db_rows = db.list_browser_credentials(effective_owner, include_revoked=False)
    if not db_rows and effective_owner != userId:
        db_rows = db.list_browser_credentials(userId, include_revoked=False)

    if db_rows:
        for row in db_rows:
            decrypted = cred_store.decrypt(row.get("encrypted_secret", ""), row.get("key_ref"))
            try:
                decrypted_dict = json.loads(decrypted)
            except Exception:
                decrypted_dict = {"secret": decrypted}

            masked_dict = {
                "id": row.get("id"),
                "serviceName": row.get("provider") or row.get("label"),
                "provider": row.get("provider"),
                "username": row.get("label"),
                "label": row.get("label"),
                "status": "revoked" if row.get("is_revoked") else "active",
                "createdAt": row.get("created_at"),
                "updatedAt": row.get("updated_at"),
                "lastUsedAt": row.get("updated_at"),
            }
            # Mask sensitive values
            for k, v in decrypted_dict.items():
                if k in ("password", "token", "secret", "api_key") and isinstance(v, str):
                    masked_dict[k] = cred_store.mask(v)
                elif k == "username":
                    masked_dict["username"] = v
            if "password" not in masked_dict and "secret" in decrypted_dict:
                masked_dict["password"] = cred_store.mask(decrypted_dict.get("secret", ""))

            user_creds.append(masked_dict)
    else:
        # Fallback to in-memory store for backwards compatibility or offline/test mode
        for c in CREDENTIALS:
            if c.get("userId") in (effective_owner, userId):
                decrypted = cred_store.decrypt(c.get("ciphertext", ""), c.get("key_ref"))
                try:
                    decrypted_dict = json.loads(decrypted)
                except Exception:
                    decrypted_dict = {}

                masked_dict = {"id": c.get("id")}
                for k, v in decrypted_dict.items():
                    if k in ("password", "token", "secret", "api_key", "username") and isinstance(
                        v, str
                    ):
                        if k == "username":
                            masked_dict[k] = v
                        else:
                            masked_dict[k] = cred_store.mask(v)
                    else:
                        masked_dict[k] = v
                masked_dict["serviceName"] = str(c.get("serviceName", ""))
                masked_dict["username"] = masked_dict.get("username") or str(c.get("username", ""))
                masked_dict["status"] = "active"
                user_creds.append(masked_dict)

    return {"credentials": user_creds}


@router.post("/credentials", dependencies=[Depends(require_admin_token)])
def save_credential(
    cred: CredentialRequest,
    current_user: dict = Depends(get_current_user_token),
):
    from database.supabase_client import db

    provider = cred.provider or cred.serviceName or "unknown_provider"
    label = cred.label or cred.username or "default"
    raw_secret = cred.secret or cred.password or ""
    owner_id = current_user.get("sub") or cred.userId or "default"

    if not raw_secret:
        raise HTTPException(status_code=400, detail="Secret or password is required")

    cred_store = get_credential_store()
    secret_payload = json.dumps(
        {
            "serviceName": provider,
            "username": label,
            "password": raw_secret,
            "secret": raw_secret,
            "authType": cred.authType or "basic_auth",
        }
    )
    ciphertext, key_ref = cred_store.encrypt(secret_payload)
    cred_id = f"cred_{uuid.uuid4().hex[:12]}"

    # Persist to Supabase
    db_row = {
        "id": cred_id,
        "owner_id": owner_id,
        "provider": provider,
        "label": label,
        "encrypted_secret": ciphertext,
        "key_ref": key_ref,
        "secret_metadata": cred.secret_metadata or {"auth_type": cred.authType or "basic_auth"},
        "is_revoked": False,
    }
    db.save_browser_credential(db_row)

    # In-memory mirror for local fallback
    new_cred = {
        "id": cred_id,
        "userId": owner_id,
        "serviceName": provider,
        "username": label,
        "ciphertext": ciphertext,
        "key_ref": key_ref,
    }
    CREDENTIALS.append(new_cred)

    # Redacted audit logging (Zero Secrets Exposed)
    get_audit().log_decision(
        action_type="browser_credential_created",
        decision_details=f"Stored credential id '{cred_id}' for provider '{provider}' and label '{label}'",
        reasoning=f"Owner '{owner_id}' created an encrypted browser credential.",
    )

    return {
        "id": cred_id,
        "serviceName": provider,
        "provider": provider,
        "label": label,
        "owner_id": owner_id,
        "success": True,
    }


@router.post("/credentials/{credential_id}/use", dependencies=[Depends(require_admin_token)])
def use_credential(
    credential_id: str,
    req: CredentialUseRequest | None = None,
    current_user: dict = Depends(get_current_user_token),
):
    from database.supabase_client import db

    caller_id = current_user.get("sub") or "admin"
    cred_store = get_credential_store()

    # Look up in Supabase
    row = db.get_browser_credential(credential_id)
    if not row:
        # Fallback to in-memory
        row = next((c for c in CREDENTIALS if c.get("id") == credential_id), None)

    if not row:
        get_audit().log_decision(
            action_type="browser_credential_access_failed",
            decision_details=f"Attempted access to non-existent credential id '{credential_id}'",
            reasoning=f"Caller '{caller_id}' requested unknown credential.",
        )
        raise HTTPException(status_code=404, detail="Credential not found")

    owner_id = row.get("owner_id") or row.get("userId")
    # Ownership verification: must be owner or admin
    if current_user.get("role") != "admin" and owner_id != caller_id:
        get_audit().log_decision(
            action_type="browser_credential_unauthorized_access",
            decision_details=f"Unauthorized use attempt for credential '{credential_id}' owned by '{owner_id}'",
            reasoning=f"Caller '{caller_id}' denied access due to ownership mismatch.",
        )
        raise HTTPException(status_code=403, detail="Forbidden: You do not own this credential")

    if row.get("is_revoked"):
        get_audit().log_decision(
            action_type="browser_credential_access_failed",
            decision_details=f"Attempted access to revoked credential id '{credential_id}'",
            reasoning="Credential has been revoked.",
        )
        raise HTTPException(
            status_code=400, detail="Credential has been revoked and cannot be used"
        )

    # Decrypt in memory for automation execution
    ciphertext = row.get("encrypted_secret") or row.get("ciphertext") or ""
    key_ref = row.get("key_ref")
    decrypted = cred_store.decrypt(ciphertext, key_ref)
    try:
        decrypted_payload = json.loads(decrypted)
    except Exception:
        decrypted_payload = {"secret": decrypted}

    # Audit log (audit log receives NO raw secrets)
    action = req.action if req else "autofill"
    provider = row.get("provider") or row.get("serviceName") or "unknown"
    get_audit().log_decision(
        action_type="browser_credential_used",
        decision_details=f"Used credential id '{credential_id}' for provider '{provider}', action='{action}'",
        reasoning=f"Authorized autonomous browser execution by '{caller_id}'.",
    )

    return {
        "id": credential_id,
        "provider": provider,
        "label": row.get("label") or row.get("username"),
        "status": "active",
        "action": action,
        "secret": decrypted_payload.get("password") or decrypted_payload.get("secret"),
        "username": decrypted_payload.get("username"),
    }


@router.post("/credentials/{credential_id}/revoke", dependencies=[Depends(require_admin_token)])
def revoke_credential(
    credential_id: str,
    current_user: dict = Depends(get_current_user_token),
):
    from database.supabase_client import db

    caller_id = current_user.get("sub") or "admin"
    row = db.get_browser_credential(credential_id)
    if not row:
        row = next((c for c in CREDENTIALS if c.get("id") == credential_id), None)

    if not row:
        raise HTTPException(status_code=404, detail="Credential not found")

    owner_id = row.get("owner_id") or row.get("userId")
    if current_user.get("role") != "admin" and owner_id != caller_id:
        get_audit().log_decision(
            action_type="browser_credential_unauthorized_access",
            decision_details=f"Unauthorized revoke attempt for credential '{credential_id}'",
            reasoning=f"Caller '{caller_id}' denied access due to ownership mismatch.",
        )
        raise HTTPException(status_code=403, detail="Forbidden: You do not own this credential")

    # Update in DB
    db.revoke_browser_credential(credential_id, owner_id)
    # Update in-memory
    for c in CREDENTIALS:
        if c.get("id") == credential_id:
            c["is_revoked"] = True

    get_audit().log_decision(
        action_type="browser_credential_revoked",
        decision_details=f"Revoked credential id '{credential_id}'",
        reasoning=f"Revocation executed by '{caller_id}'.",
    )
    return {"id": credential_id, "is_revoked": True, "success": True}


@router.delete("/credentials/{id}", dependencies=[Depends(require_admin_token)])
@router.delete("/credentials/{credential_id}", dependencies=[Depends(require_admin_token)])
def delete_credential(
    id: str | None = None,
    credential_id: str | None = None,
    current_user: dict = Depends(get_current_user_token),
):
    global CREDENTIALS
    from database.supabase_client import db

    target_id = id or credential_id
    if not target_id:
        raise HTTPException(status_code=400, detail="Credential id is required")

    caller_id = current_user.get("sub") or "admin"
    row = db.get_browser_credential(target_id)
    if not row:
        row = next((c for c in CREDENTIALS if c.get("id") == target_id), None)

    if not row:
        raise HTTPException(status_code=404, detail="Credential not found")

    owner_id = row.get("owner_id") or row.get("userId")
    if current_user.get("role") != "admin" and owner_id != caller_id:
        get_audit().log_decision(
            action_type="browser_credential_unauthorized_access",
            decision_details=f"Unauthorized delete attempt for credential '{target_id}'",
            reasoning=f"Caller '{caller_id}' denied access due to ownership mismatch.",
        )
        raise HTTPException(status_code=403, detail="Forbidden: You do not own this credential")

    db.delete_browser_credential(target_id, owner_id)
    CREDENTIALS = [c for c in CREDENTIALS if c.get("id") != target_id]

    get_audit().log_decision(
        action_type="browser_credential_deleted",
        decision_details=f"Deleted credential id '{target_id}'",
        reasoning=f"Deletion executed by '{caller_id}'.",
    )
    return {"id": target_id, "success": True}
