#!/usr/bin/env python3
"""Scheduled Render recheck automation runner.

Runs idempotently to re-evaluate capacity for Render accounts whose recheck_at <= now().
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from backend.services.render_preflight_service import RenderPreflightService


def main() -> int:
    service = RenderPreflightService()
    role_keys = {
        "core": os.getenv("RENDER_API_KEY_1") or os.getenv("RENDER_API_KEY", ""),
        "worker": os.getenv("RENDER_API_KEY_2", ""),
        "scraper": os.getenv("RENDER_API_KEY_3", ""),
        "mcp": os.getenv("RENDER_API_KEY_4", ""),
    }

    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting scheduled Render recheck scan...")
    refreshed = service.run_scheduled_rechecks(role_keys)
    print(f"Recheck scan completed. Refreshed accounts count: {len(refreshed)}")
    for record in refreshed:
        print(f" - {record.get('account_role')}: status={record.get('status')} recheck_at={record.get('recheck_at')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
