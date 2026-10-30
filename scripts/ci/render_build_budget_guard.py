#!/usr/bin/env python3
"""
Render Build Budget Guard (Zero Infrastructure Cost Protection)
Protects all 4 Render accounts against exceeding the free-tier 500 build-minute limit.

If a service's estimated monthly build usage reaches threshold (default: 450 mins):
  -> Automatically toggles autoDeploy to "no" via Render API
  -> Prevents uncontrolled auto-build runs on git push

If usage is under threshold and month resets:
  -> Automatically restores autoDeploy to "yes"
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# render_client lives at scripts/ops/lib/render_client.py — the historical
# scripts/lib/ path vanished in the ops/ relocation and crashed this guard at
# import in every context (the #2811 hardening ride-along).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops" / "lib"))
from render_client import RenderClient  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BUILD_MINUTE_THRESHOLD = 450.0  # Max safe minutes out of 500 monthly free tier

# Render caps a deploys page at 100; 12 pages covers a 1200-deploy month,
# far beyond any observed retry-fail volume (#2811 window class).
DEPLOY_WINDOW_PAGE_SIZE = 100
DEPLOY_WINDOW_MAX_PAGES = 12


def _unwrap_deploy(item):
    """Render lists deploys as {"deploy": {...}} — tolerate both envelopes."""
    if not isinstance(item, dict):
        return {}
    dep = item.get("deploy")
    return dep if isinstance(dep, dict) else item


def sum_month_build_seconds(deploys, month_start):
    """Pure: sum durations of deploys started within [month_start, *).

    Returns (total_seconds, deploy_count, saw_pre_month). ``saw_pre_month``
    flags that the newest-first stream has reached back past the month start
    (the pagination stop rule; see the #2811 window class).
    """
    total_seconds = 0.0
    deploy_count = 0
    saw_pre_month = False
    for item in deploys:
        dep = _unwrap_deploy(item)
        created_at_str = dep.get("createdAt")
        finished_at_str = dep.get("finishedAt")
        if not created_at_str or not finished_at_str:
            continue
        try:
            created_at = datetime.fromisoformat(str(created_at_str).replace("Z", "+00:00"))
            finished_at = datetime.fromisoformat(str(finished_at_str).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if created_at < month_start:
            saw_pre_month = True
            continue
        if created_at.year == month_start.year and created_at.month == month_start.month:
            duration = (finished_at - created_at).total_seconds()
            if duration > 0:
                total_seconds += duration
                deploy_count += 1
    return total_seconds, deploy_count, saw_pre_month


SERVICES = [
    {
        "role": "Core",
        "name": "supremeai-primary-node",
        "key_env": "RENDER_API_KEY_1",
        "fallback_key": "RENDER_API_KEY",
        "svc_env": "RENDER_PRIMARY_SVC_ID",
        "default_svc": "srv-dabm7dfqj5pc738jkbmg"
    },
    {
        "role": "Worker",
        "name": "supremeai-worker-node",
        "key_env": "RENDER_API_KEY_2",
        "fallback_key": None,
        "svc_env": "RENDER_WORKER_SVC_ID",
        "default_svc": "srv-dabm7evqj5pc738jkf30"
    },
    {
        "role": "Scraper",
        "name": "supremeai-scraper-node",
        "key_env": "RENDER_API_KEY_3",
        "fallback_key": None,
        "svc_env": "RENDER_SCRAPER_SVC_ID",
        "default_svc": "srv-dabm7gfqj5pc738jkicg"
    },
    {
        "role": "MCP",
        "name": "supremeai-mcp-tower",
        "key_env": "RENDER_API_KEY_4",
        "fallback_key": None,
        "svc_env": "RENDER_MCP_SVC_ID",
        "default_svc": "srv-dabm7inqj5pc738jkrt0"
    }
]


def calculate_monthly_build_minutes(api_key: str, service_id: str) -> float:
    """Calculate total build minutes used in the current calendar month.

    Cursor-paginates until the month window is saturated instead of reading a
    fixed first page (#2811 window class): a truncated window under-counts
    month-to-date burn during retry-fail loops and can present a false safe
    posture to the autoDeploy toggle below.
    """
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    deploys = []
    try:
        client = RenderClient(api_key=api_key)
        for page in client.paginate(
            f"/services/{service_id}/deploys",
            page_size=DEPLOY_WINDOW_PAGE_SIZE,
            max_pages=DEPLOY_WINDOW_MAX_PAGES,
        ):
            deploys.extend(page)
            _, _, saw_pre_month = sum_month_build_seconds(page, month_start)
            if saw_pre_month or len(page) < DEPLOY_WINDOW_PAGE_SIZE:
                break
    except Exception as e:
        print(f"  ⚠️ Warning: Unable to fetch deploys for service {service_id}: {e}")
        return 0.0

    total_seconds, _count, _sat = sum_month_build_seconds(deploys, month_start)
    return total_seconds / 60.0


def set_auto_deploy(api_key: str, service_id: str, enable: bool) -> bool:
    """Toggle autoDeploy on Render service via REST API."""
    target_value = "yes" if enable else "no"

    try:
        data = RenderClient(api_key=api_key).update_service(
            service_id, {"autoDeploy": target_value}
        )
        return data.get("autoDeploy") == target_value
    except Exception as e:
        print(f"  ❌ Error toggling autoDeploy={target_value} on {service_id}: {e}")
        return False


def get_service_info(api_key: str, service_id: str) -> dict | None:
    try:
        return RenderClient(api_key=api_key).get_service(service_id)
    except Exception:
        return None


def run_guard(threshold: float = BUILD_MINUTE_THRESHOLD) -> dict[str, dict]:
    results = {}
    print(f"🛡️ Running Render Build Budget Guard (Threshold: {threshold} mins / account)...")

    for svc_cfg in SERVICES:
        role = svc_cfg["role"]
        name = svc_cfg["name"]
        key = os.environ.get(svc_cfg["key_env"])
        if not key and svc_cfg.get("fallback_key"):
            key = os.environ.get(svc_cfg["fallback_key"])

        svc_id = os.environ.get(svc_cfg["svc_env"]) or svc_cfg["default_svc"]

        print(f"\n[{role}] {name} (ID: {svc_id})")
        if not key:
            print(f"  ⚠️ Skipping: Missing API Key ({svc_cfg['key_env']})")
            continue

        svc_info = get_service_info(key, svc_id)
        current_auto_deploy = svc_info.get("autoDeploy", "unknown") if svc_info else "unknown"

        minutes_used = calculate_monthly_build_minutes(key, svc_id)
        print(f"  Estimated Build Usage (Current Month): {minutes_used:.2f} / 500 mins")
        print(f"  Current autoDeploy State: {current_auto_deploy}")

        action = "none"
        if minutes_used >= threshold:
            print(f"  🚨 USAGE EXCEEDED THRESHOLD ({minutes_used:.1f} >= {threshold}m)!")
            if current_auto_deploy == "yes":
                print("  🔒 Disabling autoDeploy to prevent quota overrun...")
                if set_auto_deploy(key, svc_id, enable=False):
                    print("  ✅ autoDeploy successfully DISABLED.")
                    action = "disabled"
                else:
                    action = "failed_disable"
            else:
                print("  ℹ️ autoDeploy is already disabled. Safe.")
        else:
            remaining = threshold - minutes_used
            print(f"  ✅ Safe posture ({remaining:.1f} mins remaining before cap).")
            if current_auto_deploy == "no":
                print("  🔓 Under budget cap! Restoring autoDeploy to 'yes'...")
                if set_auto_deploy(key, svc_id, enable=True):
                    print("  ✅ autoDeploy successfully RESTORED.")
                    action = "restored"
                else:
                    action = "failed_restore"

        results[role] = {
            "name": name,
            "minutes_used": round(minutes_used, 2),
            "auto_deploy": current_auto_deploy,
            "action": action
        }

    return results


if __name__ == "__main__":
    guard_results = run_guard()
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path and os.path.exists(summary_path):
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("\n### 🛡️ Render Build Budget Guard Report\n\n")
            f.write("| Node | Service | Monthly Build Mins | AutoDeploy State | Action |\n")
            f.write("|---|---|---|---|---|\n")
            for role, r in guard_results.items():
                f.write(f"| {role} | {r['name']} | {r['minutes_used']}m / 500m | {r['auto_deploy']} | {r['action']} |\n")
    sys.exit(0)
