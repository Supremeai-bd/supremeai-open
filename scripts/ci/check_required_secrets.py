#!/usr/bin/env python3
"""
check_required_secrets.py
Validates the presence of required environment variables/secrets in CI.
Fails the job if critical keys are missing.
Prints warnings for missing non-critical keys.
"""

import os
import sys

def check_secrets():
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    # Define phase based on argument
    phase = sys.argv[1] if len(sys.argv) > 1 else "pre_check"

    if phase == "pre_check":
        critical_keys = [
            "INFISICAL_CLIENT_ID",
            "INFISICAL_CLIENT_SECRET",
            "INFISICAL_PROJECT_ID",
            "RENDER_API_KEY",
            "CLOUDFLARE_API_TOKEN",
            "CLOUDFLARE_ACCOUNT_ID",
            "FIREBASE_PROJECT_ID",
            "GCP_SA_KEY"
        ]
        warning_keys = [
            "RENDER_PRIMARY_SVC_ID"
        ]
    elif phase == "post_check_backend":
        critical_keys = [
            "RENDER_API_KEY"
        ]
        warning_keys = [
            "RENDER_PRIMARY_SVC_ID",
            "RENDER_WORKER_SVC_ID",
            "RENDER_SCRAPER_SVC_ID"
        ]
    elif phase == "post_check_cloudflare":
        critical_keys = [
            "CLOUDFLARE_API_TOKEN",
            "CLOUDFLARE_ACCOUNT_ID"
        ]
        warning_keys = []
    else:
        print(f"Unknown phase: {phase}")
        sys.exit(1)

    has_critical_failure = False

    print(f"\n🔍 Running secret validation for phase: {phase}...")
    
    # Check critical keys
    for key in critical_keys:
        val = os.environ.get(key, "").strip()
        if not val:
            print(f"🚨 CRITICAL MISSING: {key} is required but missing or empty!")
            has_critical_failure = True
        else:
            print(f"✅ Found: {key}")

    # Check warning keys
    for key in warning_keys:
        val = os.environ.get(key, "").strip()
        if not val:
            print(f"⚠️ WARNING MISSING: {key} is missing. Some non-critical features may fail.")
        else:
            print(f"✅ Found: {key}")

    if has_critical_failure:
        print("\n❌ Job failed due to missing CRITICAL secrets.")
        sys.exit(1)
    else:
        print(f"\n✅ All critical secrets for {phase} are present.")
        sys.exit(0)

if __name__ == "__main__":
    check_secrets()
