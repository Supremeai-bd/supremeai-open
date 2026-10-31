#!/usr/bin/env python3
"""Read-only HTTP probe for SupremeAI Render / Cloudflare / Supabase endpoints.

Usage: python scripts/ci/service_latency_probe.py --url name=https://example/health ...
It never sends credentials and never probes Redis commands directly.
Outputs structured JSON and human-readable latency summary with p95 metrics.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def probe(name: str, url: str, attempts: int, timeout: float) -> dict:
    samples, errors = [], []
    for _ in range(attempts):
        started = time.perf_counter()
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": "supremeai-service-latency-probe/1.0",
                    "Accept": "application/json",
                },
            )
            with urlopen(req, timeout=timeout) as response:
                response.read(512)
                status = response.status
            samples.append(round((time.perf_counter() - started) * 1000, 2))
            if status >= 500:
                errors.append(f"HTTP {status}")
        except (HTTPError, URLError, TimeoutError) as exc:
            errors.append(type(exc).__name__)
    result = {
        "name": name,
        "url": url,
        "attempts": attempts,
        "samples_ms": samples,
        "errors": errors,
    }
    if samples:
        result.update(
            {
                "min_ms": min(samples),
                "avg_ms": round(statistics.mean(samples), 2),
                "p95_ms": sorted(samples)[max(0, int(len(samples) * 0.95) - 1)],
            }
        )
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="SupremeAI Service Latency Probe")
    ap.add_argument(
        "--url",
        action="append",
        help="name=https://host/health (can be repeated)",
    )
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=5.0)
    args = ap.parse_args()

    target_urls = args.url or [
        "primary=https://supremeai-primary-node.onrender.com/health",
        "worker=https://supremeai-worker-node.onrender.com/health",
        "tower=https://supremeai-mcp-tower.onrender.com/",
    ]

    results = []
    for item in target_urls:
        name, sep, url = item.partition("=")
        if not sep or not url.startswith(("https://", "http://")):
            ap.error(f"--url must be name=http(s)://..., got: {item}")
        results.append(probe(name, url, max(1, min(args.attempts, 10)), args.timeout))

    output = {"generated_at": time.time(), "results": results}
    print(json.dumps(output, indent=2))
    return 1 if any(r["errors"] and not r["samples_ms"] for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
