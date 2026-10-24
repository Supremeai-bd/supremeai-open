import json
import os
import urllib.request

client_id = os.getenv("INFISICAL_CLIENT_ID", "")
client_secret = os.getenv("INFISICAL_CLIENT_SECRET", "")
workspace_id = os.getenv("INFISICAL_PROJECT_ID", "")

def get_token():
    req = urllib.request.Request(
        "https://app.infisical.com/api/v1/auth/universal-auth/login",
        data=json.dumps({"clientId": client_id, "clientSecret": client_secret}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["accessToken"]

def upsert_secret(token, key, value):
    update_data = {
        "workspaceId": workspace_id,
        "environment": "prod",
        "secretPath": "/",
        "secretValue": value,
        "type": "shared"
    }

    # Try updating first
    req = urllib.request.Request(
        f"https://app.infisical.com/api/v3/secrets/raw/{key}",
        data=json.dumps(update_data).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH"
    )
    try:
        with urllib.request.urlopen(req):
            print(f"Updated {key}")
            return
    except Exception as e:
        if "404" in str(e) or "not found" in str(e).lower():
            # Create if not exists
            create_data = {
                "workspaceId": workspace_id,
                "environment": "prod",
                "secretPath": "/",
                "secretName": key,
                "secretValue": value,
                "type": "shared"
            }
            req = urllib.request.Request(
                f"https://app.infisical.com/api/v3/secrets/raw/{key}",
                data=json.dumps(create_data).encode(),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                method="POST"
            )
            try:
                with urllib.request.urlopen(req):
                    print(f"Created {key}")
            except Exception as e2:
                print(f"Failed to create {key}: {e2}")
        else:
            print(f"Failed to update {key}: {e}")

if __name__ == "__main__":
    if not workspace_id:
        raise RuntimeError("INFISICAL_PROJECT_ID environment variable is required.")
    token = get_token()

    # Read secrets from environment
    secrets_to_add = {}
    if os.getenv("ADMIN_EMAIL"):
        secrets_to_add["ADMIN_EMAIL"] = os.getenv("ADMIN_EMAIL")
    if os.getenv("OPENAI_API_KEY"):
        secrets_to_add["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

    for k, v in secrets_to_add.items():
        upsert_secret(token, k, v)

    print("Done adding secrets to Infisical!")
