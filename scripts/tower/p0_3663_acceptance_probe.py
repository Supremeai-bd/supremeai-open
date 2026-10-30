#!/usr/bin/env python3
"""P0 #3663 post-deploy acceptance probe — anonymous-session fail-open tripwire.

security(P0) #3663: unauthenticated tower sessions resolve to GLOBAL-ADMIN via
the fail-open default (`role ?? "admin"`, infrastructure/mcp-control-plane/
src/http_server.ts L988/L1020/L1119). The fix itself is OWNER LANE (guest
role-set decision + deploy window; filer directive, corroborated by receipts
#3670/#3672/#3676) — this tool does NOT change auth anywhere. It only makes
the issue's own acceptance criteria machine-checkable so the owner can verify
a redeploy in one command, and any agent can re-assert the exposure state
without re-deriving the anatomy by hand each cron cycle.

Acceptance criteria (verbatim from #3663):
  1. Fresh anonymous session -> assert !ctx.isGlobalAdmin && ctx.role != "admin"
  2. Assert client.list returns isError
  3. Assert tools/list omits autonomy_kill_switch / tenant_create / github_list_secrets

Read-only by construction: the probe may call ONLY initialize,
notifications/initialized, tools/list, client_list, system_summary. Destructive
tools are unreachable — no other tool name is ever sent. No credentials are
read, stored or required (the audited surface is the anonymous session itself).

Usage:
    python3 scripts/tower/p0_3663_acceptance_probe.py              # live tower
    python3 scripts/tower/p0_3663_acceptance_probe.py --json       # machine output
    python3 scripts/tower/p0_3663_acceptance_probe.py --base-url https://staging.example  # staged deploy window
    python3 scripts/tower/p0_3663_acceptance_probe.py --self-test  # offline, no network

Exit codes: 0 = fail-closed (remediated) | 2 = fail-open (exposed, pre-deploy
expected state) | 1 = indeterminate (tower unreachable / observables missing).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
from mcp_tower_client import (  # noqa: E402  (SSOT import, never copy constants)
    MCP_STREAMABLE_PATH,
    PROTOCOL_VERSION_STREAMABLE,
    resolve_mcp_server_url,
)

FALLBACK_PROTOCOL_VERSION = "2024-11-05"
REQUEST_TIMEOUT_S = 30

# The probe's entire call surface. Anything else is refused before the wire.
ALLOWED_TOOLS = frozenset({"tools/list", "client_list", "system_summary"})

# tools/list descriptor substrings whose PRESENCE for an anonymous session is
# the fail-open signature (#3663 criterion 3). Matched case-insensitively on
# the descriptor name so naming drift (autonomy_kill_switch vs kill_switch)
# cannot silently defuse the tripwire.
FORBIDDEN_TOOL_FRAGMENTS = ("kill_switch", "tenant_create", "list_secrets")


class Verdict:
    EXPOSED = "EXPOSED"
    FAIL_CLOSED = "FAIL-CLOSED"
    INDETERMINATE = "INDETERMINATE"


def _post(url: str, payload: dict, session: str | None, timeout: int) -> tuple[dict | None, str, str]:
    """One streamable-HTTP JSON-RPC POST. Returns (jsonrpc-payload, session-id, raw-err)."""
    import requests  # lazy import keeps --self-test dependency-free

    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    if session:
        headers["Mcp-Session-Id"] = session
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — operator tool, report every failure mode
        return None, session or "", f"transport: {exc}"
    sid = r.headers.get("mcp-session-id", session or "")
    text = r.text.strip()
    body = None
    for line in text.splitlines():
        if line.startswith("data:"):  # SSE-framed: find first data line anywhere
            body = line[5:].strip()
            break
    if body is None and text:
        body = text  # plain-JSON transport
    if body is None:
        return None, sid, f"unparseable body (http {r.status_code})"
    try:
        return json.loads(body), sid, ""
    except json.JSONDecodeError:
        return None, sid, f"non-JSON body (http {r.status_code}): {body[:120]}"


def _rpc(url: str, method: str, params: dict | None, session: str | None,
         req_id: int | None, timeout: int, protocol_version: str) -> tuple[dict | None, str, str]:
    payload: dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    if req_id is not None:
        payload["id"] = req_id
    return _post(url, payload, session, timeout)


def open_anonymous_session(url: str, timeout: int) -> tuple[str | None, str, str]:
    """initialize + notifications/initialized. Returns (session_id, protocol_used, err)."""
    for pv in (PROTOCOL_VERSION_STREAMABLE, FALLBACK_PROTOCOL_VERSION):
        init_params = {"protocolVersion": pv, "capabilities": {},
                       "clientInfo": {"name": "p0-3663-acceptance-probe", "version": "1.0"}}
        p, sid, err = _rpc(url, "initialize", init_params, None, 1, timeout, pv)
        if err or p is None or "error" in (p or {}):
            continue  # protocol ladder down
        if not sid:
            return None, pv, "initialize succeeded but no Mcp-Session-Id header (stateless/nonconformant)"
        _rpc(url, "notifications/initialized", None, sid, None, timeout, pv)
        return sid, pv, ""
    return None, "", err or "initialize failed on both protocol revisions"


def call_tool(url: str, session: str, tool: str, arguments: dict | None,
              timeout: int, req_id: int) -> dict:
    """tools/call, allowlist-enforced. Returns the full JSON-RPC payload."""
    if tool not in ALLOWED_TOOLS:
        return {"error": {"code": -32602, "message": f"probe allowlist refuses tool: {tool}"}}
    p, _, err = _rpc(url, "tools/call", {"name": tool, "arguments": arguments or {}},
                     session, req_id, timeout, PROTOCOL_VERSION_STREAMABLE)
    if err:
        return {"error": {"code": -32000, "message": err}}
    return p or {}


def _result_text(p: dict) -> str:
    try:
        return "\n".join(c.get("text", "") for c in p["result"]["content"])
    except (KeyError, TypeError):
        return ""


def _walk(node, key_substrings: tuple[str, ...], out: list) -> None:
    """Depth-first collection of (key, value) whose key mentions any substring."""
    if isinstance(node, dict):
        for k, v in node.items():
            if any(s in str(k).lower() for s in key_substrings):
                out.append((str(k), v))
            _walk(v, key_substrings, out)
    elif isinstance(node, list):
        for item in node:
            _walk(item, key_substrings, out)


def check_identity_role(p: dict) -> tuple[str, str]:
    """Criterion 1: anonymous session must not resolve admin / GLOBAL-ADMIN.

    Own-ctx is only verifiable when a session-scoped identity plane answers
    (whoami/session/ctx/self/identity keys). Infra summaries (byProvider,
    services) list OTHER principals' roles — those cannot prove the session's
    own resolution, so they stay INDETERMINATE unless an admin-shaped identity
    leaks into the anonymous view (which is itself exposure).
    """
    blob = _result_text(p)
    if not blob:
        return Verdict.INDETERMINATE, "system_summary unavailable or empty on this tower build"
    try:
        doc = json.loads(blob)
    except json.JSONDecodeError:
        doc = blob
    if not isinstance(doc, (dict, list)):
        return Verdict.INDETERMINATE, f"summary is not structured: {blob[:120]!r}"
    found: list = []
    _walk(doc, ("role", "globaladmin", "is_admin"), found)
    admin_hits = [(k, v) for k, v in found
                  if (isinstance(v, str) and v.strip().lower() == "admin")
                  or (isinstance(v, bool) and v is True)]
    if admin_hits:
        snippet = "; ".join(f"{k}={v!r}" for k, v in admin_hits[:4])
        return Verdict.EXPOSED, f"elevated identity visible to anonymous session: {snippet}"
    markers: list = []
    _walk(doc, ("session", "ctx", "whoami", "self"), markers)
    if markers:
        snippet = "; ".join(f"{k}={v!r}" for k, v in markers[:4])
        return Verdict.FAIL_CLOSED, f"session-scoped identity plane fail-closed: {snippet}"
    if found:
        snippet = "; ".join(f"{k}={v!r}" for k, v in found[:4])
        return (Verdict.INDETERMINATE,
                f"own ctx not observable (only third-party principals: {snippet})")
    return Verdict.INDETERMINATE, f"no role/globalAdmin observables in summary ({blob[:120]!r})"


DENY_MARKERS = ("forbidden", "default-deny", "requires agent role", "unauthorized",
                "access denied", "requires authentication", "not authorized")


def check_client_list(p: dict) -> tuple[str, str]:
    """Criterion 2: client.list must be isError for an anonymous session.

    Deny responses arrive in three shapes — the JSON-RPC error plane, an
    isError envelope, or plain prose inside the content envelope (observed
    post-redeploy: "Forbidden: tool 'client_list' requires agent role or
    higher (default-deny RBAC)"). All three are fail-closed evidence; only a
    non-empty row set is exposure.
    """
    if "error" in p:
        return Verdict.FAIL_CLOSED, f"JSON-RPC error plane: {p['error'].get('message', '')[:120]}"
    text = _result_text(p)
    low = text.lower()
    if any(m in low for m in DENY_MARKERS):
        return Verdict.FAIL_CLOSED, f"deny prose (fail-closed RBAC): {text[:120]!r}"
    try:
        doc = json.loads(text)
        if isinstance(doc, dict) and doc.get("isError") is True:
            return Verdict.FAIL_CLOSED, "isError=true envelope"
        rows = doc.get("rows", doc.get("clients")) if isinstance(doc, dict) else doc
        n = len(rows) if isinstance(rows, list) else None
    except json.JSONDecodeError:
        n = None
    if n is None:
        return Verdict.INDETERMINATE, f"unrecognized client_list shape: {text[:120]!r}"
    if n > 0:
        return Verdict.EXPOSED, f"anonymous session listed {n} client rows (PII plane open)"
    return Verdict.FAIL_CLOSED, "empty row set for anonymous scope"


def check_tools_list_payload(p: dict) -> tuple[str, str]:
    """Criterion 3: destructive tools must be absent from anonymous tools/list."""
    # tools/list is a TOP-LEVEL JSON-RPC method (MCP spec), so its result rides
    # directly on p["result"], not inside a content envelope. Tolerate both.
    if "error" in p:
        return Verdict.INDETERMINATE, f"tools/list error plane: {p['error'].get('message', '')[:120]}"
    doc = p.get("result")
    if isinstance(doc, dict) and "content" in doc and "tools" not in doc:
        # legacy tools/call envelope — unwrap the text payload
        text = "\n".join(c.get("text", "") for c in doc["content"])
        try:
            doc = json.loads(text)
        except json.JSONDecodeError:
            return Verdict.INDETERMINATE, f"unrecognized tools/list envelope: {text[:120]!r}"
    if doc is None:
        text = _result_text(p)
        try:
            doc = json.loads(text)
        except json.JSONDecodeError:
            return Verdict.INDETERMINATE, f"unrecognized tools/list shape: {text[:120]!r}"
    try:
        tools = doc.get("tools", doc) if isinstance(doc, dict) else doc
        names = [str(t.get("name", "")) for t in tools if isinstance(t, dict)]
    except (AttributeError, TypeError):
        return Verdict.INDETERMINATE, "tools/list result lacks a tools descriptor array"
    hits = sorted({n for n in names if any(f in n.lower() for f in FORBIDDEN_TOOL_FRAGMENTS)})
    if hits:
        return Verdict.EXPOSED, f"destructive surface visible anonymously: {', '.join(hits[:6])}"
    return Verdict.FAIL_CLOSED, f"{len(names)} tools listed, none matches {FORBIDDEN_TOOL_FRAGMENTS}"


def aggregate(verdicts: list[str]) -> tuple[str, int]:
    """Map 3 criterion verdicts to (banner, exit code).

    Root-cause note (r2): the original else-branch fired on ANY non-uniform
    verdict set, so a post-redeploy mixed state (FAIL-CLOSED + INDETERMINATE,
    zero EXPOSED) was mislabeled "FAIL-OPEN STILL LIVE" — a false alarm that
    would have kept the fleet believing the redeploy never happened. Exposure
    is now the ONLY trigger for the fail-open verdict; absence of exposure is
    reported for what it is.

    Exit contract: 0 = 3/3 fail-closed (remediated) | 2 = any EXPOSED (fail
    open) | 3 = no exposure observed but acceptance incomplete (mixed) |
    1 = all INDETERMINATE (zero signal).
    """
    n_exposed = verdicts.count(Verdict.EXPOSED)
    n_fc = verdicts.count(Verdict.FAIL_CLOSED)
    n_ind = verdicts.count(Verdict.INDETERMINATE)
    if n_exposed:
        return (f"P0 #3663 FAIL-OPEN STILL LIVE ({n_exposed}/3 criteria exposed) — "
                "pre-deploy expected state; owner redeploy pending", 2)
    if n_fc == len(verdicts):
        return ("P0 #3663 REMEDIATED on live tower — anonymous sessions fail closed (3/3)", 0)
    if n_ind == len(verdicts):
        return ("P0 #3663 INDETERMINATE — observables unavailable; manual review needed", 1)
    return (f"P0 #3663 NO EXPOSURE OBSERVED — fail-closed signals {n_fc}/3, "
            f"indeterminate {n_ind}/3 (positive redeploy evidence; full 3/3 "
            "acceptance pending observability)", 3)


def run_probe(base_url: str | None, timeout: int) -> dict:
    origin = (base_url or resolve_mcp_server_url()).rstrip("/")
    url = origin + MCP_STREAMABLE_PATH
    out: dict = {"tower": origin, "criteria": {}}
    sid, pv, err = open_anonymous_session(url, timeout)
    if not sid:
        out["error"] = f"session open failed: {err}"
        return out
    out["session"] = {"protocol": pv}
    rid = 10

    p = call_tool(url, sid, "system_summary", {}, timeout, rid); rid += 1
    v, ev = check_identity_role(p)
    out["criteria"]["1_identity_not_admin"] = {"verdict": v, "evidence": ev}

    p = call_tool(url, sid, "client_list", {"scope": "*"}, timeout, rid); rid += 1
    v, ev = check_client_list(p)
    out["criteria"]["2_client_list_is_error"] = {"verdict": v, "evidence": ev}

    p, _, err = _rpc(url, "tools/list", {}, sid, rid, timeout, PROTOCOL_VERSION_STREAMABLE)
    p = p or (call_tool(url, sid, "tools/list", {}, timeout, rid) if err else p)
    v, ev = check_tools_list_payload(p)
    out["criteria"]["3_destructive_tools_hidden"] = {"verdict": v, "evidence": ev}

    verdicts = [c["verdict"] for c in out["criteria"].values()]
    out["banner"], out["exit"] = aggregate(verdicts)
    return out


def _self_test() -> int:
    """Offline classifier assertions — no network, no tower dependency."""
    ok = True

    def expect(cond: bool, label: str) -> None:
        nonlocal ok
        print(("PASS" if cond else "FAIL"), label)
        ok = ok and cond

    mk = lambda txt: {"result": {"content": [{"type": "text", "text": txt}]}}  # noqa: E731

    v, _ = check_identity_role(mk(json.dumps({"role": "admin", "isGlobalAdmin": True})))
    expect(v == Verdict.EXPOSED, "identity: role=admin exposed")
    v, _ = check_identity_role(mk(json.dumps({"session": {"role": "viewer", "isGlobalAdmin": False}})))
    expect(v == Verdict.FAIL_CLOSED, "identity: session-scoped viewer fail-closed")
    v, _ = check_identity_role(mk(json.dumps({"byProvider": [{"role": "core-api"}]})))
    expect(v == Verdict.INDETERMINATE, "identity: third-party roles indeterminate")
    v, _ = check_identity_role(mk("not json at all"))
    expect(v == Verdict.INDETERMINATE, "identity: garbage -> indeterminate")

    v, _ = check_client_list(mk(json.dumps({"rows": [{"id": i} for i in range(88)]})))
    expect(v == Verdict.EXPOSED, "client_list: 88 rows exposed")
    v, _ = check_client_list(mk(json.dumps({"isError": True})))
    expect(v == Verdict.FAIL_CLOSED, "client_list: isError fail-closed")
    v, _ = check_client_list({"error": {"message": "forbidden"}})
    expect(v == Verdict.FAIL_CLOSED, "client_list: JSON-RPC error plane fail-closed")
    v, _ = check_client_list(mk("Forbidden: tool 'client_list' requires agent role or "
                               "higher (default-deny RBAC). Present a valid MCP Bearer token."))
    expect(v == Verdict.FAIL_CLOSED, "client_list: deny prose fail-closed (post-redeploy shape)")

    expect(aggregate([Verdict.FAIL_CLOSED] * 3) == (
        "P0 #3663 REMEDIATED on live tower — anonymous sessions fail closed (3/3)", 0),
        "aggregate: 3x fail-closed -> remediated exit 0")
    expect(aggregate([Verdict.FAIL_CLOSED, Verdict.FAIL_CLOSED, Verdict.INDETERMINATE])[1] == 3,
        "aggregate: mixed no-exposure -> exit 3 (NOT fail-open)")
    expect(aggregate([Verdict.INDETERMINATE] * 3)[1] == 1,
        "aggregate: all indeterminate -> exit 1")
    expect(aggregate([Verdict.EXPOSED, Verdict.FAIL_CLOSED, Verdict.INDETERMINATE])[1] == 2,
        "aggregate: any exposed -> exit 2")

    v, _ = check_tools_list_payload({"result": {"tools": [{"name": "autonomy_kill_switch"},
                                                           {"name": "bridge_submit"}]}})
    expect(v == Verdict.EXPOSED, "tools_list: kill_switch visible exposed (top-level)")
    v, _ = check_tools_list_payload(mk(json.dumps({"tools": [{"name": "autonomy.kill_switch"}]})))
    expect(v == Verdict.EXPOSED, "tools_list: kill_switch visible exposed (envelope)")
    v, _ = check_tools_list_payload({"result": {"tools": [{"name": "bridge_submit"},
                                                          {"name": "client_list"}]}})
    expect(v == Verdict.FAIL_CLOSED, "tools_list: benign set fail-closed")
    v, _ = check_tools_list_payload({"error": {"message": "denied"}})
    expect(v == Verdict.INDETERMINATE, "tools_list: error plane indeterminate")

    # allowlist enforcement
    p = call_tool("offline", "no-session", "autonomy_kill_switch", {}, 1, 99)
    expect("error" in p, "allowlist refuses non-read-only tool call")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="P0 #3663 post-deploy acceptance probe (read-only)")
    ap.add_argument("--base-url", default=os.environ.get("PROBE_TOWER_URL"),
                    help="tower origin override (staged deploy window); default = SSOT resolution")
    ap.add_argument("--timeout", type=int, default=REQUEST_TIMEOUT_S)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--self-test", action="store_true", help="offline classifier assertions")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    out = run_probe(args.base_url, args.timeout)
    if args.json:
        print(json.dumps(out, indent=1, ensure_ascii=False))
    else:
        print(f"tower: {out.get('tower')}")
        if "error" in out:
            print(f"ERROR: {out['error']}")
        for name, c in out.get("criteria", {}).items():
            print(f"  [{c['verdict']:>13}] {name}: {c['evidence']}")
        print(out.get("banner", "no verdict"))
    return int(out.get("exit", 1))


if __name__ == "__main__":
    sys.exit(main())
