"""
Infisical Vault Cleanup Utility:
Removes expired/stale keys:
- INFISICAL_TOKEN (Expired Google-OAuth token)
- RENDER_API_KEY_BACKUP (Duplicate of RENDER_API_KEY_2)
- RENDER_BACKUP_API_KEY_2 (Duplicate of RENDER_API_KEY_3)

Usage:
  python scripts/security/delete_vault_stale_keys.py
"""

import json
import os
import sys
import urllib.request
import urllib.error

INFISICAL_API = os.getenv("INFISICAL_API_URL", "https://app.infisical.com/api")
CLIENT_ID = os.getenv("INFISICAL_CLIENT_ID")
CLIENT_SECRET = os.getenv("INFISICAL_CLIENT_SECRET")
PROJECT_ID = os.getenv("INFISICAL_PROJECT_ID")
ENVIRONMENT = os.getenv("INFISICAL_ENV", "prod")

KEYS_TO_DELETE = [
    "INFISICAL_TOKEN",
    "RENDER_API_KEY_BACKUP",
    "RENDER_BACKUP_API_KEY_2",
]


def login() -> str:
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError("INFISICAL_CLIENT_ID and INFISICAL_CLIENT_SECRET must be set.")

    url = f"{INFISICAL_API}/v1/auth/universal-auth/login"
    payload = json.dumps({"clientId": CLIENT_ID, "clientSecret": CLIENT_SECRET}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("accessToken")


def delete_secret(token: str, secret_name: str) -> bool:
    if not PROJECT_ID:
        raise RuntimeError("INFISICAL_PROJECT_ID must be set.")

    url = f"{INFISICAL_API}/v3/secrets/raw/{secret_name}"
    payload = json.dumps({
        "workspaceId": PROJECT_ID,
        "environment": ENVIRONMENT,
        "secretPath": "/",
        "type": "shared",
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"✅ Successfully deleted {secret_name} from Infisical ({ENVIRONMENT}).")
            return True
    except urllib.error.HTTPError as err:
        if err.code == 404:
            print(f"ℹ️ {secret_name} not found in Infisical ({ENVIRONMENT}) (already removed).")
            return True
        print(f"❌ Failed to delete {secret_name}: HTTP {err.code} - {err.reason}")
        return False
    except Exception as exc:
        print(f"❌ Error deleting {secret_name}: {exc}")
        return False


def main():
    print("🔐 Starting Infisical Vault Cleanup (Removing expired & duplicate keys)...")
    if not CLIENT_ID or not CLIENT_SECRET or not PROJECT_ID:
        print("⚠️ Missing Infisical credentials in environment:")
        print(f"  INFISICAL_CLIENT_ID: {'SET' if CLIENT_ID else 'NOT SET'}")
        print(f"  INFISICAL_CLIENT_SECRET: {'SET' if CLIENT_SECRET else 'NOT SET'}")
        print(f"  INFISICAL_PROJECT_ID: {'SET' if PROJECT_ID else 'NOT SET'}")
        print("\nPlease run this script in an environment where Infisical credentials are loaded,")
        print("or via GitHub Actions / CI.")
        sys.exit(1)

    token = login()
    success = True
    for key in KEYS_TO_DELETE:
        if not delete_secret(token, key):
            success = False

    if success:
        print("✨ Vault cleanup completed successfully.")
    else:
        print("⚠️ Some keys could not be deleted.")
        sys.exit(2)


if __name__ == "__main__":
    main()
