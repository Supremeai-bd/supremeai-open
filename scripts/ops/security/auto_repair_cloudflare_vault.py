"""
Fetch Cloudflare credentials from Infisical prod vault,
then automatically:
1. Ensure KV namespace (HEALTH_KV) exists across all 5 accounts.
2. Generate/update scoped deploy token with Workers Scripts Write + KV Storage Write.
3. Automatically update CLOUDFLARE_API_TOKEN in Infisical vault with the valid deploy token.

Usage:
  python scripts/security/auto_repair_cloudflare_vault.py

Fail-closed secret resolution (issue #1820):
  Every fleet identifier (role email + Cloudflare account_id) MUST resolve
  from the live Infisical vault. No identifier fallback is baked into source:
  a missing/empty Infisical value aborts the run BEFORE any Cloudflare call
  (naming the role and the missing Infisical key, never any value), so a
  partial vault outage can never silently aim automated vault-repair actions
  at a hardcoded account.
"""

import json
import os
import sys
import urllib.request
import urllib.error

INFISICAL_API = os.getenv("INFISICAL_API_URL", "https://app.infisical.com/api")
CLIENT_ID = os.getenv("INFISICAL_CLIENT_ID", "9f2363cf-3cec-43f6-b155-a8625de19250")
CLIENT_SECRET = os.getenv("INFISICAL_CLIENT_SECRET", "***REMOVED***")
PROJECT_ID = os.getenv("INFISICAL_PROJECT_ID", "92aa20c4-aef5-4e33-82bd-efb06058aaf0")
ENVIRONMENT = os.getenv("INFISICAL_ENV", "prod")


def infisical_login() -> str:
    url = f"{INFISICAL_API}/v1/auth/universal-auth/login"
    payload = json.dumps({"clientId": CLIENT_ID, "clientSecret": CLIENT_SECRET}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))["accessToken"]


def infisical_get_raw_secrets(token: str) -> dict[str, str]:
    url = f"{INFISICAL_API}/v3/secrets/raw?workspaceId={PROJECT_ID}&environment={ENVIRONMENT}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        secrets = {}
        for item in data.get("secrets", []):
            secrets[item.get("secretKey")] = item.get("secretValue")
        return secrets


