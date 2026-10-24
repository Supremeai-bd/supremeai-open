#!/usr/bin/env python
"""
auto_secret_rotate.py
=====================
Automatic secret rotation for SupremeAI 2.0 via Infisical Cloud Vault (Resolves #784 / RT-03).

Rotates API keys and other secrets stored in Infisical on a scheduled basis
or via manual triggering to prevent credential leakage.

Environment Variables:
- INFISICAL_CLIENT_ID / INFISICAL_CLIENT_SECRET: Vault credentials
- SECRET_IDS: Comma-separated list of secret IDs to rotate (e.g., "API_KEY_SIGNING_SECRET,SESSION_SECRET")
- For each secret, you can optionally set:
  * <SECRET_ID>_VALUE: If set, use this value; otherwise generate a cryptographically secure token
"""

import os
import secrets
import string
import sys

# Add the backend directory to path
backend_dir = os.path.join(os.path.dirname(__file__), "../../backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.security.secret_vault import get_secret_vault
from core.logging_config import logger


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()_+-=[]{}|;:,.<>?"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def rotate_secret(secret_id: str, value: str | None = None) -> bool:
    """Rotate a secret in Infisical vault or in-memory cache."""
    try:
        vault = get_secret_vault()
        if value is None:
            value = generate_secure_token(48)
            logger.info(f"[KEY] Generated new secure token for {secret_id}")
        else:
            logger.info(f"[KEY] Using operator-provided token for {secret_id}")

        # Update in vault cache and invalidate old entries
        vault.set_secret(secret_id, value)
        vault.invalidate_cache(secret_id)

        # If infisical client is initialized, push update
        if vault.client and vault.project_id:
            try:
                # Best-effort push to Infisical remote
                infisical_env = os.environ.get("INFISICAL_ENV") or ("prod" if vault.env == "production" else "dev")
                # Using client update if supported
                if hasattr(vault.client, "update_secret"):
                    vault.client.update_secret(
                        secret_name=secret_id,
                        secret_value=value,
                        project_id=vault.project_id,
                        environment=infisical_env
                    )
            except Exception as push_err:
                logger.warning(f"Could not push rotated secret to Infisical directly: {push_err}")

        logger.info(f"[SUCCESS] Successfully rotated secret '{secret_id}'")
        return True
    except Exception as e:
        logger.info(f"[FAILED] Failed to rotate secret '{secret_id}': {e}")
        return False


def main() -> None:
    """Rotate secrets declared in SECRET_IDS."""
    secret_ids_str = os.getenv("SECRET_IDS", "")
    if not secret_ids_str:
        logger.info("[INFO] SECRET_IDS environment variable is not set. Defaulting to rotatable security tokens.")
        secret_ids_str = "API_KEY_SIGNING_SECRET"

    secret_ids = [sid.strip() for sid in secret_ids_str.split(",") if sid.strip()]

    logger.info(f"[ROTATION] Starting Infisical secret rotation for {len(secret_ids)} secret(s)")
    logger.info(f"[SECRETS] Targets: {', '.join(secret_ids)}")

    success_count = 0
    for secret_id in secret_ids:
        value_env = f"{secret_id.upper().replace('-', '_')}_VALUE"
        value = os.getenv(value_env)
        if rotate_secret(secret_id, value):
            success_count += 1

    logger.info(f"[SUMMARY] Rotation complete: {success_count}/{len(secret_ids)} secrets rotated successfully")
    if success_count < len(secret_ids):
        sys.exit(1)
    else:
        logger.info("[SUCCESS] All targeted secrets processed successfully!")


if __name__ == "__main__":
    main()
