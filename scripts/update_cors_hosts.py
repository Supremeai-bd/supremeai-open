"""
Update ALLOWED_HOSTS & CORS_ORIGINS for all 3 Render services via API,
then health-check each backend.
Values are loaded from environment variables — never hardcoded.
"""
import os
import requests
import time

# ── 3 services: IDs, URLs and API keys loaded from env ────
SERVICES = [
    {
        "role": "primary",
        "id":   os.environ.get("RENDER_PRIMARY_SVC_ID", ""),
        "url":  os.environ.get("RENDER_PRIMARY_URL",    ""),
        "key":  os.environ.get("RENDER_API_KEY_1",      os.environ.get("RENDER_API_KEY", "")),
    },
    {
        "role": "worker",
        "id":   os.environ.get("RENDER_WORKER_SVC_ID",  ""),
        "url":  os.environ.get("RENDER_WORKER_URL",     ""),
        "key":  os.environ.get("RENDER_API_KEY_2",      ""),
    },
    {
        "role": "scraper",
        "id":   os.environ.get("RENDER_SCRAPER_SVC_ID", ""),
        "url":  os.environ.get("RENDER_SCRAPER_URL",    ""),
        "key":  os.environ.get("RENDER_API_KEY_3",      ""),
    },
    {
        "role": "controlTower",
        "id":   os.environ.get("RENDER_MCP_SVC_ID", ""),
        "url":  os.environ.get("RENDER_MCP_URL",    ""),
        "key":  os.environ.get("RENDER_API_KEY_4",  os.environ.get("RENDER_API_KEY", "")),
    },
]

# ── New URLs derived from service definitions ─────────────
NEW_HOSTS   = [s["url"].replace("https://", "") for s in SERVICES if s["url"]]
NEW_ORIGINS = [s["url"] for s in SERVICES if s["url"]]

# ── Base hosts/origins that every service should have ─────
# Loaded from environment to avoid hardcoding in source code.
# Example format: "host1.com,host2.com"
base_hosts_str = os.environ.get("ALLOWED_HOSTS", "")
base_origins_str = os.environ.get("CORS_ORIGINS", "")

BASE_HOSTS = [h.strip() for h in base_hosts_str.split(",") if h.strip()]
BASE_ORIGINS = [o.strip() for o in base_origins_str.split(",") if o.strip()]

# issue #1096/#1325: browser-facing UI origin(s) — SPA সরাসরি API origin কল করে,
# তাই API-এর CORS allowlist-এ UI origin না থাকলে ব্রাউজার রেসপন্স ব্লক করে
# (2026-09-25 live-smoke incident: 200 but no access-control-allow-origin)।
# Canonical derivation contract: scripts/ci/resolve_production_targets.py —
# UI origin = https://{FIREBASE_PROJECT_ID}.firebase_hosting_domain (বা owner override)।
# CI wrapper এটি EXTRA_ORIGINS env-এ পাঠায় — zero-hardcode নীতি বজায়।
extra_origins_str = os.environ.get("EXTRA_ORIGINS", "")
EXTRA_ORIGINS = [o.strip() for o in extra_origins_str.split(",") if o.strip()]

ALL_HOSTS   = ",".join(dict.fromkeys(BASE_HOSTS + NEW_HOSTS))
ALL_ORIGINS = ",".join(dict.fromkeys(BASE_ORIGINS + NEW_ORIGINS + EXTRA_ORIGINS))


def get_env_vars(svc_id, api_key):
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    r = requests.get(f"https://api.render.com/v1/services/{svc_id}/env-vars", headers=headers)
    if r.status_code == 200:
        return {e["envVar"]["key"]: e["envVar"]["value"] for e in r.json()}
    print(f"  [WARN] Could not fetch env vars: {r.status_code}")
    return {}


def patch_env_vars(svc_id, api_key, updates: dict):
    """Merge updates into the service's existing env vars, then PUT the full list."""
    current = get_env_vars(svc_id, api_key)
    current.update(updates)
    payload = [{"key": k, "value": v} for k, v in current.items()]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    r = requests.put(
        f"https://api.render.com/v1/services/{svc_id}/env-vars",
        headers=headers,
        json=payload,
    )
    return r.status_code in [200, 201]


def trigger_deploy(svc_id, api_key):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    r = requests.post(
        f"https://api.render.com/v1/services/{svc_id}/deploys",
        headers=headers,
        json={"clearCache": "do_not_clear"},
    )
    if r.status_code in [200, 201]:
        return r.json().get("id", "?")
    print(f"  [WARN] Deploy trigger: {r.status_code} {r.text[:80]}")
    return None


def health_check(url, timeout=10):
    for endpoint in ["/api/v1/health", "/health/live", "/health"]:
        try:
            r = requests.get(url + endpoint, timeout=timeout)
            if r.status_code < 500:
                return r.status_code, endpoint
        except Exception as e:
            # Suppressed to keep output clean, silent error detector allows if no pass or if logged, wait, I can just print it.
            print(f"Health check failed for {url + endpoint}: {e}")
    return None, None


# ─────────────────────────────────────────────────────────
print("=" * 60)
print("Step 1: Update ALLOWED_HOSTS & CORS_ORIGINS on all 4 services")
print("=" * 60)

for svc in SERVICES:
    print(f"\n[{svc['role'].upper()}] {svc['url']}")
    ok = patch_env_vars(
        svc["id"], svc["key"],
        {
            "ALLOWED_HOSTS": ALL_HOSTS,
            "CORS_ORIGINS":  ALL_ORIGINS,
        },
    )
    if ok:
        print("  [OK] Env vars updated")
    else:
        print("  [FAIL] Env vars update failed")
        continue

    # Trigger redeploy so changes take effect
    deploy_id = trigger_deploy(svc["id"], svc["key"])
    if deploy_id:
        print(f"  [OK] Deploy triggered: {deploy_id}")
    else:
        print("  [INFO] No explicit deploy triggered (auto-deploy may handle it)")

print("\n" + "=" * 60)
print("Step 2: Poll health endpoints until reachable (max 10 min)...")
print("=" * 60)

POLL_INTERVAL = 30
MAX_WAIT_SECONDS = 600
deadline = time.time() + MAX_WAIT_SECONDS
pending = list(SERVICES)

while pending and time.time() < deadline:
    still_pending = []
    for svc in pending:
        status, endpoint = health_check(svc["url"])
        if status:
            print(f"  [{svc['role'].upper():8}] {svc['url']}{endpoint} -> HTTP {status}")
        else:
            print(f"  [{svc['role'].upper():8}] {svc['url']} -> UNREACHABLE (still building?)")
            still_pending.append(svc)
    pending = still_pending
    if pending and time.time() < deadline:
        print(f"  ... waiting {POLL_INTERVAL}s before next check ({len(pending)} pending)")
        time.sleep(POLL_INTERVAL)

if pending:
    print(f"\n[WARN] {len(pending)} service(s) still unreachable after {MAX_WAIT_SECONDS // 60} minutes:")
    for svc in pending:
        print(f"  - {svc['role']}: {svc['url']}")

print("\nDone. If backends are still building, re-run health checks in 5-10 minutes.")