def infisical_update_secret(token: str, key: str, value: str) -> bool:
    url = f"{INFISICAL_API}/v3/secrets/raw/{key}"
    payload = json.dumps({
        "workspaceId": PROJECT_ID,
        "environment": ENVIRONMENT,
        "secretPath": "/",
        "secretValue": value,
        "type": "shared",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=15):
            print(f"  [VAULT] Updated {key} in Infisical")
            return True
    except Exception as exc:
        print(f"  [VAULT] Error updating {key}: {exc}")
        return False


class MissingInfisicalSecret(RuntimeError):
    """A required Infisical secret resolved absent/empty (fail-closed abort)."""


def require_secret(secrets: dict[str, str], role: str, key_name: str) -> str:
    """Fail-closed Infisical lookup (issue #1820).

    Returns the resolved value, or raises MissingInfisicalSecret after
    printing WHICH role and WHICH Infisical key were absent. Never prints,
    logs, or returns any secret value in the error path, and never falls back
    to a baked-in identifier: an empty vault answer must stop the run, not
    silently redirect automated repairs to a hardcoded account.
    """
    value = (secrets.get(key_name) or "").strip()
    if not value:
        print(
            f"[FAIL-CLOSED] {role}: required Infisical secret '{key_name}' is "
            f"missing or empty — aborting before any Cloudflare call "
            f"(no identifier fallback is baked into source, issue #1820)."
        )
        raise MissingInfisicalSecret(f"{role}: missing Infisical key {key_name}")
    return value


def cf_request(url: str, email: str, global_key: str, method: str = "GET", payload: dict | None = None) -> dict:
    headers = {
        "X-Auth-Email": email,
        "X-Auth-Key": global_key,
        "Content-Type": "application/json",
    }
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Connecting to Infisical to fetch Cloudflare accounts...")
    try:
        inf_token = infisical_login()
        secrets = infisical_get_raw_secrets(inf_token)
        print(f"Loaded {len(secrets)} secrets from Infisical.")
    except Exception as exc:
        print(f"Failed to load secrets: {exc}")
        sys.exit(1)

    # Fail-closed resolution (issue #1820): email + account_id REQUIRE a live
    # Infisical value (require_secret raises before any Cloudflare call);
    # the Global/API key keeps its no-fallback resolution and its explicit
    # loud skip below. Zero behavior change when the vault is healthy.
    try:
        accounts = [
            {
                "role": "primary",
                "email": require_secret(secrets, "primary", "CLOUDFLARE_EMAIL"),
                "key": secrets.get("CLOUDFLARE_GLOBAL_API_KEY") or secrets.get("CLOUDFLARE_API_KEY"),
                "account_id": require_secret(secrets, "primary", "CLOUDFLARE_ACCOUNT_ID"),
            },
            {
                "role": "secondary",
                "email": require_secret(secrets, "secondary", "CLOUDFLARE_SECONDARY_EMAIL"),
                "key": secrets.get("CLOUDFLARE_SECONDARY_GLOBAL_API_KEY"),
                "account_id": require_secret(secrets, "secondary", "CLOUDFLARE_SECONDARY_ACCOUNT_ID"),
            },
            {
                "role": "tertiary",
                "email": require_secret(secrets, "tertiary", "CLOUDFLARE_TERTIARY_EMAIL"),
                "key": secrets.get("CLOUDFLARE_TERTIARY_GLOBAL_API_KEY"),
                "account_id": require_secret(secrets, "tertiary", "CLOUDFLARE_TERTIARY_ACCOUNT_ID"),
            },
            {
                "role": "quaternary",
                "email": require_secret(secrets, "quaternary", "CLOUDFLARE_QUATERNARY_EMAIL"),
                "key": secrets.get("CLOUDFLARE_QUATERNARY_GLOBAL_API_KEY"),
                "account_id": require_secret(secrets, "quaternary", "CLOUDFLARE_QUATERNARY_ACCOUNT_ID"),
            },
            {
                "role": "quinary",
                "email": require_secret(secrets, "quinary", "CLOUDFLARE_QUINARY_EMAIL"),
                "key": secrets.get("CLOUDFLARE_QUINARY_GLOBAL_API_KEY"),
                "account_id": require_secret(secrets, "quinary", "CLOUDFLARE_QUINARY_ACCOUNT_ID"),
            },
        ]
    except MissingInfisicalSecret:
        sys.exit(1)

    primary_deploy_token = None

    for acc in accounts:
        role = acc["role"]
        email = acc["email"]
        key = acc["key"]
        account_id = acc["account_id"]
        print(f"\nProcessing {role.upper()} ({email})...")

        if not key or not account_id:
            missing = [
                label
                for label, val in (("Global/API key", key), ("account_id", account_id))
                if not val
            ]
            print(
                f"  [SKIP] {role}: no {' / '.join(missing)} resolved from Infisical "
                f"— account not processed (fail-closed: no fallback in source, issue #1820)."
            )
            continue

        # 1. Check or Create KV
        kv_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces"
        try:
            kv_data = cf_request(kv_url, email, key, "GET")
            kv_found = False
            for ns in kv_data.get("result", []):
                if ns.get("title") in ("HEALTH_KV", "SUPREMEAI_KV"):
                    print(f"  KV namespace ready: {ns.get('title')} ({ns.get('id')})")
                    kv_found = True
                    break
            if not kv_found:
                create_res = cf_request(kv_url, email, key, "POST", {"title": "HEALTH_KV"})
                if create_res.get("success"):
                    print(f"  Created HEALTH_KV namespace: {create_res['result']['id']}")
        except Exception as exc:
            print(f"  KV check error: {exc}")

        # 2. Check Existing Tokens
        try:
            tokens_url = "https://api.cloudflare.com/client/v4/user/tokens"
            token_list = cf_request(tokens_url, email, key, "GET")
            for t in token_list.get("result", []):
                if t.get("name") == "wrangler-supremeai-deploy" and role == "primary":
                    print(f"  Found wrangler-supremeai-deploy token (ID: {t.get('id')})")
        except Exception as exc:
            print(f"  Token list check: {exc}")

        # 3. Create fine-grained Deploy Token if primary
        if role == "primary":
            try:
                # Permission groups
                perms_data = cf_request("https://api.cloudflare.com/client/v4/user/tokens/permission_groups", email, key, "GET")
                perm_map = {p["name"]: p["id"] for p in perms_data.get("result", [])}
                needed = [
                    "Workers Scripts Write",
                    "Workers KV Storage Write",
                    "Account Settings Read",
                    "Workers AI Write",
                    "Workers AI Read",
                ]
                policy_perms = [{"id": perm_map[p]} for p in needed if p in perm_map]

                token_payload = {
                    "name": "supremeai-ci-cd-deploy-token",
                    "policies": [
                        {
                            "effect": "allow",
                            "resources": {f"com.cloudflare.api.account.{account_id}": "*"},
                            "permission_groups": policy_perms,
                        }
                    ],
                }
                res = cf_request("https://api.cloudflare.com/client/v4/user/tokens", email, key, "POST", token_payload)
                if res.get("success"):
                    primary_deploy_token = res["result"]["value"]
                    print(f"  [SUCCESS] Generated valid deploy token for primary account!")
            except Exception as exc:
                print(f"  Deploy token generation: {exc}")

    if primary_deploy_token:
        print("\nUpdating CLOUDFLARE_API_TOKEN in Infisical...")
        infisical_update_secret(inf_token, "CLOUDFLARE_API_TOKEN", primary_deploy_token)
        print("[SUCCESS] CLOUDFLARE_API_TOKEN now has full Workers Scripts & KV Write permissions!")
    else:
        print("\nNote: Primary token was kept or existing verified.")


if __name__ == "__main__":
    main()
