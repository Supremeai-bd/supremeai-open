#!/usr/bin/env python3
"""Fetch AI provider keys from Infisical vault → emit as GITHUB_ENV lines.

#3478 fix: AI PR Evaluator-কে সত্যিকারের LLM-স্মার্ট বানানো।
Founder directive: "make pr bot most smartest one using api key from infisical vault"

Flow:
  1. Universal-auth login (INFISICAL_CLIENT_ID/CLIENT_SECRET — repo secrets)
  2. Raw-secrets API → fetch GROQ/GEMINI/OPENROUTER/OPENAI/DEEPSEEK/ANTHROPIC keys
  3. Emit `KEY=VALUE` lines to stdout (CI captures via $GITHUB_ENV)
  4. Fail-open: কী না পেলে ওই কী বাদ — evaluator deterministic-এ সৎ-ফলব্যাক
  5. FORBIDDEN_KEYS (INFISICAL_*) কখনো emit নয়; কোনো কী লগে না

Usage (in workflow):
  - name: Fetch AI keys from Infisical vault
    env:
      INFISICAL_CLIENT_ID: ${{ secrets.INFISICAL_CLIENT_ID }}
      INFISICAL_CLIENT_SECRET: ${{ secrets.INFISICAL_CLIENT_SECRET }}
      INFISICAL_PROJECT_ID: ${{ secrets.INFISICAL_PROJECT_ID }}
    run: |
      python scripts/security/fetch_ai_keys.py >> $GITHUB_ENV

Exit codes: 0 = OK (some keys may be missing — fail-open), 1 = auth failure
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error

INFISICAL_AUTH_URL = "https://app.infisical.com/api/v1/auth/universal-auth/login"
INFISICAL_SECRETS_URL = "https://app.infisical.com/api/v3/secrets/raw"

# Keys to fetch from vault (mapped to env var names)
AI_KEY_NAMES = [
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
]

# Keys that must NEVER be emitted (master vault creds)
FORBIDDEN_KEYS = {
    "INFISICAL_CLIENT_ID",
    "INFISICAL_CLIENT_SECRET",
    "INFISICAL_PROJECT_ID",
    "INFISICAL_TOKEN",
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_APP_ID",
    "GITHUB_APP_INSTALLATION_ID",
    "SELF_HEAL_PAT",
}


def _fetch_access_token(client_id: str, client_secret: str) -> str | None:
    """Login via universal-auth → return access token, or None on failure."""
    data = json.dumps({
        "clientId": client_id,
        "clientSecret": client_secret,
    }).encode("utf-8")
    req = urllib.request.Request(
        INFISICAL_AUTH_URL,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            return body.get("accessToken")
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
        print(f"::warning::Infisical auth failed: {e}", file=sys.stderr)
        return None


def _fetch_secrets(access_token: str, project_id: str) -> dict[str, str]:
    """Fetch raw secrets from Infisical → return {key: value} dict."""
    url = f"{INFISICAL_SECRETS_URL}?workspaceId={project_id}&environment=prod"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
            # Infisical returns {"secrets": [{"secretKey": "...", "secretValue": "..."}, ...]}
            secrets = {}
            for s in body.get("secrets", []):
                key = s.get("secretKey", "")
                val = s.get("secretValue", "")
                if key and val and key not in FORBIDDEN_KEYS:
                    secrets[key] = val
            return secrets
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
        print(f"::warning::Infisical secrets fetch failed: {e}", file=sys.stderr)
        return {}


def main() -> int:
    client_id = os.environ.get("INFISICAL_CLIENT_ID", "")
    client_secret = os.environ.get("INFISICAL_CLIENT_SECRET", "")
    project_id = os.environ.get("INFISICAL_PROJECT_ID", "")

    if not client_id or not client_secret or not project_id:
        print("::warning::INFISICAL_CLIENT_ID/CLIENT_SECRET/PROJECT_ID not set — "
              "AI keys will not be fetched from vault (fail-open: evaluator uses deterministic fallback)",
              file=sys.stderr)
        return 0  # fail-open

    token = _fetch_access_token(client_id, client_secret)
    if not token:
        return 0  # fail-open

    secrets = _fetch_secrets(token, project_id)
    if not secrets:
        return 0  # fail-open

    # Emit KEY=VALUE lines for each AI key found in vault
    emitted = 0
    for key_name in AI_KEY_NAMES:
        val = secrets.get(key_name, "")
        if val:
            # GitHub Actions GITHUB_ENV format: KEY<<DELIMITER\nvalue\nDELIMITER
            # For simple values (no newlines), use KEY=value
            if "\n" not in val:
                print(f"{key_name}={val}")
                emitted += 1
            else:
                # Multi-line value — use heredoc format
                delim = f"EOF_{key_name}"
                print(f"{key_name}<<{delim}")
                print(val)
                print(delim)
                emitted += 1

    print(f"::notice::Fetched {emitted}/{len(AI_KEY_NAMES)} AI provider keys from Infisical vault",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
