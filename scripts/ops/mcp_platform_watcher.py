#!/usr/bin/env python3
"""Unified MCP Tower 15-Minute Platform Health Watcher & Incident Guard.
========================================================================
Replaces fragmented 3rd-party platform sentries and speculative auditors.
Periodically queries the authoritative MCP Control Tower for system health
(Render, Supabase, Redis/Upstash, Cloudflare, Infisical, Kaggle, Telegram).

Rules & Invariants:
  1. Single SSOT: Queries MCP Control Tower `system_health` directly.
  2. Deterministic Dedup: Computes incident fingerprint.
  3. No Duplicate Spam: Verifies against IncidentRegistrySSOT and triage receipts.
     If an incident is already tracked (e.g. #3744 for Render), it appends
     evidence instead of spawning duplicate GitHub issues or PRs.
  4. Auto-Reporting: If and only if a novel, untracked failure is detected,
     files a structured canonical incident report via create_issue.

Usage:
  python scripts/ops/mcp_platform_watcher.py --check-once
  python scripts/ops/mcp_platform_watcher.py --loop --interval-minutes 15
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "scripts" / "agents"))

try:
    from incident_fingerprint import (
        IncidentRegistrySSOT,
        compute_incident_fingerprint,
        format_incident_marker,
    )
except ImportError:
    from scripts.agents.incident_fingerprint import (  # type: ignore
        IncidentRegistrySSOT,
        compute_incident_fingerprint,
        format_incident_marker,
    )


def query_mcp_tower_health() -> dict[str, Any] | None:
    """Query system_health from MCP Control Tower via mcp_tower_client."""
    client_script = ROOT_DIR / "scripts" / "agents" / "mcp_tower_client.py"
    if not client_script.exists():
        print(f"❌ Error: mcp_tower_client.py not found at {client_script}")
        return None

    try:
        proc = subprocess.run(
            [sys.executable, str(client_script), "call", "system_health"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            cwd=str(ROOT_DIR),
        )
        if proc.returncode != 0:
            print(f"⚠️ MCP Tower health check returned exit code {proc.returncode}: {proc.stderr[:150]}")
            return None

        # Parse MCP JSON-RPC format
        raw_output = proc.stdout.strip()
        data = json.loads(raw_output)
        content_items = data.get("content", [])
        for item in content_items:
            if item.get("type") == "text":
                return json.loads(item.get("text", "{}"))
        return None
    except Exception as exc:
        print(f"⚠️ Exception querying MCP Tower health: {exc}")
        return None


def run_watcher_cycle(
    registry: IncidentRegistrySSOT,
    auto_create_issue: bool = False,
) -> list[dict[str, Any]]:
    """Run a single audit cycle using MCP Tower data."""
    now_iso = datetime.now(timezone.utc).isoformat()
    health_data = query_mcp_tower_health()

    if not health_data:
        print(f"[{now_iso}] ⚠️ Could not obtain health report from MCP Tower.")
        return []

    services = health_data.get("services", [])
    summary = health_data.get("summary", "Unknown")
    print(f"[{now_iso}] 🛰️ MCP Tower Status: {summary}")

    findings: list[dict[str, Any]] = []

    for svc in services:
        status = svc.get("status", "unknown")
        svc_id = svc.get("id", "unknown")
        display_name = svc.get("displayName", svc_id)
        deploy_status = svc.get("deployStatus")

        is_degraded = status != "healthy" or (deploy_status and deploy_status != "live")
        if not is_degraded:
            continue

        error_class = deploy_status or status
        root_cause_family = "render-deploy" if "render" in svc_id else "unspecified"
        if "redis" in svc_id:
            root_cause_family = "redis-quota"
        elif "supabase" in svc_id:
            root_cause_family = "supabase-schema"

        fp = compute_incident_fingerprint(
            environment="production",
            service=svc_id,
            normalized_error_class=error_class,
            affected_component="service-health",
            root_cause_family=root_cause_family,
        )

        is_winner, record = registry.register_or_corroborate(
            environment="production",
            service=svc_id,
            normalized_error_class=error_class,
            affected_component="service-health",
            root_cause_family=root_cause_family,
        )

        finding = {
            "service_id": svc_id,
            "display_name": display_name,
            "status": status,
            "deploy_status": deploy_status,
            "fingerprint": fp,
            "is_new_incident": is_winner,
            "evidence_count": record.evidence_count,
            "canonical_issue": record.canonical_issue_number,
        }
        findings.append(finding)

        if is_winner:
            print(f"🚨 [NEW INCIDENT] {display_name} degraded: {error_class} (fp={fp})")
            if auto_create_issue:
                _create_canonical_issue(finding)
        else:
            ref = f"#{record.canonical_issue_number}" if record.canonical_issue_number else "tracked registry"
            print(
                f"↻ [DEDUP SUPPRESSED] {display_name} failure already known ({ref}). "
                f"Evidence count={record.evidence_count} (fp={fp}). No duplicate issue filed."
            )

    return findings


def _create_canonical_issue(finding: dict[str, Any]) -> None:
    """Create a canonical issue with incident-fp marker if authorized."""
    create_issue_script = ROOT_DIR / "scripts" / "agents" / "create_issue.py"
    if not create_issue_script.exists():
        return

    fp = finding["fingerprint"]
    title = f"fix(infra): {finding['display_name']} degraded ({finding['status']})"
    scope = f"infrastructure/{finding['service_id']}"
    body = (
        f"{format_incident_marker(fp)}\n\n"
        f"## 🛰️ Platform Health Degradation Detected via MCP Tower\n\n"
        f"- **Service:** {finding['display_name']} (`{finding['service_id']}`)\n"
        f"- **Status:** `{finding['status']}`\n"
        f"- **Deploy Status:** `{finding.get('deploy_status')}`\n"
        f"- **Incident Fingerprint:** `{fp}`\n"
        f"- **First Observed:** `{datetime.now(timezone.utc).isoformat()}`\n\n"
        f"Automated observation by MCP Platform Watcher. Deduplicated via SSOT."
    )

    try:
        subprocess.run(
            [
                sys.executable,
                str(create_issue_script),
                "--type",
                "blocker",
                "--title",
                title,
                "--scope",
                scope,
                "--group",
                "infra",
                "--body",
                body,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT_DIR),
            timeout=40,
        )
    except Exception as exc:
        print(f"⚠️ Failed to auto-create issue: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified MCP Tower 15-Minute Platform Health Watcher"
    )
    parser.add_argument(
        "--check-once",
        action="store_true",
        help="Run a single health check cycle and exit",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously every N minutes",
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=15,
        help="Loop interval in minutes (default: 15)",
    )
    parser.add_argument(
        "--auto-create-issues",
        action="store_true",
        help="Allow creating canonical issues for new incidents",
    )
    args = parser.parse_args()

    registry = IncidentRegistrySSOT()

    if args.loop:
        interval_secs = max(args.interval_minutes, 1) * 60
        print(f"🚀 Starting MCP Platform Watcher loop (every {args.interval_minutes} minutes)...")
        try:
            while True:
                run_watcher_cycle(registry, auto_create_issue=args.auto_create_issues)
                time.sleep(interval_secs)
        except KeyboardInterrupt:
            print("\n🛑 Watcher stopped by user.")
            return 0

    # Default to single check
    run_watcher_cycle(registry, auto_create_issue=args.auto_create_issues)
    return 0


if __name__ == "__main__":
    sys.exit(main())

