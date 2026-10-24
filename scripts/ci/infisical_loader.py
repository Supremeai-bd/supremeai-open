#!/usr/bin/env python3
"""Fetch Infisical secrets into GitHub Actions without logging values.

Improvements over v1:
- Retry with exponential back-off on transient network/timeout errors (3 attempts).
- Workspace resolution: tries UUID lookup first, then slug fallback, then raw value.
- Graceful degradation: non-zero exit only on auth failure; workspace/secret errors
  are warnings so CI is not broken by Infisical downtime.
- Supports both v3/secrets/raw and v2 fallback if v3 returns empty.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API = "https://app.infisical.com"
_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 5, 10]  # seconds between retries


def call(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: int = 45,
    retries: int = _MAX_RETRIES,
) -> dict[str, Any]:
    """HTTP call with retry + exponential back-off."""
    data = json.dumps(payload).encode() if payload is not None else None
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.load(response)  # type: ignore[return-value]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt < retries - 1:
                delay = _RETRY_DELAYS[attempt]
                print(
                    f"[warn] Infisical API call failed (attempt {attempt + 1}/{retries}): {exc}. "
                    f"Retrying in {delay}s...",
                    file=sys.stderr,
                )
                time.sleep(delay)
            else:
                raise RuntimeError(f"Infisical API unreachable after {retries} attempts: {exc}") from exc
    # Should never reach here, but satisfy type checker
    raise RuntimeError(f"Infisical API unreachable: {last_exc}")


def resolve_workspace_id(token: str, raw_value: str) -> str:
    """Resolve project slug or ID to an actual workspace UUID.

    Strategy:
    1. Call /api/v1/workspace to list all workspaces.
    2. Match by 'id' (UUID) or 'slug'.
    3. If the list call fails or no match, use the raw value as-is (might already be a UUID).
    """
    try:
        ws_res = call(f"{API}/api/v1/workspace", token=token)
        workspaces: list[dict[str, Any]] = ws_res.get("workspaces", [])
        for ws in workspaces:
            if ws.get("id") == raw_value or ws.get("slug") == raw_value:
                resolved = ws.get("id", raw_value)
                if resolved != raw_value:
                    print(f"[info] Resolved Infisical project slug '{raw_value}' → ID '{resolved}'")
                return resolved
        # If no match found, log and fall through to raw value
        print(
            f"[warn] Infisical workspace list returned {len(workspaces)} entries but none matched "
            f"'{raw_value}'. Using raw value (may already be a UUID).",
            file=sys.stderr,
        )
    except Exception as workspace_error:
        print(
            f"[warn] Unable to resolve Infisical workspace: {workspace_error}. "
            "Using raw INFISICAL_PROJECT_ID value.",
            file=sys.stderr,
        )
    return raw_value


def fetch_secrets(token: str, workspace_id: str, env: str, secret_path: str) -> dict[str, str]:
    """Fetch secrets, trying v3 API first then v2 as fallback."""
    query = urllib.parse.urlencode({
        "workspaceId": workspace_id,
        "environment": env,
        "secretPath": secret_path,
    })

    # Try v3 (raw secrets endpoint)
    try:
        items = call(f"{API}/api/v3/secrets/raw?{query}", token=token).get("secrets", [])
        values = {
            item["secretKey"]: item["secretValue"]
            for item in items
            if item.get("secretKey") and item.get("secretValue") is not None
        }
        if values:
            return values
        print("[warn] v3 secrets endpoint returned 0 secrets, trying v2 fallback...", file=sys.stderr)
    except Exception as v3_err:
        print(f"[warn] v3 secrets endpoint failed: {v3_err}. Trying v2...", file=sys.stderr)

    # Fallback to v2
    items_v2 = call(f"{API}/api/v2/secrets?{query}", token=token).get("secrets", [])
    values = {
        item["secretKey"]: item["secretValue"]
        for item in items_v2
        if item.get("secretKey") and item.get("secretValue") is not None
    }
    return values


def main() -> int:
    required = ["INFISICAL_CLIENT_ID", "INFISICAL_CLIENT_SECRET", "INFISICAL_PROJECT_ID"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        print(f"::error::Missing Infisical bootstrap variables: {', '.join(missing)}")
        return 2

    env = os.environ.get("INFISICAL_ENV", "prod")
    if env != "prod":
        print("::error::CI secret loader only permits INFISICAL_ENV=prod")
        return 2

    # Detect dummy/mock credentials (used in unit tests) — skip safely
    is_dummy_env = any(
        str(os.environ.get(k, "")).startswith(("dummy-", "mock-", "test-"))
        for k in required
    )
    if is_dummy_env:
        print("::warning::Detected dummy/mock credentials for Infisical. Skipping remote vault load safely.")
        return 0

    # ------------------------------------------------------------------ #
    # Step 1: Authenticate with Universal Auth                             #
    # ------------------------------------------------------------------ #
    print("[info] Attempting Universal Auth (Machine Identity) for authentication...")
    try:
        auth_resp = call(
            f"{API}/api/v1/auth/universal-auth/login",
            method="POST",
            payload={
                "clientId": os.environ["INFISICAL_CLIENT_ID"],
                "clientSecret": os.environ["INFISICAL_CLIENT_SECRET"],
            },
        )
        token = auth_resp.get("accessToken")
        if not token:
            print("::error::Infisical authentication returned no access token")
            return 1
    except Exception as auth_exc:
        print(f"::error::Infisical token is unauthorized or secret fetch failed\n::error::{auth_exc}")
        return 1

    # ------------------------------------------------------------------ #
    # Step 2: Resolve workspace ID                                         #
    # ------------------------------------------------------------------ #
    raw_project = os.environ["INFISICAL_PROJECT_ID"]
    workspace_id = resolve_workspace_id(token, raw_project)

    # ------------------------------------------------------------------ #
    # Step 3: Fetch secrets                                                #
    # ------------------------------------------------------------------ #
    secret_path = os.environ.get("INFISICAL_SECRET_PATH", "/")
    try:
        values = fetch_secrets(token, workspace_id, env, secret_path)
    except Exception as fetch_exc:
        print(f"::warning::Infisical secret fetch failed (non-blocking): {fetch_exc}")
        # Graceful degradation: don't break CI if secrets unavailable
        return 0

    if not values:
        print("::warning::Infisical returned 0 secrets — check project/environment config.")
        return 0

    # ------------------------------------------------------------------ #
    # Step 4: Write to GITHUB_ENV                                          #
    # ------------------------------------------------------------------ #
    target = os.environ.get("GITHUB_ENV")
    if not target:
        print(f"Loaded {len(values)} Infisical keys (GITHUB_ENV unavailable; validation only)")
        return 0

    with open(target, "a", encoding="utf-8") as output:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                delimiter = f"EOF_{hash(key) & 0xffffffff:x}"
                output.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")
            else:
                output.write(f"{key}={value}\n")

    print(f"Loaded {len(values)} Infisical keys into GitHub Actions environment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
