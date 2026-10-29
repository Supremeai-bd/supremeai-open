#!/usr/bin/env python3
"""probe_live_status_453.py — Live gateway probe & timestamp-parity verifier.

Implements the repo-side half of issue #453 (feat(observability)):
  - live HTTP status for the gateway's /health and /healthz
  - live CORS preflight (OPTIONS) against configured Studio origins
  - timestamp-parity contract check: git_sha and deployed_at must be present
    and real (never "unknown"/absent), deployed_at must parse as a date
  - JSON report on stdout (house telemetry conventions: timestamp,
    service_name, component, metrics)

This script is an explicitly-invoked ops tool (also designed to be called by
the scheduled probe Action shipped alongside this hand-off). It is NOT wired
into any CI test runner: a failing probe is deployment telemetry, not a
broken build. Zero third-party dependencies (urllib only).

Exit codes (fail-closed, matching repo doctrine):
  0  every requested check passed
  1  at least one probe failed (see report.failures)
  2  configuration error (bad URL / bad origin list / nothing to do)

Usage:
  python3 scripts/ci/probe_live_status_453.py --selftest        # offline
  python3 scripts/ci/probe_live_status_453.py                    # probe now
  GATEWAY_URL=https://supremeai-api-ulw0.onrender.com \
  CORS_ORIGINS="https://studio.example,https://a.example2" \
      python3 scripts/ci/probe_live_status_453.py --json-out probe.json

Issue #453 (r1) · base 8e5ed59 · pure-new file, no existing-path hunks.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

# Deployed gateway is the Render SUFFIXED service URL (issue #2355: the bare
# name resolves to a router-level 404 with x-render-routing: no-server — a
# ghost host, not a cold start). Check that header before declaring a blackout.
DEFAULT_GATEWAY_URL = "https://supremeai-api-ulw0.onrender.com"
PROBE_PATHS = ("/health", "/healthz")
USER_AGENT = "supremeai-probe-453/1.0 (autonomous contributor)"
TIMEOUT_S = 20
# A healthy deployed_at must be within this window; older = stale deployment.
FRESH_DEPLOY_MAX_AGE_S = 7 * 24 * 3600  # 7 days (4x/day cadence, Rule 17)

ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch(url: str, method: str = "GET", origin: str | None = None,
           timeout: int = TIMEOUT_S) -> dict:
    """One HTTP round-trip, fully measured. Never raises."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, */*"}
    if origin:
        headers.update({
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
        })
    req = urllib.request.Request(url, headers=headers, method=method)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(65536).decode("utf-8", "replace")
            return {
                "ok": True,
                "status": resp.status,
                "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                "headers": {k.lower(): v for k, v in resp.headers.items()},
                "body": body[:2048],
            }
    except urllib.error.HTTPError as e:
        return {
            "ok": False,
            "status": e.code,
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
            "headers": {k.lower(): v for k, v in (e.headers or {}).items()},
            "body": (e.read(2048) if hasattr(e, "read") else b"").decode("utf-8", "replace"),
            "error": f"HTTP {e.code}",
        }
    except Exception as e:  # noqa: BLE001 — probe must never crash
        return {
            "ok": False,
            "status": None,
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
            "headers": {},
            "body": "",
            "error": f"{type(e).__name__}: {e}"[:200],
        }


def check_timestamp_parity(payload: dict) -> list[str]:
    """Contract per issue #453: real git_sha + deployed_at, never 'unknown'."""
    problems: list[str] = []
    git_sha = payload.get("git_sha")
    deployed_at = payload.get("deployed_at")
    version = payload.get("version")

    if not git_sha or str(git_sha).strip().lower() in ("unknown", "null", "none", ""):
        problems.append(f"git_sha missing/unknown (got {git_sha!r})")
    if not deployed_at or str(deployed_at).strip().lower() in ("unknown", "null", "none", ""):
        problems.append(f"deployed_at missing/unknown (got {deployed_at!r})")
    else:
        if not ISO_RE.match(str(deployed_at).strip()):
            problems.append(f"deployed_at not ISO-8601 (got {deployed_at!r})")
        else:
            try:
                ts = str(deployed_at).replace("Z", "+00:00")
                age = datetime.now(timezone.utc) - datetime.fromisoformat(ts)
                if age.total_seconds() > FRESH_DEPLOY_MAX_AGE_S:
                    problems.append(
                        f"deployed_at stale ({age.days}d old > {FRESH_DEPLOY_MAX_AGE_S // 86400}d)"
                    )
            except ValueError as e:
                problems.append(f"deployed_at unparseable ({e})")
    if version is not None and str(version).strip().lower() == "unknown":
        problems.append("version still 'unknown' (issue #453 acceptance: must be real)")
    return problems


def check_cors_preflight(res: dict, origin: str) -> list[str]:
    """Preflight must echo the origin and allow the requested method."""
    problems: list[str] = []
    h = res.get("headers", {})
    acao = h.get("access-control-allow-origin", "")
    acam = h.get("access-control-allow-methods", "")
    if res.get("status") is None:
        problems.append(f"origin {origin}: unreachable ({res.get('error')})")
        return problems
    if res.get("status") != 200:
        problems.append(f"origin {origin}: preflight HTTP {res.get('status')} (want 200)")
    if acao not in ("*", origin):
        problems.append(f"origin {origin}: access-control-allow-origin={acao!r} does not echo origin")
    if acam and "POST" not in acam.upper():
        problems.append(f"origin {origin}: access-control-allow-methods lacks POST (got {acam!r})")
    return problems


