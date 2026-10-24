"""Generate cryptographically-secure secrets and fill only EMPTY .env entries.

Issue #1590 remediation (part 2):
- previously derived secrets from hashlib.sha256(prefix + "njel.com.bd" + "2026")
  - fully deterministic and guessable by anyone who read this repo
- now every secret comes from the OS CSPRNG via secrets.token_urlsafe()
- the .env path is no longer a hardcoded Windows path: pass it as argv[1]
  or set SUPREMEAI_ENV_FILE (default: .env in the current directory)

Existing non-empty values are intentionally left untouched; only empty
entries get filled, so re-running never rotates live secrets silently.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import urllib.request

ENV_FILE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SUPREMEAI_ENV_FILE", ".env")


def gen_secret(prefix: str = "") -> str:
    """CSPRNG-based secret (issue #1590: no deterministic hashes, no domains)."""
    return f"{prefix}{secrets.token_urlsafe(48)}"


# 1. Read existing .env (if present)
env_dict: dict[str, str] = {}
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        env_content = f.read()
    for line in env_content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split("=", 1)
        if len(parts) == 2:
            env_dict[parts[0]] = parts[1].strip()
else:
    env_content = ""
    print(f"[generate_secrets] no existing file at '{ENV_FILE}' — a new one will be created")

# 2. Generate secrets (all CSPRNG)
new_vars = {
    "JWT_SECRET": gen_secret(),
    "SUPREMEAI_CREDENTIAL_ENC_KEY": secrets.token_urlsafe(48),
    "TEST_VAULT_KEY": gen_secret(),
    "SECRET": gen_secret(),
    "SECRET_BACKEND": gen_secret(),
    "DB_PASSWORD": gen_secret(),
    "VITE_FIREBASE_APP_ID": "1:110488671645256111793:web:abcd1234efgh5678",  # Mocked default
    "VITE_FIREBASE_AUTH_DOMAIN": "supremeai-a" + ".firebaseapp" + ".com",
    "VITE_FIREBASE_MESSAGING_SENDER_ID": "110488671645256111793",
    "VITE_FIREBASE_STORAGE_BUCKET": "supremeai-a.appspot.com",
}

# 3. Fetch Cloudflare Zone ID (optional, only if token available)
cf_token = env_dict.get("CLOUDFLARE_API_TOKEN", "").strip("'\"")
if cf_token:
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/zones",
        headers={"Authorization": f"Bearer {cf_token}"},
    )
    try:
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode())
        if data.get("success") and len(data["result"]) > 0:
            new_vars["CLOUDFLARE_ZONE_ID"] = data["result"][0]["id"]
            print(f"CF Zone Found: {new_vars['CLOUDFLARE_ZONE_ID']}")
    except Exception as e:  # noqa: BLE001 - network probe must never crash secret generation
        print("CF Error:", e)

# 4. Fetch Render info (optional, only if token available)
render_token = env_dict.get("RENDER_API_KEY", "").strip("'\"")
if render_token:
    req = urllib.request.Request(
        "https://api.render.com/v1/services?limit=100",
        headers={"Authorization": f"Bearer {render_token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode())
        for item in data:
            svc = item["service"]
            if svc["name"] == "supremeai-backend-6nwi":
                new_vars["RENDER_BACKUP_SVC_ID"] = svc["id"]
                print(f"Render Backup SVC Found: {svc['id']}")
            if "worker" in svc["name"].lower() or svc["type"] == "background_worker":
                new_vars["RENDER_WORKER_SVC_ID"] = svc["id"]
                print(f"Render Worker SVC Found: {svc['id']}")
    except Exception as e:  # noqa: BLE001
        print("Render Error:", e)

# 5. Update .env content — fill ONLY empty entries
lines = env_content.splitlines()
new_lines = []
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        new_lines.append(line)
        continue

    parts = stripped.split("=", 1)
    if len(parts) == 2:
        key, value = parts[0], parts[1].strip()
        if (not value or value == '""' or value == "''") and key in new_vars:
            val = new_vars[key]
            if " " in val or "!" in val or "=" in val:
                val = f'"{val}"'
            new_lines.append(f"{key}={val}")
            print(f"Updated: {key}")
            continue
    new_lines.append(line)

_parent = os.path.dirname(os.path.abspath(ENV_FILE))
os.makedirs(_parent, exist_ok=True)
with open(ENV_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(new_lines) + "\n")

print("Done updating .env!")
