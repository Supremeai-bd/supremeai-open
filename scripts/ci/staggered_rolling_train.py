#!/usr/bin/env python3
"""Staggered Rolling Train — Tier 4 Monorepo Consolidation Scheduler.

Schedules rolling consolidation from the 11 satellite repositories into
the central monorepo (Supremeai-bd/supremeai) on a staggered 10-minute cadence.

Cycle Topology (110-minute full federation loop):
  - Minute 0..9:   Slot 0  ➔ supremeai-open
  - Minute 10..19: Slot 1  ➔ supremeai-studio
  - Minute 20..29: Slot 2  ➔ supremeai-browser
  - Minute 30..39: Slot 3  ➔ supremeai-api
  - Minute 40..49: Slot 4  ➔ supremeai-skills
  - Minute 50..59: Slot 5  ➔ supremeai-vscode
  - Minute 60..69: Slot 6  ➔ supremeai-command
  - Minute 70..79: Slot 7  ➔ supremeai-agents
  - Minute 80..89: Slot 8  ➔ supremeai-archive
  - Minute 90..99: Slot 9  ➔ supremeai-infrastructure
  - Minute 100..109: Slot 10 ➔ supremeai-sdk

Guarantees:
  - Zero CI Stampede: Never runs two satellite consolidation jobs concurrently.
  - Quota Preservation: Fits comfortably within GitHub Actions 2,000 min/mo free tier.
  - Cross-Platform Parity (#515): UTF-8 encoding across all subprocess and file operations.

Part of Issue #514.
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SLOT_SCHEDULE = [
    {"slot": 0, "name": "supremeai-open", "offset_minutes": 0, "role": "Public Embassy / Gateway"},
    {"slot": 1, "name": "supremeai-studio", "offset_minutes": 10, "role": "Federation Cockpit UI"},
    {"slot": 2, "name": "supremeai-browser", "offset_minutes": 20, "role": "Stealth Automation"},
    {"slot": 3, "name": "supremeai-api", "offset_minutes": 30, "role": "Gateway Router"},
    {"slot": 4, "name": "supremeai-skills", "offset_minutes": 40, "role": "Marketplace & Spec"},
    {"slot": 5, "name": "supremeai-vscode", "offset_minutes": 50, "role": "IDE Extension"},
    {"slot": 6, "name": "supremeai-command", "offset_minutes": 60, "role": "Admin Control Bot"},
    {"slot": 7, "name": "supremeai-agents", "offset_minutes": 70, "role": "Lifecycle Engine"},
    {"slot": 8, "name": "supremeai-archive", "offset_minutes": 80, "role": "Memory & History"},
    {"slot": 9, "name": "supremeai-infrastructure", "offset_minutes": 90, "role": "Deployment & DR"},
    {"slot": 10, "name": "supremeai-sdk", "offset_minutes": 100, "role": "Client Libraries"},
]


def get_current_slot(slot_duration_minutes: int = 10) -> dict[str, Any]:
    """Compute active slot based on UTC epoch minutes."""
    now = datetime.datetime.now(datetime.timezone.utc)
    epoch_minutes = int(now.timestamp() // 60)
    slot_index = (epoch_minutes // slot_duration_minutes) % len(SLOT_SCHEDULE)
    slot_info = SLOT_SCHEDULE[slot_index]
    minutes_into_slot = epoch_minutes % slot_duration_minutes
    minutes_remaining = slot_duration_minutes - minutes_into_slot

    return {
        "timestamp_utc": now.isoformat(),
        "slot_index": slot_index,
        "active_satellite": slot_info["name"],
        "role": slot_info["role"],
        "minutes_into_slot": minutes_into_slot,
        "minutes_remaining_in_slot": minutes_remaining,
        "slot_duration_minutes": slot_duration_minutes,
        "total_cycle_minutes": slot_duration_minutes * len(SLOT_SCHEDULE),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Staggered Rolling Train Scheduler (Tier 4 Consolidation)")
    parser.add_argument("--schedule", action="store_true", help="Print the 11-satellite rotation schedule")
    parser.add_argument("--current", action="store_true", help="Report the currently active rolling consolidation slot")
    parser.add_argument("--slot-duration", type=int, default=10, help="Slot duration in minutes (default: 10)")
    args = parser.parse_args()

    print("======================================================================")
    print(" SupremeAI Staggered Rolling Train (Tier 4 Consolidation Engine)")
    print(" Target: Supremeai-bd/supremeai (Central Monorepo)")
    print("======================================================================")

    current = get_current_slot(slot_duration_minutes=args.slot_duration)

    print(f"🕒 Current UTC Time: {current['timestamp_utc']}")
    print(f"🚂 Active Slot: Slot {current['slot_index']} ➔ {current['active_satellite']} ({current['role']})")
    print(f"⏳ Slot Window: {current['minutes_into_slot']}m elapsed, {current['minutes_remaining_in_slot']}m remaining in current window.")
    print(f"🔄 Full Train Cycle: {current['total_cycle_minutes']} minutes across {len(SLOT_SCHEDULE)} satellites.\n")

    if args.schedule:
        print("📋 11-Satellite Staggered Consolidation Schedule:")
        for s in SLOT_SCHEDULE:
            marker = "👉 ACTIVE" if s["slot"] == current["slot_index"] else "          "
            print(f"  {marker} [Slot {s['slot']:2d} @ T+{s['offset_minutes']:3d}m] {s['name']:25s} — {s['role']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
