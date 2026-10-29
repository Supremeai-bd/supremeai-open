#!/usr/bin/env python3
"""
MCP Tower Protocol Ceiling & Capability Conformance Probe (#2103).

Implements Option B of Issue #2103:
- Inspects MCP Tower protocol negotiation ceiling across spec revisions (2025-06-18, 2025-11-25, 2026-07-28).
- Snapshots capability matrix (tools, resources, prompts, tasks, elicitation, sampling).
- Provides self-test, local offline validation, and live network probe modes.
- Report-only, passive JSON-RPC 2.0 handshake, zero credentials required.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict

DEFAULT_TOWER_URL = "https://supremeai-mcp-tower.onrender.com/mcp"
TESTED_SPEC_VERSIONS = ["2025-06-18", "2025-11-25", "2026-07-28"]
USER_AGENT = "SupremeAI-MCP-Conformance-Probe/1.0.0"


def build_initialize_payload(protocol_version: str) -> Dict[str, Any]:
    """Build standard MCP JSON-RPC 2.0 initialize request."""
    return {
        "jsonrpc": "2.0",
        "id": f"probe-{protocol_version}",
        "method": "initialize",
        "params": {
            "protocolVersion": protocol_version,
            "capabilities": {
                "roots": {"listChanged": True},
                "sampling": {}
            },
            "clientInfo": {
                "name": "supremeai-conformance-probe",
                "version": "1.0.0"
            }
        }
    }


def analyze_capabilities(capabilities: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze server capability map and identify support/gaps."""
    return {
        "tools": "tools" in capabilities,
        "resources": "resources" in capabilities,
        "prompts": "prompts" in capabilities,
        "tasks": "tasks" in capabilities,
        "elicitation": "elicitation" in capabilities,
        "sampling": "sampling" in capabilities,
        "logging": "logging" in capabilities,
        "completions": "completions" in capabilities,
    }


def probe_version(url: str, version: str, timeout: int = 15) -> Dict[str, Any]:
    """Send initialize handshake offering specific protocolVersion."""
    req_body = json.dumps(build_initialize_payload(version)).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_body = resp.read().decode("utf-8")
            
            # Streamable HTTP MCP transport returns text/event-stream containing SSE message
            json_text = raw_body
            if "data:" in raw_body:
                for line in raw_body.splitlines():
                    if line.startswith("data:"):
                        json_text = line[len("data:"):].strip()
                        break
            
            data = json.loads(json_text)
            result = data.get("result", {})
            echoed_version = result.get("protocolVersion")
            server_info = result.get("serverInfo", {})
            capabilities = result.get("capabilities", {})
            analysis = analyze_capabilities(capabilities)
            session_id = resp.headers.get("Mcp-Session-Id")

            return {
                "offeredVersion": version,
                "echoedVersion": echoed_version,
                "status": resp.status,
                "ok": True,
                "serverInfo": server_info,
                "capabilities": capabilities,
                "capabilityAnalysis": analysis,
                "sessionId": session_id,
            }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {
            "offeredVersion": version,
            "status": e.code,
            "ok": False,
            "error": body
        }
    except Exception as ex:
        return {
            "offeredVersion": version,
            "status": 0,
            "ok": False,
            "error": str(ex)
        }


def run_full_probe(url: str = DEFAULT_TOWER_URL) -> Dict[str, Any]:
    """Execute complete protocol ceiling and capability matrix probe."""
    results = {}
    for ver in TESTED_SPEC_VERSIONS:
        res = probe_version(url, ver)
        results[ver] = res

    # Derive ceiling
    ceiling = None
    if results.get("2026-07-28", {}).get("ok"):
        echoed = results["2026-07-28"].get("echoedVersion")
        ceiling = echoed

    capabilities_snapshot = results.get("2025-11-25", {}).get("capabilityAnalysis") or {}

    return {
        "url": url,
        "negotiatedCeiling": ceiling,
        "probeResults": results,
        "capabilitiesSnapshot": capabilities_snapshot,
    }


def run_self_test() -> int:
    """Run self-tests verifying payload builder and offline analysis logic."""
    print("[mcp-tower-conformance-probe] Running self-test...")

    # 1. Payload structure test
    payload = build_initialize_payload("2026-07-28")
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "initialize"
    assert payload["params"]["protocolVersion"] == "2026-07-28"

    # 2. Capability analysis test
    caps = {
        "tools": {"listChanged": True},
        "resources": {"listChanged": True},
        "prompts": {"listChanged": True}
    }
    analysis = analyze_capabilities(caps)
    assert analysis["tools"] is True
    assert analysis["resources"] is True
    assert analysis["prompts"] is True
    assert analysis["tasks"] is False
    assert analysis["elicitation"] is False
    assert analysis["sampling"] is False

    print("  PASS initialize payload construction (2/2)")
    print("  PASS capability matrix gap analyzer (2/2)")
    print("[mcp-tower-conformance-probe] self-test: ALL PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP Tower Protocol Ceiling & Capability Conformance Probe")
    parser.add_argument("--self-test", action="store_true", help="Run local self-tests")
    parser.add_argument("--url", default=DEFAULT_TOWER_URL, help="Target MCP endpoint URL")
    parser.add_argument("--probe", action="store_true", help="Execute live protocol ceiling and capability probe")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if args.probe:
        print(f"Probing MCP endpoint at {args.url}...")
        report = run_full_probe(args.url)
        print(json.dumps(report, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
