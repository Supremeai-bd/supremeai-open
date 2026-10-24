# .github/scripts/verify-render-deploy.py
# বাংলা মন্তব্য: এই স্ক্রিপ্টটি নির্দিষ্ট Render সার্ভিসের (User/Primary বা Admin/Backup) ডেপ্লয়মেন্ট স্ট্যাটাস ও হেলথ ভেরিফাই করে।
# এটি সার্ভিস আইডি অনুযায়ী ফিল্টার করে ট্র্যাকিং নিশ্চিত করে যাতে একটি সার্ভিসের সুস্থতা অন্য ব্যর্থ সার্ভিসকে ঢেকে না ফেলে।

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    from dotenv import load_dotenv
    load_dotenv('.env')
except Exception:
    print('Silenced error in except block')

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Fallback Services Dictionary
SERVICES = {
    "srv-da07ogmgekts739amqa0": {
        "name": "Backend",
        "service_id": "srv-da07ogmgekts739amqa0",
        "url": "https://supremeai-backend-docker.onrender.com"
    }
}

# Timing: poll every 10s; timeout env-overridable (default 360s = 6 min).
# বাংলা মন্তব্য: Render free-tier-এ ভারী backend build+deploy সহজেই ২-৬ মিনিট (বা তার বেশি) নেয়।
# default ১২ মিনিট (৭২০s);
POLL_INTERVAL = 10  # poll every 10s for faster feedback
# RENDER_VERIFY_TIMEOUT env দিয়ে CI ইচ্ছে করলে বাড়ায়/কমায়; `fail/cancel/error` status এখনও instant fail।
TIMEOUT_LIMIT = int(os.environ.get("RENDER_VERIFY_TIMEOUT", "720"))  # seconds; 12 min default

class _UrllibResponse:
    def __init__(self, resp):
        self._resp = resp
        self.status_code = resp.status
        self.ok = 200 <= resp.status < 300
        self.text = resp.read().decode("utf-8")

    def json(self):
        return json.loads(self.text)


def _http_get(url, headers=None, timeout=10):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    resp = urllib.request.urlopen(req, timeout=timeout)
    return _UrllibResponse(resp)


def check_http_health(url, label, retries=3, timeout_per_try=10):
    # বাংলা মন্তব্য: দ্রুততম ভেরিফিকেশনের জন্য রিট্রাই ৩টি এবং টাইমআউট ১০ সেকেন্ডে রাখা হয়েছে যাতে অহেতুক সময় নষ্ট না হয়।
    base_url = url.rstrip('/')
    endpoints = [f"{base_url}/health", f"{base_url}/api/v1/health"]
    for attempt in range(1, retries + 1):
        for health_url in endpoints:
            print(f"⏳ Verifying {label} HTTP health at {health_url} (Attempt {attempt}/{retries})...")
            try:
                response = _http_get(health_url, timeout=timeout_per_try)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if isinstance(data, dict) and data.get('status') in ['ok', 'healthy', 'UP', 'degraded']:
                            print(f"✅ {label} HTTP check passed! Status: 200 OK ({health_url})")
                            return True
                        else:
                            print(f"⚠️ {label} HTTP check returned unverified body: {data}")
                    except Exception as json_err:
                        print(f"⚠️ {label} HTTP check response is not valid JSON: {json_err}")
                else:
                    print(f"⚠️ {label} HTTP check returned HTTP {response.status_code}")
            except Exception as e:
                print(f"⏳ {health_url} health check attempt {attempt} failed: {e}")
        if attempt < retries:
            time.sleep(5)
    print(f"❌ {label} HTTP check failed after {retries} retries.")
    return False

