#!/usr/bin/env python3
"""SupremeAI — MCP Tower ↔ Operational Truth DB Bridge (issue #2377, Deliverable 3).

MCP Tower-এর লাইভ fleet-state টুলসকে ডাটাবেসের সাথে যুক্ত করে —
"tower-এ ঘটে, DB-তে সত্য হয়" (Redis = fast-path, Postgres = persistent truth):

  agent_status    (tower read)  → agent_leases upsert (slot, heartbeat, state)
  slot.list       (#48)         → client_slots upsert (verified-slot mirror)
  resource.list + resource.status (tower read) → system_modules upsert (kind=resource)
  agent_heartbeat (tower write) → mirror into agent_leases (mirror-heartbeat mode)

Usage:
    # Tower → DB sync (state pull):
    python scripts/operations/tower_db_bridge.py sync --sqlite data/operational_truth.db

    # Dry-run (tower থেকে পড়ে, DB-তে লেখে না):
    python scripts/operations/tower_db_bridge.py sync --dry-run

    # #48 Verified Slot Architecture — slot state pull → client_slots:
    python scripts/operations/tower_db_bridge.py sync-slots --sqlite data/operational_truth.db

    # Heartbeat mirror — tower-এ ping + DB-তে truth একসাথে:
    python scripts/operations/tower_db_bridge.py mirror-heartbeat \
        --slot agent-3 --name z.ai-1 --issue 2377 \
        --branch agent-arch-foundation/issue-2377-database-operational-truth \
        --sqlite data/operational_truth.db

Tower URL resolution: MCP_TOWER_URL env var → mcp.json (fail-closed,
scripts/agents/mcp_tower_client.py-র একই চুক্তি)।
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "agents"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp_tower_client import McpTowerClient  # noqa: E402
from operational_truth_db import (  # noqa: E402
    connect,
    ensure_schema,
    upsert_rows,
)

# Tower heartbeat TTL contract (agent.tools.ts: online ≤90s, hash TTL)
ONLINE_WINDOW_SECONDS = 90


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


def _iso_plus(seconds: float, base: str | None = None) -> str:
    t = datetime.datetime.fromisoformat(base) if base else datetime.datetime.now(datetime.UTC)
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.UTC)
    return (t + datetime.timedelta(seconds=seconds)).isoformat(timespec="seconds")


def _resolve_tower_url() -> str:
    """mcp_tower_client-এর fail-closed URL resolution চুক্তি মেনে চলে।"""
    import os

    url = os.environ.get("MCP_TOWER_URL", os.environ.get("MCP_SERVER_URL", ""))
    if not url:
        mcp_json = REPO_ROOT / "mcp.json"
        if mcp_json.exists():
            try:
                cfg = json.loads(mcp_json.read_text(encoding="utf-8"))
                url = (
                    cfg.get("mcpServers", {})
                    .get("supremeai-control-tower", {})
                    .get("url", "")
                )
            except (json.JSONDecodeError, OSError):
                url = ""
    if not url:
        raise SystemExit(
            "Tower URL পাওয়া যায়নি — MCP_TOWER_URL env var সেট করুন "
            "(fail-closed, scripts/agents/mcp_tower_client.py চুক্তি)"
        )
    return url.rstrip("/").removesuffix("/sse")


def _tool_text(result: Any) -> str:
    """MCP tool result → text (tower content-block format)।"""
    if isinstance(result, dict):
        if result.get("isError"):
            raise RuntimeError(f"tower tool error: {result}")
        content = result.get("content") or []
        if content and isinstance(content, list):
            return content[0].get("text", "")
    return str(result)


def fetch_tower_state(client: McpTowerClient) -> dict[str, Any]:
    """agent_status + resource.list/resource.status → normalize করা state।"""
    state: dict[str, Any] = {"slots": [], "resources": []}
    raw = _tool_text(client.call_tool("agent_status", {}))
    data = json.loads(raw)
    for slot in data.get("slots", []):
        state["slots"].append(
            {
                "slot_id": slot.get("slot"),
                "agent_name": slot.get("agentId"),
                "role": slot.get("slot", "").rsplit("-", 1)[0] if slot.get("slot") else None,
                "heartbeat_at": slot.get("updatedAt"),
                "expires_at": _iso_plus(ONLINE_WINDOW_SECONDS, slot.get("updatedAt")),
                "state": slot.get("state") or "unknown",
                "source": "mcp-tower",
                "meta": {"source_field": slot.get("source")},
            }
        )
    state["tower_now"] = data.get("now")
    state["ttl_seconds"] = data.get("ttlSeconds")

    # resource.list → প্রতিটি resource-এর status (best-effort — provider না থাকলে
    # status 'unknown' হবে, সেটাও operational truth)
    try:
        resources_raw = _tool_text(client.call_tool("resource.list", {}))
        resources = json.loads(resources_raw)
        if isinstance(resources, dict):
            resources = resources.get("resources", [])
        for res in resources or []:
            res_id = res.get("id") or res.get("resourceId")
            if not res_id:
                continue
            status = None
            try:
                status_raw = _tool_text(client.call_tool("resource.status", {"resourceId": res_id}))
                status = json.loads(status_raw).get("status", "unknown")
            except (RuntimeError, json.JSONDecodeError):
                status = "unknown"
            state["resources"].append(
                {
                    "name": res_id,
                    "kind": "resource",
                    "layer": res_id.split("/")[0] if "/" in res_id else "infra",
                    "status": "active" if status in ("healthy", "ok", "up") else "offline",
                    "meta": {"raw_status": status, **{k: res[k] for k in ("provider", "type") if k in res}},
                }
            )
    except (RuntimeError, json.JSONDecodeError) as exc:
        state["resource_error"] = str(exc)
    return state


def fetch_tower_slots(client: McpTowerClient) -> dict[str, Any]:
    """#48: tower `slot.list` → client_slots row-রূপ (Verified Slot Architecture)।

    Tower-এর client registry (Upstash) লাইভ authorization store; এই ফাংশন
    সেটির credential-bound slot রেকর্ডগুলোকে operational DB-র persistent
    projection-এ মিরর করে (dashboard/forensics)।
    """
    raw = _tool_text(client.call_tool("slot.list", {}))
    data = json.loads(raw)
    slots = data.get("slots", []) if isinstance(data, dict) else []
    normalized: list[dict[str, Any]] = []
    for slot in slots or []:
        slot_id = slot.get("slot_id") or slot.get("id")
        if not slot_id:
            continue
        normalized.append(
            {
                "slot_id": slot_id,
                "slot_name": slot.get("slot_name") or slot.get("name"),
                "tenant_id": slot.get("tenant_id") or slot.get("tenantId") or "tenant_default",
                "role": slot.get("role") or "viewer",
                "status": slot.get("status") or "pending",
                "credential_id": slot.get("credential_id"),
                "provisioned_at": slot.get("provisioned_at") or slot.get("createdAt"),
                "rotated_at": slot.get("rotated_at"),
                "last_verified_at": None,  # bridge sync-এই প্রমাণিত — _write_rows-এ now বসে
                "suspended_reason": slot.get("suspended_reason"),
                "meta": {"source_field": "tower:slot.list"},
            }
        )
    return {"slots": normalized}


def tower_slots_to_rows(state: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Normalize করা tower slot state → upsert-ready row dicts।"""
    now = _now_iso()
    rows = []
    for slot in state.get("slots", []):
        row = dict(slot)
        row["updated_at"] = now
        if not row.get("last_verified_at"):
            row["last_verified_at"] = now
        rows.append(row)
    return {"client_slots": rows}


