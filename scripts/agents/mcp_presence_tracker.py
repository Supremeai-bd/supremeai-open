#!/usr/bin/env python3
"""
MCP Auto-Presence Tracking for Connected AI Clients (#3297).

Tracks interactive AI clients (ChatGPT, Claude Desktop, Gemini, Cursor,
Copilot) connected via MCP Control Tower. Makes them visible in the
active agent workspace alongside autonomous Git workers.

Design (AGENT_RULES.md P1 — Simple + Effective):
  - Polls MCP Tower API for connected clients
  - Writes presence to docs/master_docs/MCP_PRESENCE_LEDGER.json
  - Integrates with agent_dashboard.py for unified view
  - Heartbeat: clients must ping every 5 min or marked "stale"

Usage:
    python scripts/agents/mcp_presence_tracker.py --check
    python scripts/agents/mcp_presence_tracker.py --update
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
PRESENCE_FILE = ROOT_DIR / "docs" / "master_docs" / "MCP_PRESENCE_LEDGER.json"
STALE_THRESHOLD_SEC = 300  # 5 minutes


def get_mcp_clients() -> list[dict]:
    """Get connected MCP clients from MCP Tower API."""
    # Try MCP Tower API
    tower_url = os.environ.get("MCP_TOWER_URL", "http://localhost:8080")
    tower_token = os.environ.get("MCP_TOWER_TOKEN", "")
    
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{tower_url}/api/v1/clients",
            headers={"Authorization": f"Bearer {tower_token}"} if tower_token else {},
        )
        import urllib.error
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("clients", [])
    except Exception:
        return []  # Fail-open — no MCP Tower running


def update_presence() -> dict:
    """Update the presence ledger with current MCP client status."""
    clients = get_mcp_clients()
    now = time.time()
    
    ledger = {
        "updated_at": now,
        "updated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "total_clients": len(clients),
        "clients": [],
    }
    
    for c in clients:
        client_info = {
            "client_id": c.get("id", "unknown"),
            "client_type": c.get("type", "unknown"),  # chatgpt, claude, gemini, cursor, copilot
            "name": c.get("name", "unknown"),
            "connected_at": c.get("connected_at", 0),
            "last_ping": c.get("last_ping", 0),
            "status": "active" if (now - c.get("last_ping", 0)) < STALE_THRESHOLD_SEC else "stale",
        }
        ledger["clients"].append(client_info)
    
    # Write ledger
    PRESENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PRESENCE_FILE.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    
    return ledger


def check_presence() -> int:
    """Check presence and return number of active clients."""
    if not PRESENCE_FILE.exists():
        print("No presence ledger found. Run with --update first.")
        return 0
    
    try:
        ledger = json.loads(PRESENCE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("Corrupt presence ledger.")
        return 0
    
    active = sum(1 for c in ledger.get("clients", []) if c.get("status") == "active")
    stale = sum(1 for c in ledger.get("clients", []) if c.get("status") == "stale")
    
    print(f"MCP Presence: {active} active, {stale} stale, {ledger.get('total_clients', 0)} total")
    for c in ledger.get("clients", []):
        status_icon = "🟢" if c.get("status") == "active" else "🟡"
        print(f"  {status_icon} {c.get('name', '?'):<20} type={c.get('client_type', '?'):<10} status={c.get('status')}")
    
    return active


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MCP Presence Tracker (#3297)")
    parser.add_argument("--check", action="store_true", help="Check current presence")
    parser.add_argument("--update", action="store_true", help="Update presence from MCP Tower")
    args = parser.parse_args()
    
    if args.update:
        ledger = update_presence()
        print(f"Updated: {ledger['total_clients']} clients ({sum(1 for c in ledger['clients'] if c['status'] == 'active')} active)")
    else:
        check_presence()