def monitor_service(service, skip_health=False):
    name = service["name"]
    service_id = service["service_id"]

    def do_health(url, n=name, retries=3, timeout_per_try=10):
        if skip_health:
            print(f"ℹ️ Skipping HTTP health check for {n} (--skip-health). Verifying deploy status only.")
            return True
        return check_http_health(url, n, retries=retries, timeout_per_try=timeout_per_try)

    primary_key = os.getenv("RENDER_API_KEY")
    candidate_keys = [k for k in [primary_key] if k]

    if not candidate_keys:
        print(f"ℹ️ No API keys configured in environment. Checking HTTP health directly for {name}.")
        return do_health(service["url"])

    headers = None
    for key in candidate_keys:
        test_headers = {
            "Authorization": f"Bearer {key}",
            "Accept": "application/json"
        }
        deploys_url = f"https://api.render.com/v1/services/{service_id}/deploys"
        try:
            res = _http_get(deploys_url, headers=test_headers, timeout=10)
            if res.status_code == 200:
                headers = test_headers
                print(f"✅ Authenticated API key found for {name} (service {service_id}).")
                break
            elif res.status_code == 404:
                print(f"⚠️ Service {service_id} returned 404 for this API key. Key does not own this service.")
            elif res.status_code in (401, 403):
                print(f"⚠️ API key unauthorized (HTTP {res.status_code}) for service {service_id}.")
        except Exception as e:
            print(f"⚠️ API connectivity error for {name}: {e}")

    if not headers:
        print(f"⚠️ No valid API key found for service {service_id} ({name}). Falling back to HTTP health check.")
        return do_health(service["url"])

    print(f"\n🔍 Tracking latest deploy for {name} (Service ID: {service_id})...")

    deploy_id = None
    status_str = ""
    fetch_start = time.time()

    # Poll for a NEW deploy to appear in the API (up to 30 seconds)
    while True:
        deploys_url = f"https://api.render.com/v1/services/{service_id}/deploys"
        try:
            res = _http_get(deploys_url, headers=headers, timeout=10)
            if res.status_code == 200:
                deploys = res.json()
                if deploys:
                    latest = deploys[0].get("deploy", deploys[0]) if isinstance(deploys[0], dict) else deploys[0]
                    created_at_str = latest.get("createdAt", "")
                    if created_at_str:
                        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                        now = datetime.now(timezone.utc)
                        # If the deploy is newer than 10 minutes, we consider it our new deploy
                        if (now - created_at) < timedelta(minutes=10):
                            deploy_id = latest.get("id")
                            status_str = (latest.get("status") or "").lower()
                            print(f"📋 Found recent Deploy: ID={deploy_id}, Status={status_str}, CreatedAt={created_at_str}")
                            break

            if time.time() - fetch_start > 30:
                print("⚠️ Could not find a recent deploy (within last 10 mins) after 30s. Falling back to HTTP health check.")
                return do_health(service["url"], retries=24)

        except Exception as e:
            print(f"❌ Error fetching deploys: {e}")
            return check_http_health(service["url"], name, retries=24)

        time.sleep(5)

    if status_str == "live":
        print(f"🎉 Deploy {deploy_id} for {name} is already LIVE on Render!")
        return do_health(service["url"], retries=24)
    elif any(f_word in status_str for f_word in ["fail", "cancel", "error"]):
        print(f"❌ Deploy {deploy_id} for {name} failed ({status_str}). Failing immediately.")
        return False

    start_time = time.time()
    deploy_url = f"https://api.render.com/v1/services/{service_id}/deploys/{deploy_id}"

    print(f"⏳ Polling status of deploy {deploy_id} for {name}...")

    while True:
        elapsed = time.time() - start_time
        if elapsed > TIMEOUT_LIMIT:
            # বাংলা মন্তব্য: ২ মিনিটের বেশি সময় ধরে ঝুলে থাকলে অহেতুক ওয়েট না করে অবিলম্বে HARD FAIL করানো হচ্ছে।
            print(f"❌ Timeout reached ({TIMEOUT_LIMIT}s) while waiting for deploy {deploy_id} (status: {status_str}).")
            print(f"❌ Deployment did not reach LIVE status within {TIMEOUT_LIMIT}s. Fast failing step.")
            return False

        try:
            res = _http_get(deploy_url, headers=headers, timeout=10)
            if res.status_code == 200:
                deploy_info = res.json()
                deploy_data = deploy_info.get("deploy", deploy_info) if isinstance(deploy_info, dict) else deploy_info
                status = str(deploy_data.get("status", "")).lower()
                status_str = status
                print(f"  Deploy {deploy_id} status: {status} (elapsed: {int(elapsed)}s)")

                if status == "live":
                    print(f"🎉 Deploy {deploy_id} is now LIVE on Render!")
                    # বাংলা মন্তব্য: deploy LIVE হলেই app-কে boot হতে সময় লাগে — তাই fresh-live-ও ১০টি HTTP retry পায়।
                    return do_health(service["url"], retries=10)
                elif any(f_word in status for f_word in ["fail", "cancel", "error"]):
                    # বাংলা মন্তব্য: ডিপ্লয় ফেইল হলে সময় নষ্ট না করে সাথে সাথে HARD FAIL রিটার্ন করা হচ্ছে।
                    print(f"⚠️ Deploy {deploy_id} reported status: {status}. HARD FAIL — new build failed to deploy.")
                    return False
            else:
                print(f"⚠️ Error fetching deploy details: HTTP {res.status_code}")
        except Exception as e:
            print(f"⚠️ Polling connection issue: {e}")

        time.sleep(POLL_INTERVAL)

def main():
    parser = argparse.ArgumentParser(description="Verify Render Deploy Status")
    parser.add_argument("--service-id", type=str, help="Specific Render Service ID to verify")
    parser.add_argument("--name", type=str, help="Custom Service Name label")
    parser.add_argument("--skip-health", action="store_true", help="Skip HTTP /health probe (use for static sites with no health endpoint)")
    args = parser.parse_args()

    if args.service_id:
        svc = SERVICES.get(args.service_id, {
            "name": args.name or f"Service ({args.service_id})",
            "service_id": args.service_id,
            "url": "https://supremeai-backend-docker.onrender.com"
        })
        targets = [svc]
    else:
        targets = list(SERVICES.values())

    results = {}
    for svc in targets:
        results[svc["name"]] = monitor_service(svc, skip_health=args.skip_health)

    print("\n================ DEPLOY SUMMARY ================")
    all_ok = True
    for name, ok in results.items():
        status_text = "✅ SUCCESS / HEALTHY" if ok else "❌ FAILED / UNHEALTHY"
        print(f"- {name}: {status_text}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\n🎉 Deployment verification PASSED! All targeted backend services are healthy and responding.")
        sys.exit(0)
    else:
        print("\n❌ Deployment verification FAILED! One or more target services failed deployment verification.")
        sys.exit(1)

if __name__ == "__main__":
    main()
