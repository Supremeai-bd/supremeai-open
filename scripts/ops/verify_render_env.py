#!/usr/bin/env python3
# scripts/verify_render_env.py
"""
বাংলা: Render API থেকে প্রকৃত service env vars fetch করে secrets_registry.yaml-এর
বিপরীতে চেক করে। এটি Gap #3 বন্ধ করে: CI GitHub secrets-এ set থাকলেও যদি Render
service-এর env-এ না থাকে, তবে এখানে ধরা পড়বে (production 503/crash এড়াতে)।

REWRITE NOTE (drift-fix & registry alignment): সরাসরি `secrets_registry.yaml` থেকে
target env (render-backend, render-admin, render-worker) অনুযায়ী tracked key এবং
criticality level (critical/important/optional) রিড করে — single source of truth।

নিরাপত্তা: কোনো secret ভ্যালু log-এ যায় না — শুধু key name।
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Optional, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from render_client import RenderApiError, RenderClient  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

try:
    import yaml
except ImportError:
    print("::error::PyYAML ইনস্টল করা নাই — `pip install pyyaml` চালান।")
    sys.exit(1)

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "..", "secrets_registry.yaml")
PROD_REPO_SLUG = os.environ.get("PROD_REPO_SLUG", "SaifulHaqueNiloy/supremeai")


def load_registry_keys(path: str, target_env: str) -> dict[str, str]:
    """
    বাংলা: secrets_registry.yaml থেকে {key_name: criticality} ম্যাপ বের করে,
    নির্দিষ্ট target_env (যেমন render-backend, render-admin, render-worker) এর জন্য।
    """
    if not os.path.exists(path):
        print(f"::error::Registry ফাইল পাওয়া যায়নি: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    result: dict[str, str] = {}
    for entry in data.get("keys", []):
        name = entry.get("name")
        crit_map = entry.get("criticality", {})
        if isinstance(crit_map, str):
            continue  # legacy flat-string entries স্কিপ
        if name and target_env in crit_map:
            result[name] = crit_map[target_env]
    return result


def fetch_render_env(service_id: str, candidate_keys: list[str], target_env: str) -> Optional[Dict[str, Optional[str]]]:
    """
    বাংলা: একাধিক candidate API key ট্রাই করে Render API থেকে service env var-এর key গুলোর dict ফেরত দেয়।
    Admin/Worker/Backup সার্ভিসের ক্ষেত্রে API 401/403/404 দিলে নন-ব্লকিং ওয়ার্নিং দিয়ে None ফেরত দেয়।
    """
    last_error = ""
    current_repo = os.environ.get("GITHUB_REPOSITORY", "")
    is_prod_repo = current_repo == PROD_REPO_SLUG

    for idx, api_key in enumerate(candidate_keys):
        if not api_key:
            continue
        try:
            payload = RenderClient(api_key=api_key).get_env_vars(service_id)
            env_data: dict[str, Optional[str]] = {}
            items = payload if isinstance(payload, list) else payload.get("envVars", [])
            for item in items:
                ev = item.get("envVar", item)
                key = ev.get("key")
                val = ev.get("value")  # manual sync secrets-এ None আসে
                if key:
                    env_data[key] = val
            return env_data
        except RenderApiError as e:
            last_error = f"HTTP {e.status} {(e.body or '')[:200]}"
            print(f"[info] Render API key candidate #{idx+1} for {service_id} returned {last_error}")
        except Exception as e:  # network/timeout
            last_error = f"Network error: {e}"
            print(f"[info] Render API key candidate #{idx+1} unreachable: {e}")

    # All candidate keys failed
    diag = f"Render API call failed for {service_id}: {last_error}"
    if target_env != "render-backend":
        # Secondary / Admin / Worker env check is non-blocking (warning-only)
        print(f"::warning::[{target_env}] {diag} — Secondary service credentials missing or permission restricted in Render. Skipping runtime env audit.")
        return None

    # For render-backend (primary production)
    if is_prod_repo:
        print(f"::error::{diag}")
        sys.exit(1)
    else:
        print(f"::warning::(Non-prod repo) {diag} — Skipping primary runtime env audit.")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Render runtime env vs registry")
    parser.add_argument("--env", required=True, choices=["render-backend", "render-admin", "render-worker"])
    parser.add_argument("--service-id", required=True, help="Render service ID")
    args = parser.parse_args()

    primary_key = os.environ.get("RENDER_API_KEY", "")
    backup_key = os.environ.get("RENDER_API_KEY_BACKUP", "")

    # Build candidate keys ordered by relevance
    candidate_keys: list[str] = []
    if args.env == "render-admin":
        if backup_key:
            candidate_keys.append(backup_key)
        if primary_key and primary_key not in candidate_keys:
            candidate_keys.append(primary_key)
    else:
        if primary_key:
            candidate_keys.append(primary_key)
        if backup_key and backup_key not in candidate_keys:
            candidate_keys.append(backup_key)

    if not candidate_keys:
        if args.env != "render-backend":
            print(f"::warning::[{args.env}] RENDER_API_KEY / RENDER_API_KEY_BACKUP env চার্জ করা হয়নি — skipping secondary check.")
            return 0
        print("::error::RENDER_API_KEY / RENDER_API_KEY_BACKUP env চার্জ করা হয়নি (GitHub secret থেকে ইনজেক্ট করুন)।")
        sys.exit(1)

    # secrets_registry.yaml থেকে এই target env-এর জন্য tracked keys ও criticality লোড করো
    registry_keys = load_registry_keys(REGISTRY_PATH, args.env)

    if not registry_keys:
        print(f"[info] কোনো tracked keys পাওয়া যায়নি {args.env}-এর জন্য secrets_registry.yaml ফাইলে।")
        return 0

    # Render API থেকে service-এর actual env var keys fetch করো
    present_keys = fetch_render_env(args.service_id, candidate_keys, args.env)
    if present_keys is None:
        # Non-blocking skip (e.g. secondary service 403 or non-prod repo)
        return 0

    print(f"=== Render Runtime Env Health Check [{args.env}] ===")
    print(f"[info] Render [{args.env}] service-এ পাওয়া env var সংখ্যা: {len(present_keys)}")
    print(f"[info] secrets_registry.yaml-এ [{args.env}]-এর জন্য tracked key সংখ্যা: {len(registry_keys)}")

    has_critical_failure = False
    warnings = 0

    for name in sorted(registry_keys):
        crit = registry_keys[name]
        if name in present_keys:
            continue
        if crit == "critical":
            if args.env == "render-backend":
                print(f"::error::CRITICAL key missing in Render [{args.env}]: {name} — সার্ভার boot crash হবে!")
                has_critical_failure = True
            else:
                print(f"::warning::[Non-blocking] CRITICAL key missing in Render [{args.env}]: {name} — Second backend needs secret sync.")
                warnings += 1
        elif crit == "important":
            print(f"::warning::IMPORTANT key missing in Render [{args.env}]: {name} — ফিচারের পারফরম্যান্স হ্রাস পাবে।")
            warnings += 1
        else:
            print(f"[optional] key missing in Render [{args.env}]: {name} (optional feature disabled)")
            warnings += 1

    if has_critical_failure:
        print(f"\n❌ FAIL [{args.env}]: এক বা একাধিক critical key missing! Render deploy crash করবে।")
        return 1

    if warnings:
        print(f"\n⚠️ PASS [{args.env}] with {warnings} warning(s): critical সব ঠিক আছে, কিছু important/optional key missing।")
    else:
        print(f"\n✅ PASS [{args.env}]: সব tracked key Render-এ উপস্থিত।")

    return 0


if __name__ == "__main__":
    sys.exit(main())
