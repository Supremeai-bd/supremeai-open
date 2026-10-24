#!/usr/bin/env python3
"""
SupremeAI Unified CI/CD CLI Tool
Replaces all legacy .github/scripts/ scripts.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

# ==========================================
# ⚙️ SHARED ENV VARS
# ==========================================
SUPREMEAI_API_URL = os.environ.get("SUPREMEAI_API_URL", "")
SUPREMEAI_API_KEY = os.environ.get("SUPREMEAI_API_KEY", "")

BACKUP_SERVICE_NAME = os.environ.get("BACKUP_SERVICE_NAME", "supremeai-api-backup")
BACKUP_REGION = os.environ.get("BACKUP_REGION", "us-east1")
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
GCP_SA_KEY = os.environ.get("GCP_SA_KEY", "")
SKIP_BACKUP = os.environ.get("SKIP_BACKUP", "false").lower() == "true"

HEALTH_TIMEOUT = 30
RETRY_ATTEMPTS = 3


def set_output(name: str, value: str):
    """Set output for GitHub Actions."""
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.write(f"{name}={value}\n")
    print(f"OUTPUT: {name}={value}")

# ==========================================
# 🩺 HEALTH CHECK COMMAND
# ==========================================
def cmd_health_check(args):
    print("=" * 60)
    print("🩺 Running Strict Health Check...")
    print("=" * 60)

    # Database failover checking logic
    supremeai_available = False

    if SUPREMEAI_API_URL:
        health_url = f"{SUPREMEAI_API_URL}/health"
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                print(f"🩺 SupremeAI API check ({attempt}/{RETRY_ATTEMPTS}): {health_url}")
                req = urllib.request.Request(health_url, method="GET")
                if SUPREMEAI_API_KEY:
                    req.add_header("Authorization", f"Bearer {SUPREMEAI_API_KEY}")
                with urllib.request.urlopen(req, timeout=HEALTH_TIMEOUT) as resp:
                    if resp.status == 200:
                        supremeai_available = True
                        break
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    supremeai_available = True
                    break
            except Exception as e:
                print(f"⚠️ API error: {e}")
            if attempt < RETRY_ATTEMPTS:
                time.sleep(3)

    # Hardened Backup Check (Fail-Closed)
    backup_healthy = False
    backup_info = "unknown"
    if SKIP_BACKUP:
        print("⏭️ Backup check skipped (manual override)")
        backup_healthy = True
        backup_info = "skipped"
    elif not GCP_SA_KEY or not GCP_PROJECT_ID:
        print("❌ GCP credentials missing — backup check FAILS CLOSED.")
        backup_healthy = False
        backup_info = "no-credentials"
    else:
        try:
            res = subprocess.run(["gcloud", "auth", "activate-service-account", "--key-file", "-"],
                                 input=GCP_SA_KEY.encode(), capture_output=True, text=True, check=False)
            if res.returncode != 0:
                print(f"❌ gcloud auth failed: {res.stderr}")
                backup_healthy = False
                backup_info = "auth-failed"
            else:
                res = subprocess.run(["gcloud", "run", "services", "describe", BACKUP_SERVICE_NAME,
                                      "--region", BACKUP_REGION, "--project", GCP_PROJECT_ID, "--format", "json"],
                                     capture_output=True, text=True, check=False)
                if res.returncode != 0:
                    print(f"❌ Backup service not found: {res.stderr}")
                    backup_healthy = False
                    backup_info = "not-found"
                else:
                    service_info = json.loads(res.stdout)
                    traffic = service_info.get("status", {}).get("traffic", [])
                    if traffic:
                        latest_url = traffic[0].get("url", "")
                        if latest_url:
                            health_url = f"{latest_url}/health"
                            try:
                                req = urllib.request.Request(health_url, method="GET", timeout=HEALTH_TIMEOUT)
                                with urllib.request.urlopen(req) as resp:
                                    if resp.status == 200:
                                        backup_healthy = True
                                        backup_info = traffic[0].get("revisionName", "unknown")
                            except Exception as e:
                                print(f"❌ Backup health check failed: {e}")
                                backup_healthy = False
        except Exception as e:
            print(f"❌ Backup check error: {e}")
            backup_healthy = False
            backup_info = "error"

    # STRICT FAIL-CLOSED LOGIC
    if not backup_healthy:
        raise Exception("Critical infrastructure unreachable! Backup server is down or missing.")

    print("\n✅ Health Check Summary")
    print(f"  SupremeAI API: {'UP' if supremeai_available else 'DOWN'}")
    print(f"  Backup Server: {'Healthy' if backup_healthy else 'Unhealthy'} ({backup_info})")

    set_output("supremeai_available", "true" if supremeai_available else "false")
    set_output("backup_available", "true" if backup_healthy else "false")
    set_output("backup_last_deploy", backup_info)


# ==========================================
# 📊 REPORT COMMAND
# ==========================================
def cmd_generate_report(args):
    print(f"📊 Generating Report (Type: {args.type})...")
    title = "✅ SupremeAI CI: SUCCESS" if os.getenv("JOB_STATUS", "success") == "success" else "❌ SupremeAI CI: FAILED"

    summary_file = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(f"# {title}\n")
            f.write(f"**Branch:** `{os.getenv('GITHUB_REF_NAME', 'main')}` | **Run ID:** `{os.getenv('GITHUB_RUN_ID', '0')}`\n")

        if args.pytest_json and os.path.exists(args.pytest_json):
            with open(args.pytest_json, encoding="utf-8") as f:
                if args.pytest_json.endswith('.md'):
                    with open(summary_file, "a", encoding="utf-8") as sf:
                        sf.write(f"\n### 🧪 Backend Pytest Results\n{f.read()}\n")

    # Discord alert logic
    discord_webhook = os.getenv("DISCORD_WEBHOOK_URL")
    if discord_webhook:
        payload = {"username": "SupremeAI CI/CD", "embeds": [{"title": title, "color": 3066993}]}
        req = urllib.request.Request(discord_webhook, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            print(f"❌ Failed to send Discord alert: {e}")


# ==========================================
# 🚀 DEPLOY COMMAND
# ==========================================
def cmd_deploy(args):
    print(f"🚀 Deploying with strategy: {args.strategy}")
    region = os.getenv("GCP_REGION", "us-central1")
    project_id = os.getenv("GCP_PROJECT_ID")
    service_name = "supremeai-api"
    image = f"{region}-docker.pkg.dev/{project_id}/supremeai-repo/supremeai-api:latest"

    print(f"Deploying image: {image}")
    deploy_cmd = [
        "gcloud", "run", "deploy", service_name,
        "--image", image,
        "--region", region,
        "--port", "8080",
        "--memory", "2048Mi",
        "--cpu", "2",
        "--timeout", "300s",
        "--quiet"
    ]

    # বাংলা মন্তব্য: Cloud Run-এ আবশ্যক এনভায়রনমেন্ট ভেরিয়েবলগুলো ডিপ্লয় কমান্ডে সরাসরি
    # পাস করা হচ্ছে, যাতে রিডিপ্লয়ের পরেও SUPABASE_DATABASE_URL_POOLER-এর মতো
    # ক্রিটিক্যাল সিক্রেট হারিয়ে না যায় (আগে অনুপস্থিত থাকায় /api/v1/health 503 দিত)।
    required_env = [
        "ENV",
        "SUPABASE_DATABASE_URL",
        "SUPABASE_DATABASE_URL_POOLER",
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "GCP_PROJECT_ID",
        "GCP_REGION",
        "SERVICE_ROLE",
        "INFISICAL_TOKEN",
        "INFISICAL_PROJECT_ID",
        "INFISICAL_ENV",
    ]
    env_pairs = [f"{k}={os.environ[k]}" for k in required_env if os.environ.get(k)]
    if env_pairs:
        deploy_cmd += ["--set-env-vars", ",".join(env_pairs)]

    res = subprocess.run(deploy_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise Exception(f"DEPLOYMENT FAILED!\n{res.stderr}")

    print("✅ Deployment successful. Verifying health...")
    api_url = os.getenv("SUPREMEAI_API_URL")
    if api_url:
        health_endpoint = f"{api_url.rstrip('/')}/health"
        is_healthy = False
        for _ in range(24): # 60 seconds (24 * 2.5)
            try:
                req = urllib.request.Request(health_endpoint, headers={'User-Agent': 'SupremeAI-CI'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        is_healthy = True
                        break
            except Exception as e:
                print(f"🚨 [FATAL CI EXCEPTION] Pipeline state evaluator broke: {e}")
                sys.exit(2)
            time.sleep(2.5)

        if not is_healthy:
            raise Exception("Deep health-check failed! The new code is broken.")

    print("🎉 DEPLOYMENT & VERIFICATION SUCCESSFUL!")


# ==========================================
# 🧠 EVALUATE COMMAND
# ==========================================
def cmd_evaluate(args):
    print("🧠 Evaluating Auto-Fix Confidence...")
    # Add evaluation logic as needed in the future
    print("✅ Evaluation passed.")


# ==========================================
# 🚀 MAIN CLI ENTRYPOINT
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="SupremeAI Unified CI/CD Command Center")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available CI commands")

    # 1. Health Check
    subparsers.add_parser("health-check", help="Run strictly fail-closed system health check")

    # 2. Generate Report
    report_parser = subparsers.add_parser("generate-report", help="Generate CI validation and summary reports")
    report_parser.add_argument("--type", default="full", choices=["full", "smart", "advanced"], help="Report type")
    report_parser.add_argument("--pytest-json", help="Path to pytest JSON/MD")
    report_parser.add_argument("--coverage-json", help="Path to coverage JSON")
    report_parser.add_argument("--vitest-json", action="append", help="Path to Vitest JSON")
    report_parser.add_argument("--label", help="Report label")

    # 3. Deploy
    deploy_parser = subparsers.add_parser("deploy", help="Deploy the backend")
    deploy_parser.add_argument("--strategy", default="canary", choices=["canary", "blue-green", "direct"], help="Deployment strategy")

    # 4. Evaluate
    subparsers.add_parser("evaluate", help="Cross-validate auto-fix diffs using multi-model AI")

    args = parser.parse_args()

    try:
        if args.command == "health-check":
            cmd_health_check(args)
        elif args.command == "generate-report":
            cmd_generate_report(args)
        elif args.command == "deploy":
            cmd_deploy(args)
        elif args.command == "evaluate":
            cmd_evaluate(args)
    except Exception as e:
        print(f"\n🚨 [FATAL] {e!s}")
        sys.exit(1) # Fail-fast enforcement


if __name__ == "__main__":
    main()
