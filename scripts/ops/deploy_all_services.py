"""Provision/refresh the 4 Render services (primary/worker/scraper/mcp).

DRY Phase 2-C3: all Render API calls migrated onto
scripts/lib/render_client.py — the single-sourced client (drops the requests
dependency). Output text preserved (deploy_results.json schema unchanged).
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from render_client import RenderApiError, RenderClient  # noqa: E402

load_dotenv()

# ── Render API Keys (loaded from env — never hardcode) ──
RENDER_KEYS = {
    "primary": os.environ.get("RENDER_API_KEY_1", os.environ.get("RENDER_API_KEY", "")),
    "worker":  os.environ.get("RENDER_API_KEY_2", ""),
    "scraper": os.environ.get("RENDER_API_KEY_3", ""),
    "mcp":     os.environ.get("RENDER_API_KEY_4", os.environ.get("RENDER_API_KEY", "")), # fallback to main key
}

# --- Service Configurations ---
REPO_URL = "https://github.com/SaifulHaqueNiloy/supremeai"
BRANCH = "main"


def get_owner_id(client: RenderClient, api_key: str) -> str | None:
    try:
        owners = client.list_owners()
        if owners:
            return owners[0]["owner"]["id"]
    except RenderApiError as e:
        print(f"Failed to fetch owner for key {api_key[:10]}... : {e} {e.body}".rstrip())
        return None
    print(f"Failed to fetch owner for key {api_key[:10]}... : no owners returned")
    return None


def create_or_update_service(role: str, api_key: str) -> dict | None:
    print(f"\n[Processing {role.upper()} service...]")
    client = RenderClient(api_key=api_key)
    owner_id = get_owner_id(client, api_key)
    if not owner_id:
        return None

    env_vars = [
        {"key": "SUPREMEAI_JWT_SECRET", "value": os.environ.get("SUPREMEAI_JWT_SECRET", "")},
        {"key": "SECRET_KEY", "value": os.environ.get("SECRET_KEY", "")},
        {"key": "JWT_SECRET_KEY", "value": os.environ.get("JWT_SECRET_KEY", "")},
        {"key": "ENCRYPTION_KEY", "value": os.environ.get("ENCRYPTION_KEY", "")},
        {"key": "SUPABASE_URL", "value": os.environ.get("SUPABASE_URL", "")},
        {"key": "SUPABASE_KEY", "value": os.environ.get("SUPABASE_KEY", "")},
        {"key": "SUPABASE_DATABASE_URL", "value": os.environ.get("SUPABASE_DATABASE_URL", "")},
        {"key": "INSTANCE_ROLE", "value": role},
        {"key": "ENV", "value": "production"},
        {"key": "PORT", "value": "8080"}
    ]

    if role == "mcp":
        service_name = "supremeai-mcp-tower"
        root_dir = "infrastructure/mcp-control-plane"
    else:
        service_name = f"supremeai-{role}-node"
        root_dir = "backend"

    # Find existing service
    service_id = None
    service_url = None

    try:
        services = client.list_services(limit=100)
    except RenderApiError as e:
        print(f"[FAIL] Failed to list services: {e} {e.body}".rstrip())
        return None

    for s in services:
        if s["service"]["name"] == service_name:
            region = s["service"]["serviceDetails"].get("region", "")
            if region == "oregon":
                print(f"Found existing {service_name} in oregon. Deleting it...")
                try:
                    client.delete_service(s["service"]["id"])
                    print("Deleted successfully. Will recreate in singapore.")
                except RenderApiError as e:
                    print(f"Failed to delete: {e} {e.body}".rstrip())
            else:
                service_id = s["service"]["id"]
                service_url = s["service"]["serviceDetails"].get("url")
                print(f"Service {service_name} already exists in {region}. ID: {service_id}")
            break

    if not service_id:
        print(f"Creating new service {service_name} in singapore...")

        env_specific_details = {
            "dockerfilePath": "Dockerfile"
        }

        # Add celery command for worker
        if role == "worker":
            env_specific_details["dockerCommand"] = "celery -A workers.celery_app worker --loglevel=INFO -c 2"

        payload = {
            "type": "web_service",
            "name": service_name,
            "ownerId": owner_id,
            "repo": REPO_URL,
            "branch": BRANCH,
            "autoDeploy": "yes",
            "rootDir": root_dir,
            "serviceDetails": {
                "env": "docker",
                "envSpecificDetails": env_specific_details,
                "plan": "free",
                "region": "singapore",
                "envVars": env_vars
            }
        }
        try:
            data = client.create_service(payload)
        except RenderApiError as e:
            print(f"[FAIL] Failed to create: {e} {e.body}".rstrip())
            return None
        service_id = data.get("service", {}).get("id")
        if not service_id:
            print("[FAIL] Missing 'id' in response")
            return None
        service_url = data.get("service", {}).get("serviceDetails", {}).get("url")
        print(f"[OK] Created successfully: {service_id}")
    else:
        print(f"Updating env vars for {service_id}...")
        try:
            client.update_env_vars(service_id, env_vars)
            print("[OK] Env vars updated.")
        except RenderApiError as e:
            print(f"[FAIL] Failed to update env vars: {e} {e.body}".rstrip())

        # Update docker command for worker if updating existing service
        if role == "worker":
            print(f"Updating dockerCommand for {service_id}...")
            patch_payload = {
                "serviceDetails": {
                    "envSpecificDetails": {
                        "dockerCommand": "celery -A workers.celery_app worker --loglevel=INFO -c 2"
                    }
                }
            }
            try:
                client.update_service(service_id, patch_payload)
                print("[OK] Docker command updated.")
            except RenderApiError as e:
                print(f"[FAIL] Failed to update docker command: {e} {e.body}".rstrip())

        print(f"Triggering deploy for {service_id}...")
        try:
            client.trigger_deploy(service_id)
            print("[OK] Deploy triggered.")
        except RenderApiError as e:
            print(f"[FAIL] Failed to trigger deploy: {e} {e.body}".rstrip())

    return {"id": service_id, "url": service_url}


if __name__ == "__main__":
    results = {}
    for role, key in RENDER_KEYS.items():
        if key:
            res = create_or_update_service(role, key)
            if res:
                results[role] = res
        else:
            print(f"Skipping {role} because API key is missing.")

    print("\n\n=== DEPLOYMENT RESULTS ===")
    for role, res in results.items():
        print(f"{role.upper()}:")
        print(f"  URL: {res.get('url')}")
        print(f"  ID:  {res.get('id')}")

    with open("deploy_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved to deploy_results.json")
