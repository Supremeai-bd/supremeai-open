#!/usr/bin/env python3
"""Vercel Deployment Preflight Quota & Rate-Limit Guard.

Checks both:
1. Daily Rolling Limit: Tracks deployments in last 24h against a safe threshold (e.g. 85 / 100).
2. Monthly Limit: Tracks billing cycle deployment counts since 1st of current month.

Emits machine-readable output and step summaries to gracefully gate Vercel deployments.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone


def get_json(url: str, token: str) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "SupremeAI-CI-Preflight/1.0",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.loads(res.read().decode("utf-8"))


def main() -> None:
    token = os.getenv("VERCEL_TOKEN")
    project_id = os.getenv("VERCEL_PROJECT_ID")
    team_id = os.getenv("VERCEL_ORG_ID") or os.getenv("VERCEL_TEAM_ID")

    # Safe limits with 15% buffer
    daily_cap = int(os.getenv("VERCEL_DAILY_DEPLOY_LIMIT", "85"))  # Hobby max 100
    monthly_cap = int(os.getenv("VERCEL_MONTHLY_DEPLOY_LIMIT", "1500"))

    if not token:
        print("[WARN] VERCEL_TOKEN not provided. Skipping preflight check (allowing build).")
        set_output("build_allowed", "true")
        set_output("reason", "token_missing_permissive")
        return

    now = datetime.now(timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    rolling_24h_ms = now_ms - (24 * 60 * 60 * 1000)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start_ms = int(month_start.timestamp() * 1000)

    url = "https://api.vercel.com/v6/deployments?limit=100"
    if project_id:
        url += f"&projectId={project_id}"
    if team_id:
        url += f"&teamId={team_id}"

    try:
        data = get_json(url, token)
        deployments = data.get("deployments", [])

        # Count 24h rolling and current month deploys
        daily_count = 0
        monthly_count = 0
        rate_limited = False

        for d in deployments:
            created_ms = d.get("created", 0)
            state = d.get("state", "")
            if state == "ERROR" and "rate-limit" in str(d.get("errorMessage", "")).lower():
                rate_limited = True

            if created_ms >= rolling_24h_ms:
                daily_count += 1
            if created_ms >= month_start_ms:
                monthly_count += 1

        print("Vercel Usage Telemetry:")
        print(f"  - Last 24 Hours: {daily_count} / {daily_cap} deploys (Hard limit: 100)")
        print(f"  - Current Month (from {month_start.strftime('%Y-%m-%d')}): {monthly_count} / {monthly_cap} deploys")
        print(f"  - Recent Rate-Limit Detected: {rate_limited}")

        # Evaluate gating
        build_allowed = True
        reasons = []

        if rate_limited:
            build_allowed = False
            reasons.append("Recent rate-limit signal detected in deployment history")

        if daily_count >= daily_cap:
            build_allowed = False
            reasons.append(f"Daily deployment count ({daily_count}) reached safe threshold ({daily_cap})")

        if monthly_count >= monthly_cap:
            build_allowed = False
            reasons.append(f"Monthly deployment count ({monthly_count}) reached safe threshold ({monthly_cap})")

        reason_str = "; ".join(reasons) if reasons else "Quota healthy"

        set_output("build_allowed", "true" if build_allowed else "false")
        set_output("daily_count", str(daily_count))
        set_output("monthly_count", str(monthly_count))
        set_output("reason", reason_str)

        evidence_path = os.getenv("PREFLIGHT_EVIDENCE_PATH", "ci-reports/vercel-deploy-preflight.json")
        try:
            os.makedirs(os.path.dirname(evidence_path), exist_ok=True)
            with open(evidence_path, "w", encoding="utf-8") as ef:
                json.dump({
                    "timestamp": now.isoformat(),
                    "build_allowed": build_allowed,
                    "daily_count": daily_count,
                    "daily_cap": daily_cap,
                    "monthly_count": monthly_count,
                    "monthly_cap": monthly_cap,
                    "rate_limited": rate_limited,
                    "reason": reason_str,
                }, ef, indent=2)
        except Exception as ef_err:
            print(f"[WARN] Failed to write preflight evidence file: {ef_err}")

        # Write to GITHUB_STEP_SUMMARY
        summary_path = os.getenv("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write("### ⚡ Vercel Deployment Preflight Guard\n\n")
                f.write("| Metric | Observed | Safe Threshold | Plan Limit |\n")
                f.write("|---|:---:|:---:|:---:|\n")
                f.write(f"| **Daily Deploys (24h)** | `{daily_count}` | `{daily_cap}` | 100 |\n")
                f.write(f"| **Monthly Deploys** | `{monthly_count}` | `{monthly_cap}` | Fair-Use |\n")
                f.write(f"| **Status** | {'🟢 **Ready**' if build_allowed else '🟡 **Quota Throttled (Skipped)**'} | — | — |\n\n")
                if not build_allowed:
                    f.write(f"> ⚠️ **Notice**: Vercel preview deployment safely gated: {reason_str}. Main Firebase Hosting is unaffected.\n")

        print(f"Decision: build_allowed={'true' if build_allowed else 'false'} ({reason_str})")

    except Exception as e:
        print(f"[WARN] Vercel API check encountered error: {e}")
        # Fail-open / permissive so API glitches don't break main build
        set_output("build_allowed", "true")
        set_output("reason", f"error_fallback: {str(e)[:100]}")


def set_output(name: str, value: str) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


if __name__ == "__main__":
    main()

