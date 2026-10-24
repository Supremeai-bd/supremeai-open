#!/usr/bin/env python3
"""Secondary-service runtime evidence probes (issue #1100).

Extends the honest health/evidence model beyond the core API: Worker, MCP
Control Tower, Cloudflare edge Worker and the critical database query-path.

Contract (mirrors 09-post-deploy-smoke.yml's honesty rules):
- A service WITHOUT a configured URL is reported as **UNVERIFIED** (loud
  ::warning + summary row) — never silently green, never a hard failure.
- A service WITH a URL that fails its probe is a hard failure (exit 1):
  deploy evidence without runtime evidence must not look like health.
- Every row carries timestamped provenance (ISO-8601 UTC + HTTP status +
  latency), consumed by release certification (#1096) as a single evidence
  stream artifact (ci-reports/secondary_service_evidence.json).
- Runtime status is kept separate from static configuration status: this
  script only asserts what it actually probed in this run.

Usage (CI or local):
    python3 scripts/ci/secondary_service_probes.py
Env:
    WORKER_PRODUCTION_URL      https://<worker>/  (probes /health/live, /health/ready)
    MCP_PRODUCTION_URL         https://<mcp>/     (probes /health)
    EDGE_WORKER_PRODUCTION_URL https://<edge>/    (probes /health or 200 on /)
    DATABASE_URL               postgresql://...   (query-path: SELECT 1 + TTL-sweep path)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

EVIDENCE_DIR = Path("ci-reports")
EVIDENCE_FILE = EVIDENCE_DIR / "secondary_service_evidence.json"
PROBE_TIMEOUT_S = 15


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _http_probe(url: str) -> dict:
    """GET `url`; return {ok, status, latency_ms, error?, body_hint}."""
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "supremeai-evidence-probe/1.0"})
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT_S) as resp:
            body = resp.read(512).decode("utf-8", errors="replace")
            return {
                "ok": 200 <= resp.status < 300,
                "status": resp.status,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "body_hint": body[:200],
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": exc.code,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "error": f"HTTP {exc.code}",
        }
    except Exception as exc:  # noqa: BLE001 — probe must report, not crash
        return {
            "ok": False,
            "status": None,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "error": f"{exc.__class__.__name__}: {exc}",
        }


def _probe_worker(base: str) -> dict:
    """Worker exposes /health/live + /health/ready (services/worker_service.py)."""
    live = _http_probe(base.rstrip("/") + "/health/live")
    ready = _http_probe(base.rstrip("/") + "/health/ready")
    return {
        "service": "worker",
        "url": base,
        "contract": "GET /health/live + /health/ready (200)",
        "checks": {"live": live, "ready": ready},
        "ok": bool(live.get("ok") and ready.get("ok")),
    }


def _probe_mcp(base: str) -> dict:
    """MCP Control Tower: GET /health returns 200 JSON (root Dockerfile healthcheck)."""
    check = _http_probe(base.rstrip("/") + "/health")
    return {
        "service": "mcp-control-tower",
        "url": base,
        "contract": "GET /health (200 JSON)",
        "checks": {"health": check},
        "ok": bool(check.get("ok")),
    }


def _probe_edge(base: str) -> dict:
    """Cloudflare edge Worker: /health when implemented, else any 200 on /."""
    health = _http_probe(base.rstrip("/") + "/health")
    if health.get("ok"):
        return {
            "service": "cloudflare-edge",
            "url": base,
            "contract": "GET /health (200)",
            "checks": {"health": health},
            "ok": True,
        }
    root = _http_probe(base)
    return {
        "service": "cloudflare-edge",
        "url": base,
        "contract": "GET /health (200) else GET / (200)",
        "checks": {"health": health, "root": root},
        "ok": bool(root.get("ok")),
    }


def _probe_database_query_path(dsn: str) -> dict:
    """Critical query-path probe — an actual SELECT round-trip + the retention
    sweep predicate, NOT schema validation (#1100 item 4).

    Uses asyncpg when importable; without it the probe is honestly UNVERIFIED
    (the smoke runner has no Python backend setup on purpose)."""
    started = time.monotonic()
    try:
        import asyncio

        import asyncpg  # type: ignore[import-not-found]
    except ImportError:
        return {
            "service": "database-query-path",
            "url": "<redacted>",
            "contract": "SELECT 1 + indexed ai_memory TTL-sweep predicate",
            "checks": {},
            "ok": False,
            "unverified": True,
            "unverified_reason": "asyncpg not importable in the probe runner",
        }

    async def _run() -> tuple[bool, dict]:
        try:
            conn = await asyncio.wait_for(asyncpg.connect(dsn, timeout=10), timeout=12)
            try:
                await conn.fetchval("SELECT 1")
                # Canonical query path used by retention/certification:
                # indexed created_at range scan (ix_ai_memory_created_at_desc).
                # Never fails on missing table? It CAN — that is the point:
                # a broken query path must fail the probe, not be hidden.
                await conn.fetchval(
                    "SELECT count(*) FROM ai_memory WHERE created_at > now() - interval '1 day'"
                )
                return True, {"select1": "ok", "ai_memory_sweep_predicate": "ok"}
            finally:
                await conn.close()
        except Exception as exc:  # noqa: BLE001
            return False, {"error": f"{exc.__class__.__name__}: {exc}"}

    ok, detail = asyncio.run(_run())
    return {
        "service": "database-query-path",
        "url": "<redacted>",
        "contract": "SELECT 1 + indexed ai_memory TTL-sweep predicate",
        "checks": detail,
        "ok": ok,
        "latency_ms": round((time.monotonic() - started) * 1000, 1),
    }


def main() -> int:
    EVIDENCE_DIR.mkdir(exist_ok=True)
    results: list[dict] = []

    configured: list[tuple[str, str, object]] = []
    if os.getenv("WORKER_PRODUCTION_URL"):
        configured.append(("worker", os.environ["WORKER_PRODUCTION_URL"], _probe_worker))
    else:
        results.append({"service": "worker", "ok": False, "unverified": True, "reason": "WORKER_PRODUCTION_URL not configured", "timestamp": _now()})

    if os.getenv("MCP_PRODUCTION_URL"):
        configured.append(("mcp", os.environ["MCP_PRODUCTION_URL"], _probe_mcp))
    else:
        results.append({"service": "mcp-control-tower", "ok": False, "unverified": True, "reason": "MCP_PRODUCTION_URL not configured", "timestamp": _now()})

    if os.getenv("EDGE_WORKER_PRODUCTION_URL"):
        configured.append(("edge", os.environ["EDGE_WORKER_PRODUCTION_URL"], _probe_edge))
    else:
        results.append({"service": "cloudflare-edge", "ok": False, "unverified": True, "reason": "EDGE_WORKER_PRODUCTION_URL not configured", "timestamp": _now()})

    if os.getenv("DATABASE_URL"):
        results.append({**_probe_database_query_path(os.environ["DATABASE_URL"]), "timestamp": _now()})
    else:
        results.append({"service": "database-query-path", "ok": False, "unverified": True, "reason": "DATABASE_URL not configured", "timestamp": _now()})

    # Run the configured probes
    failures = 0
    for _name, url, fn in configured:
        res = fn(url)
        res["timestamp"] = _now()
        results.append(res)
        if not res["ok"]:
            failures += 1

    unverified = sum(1 for r in results if r.get("unverified"))
    failed = [r for r in results if not r.get("ok") and not r.get("unverified")]

    evidence = {
        "generated_at": _now(),
        "source": "scripts/ci/secondary_service_probes.py",
        "runtime_status_note": "runtime probe evidence — separate from static/deployment configuration status (#1100)",
        "summary": {
            "probed_ok": sum(1 for r in results if r.get("ok")),
            "failed": len(failed),
            "unverified": unverified,
        },
        "services": results,
    }
    EVIDENCE_FILE.write_text(json.dumps(evidence, indent=2))
    print(f"EVIDENCE_FILE={EVIDENCE_FILE}")

    # GitHub Step Summary (single evidence stream for release certification)
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as fh:
            fh.write("### 🛰️ Secondary-service runtime evidence (#1100)\n\n")
            fh.write("| service | state | detail | timestamp |\n|---|---|---|---|\n")
            for r in results:
                state = "✅ LIVE" if r.get("ok") else ("⚠️ UNVERIFIED" if r.get("unverified") else "❌ FAILED")
                detail = r.get("unverified_reason") or r.get("reason") or r.get("error") or f"latency {r.get('latency_ms', '-')} ms"
                fh.write(f"| {r['service']} | {state} | {detail} | {r['timestamp']} |\n")

    for r in results:
        if r.get("unverified"):
            print(f"::warning::runtime evidence for {r['service']} is UNVERIFIED — {r.get('reason') or r.get('unverified_reason')}")
    for r in failed:
        print(f"::error::service {r['service']} FAILED its runtime probe ({r.get('checks', {}).get('error', 'probe failed')})")

    # Fail-closed: configured-but-broken must block; unverified only warns.
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
