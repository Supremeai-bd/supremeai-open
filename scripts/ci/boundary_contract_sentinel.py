#!/usr/bin/env python3
"""boundary_contract_sentinel.py — live-edge boundary contract sentinel (D3 of #1819/#1835/#1874).

The measured failure class (#1819, exposure window ~1.5 h on 2026-10-27/28):
merged security remediations stayed un-deployed at the public edge while the
health plane reported nothing incident-grade — and after recovery, provider
snapshots kept reporting the stale failure (D4 polarity evidence, #1874).
The #1819 probe table was executed three times by hand; this sentinel makes
it a standing, wolf-proof check.

Contract under probe (the merged #1728/#1729 edge, live-verified 10/10 at
2026-10-28T01:11Z per bridge-20261028-gateway-drift-closed.md; extended to
12/12 against the edge serving the #1904/#1908 build at 2026-10-28T03:5xZ —
the redaction class the first ten probes caught live is now guarded end-to-end):
  1. GET /                     -> exactly {status, service_name, version, chat_ready}
  2. HEAD /                    -> 200
  3. OPTIONS / preflight       -> 200/204 + ACAO echo for an ALLOWLISTED origin
                                  (fail-closed 400 for foreign origins is a PASS,
                                  not drift — allow_credentials=true, no wildcard)
  4-6. GET /healthz|/api/health|/v1/health -> 5-field liveness, zero operator fields
  7-8. security headers on / and on a 404  -> all six (CSP may ship as the
                                  Report-Only variant per #1728 AC3 phase 1)
  9-10. GET /internal/status + /webhook/scout/status unauth -> 401/403
  11. GET /openapi.json        -> route inventory NOT served unauth (#1901/#1904:
                                  404 via openapi_url=None; 401/403 operator gate
                                  equally accepted — class intent, not shape)
  12. GET /readyz              -> redacted readiness (#1902/#1908): 200 is exactly
                                  {status, chat_ready, timestamp}; 503 adds one
                                  generic reason; body must carry zero operator
                                  fields AND zero stealth/infisical markers

Wolf-proof probe methodology (#1874 lessons — a sentinel that cries wolf gets
ignored, which is how the original drift stayed silent):
  a. CSP lookup accepts BOTH the enforced and the Report-Only header names,
     and header lookups are case-insensitive (HTTP headers are; dicts are not).
  b. CORS preflight is only preflight-shaped with Origin +
     Access-Control-Request-Method from an allowlisted origin; a bare OPTIONS
     405 (routing) and a foreign-origin 400 (fail-closed) are both contract.

Modes:
  --self-test                hermetic detector proof: local fixture servers for
                             the pre-fix and post-fix edge; asserts miss=0 AND
                             false-positive=0. No network. (roster mode)
  --base-url URL             live probe against the served edge (default: the
                             README SSOT gateway). Report-only by default.
  --strict                   exit 1 on drift (ops/cron lane; report-only exits 0
                             with the verdict so a live probe never reds a gate
                             on a transient network condition).

Exit codes: 0 = contract OK (or self-test pass), 1 = drift (strict/live-declared),
            2 = gateway unreachable (honest skip — never reported as pass).

Zero credentials, read-only GET/HEAD/OPTIONS, no browser, no production mutation.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "https://supremeai-api-ulw0.onrender.com"  # README SSOT line ~136
ALLOWLISTED_ORIGIN = "https://supremeai-studio.pages.dev"  # gateway/service/app.py _default_cors
FOREIGN_ORIGIN = "https://recon.example.invalid"

# The six baseline headers (#1728) — CSP accepts the Report-Only variant in
# phase 1; the enforced name is equally accepted for the future flip.
SECURITY_HEADERS: dict[str, tuple[str, ...]] = {
    "hsts": ("strict-transport-security",),
    "x-content-type-options": ("x-content-type-options",),
    "x-frame-options": ("x-frame-options",),
    "csp": ("content-security-policy", "content-security-policy-report-only"),
    "referrer-policy": ("referrer-policy",),
    "permissions-policy": ("permissions-policy",),
}

# Operator-only field SSOT (gateway/service/status_publication.py — stdlib-only,
# import-safe without fastapi; satellite fallback mirrors the test-suite layout).
try:
    sys.path.insert(0, str(REPO_ROOT / "gateway" / "service"))
    from status_publication import OPERATOR_ONLY_FIELDS  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001 - sentinel must degrade to its pinned copy, not crash
    OPERATOR_ONLY_FIELDS = (
        "total_keys", "total_healthy_keys", "stealth_priority1_configured",
        "stealth_dns", "web_sessions_active", "web_session_status",
        "webhook_scout", "telegram_webhook_configured", "active_providers",
    )

LIVENESS_FIELDS = {"status", "service_name", "version", "chat_ready", "timestamp"}
ROOT_FIELDS = {"status", "service_name", "version", "chat_ready"}
# #1902/#1908 redaction contract: 200 ships exactly these three; 503 adds one
# generic `reason`. Anything else (stealth posture, env-var names, store names)
# is the leak class the marker scan below flags.
READINESS_FIELDS = {"status", "chat_ready", "timestamp"}
# Body markers that re-introduce the #1902 posture leak even through a "reason"
# string (case-insensitive scan of the raw body).
READINESS_LEAK_MARKERS = ("stealth", "infisical")


def _get(base_url: str, path: str, method: str = "GET", headers: dict | None = None,
         timeout: float = 15.0):
    """Read-only HTTP probe returning (status, case-insensitive headers, body)."""
    req = urllib.request.Request(base_url.rstrip("/") + path, method=method)
    req.add_header("user-agent", "supremeai-boundary-sentinel/1.0 (read-only)")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — read-only probe against repo-local base_url; audited #2081
            body = resp.read().decode("utf-8", "replace")
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if e.fp else ""
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, body


def _missing_headers(h: dict) -> list[str]:
    """Case-insensitive lookup (wolf-proof lesson a, enforced at the point of
    use — callers may pass raw HTTPMessage-derived dicts in any casing)."""
    h_low = {k.lower(): v for k, v in h.items()}
    return [k for k, names in SECURITY_HEADERS.items() if not any(n in h_low for n in names)]


def run_probes(base_url: str, timeout: float = 15.0) -> list[dict]:
    """The executable #1819 table. Each result: probe/status/observed/pass."""
    results: list[dict] = []

    def probe(name: str, observed: dict, ok: bool) -> None:
        results.append({"probe": name, "observed": observed, "pass": bool(ok)})

    # 1. GET / — exactly the four consumer fields (#1729)
    s, h, b = _get(base_url, "/", timeout=timeout)
    try:
        fields = set(json.loads(b).keys())
    except Exception:  # noqa: BLE001 - non-JSON root is drift evidence, not a crash
        fields = {"<non-json>"}
    probe("GET / 4-field root", {"status": s, "fields": sorted(fields)},
          s == 200 and fields == ROOT_FIELDS)

    # 2. HEAD / — GET+HEAD declared (#1728)
    s2, _, _ = _get(base_url, "/", method="HEAD", timeout=timeout)
    probe("HEAD / 200", {"status": s2}, s2 == 200)

    # 3. OPTIONS / preflight from an allowlisted origin (#1729 class, wolf-proof b)
    s3, h3, _ = _get(base_url, "/", method="OPTIONS", timeout=timeout, headers={
        "Origin": ALLOWLISTED_ORIGIN, "Access-Control-Request-Method": "GET"})
    acao = h3.get("access-control-allow-origin")
    probe("OPTIONS / preflight (allowlisted origin)",
          {"status": s3, "acao": acao},
          s3 in (200, 204) and acao == ALLOWLISTED_ORIGIN)

    # 4-6. liveness probes — 5-field redacted payload, zero operator fields (#1729)
    for path in ("/healthz", "/api/health", "/v1/health"):
        s4, _, b4 = _get(base_url, path, timeout=timeout)
        try:
            f4 = set(json.loads(b4).keys())
        except Exception:  # noqa: BLE001
            f4 = {"<non-json>"}
        leaked = sorted(f4 & set(OPERATOR_ONLY_FIELDS))
        probe(f"GET {path} redacted liveness", {"status": s4, "fields": sorted(f4), "leaked": leaked},
              s4 == 200 and f4 == LIVENESS_FIELDS and not leaked)

    # 7-8. six security headers on / and on a 404 (#1728, wolf-proof a)
    s5, h5, _ = _get(base_url, "/", timeout=timeout)
    missing5 = _missing_headers(h5)
    probe("security headers on /", {"status": s5, "missing": missing5}, not missing5)
    s6, h6, _ = _get(base_url, "/definitely-not-a-route-sentinel", timeout=timeout)
    missing6 = _missing_headers(h6)
    probe("security headers on 404", {"status": s6, "missing": missing6},
          s6 == 404 and not missing6)

    # 9-10. operator surfaces fail-closed unauth (#1729)
    s7, _, b7 = _get(base_url, "/internal/status", timeout=timeout)
    probe("GET /internal/status unauth 401/403", {"status": s7, "body": b7[:60]},
          s7 in (401, 403))
    s8, _, b8 = _get(base_url, "/webhook/scout/status", timeout=timeout)
    probe("GET /webhook/scout/status unauth 401/403", {"status": s8, "body": b8[:60]},
          s8 in (401, 403))

    # 11. docs lockdown: machine-readable route inventory not served unauth
    # (#1901, fixed by #1904 openapi_url=None on both apps). Class intent, not
    # shape: 404 (landed contract) or an operator gate (401/403) both PASS; a
    # 200 with paths is the pre-fix leak and is drift evidence.
    s9, _, b9 = _get(base_url, "/openapi.json", timeout=timeout)
    path_count = None
    if s9 == 200:
        try:
            path_count = len(json.loads(b9).get("paths") or {})
        except Exception:  # noqa: BLE001 - non-JSON 200 is still inventory-shaped drift
            path_count = -1
    probe("GET /openapi.json inventory not served unauth",
          {"status": s9, "path_count": path_count},
          s9 in (401, 403, 404))

    # 12. readiness redaction (#1902, fixed by #1908 build_readiness_payload):
    # capability signal only — 200 exactly 3 fields, 503 + generic reason, zero
    # operator fields, zero stealth/infisical markers anywhere in the body
    # (the pre-fix body leaked the stealth_dns block through the 200 path and
    # env/store names through the 503 reason — both are this probe's class).
    s10, _, b10 = _get(base_url, "/readyz", timeout=timeout)
    try:
        f10 = set(json.loads(b10).keys())
    except Exception:  # noqa: BLE001 - non-JSON readiness is drift evidence, not a crash
        f10 = {"<non-json>"}
    expected10 = READINESS_FIELDS if s10 == 200 else READINESS_FIELDS | {"reason"}
    b10_low = b10.lower()
    markers10 = sorted(m for m in READINESS_LEAK_MARKERS if m in b10_low)
    leaked10 = sorted(f10 & set(OPERATOR_ONLY_FIELDS))
    probe("GET /readyz redacted readiness",
          {"status": s10, "fields": sorted(f10), "leaked": leaked10, "markers": markers10},
          s10 in (200, 503) and f10 == expected10 and not leaked10 and not markers10)

    return results


