"""scripts/ops/health_check.py — fail-closed endpoint health checker (issue #339 AC3).

Exit codes: 0 = healthy; 1 = ANY degradation (non-2xx, timeout, bad payload,
connection refusal). Fail-closed doctrine: a skipped or unknown state is a
FAILURE, never a pass — matching the repo's health-check contract.

Usage:
    python scripts/ops/health_check.py --url https://.../healthz [--timeout 8]
    python scripts/ops/health_check.py --url ... --expect-keys status --expect-values ok
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def check(url: str, *, timeout: float = 8.0, expect_keys: list[str] | None = None,
          expect_values: list[str] | None = None) -> tuple[bool, str]:
    """One honest health probe. Returns (healthy, reason)."""
    expect_keys = expect_keys or []
    expect_values = expect_values or []
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read(65536)
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} - degraded upstream (fail-closed)"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"transport failure: {exc} (fail-closed)"
    if status != 200:
        return False, f"HTTP {status} != 200 (fail-closed)"
    # Payload contract: /healthz answers JSON with status:"ok" (gateway OpenAPI).
    try:
        payload: Any = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False, "health payload is not valid JSON (fail-closed)"
    if not isinstance(payload, dict):
        return False, "health payload is not a JSON object (fail-closed)"
    if "status" in payload and payload["status"] != "ok":
        # A 200 that self-reports degradation IS degraded.
        return False, f"payload self-reports degraded status={payload['status']!r} (fail-closed)"
    for key in expect_keys:
        if key not in payload:
            return False, f"expected key '{key}' missing from payload (fail-closed)"
    for key, value in zip(expect_keys, expect_values):
        if value and str(payload.get(key)) != value:
            return False, f"expected {key}={value!r}, got {payload.get(key)!r} (fail-closed)"
    return True, "healthy"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed endpoint health check (issue #339)")
    parser.add_argument("--url", required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--expect-keys", default="", help="comma-separated required payload keys")
    parser.add_argument("--expect-values", default="", help="comma-separated expected values (aligned with keys)")
    args = parser.parse_args(argv)
    keys = [k.strip() for k in args.expect_keys.split(",") if k.strip()]
    values = [v.strip() for v in args.expect_values.split(",") if v.strip()]
    ok, reason = check(args.url, timeout=args.timeout, expect_keys=keys, expect_values=values)
    print(f"{'HEALTHY' if ok else 'DEGRADED'}: {args.url} - {reason}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
