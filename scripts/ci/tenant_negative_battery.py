#!/usr/bin/env python3
"""Tenant isolation negative-test battery (#1343) — bridge-20261027-tenant-dogfood.

Runs the AIQ-075 negative battery against a configured customer-tenant token:
every call that should be forbidden must 403/empty. Results are JSON-serializable
so CI can assert zero cross-tenant successes.

Env:
  SUPREMEAI_API_URL   e.g. https://supremeai-api.onrender.com
  CUSTOMER_TOKEN      admin token of the dogfood CUSTOMER tenant
  ADMIN_ENDPOINT_TOKEN  (optional) default-tenant token used only to verify it is NOT accepted cross-tenant

Exit codes: 0 = zero violations, 1 = any cross-tenant success, 2 = misconfigured.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("SUPREMEAI_API_URL", "").rstrip("/")
CUSTOMER_TOKEN = os.environ.get("CUSTOMER_TOKEN", "")
ADMIN_TOKEN = os.environ.get("ADMIN_ENDPOINT_TOKEN", "")

# (method, path, expect) — expect: 403 | empty
CASES = [
    ("GET", "/api/admin/tenants", "403"),
    ("GET", "/api/admin/clients", "403"),
    ("GET", "/api/admin/policies", "403"),
    ("GET", "/api/admin/agent/status", "403"),
    ("GET", "/api/memory/graph", "empty"),          # cross-tenant memory read -> empty
    ("GET", "/api/memory/search?query=primary", "empty"),
    ("GET", "/api/knowledge/stats", "403"),
    ("POST", "/api/admin/tenant/create", "403"),
]


def call(method: str, path: str, token: str, timeout: int = 30):
    url = f"{BASE}{path}"
    req = urllib.request.Request(url, method=method, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", errors="replace")
    except Exception as err:  # noqa: BLE001
        return 0, str(err)


def main() -> int:
    if not BASE or not CUSTOMER_TOKEN:
        print("misconfigured: set SUPREMEAI_API_URL and CUSTOMER_TOKEN")
        return 2

    violations = []
    report = []
    for method, path, expect in CASES:
        status, body = call(method, path, CUSTOMER_TOKEN)
        if expect == "403":
            ok = status in (401, 403)
        else:  # empty
            ok = status == 200 and body.strip() in ("", "[]", "{}")
        verdict = "PASS" if ok else "VIOLATION"
        report.append({"case": f"{method} {path}", "expect": expect, "status": status, "verdict": verdict})
        if not ok:
            violations.append(report[-1])
        print(f"{verdict:9} {method:4} {path:42} -> {status}")

    if ADMIN_TOKEN:
        # The customer token must not equal/derive from the admin token path:
        status, _ = call("GET", "/api/admin/tenants", ADMIN_TOKEN)
        print(f"control   GET /api/admin/tenants with admin token -> {status} (expected 200)")
        if status != 200:
            print("::warning::admin control call failed — battery evidence may be unreliable")

    print("\n=== TENANT NEGATIVE BATTERY ===")
    print(json.dumps(report, indent=2))
    if violations:
        print(f"FAIL: {len(violations)} cross-tenant violation(s)")
        return 1
    print("PASS: zero cross-tenant successes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
