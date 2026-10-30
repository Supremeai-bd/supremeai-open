#!/usr/bin/env python3
"""Annotations-census closure gate — permanent tripwire for the U4 false-close class.

Refs #2615 (audit receipt): #2608 was closed `completed` 12 minutes after filing
with zero claim/verdict/comment planes while the live tools/list census still
read 33/151 annotated — the third documented U4 false-close trip (#2584 second,
#2609 Finding 3 the class analysis). The ticket's own arbitration section defines
the tripwire this guard implements:

    "Tripwire for any future close of this lane: **annotations census > 33 on
    live tools/list** (raw JSON-RPC method, not a tools/call) **plus drift on
    the 8 slice-file shas** — both readable zero-credential in under a minute;
    a close without both is this receipt's class by definition."

What this guard does (zero-credential, stdlib-only):
  * Speaks raw JSON-RPC against the public MCP control tower (`POST /mcp`,
    streamable transport) and runs the RAW `tools/list` method — exactly the
    measurement plane the R71/R72 scout used, never a `tools/call` wrapper.
  * Counts `annotations`-carrying tools and compares against the filing-time
    baseline (default 33 — the census frozen into #2586/#2608/#2615).
  * Verdicts a hypothetical/actual `completed` close of an annotations-residual
    ticket: LAND_VERIFIED (census advanced past baseline) vs RESIDUAL_UNLANDED
    (census frozen at baseline) vs REGRESSION (census dropped) — fail-closed.

Verdict table (pure function, exercised offline by --self-test):
  total==0                      -> INSUFFICIENT_EVIDENCE  (exit 2)
  annotated < baseline          -> REGRESSION             (exit 2)
  annotated == baseline         -> RESIDUAL_UNLANDED      (exit 2)
  annotated > baseline          -> LAND_VERIFIED          (exit 0)

Usage:
  python scripts/ci/annotations_census_guard.py --self-test
  python scripts/ci/annotations_census_guard.py --check
  python scripts/ci/annotations_census_guard.py --check --census-json /tmp/tl.json
  python scripts/ci/annotations_census_guard.py --check --baseline 33 --tower-url https://supremeai-mcp-tower.onrender.com

Exit codes: 0 = close justified; 1 = usage/infra error; 2 = fail-closed
(the close is NOT justified by the live plane).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

# Filing-time census frozen by #2586 (R71 landing, PR #2605) and re-derived by
# #2608/#2615: 33 of 151 tools annotated at the moment the residual was filed.
DEFAULT_BASELINE = 33
PROTOCOL_VERSION = "2025-11-25"
REQUEST_TIMEOUT = 30

VERDICT_LAND_VERIFIED = "LAND_VERIFIED"
VERDICT_RESIDUAL_UNLANDED = "RESIDUAL_UNLANDED"
VERDICT_REGRESSION = "REGRESSION"
VERDICT_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

# Mutation-verb heuristic over tool NAMES (#2608's own 21-hit heuristic):
# flags names that plausibly mutate state so the report can say whether the
# residual still concentrates on the sharpest surfaces. Read-plane names
# (health_*, *_status, *_list, bridge.work_queue) must NOT match.
MUTATION_VERB_RE = re.compile(
    r"(kill|rotate|revoke|approve|suspend|activate|update|delete|create|"
    r"push|send|flush|purge|deploy|restart|execute|register|submit)",
    re.IGNORECASE,
)
READ_PLANE_RE = re.compile(
    r"(^health_|_status$|_list$|^list_|^get_|work_queue$|work_order$|"
    r"read_feedback|read_file|read_external|^status$|dashboard)",
    re.IGNORECASE,
)


def classify(census_total: int, census_annotated: int, baseline: int) -> str:
    """Pure verdict core — the contract exercised by --self-test."""
    if census_total <= 0:
        return VERDICT_INSUFFICIENT_EVIDENCE
    if census_annotated < baseline:
        return VERDICT_REGRESSION
    if census_annotated == baseline:
        return VERDICT_RESIDUAL_UNLANDED
    return VERDICT_LAND_VERIFIED


def is_mutation_adjacent(name: str) -> bool:
    """Pure heuristic — mutation-shaped tool name, excluding the read plane."""
    if READ_PLANE_RE.search(name or ""):
        return False
    return bool(MUTATION_VERB_RE.search(name or ""))


def census_from_tools(tools: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure census — count annotated tools and mutation-adjacent residuals."""
    total = len(tools)
    annotated = [t.get("name", "?") for t in tools if t.get("annotations")]
    unannotated = [t.get("name", "?") for t in tools if not t.get("annotations")]
    sharp_residual = sorted(n for n in unannotated if is_mutation_adjacent(n))
    return {
        "total": total,
        "annotated": len(annotated),
        "unannotated": len(unannotated),
        "unannotatedMutationAdjacent": sharp_residual,
    }