def tower_to_rows(state: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Normalize করা tower state → upsert-ready row dicts।"""
    now = _now_iso()
    lease_rows = []
    for s in state.get("slots", []):
        row = dict(s)
        row["updated_at"] = now
        row.setdefault("lane", row.get("role"))
        row.setdefault("issue_number", None)
        row.setdefault("branch_name", None)
        lease_rows.append(row)

    module_rows = []
    for r in state.get("resources", []):
        module_rows.append(
            {
                "name": r["name"],
                "kind": "resource",
                "layer": r.get("layer", "infra"),
                "domain_id": None,
                "status": r.get("status", "offline"),
                "owner_lane": None,
                "owning_paths": None,
                "meta": r.get("meta", {}),
                "source_doc": "mcp-tower:resource.status",
                "updated_at": now,
            }
        )
    return {"agent_leases": lease_rows, "system_modules": module_rows}


def _write_rows(
    rows_by_table: dict[str, list[dict[str, Any]]],
    db_url: str | None,
    sqlite_path: str | None,
    ensure: bool,
) -> dict[str, int]:
    conn, flavor = connect(db_url=db_url, sqlite_path=sqlite_path)
    written: dict[str, int] = {}
    try:
        if ensure:
            ensure_schema(conn, flavor)
        for table, rows in rows_by_table.items():
            conflict = (
                ["slot_id"]
                if table in ("agent_leases", "client_slots")
                else ["name"]
            )
            written[table] = upsert_rows(conn, flavor, table, rows, conflict_cols=conflict)
    finally:
        conn.close()
    return written


def _cli() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    sync_p = sub.add_parser(
        "sync", help="Tower agent_status/resource থেকে DB-তে state pull করুন"
    )
    sync_p.add_argument("--db-url", default=None)
    sync_p.add_argument("--sqlite", default=None)
    sync_p.add_argument("--ensure-schema", action="store_true")
    sync_p.add_argument("--dry-run", action="store_true")
    sync_p.add_argument("--verbose", "-v", action="store_true")

    ss = sub.add_parser(
        "sync-slots",
        help="#48: Tower slot.list থেকে client_slots টেবিলে slot state pull করুন",
    )
    ss.add_argument("--db-url", default=None)
    ss.add_argument("--sqlite", default=None)
    ss.add_argument("--ensure-schema", action="store_true")
    ss.add_argument("--dry-run", action="store_true")
    ss.add_argument("--verbose", "-v", action="store_true")

    mh = sub.add_parser(
        "mirror-heartbeat", help="Tower-এ heartbeat পাঠান + DB-তে mirror করুন"
    )
    mh.add_argument("--db-url", default=None)
    mh.add_argument("--sqlite", default=None)
    mh.add_argument("--ensure-schema", action="store_true")
    mh.add_argument("--dry-run", action="store_true")
    mh.add_argument("--verbose", "-v", action="store_true")
    mh.add_argument("--slot", required=True, help="slot id (যেমন agent-3)")
    mh.add_argument("--name", default=None, help="agent label (যেমন z.ai-1)")
    mh.add_argument("--issue", type=int, default=None)
    mh.add_argument("--branch", default=None)

    args = p.parse_args()
    url = _resolve_tower_url()

    client = McpTowerClient(server_url=url, verbose=args.verbose)
    try:
        client.connect()
    except Exception as exc:  # tower unreachable = bridge-এর কাজ করা অসম্ভব
        print(f"[bridge] ✗ tower connect failed: {exc}", file=sys.stderr)
        return 2

    try:
        if args.cmd == "sync":
            state = fetch_tower_state(client)
            rows = tower_to_rows(state)
            if "resource_error" in state:
                print(f"[bridge] ⚠ resource pull partial: {state['resource_error']}", file=sys.stderr)
            print(
                f"[bridge] tower state: {len(rows['agent_leases'])} slots, "
                f"{len(rows['system_modules'])} resources"
            )
            if args.dry_run:
                for table, table_rows in rows.items():
                    for row in table_rows:
                        summary = {
                            k: row.get(k)
                            for k in ("slot_id", "agent_name", "state", "heartbeat_at", "name", "status")
                            if k in row
                        }
                        print(f"  [dry-run] {table}: {summary}")
                print("[bridge] dry-run সম্পন্ন — DB-তে কিছু লেখা হয়নি")
                return 0
            if not (args.db_url or args.sqlite):
                print("[bridge] ✗ write mode-এ --db-url/--sqlite লাগবে", file=sys.stderr)
                return 2
            written = _write_rows(rows, args.db_url, args.sqlite, args.ensure_schema)
            for table, count in written.items():
                print(f"  ✓ {table}: {count} upserted")
            return 0

        if args.cmd == "sync-slots":
            state = fetch_tower_slots(client)
            rows = tower_slots_to_rows(state)
            print(f"[bridge] tower slots: {len(rows['client_slots'])} verified-slot record(s)")
            if args.dry_run:
                for row in rows["client_slots"]:
                    print(
                        f"  [dry-run] client_slots: "
                        f"{ {k: row.get(k) for k in ('slot_id', 'role', 'status', 'credential_id')} }"
                    )
                print("[bridge] dry-run সম্পন্ন — DB-তে কিছু লেখা হয়নি")
                return 0
            if not (args.db_url or args.sqlite):
                print("[bridge] ✗ write mode-এ --db-url/--sqlite লাগবে", file=sys.stderr)
                return 2
            written = _write_rows(rows, args.db_url, args.sqlite, args.ensure_schema)
            for table, count in written.items():
                print(f"  ✓ {table}: {count} upserted")
            return 0

        if args.cmd == "mirror-heartbeat":
            result = client.call_tool("agent_heartbeat", {"slot": args.slot, "agentId": args.name or args.slot})
            print(f"[bridge] tower heartbeat sent: {_tool_text(result)[:120]}")
            now = _now_iso()
            row = {
                "slot_id": args.slot,
                "agent_name": args.name or args.slot,
                "role": args.slot.rsplit("-", 1)[0],
                "lane": args.slot.rsplit("-", 1)[0],
                "issue_number": args.issue,
                "branch_name": args.branch,
                "heartbeat_at": now,
                "expires_at": _iso_plus(ONLINE_WINDOW_SECONDS),
                "state": "online",
                "source": "mcp-tower",
                "meta": {"mirrored_by": "tower_db_bridge"},
                "updated_at": now,
            }
            if args.dry_run:
                print(f"  [dry-run] agent_leases: {row}")
                return 0
            if not (args.db_url or args.sqlite):
                print("[bridge] ✗ write mode-এ --db-url/--sqlite লাগবে", file=sys.stderr)
                return 2
            written = _write_rows({"agent_leases": [row]}, args.db_url, args.sqlite, args.ensure_schema)
            print(f"  ✓ agent_leases: {written['agent_leases']} upserted")
            return 0
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