# ── hermetic fixture servers for --self-test (no network, no fastapi) ────────
_CSP_RO = ("content-security-policy-report-only",
           "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")


def _postfix_headers(extra: dict | None = None) -> dict:
    h = {
        "strict-transport-security": "max-age=31536000; includeSubDomains",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "strict-origin-when-cross-origin",
        "permissions-policy": "interest-cohort=()",
        _CSP_RO[0]: _CSP_RO[1],
    }
    h.update(extra or {})
    return h


def _fixture_handler(mode: str):
    """Serve the pre-fix or post-fix edge fixture from the #1819/#1874 tables."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # noqa: D401 - silence request logging
            return

        def _send(self, code: int, payload: dict | str, headers: dict | None = None) -> None:
            body = (payload if isinstance(payload, str) else json.dumps(payload)).encode()
            self.send_response(code)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self):  # noqa: N802 - stdlib naming
            if mode == "post":
                if self.path == "/":
                    self._send(200, {k: "v" for k in sorted(ROOT_FIELDS)}, _postfix_headers())
                elif self.path in ("/healthz", "/api/health", "/v1/health"):
                    self._send(200, {k: "v" for k in sorted(LIVENESS_FIELDS)}, _postfix_headers())
                elif self.path == "/internal/status":
                    self._send(401, {"error": {"message": "operator fleet status requires a valid gateway key"}},
                               _postfix_headers())
                elif self.path == "/webhook/scout/status":
                    self._send(401, {"error": {"message": "webhook scout fleet status requires a valid gateway key"}},
                               _postfix_headers())
                elif self.path == "/openapi.json":
                    self._send(404, {"detail": "Not Found"}, _postfix_headers())
                elif self.path == "/readyz":
                    self._send(200, {k: "v" for k in sorted(READINESS_FIELDS)},
                               _postfix_headers())
                else:
                    self._send(404, {"detail": "Not Found"}, _postfix_headers())
            else:  # pre-fix fixture (the #1819 baseline + the #1901/#1902 residuals)
                leak = {k: "v" for k in sorted(ROOT_FIELDS | set(OPERATOR_ONLY_FIELDS))}
                if self.path in ("/", "/healthz", "/api/health", "/v1/health"):
                    self._send(200, leak)  # 14-field operator payload, no headers
                elif self.path == "/internal/status":
                    self._send(404, {"detail": "Not Found"})
                elif self.path == "/webhook/scout/status":
                    self._send(200, {"status": "unavailable"})
                elif self.path == "/openapi.json":
                    # pre-#1904: the full machine-readable inventory, unauth 200
                    self._send(200, {"openapi": "3.1.0",
                                     "paths": {f"/drift-class-{i}": {"get": {}} for i in range(70)}})
                elif self.path == "/readyz":
                    # pre-#1908: the stealth posture block shipped unauth (#1902)
                    self._send(200, {
                        "status": "ready", "chat_ready": True,
                        "stealth_priority1_configured": True,
                        "stealth_dns": {"ok": True, "host": "relay.example.invalid",
                                        "detail": "resolved"},
                        "timestamp": "2026-10-28T00:00:00Z",
                    })
                else:
                    self._send(404, {"detail": "Not Found"})

        def do_HEAD(self):  # noqa: N802
            if mode == "post" and self.path == "/":
                self._send(200, {}, _postfix_headers())
            else:
                self._send(405, {"detail": "Method Not Allowed"})

        def do_OPTIONS(self):  # noqa: N802
            origin = self.headers.get("Origin")
            if mode == "post" and origin == ALLOWLISTED_ORIGIN:
                self._send(200, {}, _postfix_headers({
                    "access-control-allow-origin": origin,
                    "access-control-allow-methods": "GET, POST, PUT, DELETE, OPTIONS",
                }))
            elif mode == "post":
                self._send(400, {"detail": "Disallowed CORS origin"})
            else:
                self._send(405, {"detail": "Method Not Allowed"})

    return Handler


def _serve(mode: str):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _fixture_handler(mode))
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def self_test() -> list[tuple[str, bool, str]]:
    """Hermetic detector proof: post-fix -> 12/12 (no false positives);
    pre-fix -> every drifted probe flagged (no misses)."""
    cases: list[tuple[str, bool, str]] = []

    srv, url = _serve("post")
    try:
        res = run_probes(url, timeout=5.0)
        failed = [r for r in res if not r["pass"]]
        cases.append(("post-fix fixture: 12/12 pass (false-positive=0)",
                      len(res) == 12 and not failed, json.dumps(failed)[:200]))
    finally:
        srv.shutdown()

    srv2, url2 = _serve("pre")
    try:
        res2 = run_probes(url2, timeout=5.0)
        drifted = sorted(r["probe"] for r in res2 if not r["pass"])
        expected = {"GET / 4-field root", "HEAD / 200", "OPTIONS / preflight (allowlisted origin)",
                    "GET /healthz redacted liveness", "GET /api/health redacted liveness",
                    "GET /v1/health redacted liveness", "security headers on /",
                    "security headers on 404", "GET /internal/status unauth 401/403",
                    "GET /webhook/scout/status unauth 401/403",
                    "GET /openapi.json inventory not served unauth",
                    "GET /readyz redacted readiness"}
        cases.append(("pre-fix fixture: all 12 drifted probes flagged (miss=0)",
                      set(drifted) == expected, json.dumps(drifted)[:300]))
        leaked = any(r["probe"].startswith("GET /healthz") and r["observed"].get("leaked")
                     for r in res2)
        cases.append(("pre-fix fixture: operator-field leak detected on liveness",
                      leaked, "leak not detected"))
        # #1901 residual: the pre-fix inventory exposure must be flagged with
        # its path-count evidence (70-class inventory, not a silent pass).
        openapi_res = next((r for r in res2
                            if r["probe"] == "GET /openapi.json inventory not served unauth"), None)
        cases.append(("pre-fix fixture: openapi inventory exposure flagged with path evidence",
                      bool(openapi_res) and not openapi_res["pass"]
                      and openapi_res["observed"].get("path_count") == 70,
                      json.dumps(openapi_res or {})[:200]))
        # #1902 residual: the pre-fix stealth posture must be flagged twice —
        # by the operator-field intersection AND by the body marker scan.
        readyz_res = next((r for r in res2 if r["probe"] == "GET /readyz redacted readiness"), None)
        cases.append(("pre-fix fixture: readyz stealth posture flagged (fields + markers)",
                      bool(readyz_res) and not readyz_res["pass"]
                      and bool(readyz_res["observed"].get("leaked"))
                      and bool(readyz_res["observed"].get("markers")),
                      json.dumps(readyz_res or {})[:200]))
    finally:
        srv2.shutdown()

    # Wolf-proof lesson (a): header lookups are case-insensitive and CSP is
    # accepted in its Report-Only phase-1 name (#1728 AC3) — and in the
    # enforced name for the future flip.
    mixed_case = {
        "Strict-Transport-Security": "v", "X-Content-Type-Options": "v",
        "X-Frame-Options": "v", "Content-Security-Policy-Report-Only": "v",
        "Referrer-Policy": "v", "Permissions-Policy": "v",
    }
    cases.append(("CSP Report-Only accepted by case-insensitive lookup",
                  not _missing_headers(mixed_case), "CSP-RO lookup failed"))
    enforced_only = dict(mixed_case)
    del enforced_only["Content-Security-Policy-Report-Only"]
    enforced_only["Content-Security-Policy"] = "v"
    cases.append(("enforced CSP name equally accepted (future flip)",
                  not _missing_headers(enforced_only), "enforced CSP lookup failed"))

    # Wolf-proof lesson (b): the preflight probe must be preflight-shaped from
    # the allowlisted origin — pin the constants so a refactor cannot silently
    # turn the probe into a bare-OPTIONS 405 / foreign-origin 400 wolf.
    cases.append(("preflight targets the allowlisted studio origin",
                  ALLOWLISTED_ORIGIN == "https://supremeai-studio.pages.dev"
                  and FOREIGN_ORIGIN != ALLOWLISTED_ORIGIN,
                  f"origin pin drifted: {ALLOWLISTED_ORIGIN}"))

    return cases


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Live-edge boundary contract sentinel (#1819 D3)")
    p.add_argument("--self-test", action="store_true",
                   help="hermetic detector proof against local fixtures (roster mode)")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL,
                   help=f"edge to probe (default: README SSOT {DEFAULT_BASE_URL})")
    p.add_argument("--strict", action="store_true",
                   help="exit 1 on drift (default is report-only: verdict printed, exit 0)")
    p.add_argument("--timeout", type=float, default=15.0)
    args = p.parse_args(argv)

    if args.self_test:
        cases = self_test()
        failed = [c for c in cases if not c[1]]
        for name, ok, ev in cases:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {ev}" if not ok else ""))
        print(f"\n==== {len(cases) - len(failed)}/{len(cases)} self-test cases PASS ====")
        return 1 if failed else 0

    print(f"probing {args.base_url} (mode: {'strict' if args.strict else 'report-only'})")
    try:
        results = run_probes(args.base_url, timeout=args.timeout)
    except Exception as e:  # noqa: BLE001 - unreachable edge is a skip, never a pass
        print(f"SKIP: gateway unreachable ({e.__class__.__name__}: {e})")
        return 2
    failed = [r for r in results if not r["pass"]]
    for r in results:
        mark = "PASS" if r["pass"] else "DRIFT"
        print(f"  [{mark}] {r['probe']}: {json.dumps(r['observed'])[:110]}")
    verdict = f"{len(results) - len(failed)}/{len(results)} boundary probes pass"
    print(f"VERDICT: {verdict}")
    if not failed:
        return 0
    if args.strict:
        print("DRIFT: served edge diverges from the merged contract — file a WO "
              "with this table (tracker class: #1819; redeploy pass criteria: "
              "bridge-20261028-gateway-drift-closed.md)")
        return 1
    print("REPORT-ONLY drift (exit 0) — rerun with --strict for a fail-closed verdict.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
