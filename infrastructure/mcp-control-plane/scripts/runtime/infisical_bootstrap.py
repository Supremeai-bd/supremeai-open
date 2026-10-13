#!/usr/bin/env python3
"""Load production secrets from Infisical, then exec the service command."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

API = "https://app.infisical.com"

def request_json(url: str, *, method: str = "GET", payload: dict | None = None, token: str | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)

def load_secrets() -> dict[str, str]:
    project = os.environ.get("INFISICAL_PROJECT_ID")
    environment = os.environ.get("INFISICAL_ENV", "prod")
    path = os.environ.get("INFISICAL_SECRET_PATH", "/")
    if not project or environment != "prod":
        raise RuntimeError("Production Infisical bootstrap requires INFISICAL_PROJECT_ID and INFISICAL_ENV=prod")

    token = os.environ.get("INFISICAL_TOKEN")
    if not token:
        client_id = os.environ.get("INFISICAL_CLIENT_ID")
        client_secret = os.environ.get("INFISICAL_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise RuntimeError("Infisical bootstrap credentials are missing")
        token = request_json(f"{API}/api/v1/auth/universal-auth/login", method="POST", payload={"clientId": client_id, "clientSecret": client_secret}).get("accessToken")
    if not token:
        raise RuntimeError("Infisical authentication returned no access token")

    workspace_id = project
    try:
        ws_res = request_json(f"{API}/api/v1/workspace", token=token)
        for ws in ws_res.get("workspaces", []):
            if ws.get("id") == workspace_id or ws.get("slug") == workspace_id:
                workspace_id = ws.get("id")
                break
    except Exception as error:
        print(f"Unable to resolve Infisical workspace: {error}", file=sys.stderr)

    query = urllib.parse.urlencode({"workspaceId": workspace_id, "environment": environment, "secretPath": path})
    response = request_json(f"{API}/api/v3/secrets/raw?{query}", token=token)
    secrets = {}
    for item in response.get("secrets", []):
        key = item.get("secretKey")
        value = item.get("secretValue")
        if key and value:
            secrets[key] = value
    if not secrets:
        raise RuntimeError("Infisical returned no production secrets")
    return secrets

def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: infisical_bootstrap.py <command> [args...]", file=sys.stderr)
        return 2
    try:
        os.environ.update(load_secrets())
    except Exception as exc:
        print(f"Infisical bootstrap failed: {exc}", file=sys.stderr)
        return 1
    os.execvp(sys.argv[1], sys.argv[1:])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
