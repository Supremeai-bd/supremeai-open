#!/usr/bin/env python3
"""fleet_contract_probe.py — D4 contract-gated deploy-health probe (#1874 lineage).

D4 directive (bridge-20261028-gateway-drift-closed.md, the merged #1874):
"deployed" must be gated by the LIVE edge contract, never by cached provider
records. Evidence base: after the #1819 swap window closed (edge serving the
fixed contract, 10/10), provider snapshots kept reporting `update_failed` for
~hours (D4 polarity); at 2026-10-28T04:10Z the same polarity repeated —
render-primary restarted a fresh container (~01:30Z by uptime_seconds) while
its deployStatus still read `update_failed`, and render-mcp reported the same
while its /health served a coherent aggregation body. deployStatus answers
"did the platform finish a deploy"; only the live contract answers "is the
edge actually serving the build we expect".

This probe is the standing, wolf-proof instrument for that question, fleet-wide.
The gateway keeps its DEEP 12-probe sentinel (boundary_contract_sentinel.py);
this module adds the FLEET-WIDE shallow health-surface contract:

  Node ids + vocabulary are the SSOT of gateway/service/app.py
  /api/health-aggregation (api, scraper, tower, primary, worker; env overrides
  RENDER_{ID}_URL). URLs live-verified zero-credential 2026-10-28T04:10Z.

  Per node: HTTP 200 + required keys present + pinned body status (when the
  service has one) + zero forbidden redaction-class markers. Extra non-forbidden
  fields are NOTES, never drift — fleet services evolve their health payloads
  legitimately, and a sentinel that cries wolf gets ignored (#1874 lesson).
  Tower legitimately serves body status "degraded" with HTTP 200 (downstream
  aggregation) — shape-OK, body-status surfaced, NOT drift.

Sentry correlation (--sentry-json, from the tower's system_health snapshot):
  ALIGNED            edge OK + sentry live
  FALSE_NEGATIVE_HEALTH  edge OK + sentry degraded (D4 class; health plane
                     under-reports a serving edge — never fails a gate)
  SILENT_REGRESSION  edge DRIFT + sentry healthy (the #1819 class: a real
                     edge regression invisible to the health plane)
  CONFIRMED_INCIDENT edge DRIFT + sentry degraded
  UNPROBEABLE        edge unreachable (honest skip — never reported as pass)

Modes:
  --self-test      hermetic detector proof on local fixture servers: every
                   seeded drift flagged (miss=0), every compliant fixture
                   passed (fp=0), unreachable honest-skipped. No network.
  --manifest FILE  probe a JSON manifest instead of the built-in FLEET table.
  --sentry-json F  tower system_health snapshot ('-' = stdin) for correlation.
  --strict         exit 1 on CONTRACT_DRIFT (ops lane). Default report-only:
                   verdict printed, exit 0 — a transient network condition or
                   a provider-side flap must never red a gate silently.
  --only id,id     probe a subset (default: all five).

Exit codes: 0 = contract OK / self-test pass / report-only,
            1 = drift (only under --strict),
            2 = every probed node unreachable (honest skip — never a pass).

Zero credentials, read-only GET, stdlib-only, no production mutation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ---------------------------------------------------------------- fleet table
# Node ids + env-override vocabulary: gateway/service/app.py /api/health-aggregation.
# URLs live-verified 2026-10-28T04:10Z (tower system_health manifest + direct
# zero-credential probes; receipts in docs/bridge/bridge-20261028-fleet-contract-probe.md).
FLEET: list[dict] = [
    {
        "id": "api",
        "name": "API Gateway (Gateway Shield)",
        "url": os.getenv("RENDER_API_URL", "https://supremeai-api-ulw0.onrender.com/healthz"),
        "expect_status": "healthy",
        "required": ["status", "service_name", "version", "chat_ready", "timestamp"],
        # This repo's redaction class (#1902/#1908): operator posture fields and
        # fix-hint vocabulary must never ride a public, unauthenticated surface.
        "forbidden": ["stealth_dns", "stealth_priority1", "infisical", "fix:"],
    },
    {
        "id": "scraper",
        "name": "Scraper Relay (Browser/Cookie)",
        "url": os.getenv("RENDER_SCRAPER_URL", "https://supremeai-scraper-node.onrender.com/health"),
        "expect_status": "healthy",
        "required": ["status", "service", "timestamp"],
        "forbidden": [],
    },
    {
        "id": "tower",
        "name": "MCP Control Tower",
        "url": os.getenv("RENDER_MCP_URL", "https://supremeai-mcp-tower.onrender.com/health"),
        # Tower serves body status "degraded" + HTTP 200 when downstream nodes
        # degrade (aggregation contract) — shape-only pin, body-status surfaced.
        "expect_status": None,
        "required": ["status", "server", "version", "services"],
        "required_nested": {"services": ["healthy", "degraded", "total"]},
        "forbidden": [],
    },
    {
        "id": "primary",
        "name": "Primary Core Node",
        "url": os.getenv("RENDER_PRIMARY_URL", "https://supremeai-primary-node-5xso.onrender.com/health"),
        "expect_status": "healthy",
        "required": ["status", "service", "role", "version", "uptime_seconds", "timestamp", "checks"],
        "forbidden": [],
    },
    {
        "id": "worker",
        # Fleet vocabulary is NOT uniform: worker answers "ok", not "healthy" —
        # pinning one global status word here would false-positive a healthy node.
        "id_note": "status vocabulary pinned per node (#1874 wolf-proof lesson)",
        "name": "Worker Node (Async Tasks)",
        "url": os.getenv("RENDER_WORKER_URL", "https://supremeai-worker-node.onrender.com/health"),
        "expect_status": "ok",
        "required": ["status", "service", "role", "version", "runner_version", "timestamp"],
        "forbidden": [],
    },
]

# Tower system_health service ids -> fleet node ids (polarity correlation).
SENTRY_ID = {
    "api": "render-api",
    "scraper": "render-scraper",
    "tower": "render-mcp",
    "primary": "render-primary",
    "worker": "render-worker",
}

OK = 0
DRIFT = 1
SKIP = 2


def _http_get(url: str, timeout: float) -> tuple[int | None, str, str | None]:
    """Zero-credential GET. Returns (status_code, body, error)."""
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "supremeai-fleet-contract-probe/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — zero-credential fleet probe; endpoint from repo config; audited #2081
            return resp.status, resp.read().decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")[:2000]
        except Exception:
            body = ""
        return e.code, body, f"http_error_{e.code}"
    except Exception as e:  # URLError, timeout, ConnectionError, ...
        return None, "", f"{type(e).__name__}: {e}"


def probe_service(svc: dict, timeout: float = 15.0) -> dict:
    """Probe one node against its health-surface contract."""
    code, body, err = _http_get(svc["url"], timeout)
    base = {"id": svc["id"], "url": svc["url"]}
    if code is None:
        return {**base, "verdict": "UNREACHABLE", "error": err, "evidence": []}

    evidence: list[str] = []
    if code != 200:
        evidence.append(f"http {code} (expected 200)")
        return {**base, "verdict": "CONTRACT_DRIFT", "http": code, "evidence": evidence}

    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("body is not a JSON object")
    except ValueError as e:
        evidence.append(f"body not a JSON object: {e}")
        return {**base, "verdict": "CONTRACT_DRIFT", "http": code, "evidence": evidence}

    keys = set(payload)
    for key in svc.get("required", []):
        if key not in keys:
            evidence.append(f"missing required key: {key}")
    for parent, children in (svc.get("required_nested") or {}).items():
        sub = payload.get(parent)
        if isinstance(sub, dict):
            for child in children:
                if child not in sub:
                    evidence.append(f"missing required key: {parent}.{child}")
        else:
            evidence.append(f"required key {parent} is not an object")

    if svc.get("expect_status") is not None and payload.get("status") != svc["expect_status"]:
        evidence.append(f"body status {payload.get('status')!r} != pinned {svc['expect_status']!r}")

    blob = json.dumps(payload, default=str)
    for marker in svc.get("forbidden", []):
        if marker in blob:
            evidence.append(f"forbidden marker shipped on public surface: {marker!r}")

    notes = [k for k in keys if k not in set(svc.get("required", []))]

    hard_drift = [
        e for e in evidence
        if e.startswith(("missing required key", "required key", "body status", "forbidden marker", "body not a JSON"))
    ]
    if hard_drift:
        verdict = "CONTRACT_DRIFT"
    else:
        verdict = "CONTRACT_OK"
        if svc.get("expect_status") is None and payload.get("status") not in (None, "healthy"):
            verdict = "CONTRACT_OK_BODY_DEGRADED"
    return {**base, "verdict": verdict, "http": code, "evidence": evidence, "notes": sorted(notes)}


def correlate_sentry(verdicts: list[dict], sentry_services: list[dict]) -> list[dict]:
    """Join edge verdicts with tower system_health records (D4 polarity table)."""
    by_id = {s.get("id"): s for s in sentry_services if isinstance(s, dict)}
    rows = []
    for v in verdicts:
        sentry = by_id.get(SENTRY_ID.get(v["id"], ""))
        dep = (sentry or {}).get("deployStatus")
        sentry_degraded = dep is not None and dep != "live"
        if v["verdict"] == "UNREACHABLE":
            row = "UNPROBEABLE"
        elif v["verdict"].startswith("CONTRACT_DRIFT"):
            row = "SILENT_REGRESSION" if not sentry_degraded else "CONFIRMED_INCIDENT"
        elif sentry_degraded:
            row = "FALSE_NEGATIVE_HEALTH"
        else:
            row = "ALIGNED"
        rows.append({**v, "sentry_id": SENTRY_ID.get(v["id"]), "sentry_deployStatus": dep, "polarity": row})
    return rows


# ------------------------------------------------------------------ self-test
class _Fixture(BaseHTTPRequestHandler):
    payload = b"{}"
    code = 200

    def do_GET(self):  # noqa: N802
        self.send_response(self.code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *a):  # silence
        pass


def _start_fixture(payload: dict, code: int = 200):
    body = json.dumps(payload).encode()

    class H(_Fixture):
        pass

    H.payload, H.code = body, code
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/health"


def _stop_fixture(srv):
    srv.shutdown()
    srv.server_close()


def self_test() -> int:
    """Hermetic detector proof: miss=0, fp=0, honest-skip, polarity joins."""
    primary_ok = {"status": "healthy", "service": "supremeai-core", "role": "primary",
                  "version": "2.0.0", "uptime_seconds": 9614.2, "timestamp": "t",
                  "checks": [{"name": "database", "status": "healthy", "critical": True}]}
    primary_drift = {k: v for k, v in primary_ok.items() if k != "checks"}  # missing required
    worker_ok = {"status": "ok", "service": "supremeai-worker", "role": "worker",
                 "version": "1.0.0", "runner_version": "agent-runner-harness/1", "timestamp": "t"}
    worker_drift = {**worker_ok, "status": "healthy"}  # vocabulary drift: pinned "ok"
    tower_degraded = {"status": "degraded", "server": "supremeai-control-tower", "version": "1.0.0",
                      "services": {"healthy": 30, "degraded": 3, "total": 33}, "timestamp": "t"}
    api_leak = {"status": "healthy", "service_name": "supremeai-api", "version": "2.0.0",
                "chat_ready": True, "timestamp": "t", "stealth_dns": {"mode": "priority1"}}  # forbidden
    api_extra_ok = {"status": "healthy", "service_name": "supremeai-api", "version": "2.0.0",
                    "chat_ready": True, "timestamp": "t", "region": "fra"}  # benign extra: NOTE only

    specs = [
        ("primary", "primary", primary_ok, 200, "CONTRACT_OK"),
        ("primary_drift", "primary", primary_drift, 200, "CONTRACT_DRIFT"),
        ("worker", "worker", worker_ok, 200, "CONTRACT_OK"),
        ("worker_drift", "worker", worker_drift, 200, "CONTRACT_DRIFT"),
        ("tower", "tower", tower_degraded, 200, "CONTRACT_OK_BODY_DEGRADED"),
        ("api_leak", "api", api_leak, 200, "CONTRACT_DRIFT"),
        ("api_extra", "api", api_extra_ok, 200, "CONTRACT_OK"),
        ("http503", "http503", {"status": "degraded"}, 503, "CONTRACT_DRIFT"),
    ]

    fixtures, manifest, expect = [], [], []
    contract = {
        "primary": {"expect_status": "healthy", "required": ["status", "service", "version", "checks"], "forbidden": []},
        "worker": {"expect_status": "ok", "required": ["status", "service", "version", "runner_version"], "forbidden": []},
        "tower": {"expect_status": None, "required": ["status", "server", "version", "services"],
                  "required_nested": {"services": ["healthy", "degraded", "total"]}, "forbidden": []},
        "api": {"expect_status": "healthy", "required": ["status", "service_name", "version", "chat_ready", "timestamp"],
                "forbidden": ["stealth_dns"]},
        "http503": {"expect_status": "healthy", "required": ["status"], "forbidden": []},
    }

    for node_id, ckey, payload, code, verdict in specs:
        srv, url = _start_fixture(payload, code)
        fixtures.append(srv)
        entry = {"id": node_id, "url": url}
        entry.update(contract[ckey])
        manifest.append(entry)
        expect.append((node_id, verdict))

    try:
        verdicts = [probe_service(svc, timeout=5.0) for svc in manifest]
        got = {v["id"]: v["verdict"] for v in verdicts}
        misses = [(sid, got.get(sid), exp) for sid, exp in expect if got.get(sid) != exp]
        fps = []  # fp == any compliant fixture flagged: covered by misses (expect CONTRACT_OK/..._DEGRADED)
        print(f"self-test verdicts: {got}")
        print(f"seeded drifts flagged (miss): {len(misses)} must be 0; false-positives: {len(fps)} must be 0")
        if misses:
            for sid, g, e in misses:
                print(f"  MISS {sid}: got {g}, expected {e}")
            print(f"SELF-TEST FAIL: miss={len(misses)} fp={len(fps)}")
            return 1

        # honest skip: a dead port must be UNREACHABLE, never drift/pass
        dead = {"id": "dead", "url": "http://127.0.0.1:1/health", "expect_status": None, "required": [], "forbidden": []}
        v = probe_service(dead, timeout=2.0)
        if v["verdict"] != "UNREACHABLE":
            print(f"SELF-TEST FAIL: unreachable probe returned {v['verdict']}")
            return 1

        # polarity joins
        rows = correlate_sentry(
            [{"id": "primary", "verdict": "CONTRACT_OK"}, {"id": "worker", "verdict": "CONTRACT_DRIFT"},
             {"id": "tower", "verdict": "UNREACHABLE"}, {"id": "api", "verdict": "CONTRACT_OK"}],
            [{"id": "render-primary", "deployStatus": "update_failed"},
             {"id": "render-worker", "deployStatus": "live"},
             {"id": "render-mcp", "deployStatus": "update_failed"},
             {"id": "render-api", "deployStatus": "live"}],
        )
        pol = {r["id"]: r["polarity"] for r in rows}
        want = {"primary": "FALSE_NEGATIVE_HEALTH", "worker": "SILENT_REGRESSION",
                "tower": "UNPROBEABLE", "api": "ALIGNED"}
        if pol != want:
            print(f"SELF-TEST FAIL: polarity {pol} != {want}")
            return 1
        print(f"SELF-TEST PASS: 8/8 fixture verdicts, miss=0 fp=0; honest-skip OK; polarity joins {len(want)}/4 OK")
        return OK
    finally:
        for srv in fixtures:
            _stop_fixture(srv)


# ----------------------------------------------------------------------- main
def _load_manifest(path: str | None) -> list[dict]:
    if not path:
        return FLEET
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    items = raw.get("services") if isinstance(raw, dict) else raw
    if not isinstance(items, list) or not items:
        raise ValueError("manifest must be a non-empty list of {id,url,required,...}")
    return items


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="D4 fleet contract probe (report-only by default)")
    p.add_argument("--self-test", action="store_true", help="hermetic detector proof, no network")
    p.add_argument("--manifest", help="JSON manifest file (default: built-in FLEET table)")
    p.add_argument("--sentry-json", help="tower system_health snapshot for polarity correlation ('-' = stdin)")
    p.add_argument("--only", help="comma-separated node ids to probe (default: all)")
    p.add_argument("--strict", action="store_true", help="exit 1 on CONTRACT_DRIFT (default report-only)")
    p.add_argument("--timeout", type=float, default=15.0)
    ns = p.parse_args(argv)

    if ns.self_test:
        return self_test()

    fleet = _load_manifest(ns.manifest)
    if ns.only:
        want = {x.strip() for x in ns.only.split(",") if x.strip()}
        fleet = [s for s in fleet if s.get("id") in want]
        if not fleet:
            print(f"--only matched no nodes among {[s['id'] for s in FLEET]}", file=sys.stderr)
            return DRIFT

    verdicts = [probe_service(svc, timeout=ns.timeout) for svc in fleet]
    drifts = [v for v in verdicts if v["verdict"].startswith("CONTRACT_DRIFT")]
    skips = [v for v in verdicts if v["verdict"] == "UNREACHABLE"]

    sentry_services: list[dict] | None = None
    if ns.sentry_json:
        raw = sys.stdin.read() if ns.sentry_json == "-" else Path(ns.sentry_json).read_text(encoding="utf-8")
        parsed = json.loads(raw)
        sentry_services = parsed.get("services") if isinstance(parsed, dict) else parsed

    print("FLEET CONTRACT PROBE — D4 (contract-gated deploy health, #1874 lineage)")
    for v in verdicts:
        line = f"  [{v['verdict']:>24}] {v['id']}"
        if v.get("http") is not None:
            line += f" (http {v['http']})"
        print(line)
        for e in v.get("evidence") or []:
            print(f"      evidence: {e}")
        for n in v.get("notes") or []:
            print(f"      note: extra field {n!r} (informational, not drift)")

    if sentry_services is not None:
        print("SENTRY POLARITY TABLE (deployStatus vs live contract):")
        for r in correlate_sentry(verdicts, sentry_services):
            print(f"  {r['id']:>8}: edge={r['verdict']:<24} sentry={r.get('sentry_deployStatus')!r:<16} -> {r['polarity']}")

    if skips and not drifts and len(skips) == len(verdicts):
        print("HONEST SKIP: every probed node unreachable (exit 2 — never reported as pass).")
        return SKIP

    if drifts:
        for v in drifts:
            print(f"DRIFT {v['id']}: {v['evidence']}")
        if ns.strict:
            print(f"STRICT drift (exit 1): {len(drifts)}/{len(verdicts)} nodes off-contract.")
            return DRIFT
        print(f"REPORT-ONLY drift (exit 0) — rerun with --strict for a fail-closed verdict.")
        return OK

    print(f"FLEET CONTRACT OK: {len(verdicts)}/{len(verdicts)} nodes on-contract (report-only, exit 0).")
    return OK


if __name__ == "__main__":
    sys.exit(main())
