#!/usr/bin/env python3
"""render_build_quota_guard.py — Render Account Build Minutes Tracker & Deployment Router.

Monitors monthly build minutes for each specific Render account / service.
- If Monthly Build Time < 450 min:
    Permits native Render autoDeploy (burns remaining free Render build minutes).
- If Monthly Build Time >= 450 min:
    Switches strategy to GitHub Actions Build & Push (builds Docker container via
    GitHub Actions runner to protect Render's 500 min/mo free quota, then triggers
    image deploy on Render consuming 0 build minutes).

Usage:
  python3 scripts/ci/render_build_quota_guard.py --service supremeai-primary-node
  python3 scripts/ci/render_build_quota_guard.py --all --threshold 450
  python3 scripts/ci/render_build_quota_guard.py --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SAFE_BUILD_THRESHOLD_MINUTES = 450.0
RENDER_MONTHLY_LIMIT_MINUTES = 500.0

SERVICE_ACCOUNT_MAP: dict[str, str] = {
    "supremeai-primary-node": "RENDER_API_KEY_1",
    "supremeai-worker-node": "RENDER_API_KEY_2",
    "supremeai-scraper-node": "RENDER_API_KEY_3",
    "supremeai-mcp-tower": "RENDER_API_KEY_4",
    "supremeai-api": "RENDER_API_KEY_5",
}


def load_env(env_path: Path | None = None) -> dict[str, str]:
    """Load key-value pairs from .env file if available."""
    env: dict[str, str] = {}
    target_path = env_path or (Path(__file__).resolve().parents[2] / ".env")
    if not target_path.is_file():
        return env
    with target_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get_current_month_start() -> datetime:
    """Return the start of the current month in UTC."""
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


def fetch_account_services(api_key: str) -> list[dict[str, Any]]:
    """Fetch all services associated with a specific Render API key."""
    req = urllib.request.Request(
        "https://api.render.com/v1/services?limit=50",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "SupremeAI-Quota-Guard/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode())
        return [item.get("service", {}) for item in data]


def fetch_service_deploys(
    service_id: str, api_key: str, limit: int = 50
) -> list[dict[str, Any]]:
    """Fetch recent deploys for a given service."""
    req = urllib.request.Request(
        f"https://api.render.com/v1/services/{service_id}/deploys?limit={limit}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "SupremeAI-Quota-Guard/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode())
        return [d.get("deploy", {}) for d in data]


def calculate_monthly_build_minutes(
    service_id: str,
    api_key: str,
    month_start: datetime | None = None,
) -> tuple[float, int]:
    """Calculate total build duration in minutes for the current calendar month."""
    if month_start is None:
        month_start = get_current_month_start()

    deploys = fetch_service_deploys(service_id, api_key, limit=50)
    total_seconds = 0.0
    deploy_count = 0

    for dep in deploys:
        c_str = dep.get("createdAt")
        f_str = dep.get("finishedAt")
        if not c_str or not f_str:
            continue
        try:
            c_dt = datetime.fromisoformat(c_str.replace("Z", "+00:00"))
            f_dt = datetime.fromisoformat(f_str.replace("Z", "+00:00"))
            if c_dt >= month_start:
                duration = max(0.0, (f_dt - c_dt).total_seconds())
                total_seconds += duration
                deploy_count += 1
        except Exception:
            continue

    return round(total_seconds / 60.0, 2), deploy_count


def evaluate_deployment_mode(
    build_minutes: float,
    threshold: float = SAFE_BUILD_THRESHOLD_MINUTES,
) -> dict[str, Any]:
    """Determine whether to permit native autoDeploy or switch to GitHub Actions build."""
    exceeded = build_minutes >= threshold
    return {
        "build_minutes": build_minutes,
        "threshold": threshold,
        "limit": RENDER_MONTHLY_LIMIT_MINUTES,
        "mode": "GITHUB_ACTIONS_BUILD_AND_PUSH"
        if exceeded
        else "RENDER_NATIVE_AUTODEPLOY",
        "allow_render_native_build": not exceeded,
        "warning": exceeded,
        "message": (
            f"Build time ({build_minutes}m) >= threshold ({threshold}m)! "
            "Switching to GitHub Actions build to protect free limit."
            if exceeded
            else f"Build time ({build_minutes}m) is healthy (< {threshold}m). "
            "Native Render auto-deploy permitted."
        ),
    }


def set_render_autodeploy(service_id: str, api_key: str, enabled: bool) -> bool:
    """Toggle autoDeploy setting on Render via REST API."""
    url = f"https://api.render.com/v1/services/{service_id}"
    payload = json.dumps({"autoDeploy": "yes" if enabled else "no"}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "SupremeAI-Quota-Guard/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Failed to toggle autoDeploy: {e}", file=sys.stderr)
        return False


def run_self_test() -> int:
    """Offline self-test for build calculations and decision branching."""
    print("Running render_build_quota_guard offline self-test...")

    # Under threshold check
    res_ok = evaluate_deployment_mode(245.5, threshold=450.0)
    assert res_ok["mode"] == "RENDER_NATIVE_AUTODEPLOY", (
        f"Expected native deploy, got {res_ok}"
    )
    assert res_ok["allow_render_native_build"] is True
    assert res_ok["warning"] is False

    # Over threshold check
    res_over = evaluate_deployment_mode(452.1, threshold=450.0)
    assert res_over["mode"] == "GITHUB_ACTIONS_BUILD_AND_PUSH", (
        f"Expected GH actions, got {res_over}"
    )
    assert res_over["allow_render_native_build"] is False
    assert res_over["warning"] is True

    # Exact threshold boundary check
    res_exact = evaluate_deployment_mode(450.0, threshold=450.0)
    assert res_exact["mode"] == "GITHUB_ACTIONS_BUILD_AND_PUSH"
    assert res_exact["allow_render_native_build"] is False

    print("render_build_quota_guard self-test: PASS (deterministic exit 0)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render Account Build Minutes Tracker & Deployment Router"
    )
    parser.add_argument(
        "--service",
        type=str,
        help="Specific service name to inspect (e.g. supremeai-primary-node)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=SAFE_BUILD_THRESHOLD_MINUTES,
        help="Build minutes threshold (default: 450.0)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Inspect all known services across all configured keys",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Run offline deterministic self-test"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results in pure JSON format"
    )
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    env = {**os.environ, **load_env()}

    # Resolve target services
    services_to_check: list[tuple[str, str]] = []
    if args.service:
        key_var = SERVICE_ACCOUNT_MAP.get(args.service, "RENDER_API_KEY")
        services_to_check.append((args.service, key_var))
    elif args.all:
        for svc_name, key_var in SERVICE_ACCOUNT_MAP.items():
            services_to_check.append((svc_name, key_var))
    else:
        # Default: check all
        for svc_name, key_var in SERVICE_ACCOUNT_MAP.items():
            services_to_check.append((svc_name, key_var))

    results = []
    has_warning = False

    for svc_name, key_var in services_to_check:
        api_key = env.get(key_var) or (
            env.get("RENDER_API_KEY_API") if key_var == "RENDER_API_KEY_5" else None
        )
        if not api_key:
            results.append(
                {
                    "service": svc_name,
                    "account_key_var": key_var,
                    "warning": False,
                    "notice": f"API key '{key_var}' not configured in current environment. Ready for configuration.",
                }
            )
            continue

        try:
            # Find service ID
            services = fetch_account_services(api_key)
            target = next((s for s in services if s.get("name") == svc_name), None)
            if not target:
                results.append(
                    {
                        "service": svc_name,
                        "error": f"Service '{svc_name}' not found under key '{key_var}'",
                    }
                )
                continue

            svc_id = target.get("id", "")
            build_mins, deploy_count = calculate_monthly_build_minutes(svc_id, api_key)
            eval_res = evaluate_deployment_mode(build_mins, threshold=args.threshold)
            eval_res["service"] = svc_name
            eval_res["service_id"] = svc_id
            eval_res["monthly_deploys"] = deploy_count
            eval_res["account_key_var"] = key_var
            eval_res["current_auto_deploy"] = target.get("autoDeploy")
            results.append(eval_res)

            if eval_res["warning"]:
                has_warning = True

        except Exception as e:
            results.append(
                {
                    "service": svc_name,
                    "error": str(e),
                }
            )

    if args.json:
        print(
            json.dumps(
                {
                    "services": results,
                    "threshold": args.threshold,
                    "has_warning": has_warning,
                },
                indent=2,
            )
        )
    else:
        print("=" * 72)
        print(" SupremeAI — Render Account Build Minutes & Deployment Router")
        print(
            f" Safe Threshold: {args.threshold} mins | Render Free Quota: 500.0 mins/month"
        )
        print("=" * 72)
        for r in results:
            if "error" in r:
                print(f"[X] {r['service']}: ERROR - {r['error']}")
                continue
            if "notice" in r:
                print(f"[INFO] {r['service']} ({r['account_key_var']}):")
                print(f"   Status             : {r['notice']}")
                print("-" * 72)
                continue
            icon = "[WARN]" if r["warning"] else "[OK]"
            print(f"{icon} {r['service']} ({r['account_key_var']}):")
            print(
                f"   Monthly Build Time: {r['build_minutes']} / 500.0 mins ({r['monthly_deploys']} deploys)"
            )
            print(f"   Current autoDeploy : {r['current_auto_deploy']}")
            print(f"   Selected Action    : {r['mode']}")
            print(f"   Directive          : {r['message']}")
            print("-" * 72)

    return 1 if has_warning else 0


if __name__ == "__main__":
    sys.exit(main())