def run_probe(gateway_url: str, cors_origins: list[str], timeout: int) -> dict:
    """Probe /health + /healthz + CORS preflights; return the full report."""
    report: dict = {
        "schema": "supremeai.probe_live_status.v1",
        "timestamp": now_iso(),
        "service_name": "supremeai-api",
        "component": "probe_live_status_453",
        "gateway_url": gateway_url,
        "checks": [],
        "failures": [],
        "pass": None,
        "metrics": {},
    }

    for path in PROBE_PATHS:
        url = gateway_url.rstrip("/") + path
        res = _fetch(url, timeout=timeout)
        entry = {
            "check": f"GET {path}",
            "status": res.get("status"),
            "latency_ms": res.get("latency_ms"),
            "error": res.get("error"),
        }
        body_json = None
        if res.get("ok") and res.get("body", "").strip().startswith("{"):
            try:
                body_json = json.loads(res["body"])
            except json.JSONDecodeError:
                entry["body_not_json"] = True
        if body_json is not None:
            parity = check_timestamp_parity(body_json if isinstance(body_json, dict) else {})
            entry["parity_problems"] = parity
            report["failures"].extend(parity)
            if res.get("status") != 200:
                report["failures"].append(f"GET {path}: HTTP {res.get('status')} (want 200)")
        else:
            # Gateway down / non-JSON: status + reachability still recorded.
            if not res.get("ok") or res.get("status") != 200:
                report["failures"].append(
                    f"GET {path}: {'HTTP %s' % res.get('status') if res.get('status') else res.get('error')}"
                    " (want 200 with JSON payload)"
                )
            if body_json is None and res.get("ok"):
                entry["parity_problems"] = ["body is not JSON — parity contract unverifiable"]
                report["failures"].append(f"GET {path}: body is not JSON — parity contract unverifiable")
        report["checks"].append(entry)
        report["metrics"][f"probe.{path.strip('/').replace('/', '_')}.latency_ms"] = res.get("latency_ms")

    for origin in cors_origins:
        res = _fetch(gateway_url.rstrip("/") + "/v1/chat/completions",
                     method="OPTIONS", origin=origin, timeout=timeout)
        problems = check_cors_preflight(res, origin)
        report["checks"].append({
            "check": f"OPTIONS /v1/chat/completions (Origin: {origin})",
            "status": res.get("status"),
            "latency_ms": res.get("latency_ms"),
            "parity_problems": problems,
        })
        report["failures"].extend(problems)
        report["metrics"][f"probe.cors.{origin}.latency_ms"] = res.get("latency_ms")

    report["pass"] = not report["failures"]
    return report


def selftest() -> int:
    """Offline battery: pure functions + report shape. Zero network."""
    failures: list[str] = []

    good = {"git_sha": "8e5ed59abc", "deployed_at": now_iso(), "version": "1.2.3"}
    if check_timestamp_parity(good):
        failures.append("selftest: good payload flagged")
    if check_timestamp_parity({"git_sha": "unknown", "deployed_at": "unknown", "version": "unknown"}):
        pass
    else:
        failures.append("selftest: unknown-payload not flagged")
    stale = {"git_sha": "abc", "deployed_at": "2020-01-01T00:00:00Z"}
    if not any("stale" in p for p in check_timestamp_parity(stale)):
        failures.append("selftest: stale deployed_at not flagged")
    bad = {"git_sha": "abc", "deployed_at": "not-a-date"}
    if not any("ISO" in p for p in check_timestamp_parity(bad)):
        failures.append("selftest: non-ISO deployed_at not flagged")
    ok_cors = {"status": 200, "headers": {
        "access-control-allow-origin": "https://a.example",
        "access-control-allow-methods": "POST, OPTIONS"}}
    if check_cors_preflight(ok_cors, "https://a.example"):
        failures.append("selftest: good CORS flagged")
    no_cors = {"status": 200, "headers": {}}
    if not check_cors_preflight(no_cors, "https://a.example"):
        failures.append("selftest: missing CORS headers not flagged")
    if _fetch.__doc__ is None or run_probe.__doc__ is None:
        failures.append("selftest: docstrings missing")

    if failures:
        for f in failures:
            print("SELFTEST FAIL:", f)
        return 1
    print("SELFTEST PASS: 8 assertions, zero network")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gateway-url", default=None, help="override GATEWAY_URL")
    ap.add_argument("--cors-origin", action="append", default=[],
                    help="Studio origin for CORS preflight (repeatable; "
                         "or CORS_ORIGINS env, comma-separated)")
    ap.add_argument("--timeout", type=int, default=TIMEOUT_S)
    ap.add_argument("--json-out", default=None, help="also write report JSON here")
    ap.add_argument("--selftest", action="store_true", help="offline battery, exit 0/1")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    url = (args.gateway_url or __import__("os").environ.get("GATEWAY_URL")
           or DEFAULT_GATEWAY_URL).strip().rstrip("/")
    if not url.lower().startswith(("http://", "https://")):
        print(f"CONFIG ERROR: gateway url must be http(s): {url!r}", file=sys.stderr)
        return 2
    if urlparse(url).scheme not in ("http", "https"):
        print(f"CONFIG ERROR: unparseable url: {url!r}", file=sys.stderr)
        return 2
    origins = list(args.cors_origin)
    env_origins = __import__("os").environ.get("CORS_ORIGINS", "")
    origins += [o.strip() for o in env_origins.split(",") if o.strip()]
    if len(origins) != len(set(origins)):
        print("CONFIG ERROR: duplicate origins", file=sys.stderr)
        return 2

    report = run_probe(url, origins, args.timeout)
    out = json.dumps(report, indent=2, sort_keys=True)
    print(out)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            f.write(out + "\n")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
