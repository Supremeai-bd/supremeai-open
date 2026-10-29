#!/usr/bin/env python3
"""
Official MCP Registry Publisher & Preflight Validator (#2358).

Implements Option A of Issue #2358:
- Builds canonical ServerJSON descriptor for SupremeAI Control Tower
  complying with the official schema (https://static.modelcontextprotocol.io/schema/2025-12-11/server.schema.json).
- Implements pre-flight dry-run validation against POST /v0/validate.
- Provides --self-test, --dry-run, and --validate CLI modes.
- Zero mutation against registry by default (probe-first, zero-credential).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict

REGISTRY_BASE = "https://registry.modelcontextprotocol.io"
SCHEMA_URI = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
USER_AGENT = "SupremeAI-Tower-Publisher/1.0.0 (https://github.com/Supremeai-bd/supremeai-open; probe-lane)"

TOWER_SERVER_JSON: Dict[str, Any] = {
    "$schema": SCHEMA_URI,
    "name": "org.supremeai/control-tower",
    "title": "SupremeAI MCP Control Tower",
    "description": "Autonomous multi-agent intelligence and software engineering MCP proxy hub.",
    "version": "1.0.0",
    "websiteUrl": "https://supremeai.org",
    "repository": {
        "url": "https://github.com/Supremeai-bd/supremeai-open",
        "source": "github"
    },
    "remotes": [
        {
            "type": "streamable-http",
            "url": "https://supremeai-mcp-tower.onrender.com/mcp"
        }
    ]
}


def build_server_json() -> Dict[str, Any]:
    """Returns the canonical ServerJSON dictionary."""
    return dict(TOWER_SERVER_JSON)


def validate_server_json_schema(payload: Dict[str, Any]) -> list[str]:
    """Offline schema validation for required fields per official MCP Registry OpenAPI spec."""
    errors = []
    required_fields = ["$schema", "name", "description", "version"]
    for field in required_fields:
        if field not in payload or not payload[field]:
            errors.append(f"Missing required field: '{field}'")

    if "$schema" in payload and "server.schema.json" not in payload["$schema"]:
        errors.append("Invalid $schema URI")

    if "name" in payload and not payload["name"].startswith("org.supremeai/"):
        errors.append("Server name must use domain-prefixed identifier")

    return errors


def validate_remote(server_json: Dict[str, Any], timeout: int = 15) -> Dict[str, Any]:
    """Pre-flight dry-run validation against registry POST /v0/validate."""
    target_url = f"{REGISTRY_BASE}/v0/validate"
    data = json.dumps(server_json).encode("utf-8")
    req = urllib.request.Request(
        target_url,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return {
                "status": resp.status,
                "ok": True,
                "response": json.loads(body) if body else {}
            }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {
            "status": e.code,
            "ok": False,
            "error": body
        }
    except Exception as ex:
        return {
            "status": 0,
            "ok": False,
            "error": str(ex)
        }


def run_self_test() -> int:
    """Run self-tests verifying schema builder, validation, and constants."""
    print("[mcp-registry-publisher] Running self-test...")

    # 1. Builder check
    doc = build_server_json()
    assert doc["name"] == "org.supremeai/control-tower", "Name mismatch"
    assert doc["version"] == "1.0.0", "Version mismatch"
    assert doc["remotes"][0]["type"] == "streamable-http", "Remote type mismatch"

    # 2. Schema check (valid)
    errs = validate_server_json_schema(doc)
    assert not errs, f"Expected clean validation, got: {errs}"

    # 3. Schema check (missing field)
    broken = dict(doc)
    del broken["description"]
    errs2 = validate_server_json_schema(broken)
    assert "Missing required field: 'description'" in errs2, "Failed to catch missing description"

    # 4. Schema check (bad prefix)
    broken_name = dict(doc, name="random-server")
    errs3 = validate_server_json_schema(broken_name)
    assert any("domain-prefixed" in e for e in errs3), "Failed to catch invalid domain prefix"

    print("  PASS schema builder & offline validations (4/4)")
    print("[mcp-registry-publisher] self-test: ALL PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Official MCP Registry Publisher & Preflight Validator")
    parser.add_argument("--self-test", action="store_true", help="Run local offline tests")
    parser.add_argument("--print-json", action="store_true", help="Print canonical ServerJSON descriptor")
    parser.add_argument("--validate", action="store_true", help="Execute remote pre-flight dry-run POST /v0/validate")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    payload = build_server_json()

    if args.print_json:
        print(json.dumps(payload, indent=2))
        return 0

    if args.validate:
        local_errs = validate_server_json_schema(payload)
        if local_errs:
            print(f"Local validation errors: {local_errs}", file=sys.stderr)
            return 1
        print("Calling official MCP registry POST /v0/validate...")
        res = validate_remote(payload)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
