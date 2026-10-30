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
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SAFE_BUILD_THRESHOLD_MINUTES = 450.0
RENDER_MONTHLY_LIMIT_MINUTES = 500.0

# Render caps a deploys page at 100; 12 pages covers a 1200-deploy month,
# far beyond any observed retry-fail volume (#2811 window class).
DEPLOY_WINDOW_PAGE_SIZE = 100
DEPLOY_WINDOW_MAX_PAGES = 12

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


def _unwrap_deploy(item: Any) -> dict[str, Any]:
    """Render lists deploys as {"deploy": {...}} — tolerate both envelopes."""
    if not isinstance(item, dict):
        return {}
    dep = item.get("deploy")
    return dep if isinstance(dep, dict) else item


def sum_month_build_seconds(
    deploys: list[Any], month_start: datetime
) -> tuple[float, int, bool]:
    """Pure: sum durations of deploys started within [month_start, *).

    Returns (total_seconds, deploy_count, saw_pre_month). ``saw_pre_month``
    reports that a parsed deploy predates the month boundary — with Render's
    newest-first listing this certifies the stream has reached back past the
    month start (the pagination stop rule; see the #2811 window class).
    """
    total_seconds = 0.0
    deploy_count = 0
    saw_pre_month = False
    for item in deploys:
        dep = _unwrap_deploy(item)
        c_str = dep.get("createdAt")
        f_str = dep.get("finishedAt")
        if not c_str or not f_str:
            continue
        try:
            c_dt = datetime.fromisoformat(str(c_str).replace("Z", "+00:00"))
            f_dt = datetime.fromisoformat(str(f_str).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if c_dt < month_start:
            saw_pre_month = True
            continue
        duration = max(0.0, (f_dt - c_dt).total_seconds())
        total_seconds += duration
        deploy_count += 1
    return total_seconds, deploy_count, saw_pre_month


def _fetch_deploys_page(
    service_id: str, api_key: str, query: dict[str, Any]
) -> list[dict[str, Any]]:
    """Fetch a single page of deploys with an explicit query (limit/after)."""
    qs = urllib.parse.urlencode(query)
    req = urllib.request.Request(
        f"https://api.render.com/v1/services/{service_id}/deploys?{qs}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "SupremeAI-Quota-Guard/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode())
        return list(data) if isinstance(data, list) else []


def fetch_month_deploys(
    service_id: str,
    api_key: str,
    month_start: datetime,
    page_size: int = DEPLOY_WINDOW_PAGE_SIZE,
    max_pages: int = DEPLOY_WINDOW_MAX_PAGES,
) -> list[dict[str, Any]]:
    """Cursor-paginate deploys newest-first until the month window is saturated.

    Replaces the fixed limit=50 window whose slide produced the #2811 class: a
    truncated window under-counts month-to-date burn and moves the reported
    counter DOWN as old builds scroll out (the ledger 'correction' signature),
    so a retry-fail month can read as a false safe posture.
    """
    collected: list[dict[str, Any]] = []
    after: str | None = None
    for _ in range(max_pages):
        query: dict[str, Any] = {"limit": page_size}
        if after:
            query["after"] = after
        items = _fetch_deploys_page(service_id, api_key, query)
        collected.extend(items)
        _, _, saw_pre_month = sum_month_build_seconds(items, month_start)
        if saw_pre_month or len(items) < page_size:
            break
        last = _unwrap_deploy(items[-1]) if items else {}
        after = last.get("id")
        if not after:
            break
    return collected


def calculate_monthly_build_minutes(
    service_id: str,
    api_key: str,
    month_start: datetime | None = None,
) -> tuple[float, int]:
    """Calculate total build duration in minutes for the current calendar month."""
    if month_start is None:
        month_start = get_current_month_start()

    deploys = fetch_month_deploys(service_id, api_key, month_start)
    total_seconds, deploy_count, _ = sum_month_build_seconds(deploys, month_start)
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
    except (urllib.error.URLError, TimeoutError, OSError) as e:
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

    # ── #2811 window class: a month-window sum must not truncate ──
    month_start = datetime(2026, 10, 1, tzinfo=timezone.utc)

    def _dep(created: str, dur_seconds: float) -> dict[str, Any]:
        from datetime import timedelta

        c = datetime.fromisoformat(created.replace("Z", "+00:00"))
        return {
            "deploy": {
                "id": f"dep-{created}",
                "createdAt": created,
                "finishedAt": (c + timedelta(seconds=dur_seconds)).isoformat().replace(
                    "+00:00", "Z"
                ),
            }
        }

    # 120 one-minute month-to-date deploys: the old fixed limit=50 window
    # counted only the newest 50 (50.0 min); the saturated window counts all.
    deploys_120 = [_dep(f"2026-10-15T00:{i // 60:02d}:{i % 60:02d}:00Z", 60.0) for i in range(120)]
    total, count, sat = sum_month_build_seconds(deploys_120, month_start)
    assert round(total / 60.0, 2) == 120.0, f"expected 120.0, got {total / 60.0}"
    assert count == 120
    assert sat is False

    # Pre-month deploys are excluded and flag saturation (the stop rule).
    deploys_mixed = [_dep("2026-09-20T10:00:00Z", 600.0)] + deploys_120
    total_m, count_m, sat_m = sum_month_build_seconds(deploys_mixed, month_start)
    assert count_m == 120 and round(total_m / 60.0, 2) == 120.0
    assert sat_m is True

    # Calendar boundary: a deploy started exactly at month_start counts;
    # one second earlier does not.
    total_b, count_b, sat_b = sum_month_build_seconds(
        [
            _dep("2026-10-01T00:00:00Z", 60.0),
            _dep("2026-09-30T23:59:59Z", 60.0),
        ],
        month_start,
    )
    assert count_b == 1 and round(total_b / 60.0, 2) == 1.0 and sat_b is True

    # Junk / missing timestamps never crash or count; degenerate durations
    # (0s, negative clock-skew) add 0 seconds but remain deploy records —
    # the original counter semantics, preserved.
    total_j, count_j, sat_j = sum_month_build_seconds(
        [
            {"deploy": {"id": "x1", "createdAt": "not-a-date", "finishedAt": "junk"}},
            {"deploy": {"id": "x2"}},
            "garbage-item",
            _dep("2026-10-02T00:00:00Z", 0.0),
            _dep("2026-10-03T00:00:00Z", -5.0),
            _dep("2026-10-04T00:00:00Z", 30.0),
        ],
        month_start,
    )
    assert count_j == 3 and round(total_j, 2) == 30.0 and sat_j is False

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

        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
        ) as e:
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
