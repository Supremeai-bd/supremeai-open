"""
sync_cookies_to_infisical.py — Export Authenticated AI Fleet Cookies to Infisical Cloud Vault
==========================================================================================
1. Exports all 237+ decrypted cookies from ~/.gemini_isolated_session (Gemini, ChatGPT, Grok, Perplexity).
2. Encrypts the payload with Sovereign Fernet AES-256.
3. Uploads the encrypted bundle to Infisical Production Vault (SSOT).
4. Any cloud microservice (Render, Cloudflare, etc.) can pull and restore these cookies without browser login!
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
import urllib.request
import urllib.parse
import gzip
from pathlib import Path
from playwright.async_api import async_playwright

from .credential_vault import CredentialVault, get_or_create_master_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("infisical_sync")

INFISICAL_API = os.getenv("INFISICAL_API", "https://app.infisical.com")
CLIENT_ID = os.getenv("INFISICAL_CLIENT_ID", "9f2363cf-3cec-43f6-b155-a8625de19250")
CLIENT_SECRET = os.getenv("INFISICAL_CLIENT_SECRET", "")
WORKSPACE_ID = os.getenv("INFISICAL_PROJECT_ID", "92aa20c4-aef5-4e33-82bd-efb06058aaf0")
ENVIRONMENT = os.getenv("INFISICAL_ENV", "prod")


USER_DATA_DIR = os.path.expanduser(r"~\.gemini_isolated_session")
VAULT_DIR = Path(os.path.expanduser(r"~\.supremeai_vault"))


def infisical_login() -> str:
    """Authenticates using Universal Auth Machine Identity to get access token."""
    url = f"{INFISICAL_API}/api/v1/auth/universal-auth/login"
    payload = {"clientId": CLIENT_ID, "clientSecret": CLIENT_SECRET}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["accessToken"]


def set_infisical_secret(token: str, key: str, value: str):
    """Sets or updates a secret in Infisical Production Vault."""
    url = f"{INFISICAL_API}/api/v3/secrets/raw/{key}"
    payload = {
        "workspaceId": WORKSPACE_ID,
        "environment": ENVIRONMENT,
        "secretValue": value,
        "secretPath": "/",
        "secretComment": "Sovereign AI Fleet Auth Cookies SSOT",
    }
    
    # Try POST first (create), fallback to PATCH (update) if already exists
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info(f"✅ Infisical secret '{key}' created successfully (HTTP {resp.status}).")
            return
    except urllib.error.HTTPError as e:
        if e.code in (400, 404, 409):
            # Update existing secret via PATCH
            patch_req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                method="PATCH"
            )
            try:
                with urllib.request.urlopen(patch_req, timeout=15) as presp:
                    logger.info(f"✅ Infisical secret '{key}' updated successfully (HTTP {presp.status}).")
                    return
            except Exception as pe:
                logger.error(f"Failed to patch secret '{key}': {pe}")
                raise
        else:
            err_body = e.read().decode('utf-8', errors='ignore')
            logger.error(f"Infisical HTTPError {e.code}: {err_body}")
            raise



async def export_and_sync():
    print("=================================================================")
    print("   SupremeAI: AI Fleet Cookies Exporter & Infisical Cloud Sync")
    print("=================================================================")

    # 1. Export all decrypted cookies from persistent profile
    logger.info("Exporting decrypted cookies from persistent profile...")
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="msedge",
            headless=True,
            args=["--no-first-run", "--disable-blink-features=AutomationControlled"]
        )
        cookies = await ctx.cookies()
        await ctx.close()

    total = len(cookies)
    logger.info(f"Successfully extracted {total} active cookies across all domains.")

    # Filter to AI-relevant domains for optimal size and security
    ai_keywords = ["google", "chatgpt", "openai", "perplexity", "grok", "x.ai", "mistral"]
    ai_cookies = [c for c in cookies if any(k in c.get("domain", "").lower() for k in ai_keywords)]
    logger.info(f"Found {len(ai_cookies)} AI Fleet session cookies (Gemini, ChatGPT, Grok, Perplexity, Mistral).")

    raw_json = json.dumps(ai_cookies, indent=2)

    # 2. Save locally in encrypted vault
    vault = CredentialVault()
    enc_payload = vault.encrypt(raw_json)

    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    local_enc_file = VAULT_DIR / "ai_fleet_cookies.enc.json"
    local_enc_file.write_text(enc_payload, encoding="utf-8")
    logger.info(f"Encrypted local backup stored at: {local_enc_file}")

    # Compress with gzip + base64 for token-efficient storage in Infisical
    compressed = gzip.compress(raw_json.encode("utf-8"))
    b64_compressed = base64.b64encode(compressed).decode("utf-8")
    logger.info(f"Compressed cookie payload: {len(raw_json)} bytes -> {len(b64_compressed)} chars (Base64+gzip).")

    # 3. Authenticate with Infisical
    logger.info("Authenticating with Infisical Cloud Production Vault...")
    token = infisical_login()
    logger.info("Infisical Universal Auth successful.")

    # 4. Upload to Infisical
    # A. Compressed Base64 format (ready for immediate headless injection in cloud runners)
    set_infisical_secret(token, "AI_FLEET_COOKIES_GZIP_B64", b64_compressed)
    
    # B. AES-256 Encrypted format
    set_infisical_secret(token, "AI_FLEET_COOKIES_ENC", enc_payload)

    print("\n=================================================================")
    print("   [SUCCESS]: AI Fleet Cookies Synced to Infisical Cloud Vault!")
    print(f"   - Total AI Cookies: {len(ai_cookies)}")
    print(f"   - Target Vault: Infisical Production ({WORKSPACE_ID})")
    print("   - Keys Synced: AI_FLEET_COOKIES_GZIP_B64, AI_FLEET_COOKIES_ENC")
    print("   All cloud microservices can now use these sessions 24/7!")
    print("=================================================================")


if __name__ == "__main__":
    asyncio.run(export_and_sync())