def _extract_json_blocks(body: str) -> list[dict[str, Any]]:
    """Pure parse — pull every JSON object out of a JSON or SSE body."""
    blocks: list[dict[str, Any]] = []
    # Streamable HTTP may answer application/json OR text/event-stream
    # (spec 2025-03-26+); handle both without a transport library.
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("data:"):
            stripped = stripped[5:].strip()
        if not stripped or not stripped.startswith("{"):
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            blocks.append(obj)
    return blocks


def _post(url: str, payload: dict[str, Any], session_id: str | None) -> tuple[int, str, str | None]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace"), resp.headers.get("mcp-session-id")
    except urllib.error.HTTPError as exc:  # noqa: PERF203 — explicit fail-closed branch
        return exc.code, str(exc.read().decode("utf-8", errors="replace")), None


def fetch_tools_list(tower_url: str) -> list[dict[str, Any]]:
    """Raw tools/list over streamable HTTP — the measurement plane of #2615."""
    base = tower_url.rstrip("/").removesuffix("/sse").removesuffix("/mcp")
    endpoint = base + "/mcp"
    init_id = str(uuid.uuid4())
    status, body, sid = _post(
        endpoint,
        {
            "jsonrpc": "2.0",
            "id": init_id,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "annotations-census-guard", "version": "1.0.0"},
            },
        },
        None,
    )
    if status != 200:
        raise RuntimeError(f"initialize failed: HTTP {status}")
    _post(endpoint, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, sid)
    list_id = str(uuid.uuid4())
    status, body, _ = _post(endpoint, {"jsonrpc": "2.0", "id": list_id, "method": "tools/list", "params": {}}, sid)
    if status != 200:
        raise RuntimeError(f"tools/list failed: HTTP {status}")
    for obj in _extract_json_blocks(body):
        if obj.get("id") != list_id:
            continue
        if "error" in obj:
            raise RuntimeError(f"tools/list RPC error: {obj['error']}")
        result = obj.get("result") or {}
        tools = result.get("tools")
        if isinstance(tools, list):
            return tools
    raise RuntimeError("no matching tools/list response in body")


def run_check(tower_url: str, baseline: int, census_json: Path | None) -> int:
    if census_json is not None:
        payload = json.loads(census_json.read_text(encoding="utf-8"))
        tools = payload.get("tools") if isinstance(payload, dict) else payload
        source = str(census_json)
    else:
        tools = fetch_tools_list(tower_url)
        source = tower_url
    census = census_from_tools(tools)
    verdict = classify(census["total"], census["annotated"], baseline)
    receipt = {
        "guard": "annotations_census_guard",
        "source": source,
        "baseline": baseline,
        "census": census,
        "verdict": verdict,
        "method": "raw JSON-RPC tools/list (streamable HTTP, zero-credential)",
        "refs": ["#2586", "#2608", "#2615"],
    }
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    if verdict == VERDICT_LAND_VERIFIED:
        print(
            f"OK: annotations census {census['annotated']}/{census['total']} > baseline {baseline} "
            "- a `completed` close of an annotations-residual ticket is justified by the live plane",
            file=sys.stderr,
        )
        return 0
    print(
        f"FAIL-CLOSED: verdict {verdict} (census {census['annotated']}/{census['total']} vs baseline {baseline}) "
        "- do NOT accept a `completed` close of an annotations-residual ticket on this evidence",
        file=sys.stderr,
    )
    return 2


