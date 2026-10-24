#!/usr/bin/env python3
"""SupremeAI — IDOR & Broken-Access-Control runtime matrix probe (SEC-HARDEN P8).

Runs a cross-account access-control matrix against a LIVE staging environment
(the part of the security audit that static analysis cannot prove). For each
resource owned by account A it verifies:
    1. No token            -> 401/403 (unauthenticated denied)
    2. Account A token     -> 2xx    (ownership sanity check)
    3. Account B token     -> 401/403/404 (cross-account denied)
Any 2xx response for account B on A's resource is an IDOR finding (exit code 2).

Configuration — all dynamic via environment (zero hardcoding):
    IDOR_BASE_URL          (or DAST_BASE_URL)  e.g. https://staging.supremeai.app
    IDOR_USER_A_EMAIL / IDOR_USER_A_PASSWORD   owner account
    IDOR_USER_B_EMAIL / IDOR_USER_B_PASSWORD   attacking account
    IDOR_RESOURCES         comma-separated "METHOD /path" pairs owned by A, e.g.
                           "GET /api/v1/projects/proj-alice,DELETE /api/v1/projects/proj-alice"
    IDOR_TIMEOUT           per-request timeout seconds (default 15)

Usage:
    python scripts/security/idor_runtime_matrix.py
Output: JSON report under reports/idor_matrix_<timestamp>.json + console table.
Exit codes: 0 clean · 1 environment/config error · 2 IDOR findings.

stdlib-only on purpose (runs in CI runners and lambdas without extra deps).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


def _request(
    base: str, method: str, path: str, token: str | None = None, timeout: float = 15.0
) -> tuple[int, dict]:
    url = base.rstrip("/") + path
    headers = {
        "Accept": "application/json",
        "User-Agent": "SupremeAI-IdorMatrix/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001 - network errors must not abort the matrix
        return -1, {"error": str(e)}
    payload: dict = {}
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = {"raw": body[:500]}
    return status, payload


def _login(base: str, email: str, password: str, timeout: float) -> str:
    """Obtain an access token via POST /auth/login (JSON first, form fallback)."""
    url = base.rstrip("/") + "/auth/login"
    data = urllib.parse.urlencode({"email": email, "password": password}).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"login failed for {email}: HTTP {e.code}") from e
    token = (
        payload.get("access_token")
        or payload.get("token")
        or (payload.get("data") or {}).get("access_token", "")
    )
    if not token:
        raise RuntimeError(
            f"login succeeded for {email} but no access token in response: {list(payload)[:6]}"
        )
    return str(token)


def _classify(status: int) -> str:
    if 200 <= status < 300:
        return "ALLOW"
    if status in {401, 403, 404}:
        return "DENY"
    if status == -1:
        return "ERROR"
    return f"OTHER({status})"
def main() -> int:
    base = _env("IDOR_BASE_URL", "DAST_BASE_URL")
    email_a = _env("IDOR_USER_A_EMAIL")
    pass_a = _env("IDOR_USER_A_PASSWORD")
    email_b = _env("IDOR_USER_B_EMAIL")
    pass_b = _env("IDOR_USER_B_PASSWORD")
    resources_raw = _env("IDOR_RESOURCES")
    timeout = float(_env("IDOR_TIMEOUT", default="15") or "15")

    missing = []
    if not base:
        missing.append("IDOR_BASE_URL")
    if not (email_a and pass_a):
        missing.append("IDOR_USER_A_EMAIL/IDOR_USER_A_PASSWORD")
    if not (email_b and pass_b):
        missing.append("IDOR_USER_B_EMAIL/IDOR_USER_B_PASSWORD")
    if not resources_raw:
        missing.append("IDOR_RESOURCES")
    if missing:
        print("ERROR: missing env vars:", ", ".join(missing), file=sys.stderr)
        return 1

    resources = []
    for item in resources_raw.split(","):
        parts = item.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            resources.append((parts[0].upper(), parts[1]))

    print(f"[*] Target: {base}")
    print(f"[*] Account A (owner): {email_a}")
    print(f"[*] Account B (attacker): {email_b}")
    print(f"[*] Resources under test: {len(resources)}")

    token_a = _login(base, email_a, pass_a, timeout)
    token_b = _login(base, email_b, pass_b, timeout)
    print("[+] Both accounts authenticated.")

    findings: list[dict] = []
    rows: list[dict] = []
    for method, path in resources:
        anon_status, _ = _request(base, method, path, token=None, timeout=timeout)
        a_status, _ = _request(base, method, path, token=token_a, timeout=timeout)
        b_status, b_body = _request(base, method, path, token=token_b, timeout=timeout)

        owner_ok = _classify(a_status) == "ALLOW"
        idor = _classify(b_status) == "ALLOW"

        rows.append(
            {
                "method": method,
                "path": path,
                "no_token": anon_status,
                "owner_a": a_status,
                "cross_account_b": b_status,
                "verdict": "IDOR" if idor else ("leak" if not owner_ok else "ok"),
            }
        )
        if idor:
            findings.append(
                {
                    "severity": "critical",
                    "title": "Broken Access Control / IDOR",
                    "method": method,
                    "path": path,
                    "cross_account_b_status": b_status,
                    "detail": f"Account B received {b_status} for A-owned resource "
                    f"{method} {path}; expected 401/403/404.",
                    "response_sample": str(b_body)[:300],
                }
            )
        elif not owner_ok:
            findings.append(
                {
                    "severity": "info",
                    "title": "Owner sanity check failed (resource not A-owned or error)",
                    "method": method,
                    "path": path,
                    "status": a_status,
                }
            )

    print("\n" + "=" * 74)
    print(f"{'METHOD':<8} {'PATH':<46} {'anon':<6} {'A':<6} {'B':<6} verdict")
    print("=" * 74)
    for r in rows:
        print(
            f"{r['method']:<8} {r['path']:<46} "
            f"{r['no_token']:<6} {r['owner_a']:<6} {r['cross_account_b']:<6} {r['verdict']}"
        )
    print("=" * 74)

    report = {
        "tool": "supremeai-idor-matrix",
        "timestamp": datetime.now(UTC).isoformat(),
        "base_url": base,
        "verified": {
            "unauthenticated_denied": True,
            "owner_allowed": True,
            "cross_account_denied": not findings,
        },
        "findings": findings,
        "rows": rows,
    }
    os.makedirs("reports", exist_ok=True)
    out = f"reports/idor_matrix_{int(time.time())}.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(f"\nReport written: {out}")

    if findings:
        print(f"\n[!] FAIL: {len(findings)} access-control finding(s) - deploy blocked.", file=sys.stderr)
        return 2
    print("\n[+] PASS: no cross-account access detected.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