def _self_test() -> int:
    failures: list[str] = []

    def expect(desc: str, actual: Any, wanted: Any) -> None:
        if actual != wanted:
            failures.append(f"{desc}: expected {wanted!r}, got {actual!r}")

    # 1-4: verdict core (includes the live receipts of this filing day)
    expect("land-verified day shape", classify(158, 158, 33), VERDICT_LAND_VERIFIED)
    expect("residual-unlanded #2608 shape", classify(151, 33, 33), VERDICT_RESIDUAL_UNLANDED)
    expect("regression", classify(151, 20, 33), VERDICT_REGRESSION)
    expect("insufficient evidence", classify(0, 0, 33), VERDICT_INSUFFICIENT_EVIDENCE)

    # 5-7: mutation heuristic — sharpening surface flagged, read plane spared
    expect("kill_switch flagged", is_mutation_adjacent("autonomy_kill_switch"), True)
    expect("rotate token flagged", is_mutation_adjacent("tenant_rotate_admin_token"), True)
    expect("read plane spared", is_mutation_adjacent("bridge.work_queue"), False)
    expect("dashboard spared", is_mutation_adjacent("health_dashboard"), False)
    expect("get_ prefix spared", is_mutation_adjacent("get_failed_logs"), False)

    # 8-9: census purity over synthetic payloads
    tools = [
        {"name": "a_read", "annotations": {"readOnlyHint": True}},
        {"name": "b_kill"},
        {"name": "c_work_queue"},
    ]
    c = census_from_tools(tools)
    expect("census total", c["total"], 3)
    expect("census annotated", c["annotated"], 1)
    expect("census sharp residual", c["unannotatedMutationAdjacent"], ["b_kill"])

    # 10-11: dual-shape body parsing (JSON and SSE data lines)
    sse_body = 'event: message\ndata: {"jsonrpc":"2.0","id":"x1","result":{"tools":[{"name":"t1","annotations":{"readOnlyHint":true}},{"name":"t2"}]}}\n\n'
    objs = _extract_json_blocks(sse_body)
    expect("sse blocks", len(objs), 1)
    parsed = census_from_tools(objs[0]["result"]["tools"])
    expect("sse census", (parsed["total"], parsed["annotated"]), (2, 1))
    json_body = '{"jsonrpc":"2.0","id":"x1","result":{"tools":[{"name":"t1"}]}}'
    expect("json blocks", len(_extract_json_blocks(json_body)), 1)

    if failures:
        print(json.dumps({"selfTest": "FAIL", "failures": failures}, indent=2))
        return 2
    print(json.dumps({"selfTest": "PASS", "cases": 11, "class": "U4 false-close tripwire (#2615)"}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true", help="offline verdict-core self-test (no network)")
    parser.add_argument("--check", action="store_true", help="live census verdict against the tower")
    parser.add_argument("--tower-url", default="https://supremeai-mcp-tower.onrender.com")
    parser.add_argument("--baseline", type=int, default=DEFAULT_BASELINE, help="filing-time annotated census")
    parser.add_argument("--census-json", type=Path, default=None, help="pre-fetched tools/list receipt (offline check)")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()
    if args.check:
        try:
            return run_check(args.tower_url, args.baseline, args.census_json)
        except (RuntimeError, urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
            print(json.dumps({"guard": "annotations_census_guard", "error": str(exc)[:200]}), file=sys.stderr)
            return 2
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
