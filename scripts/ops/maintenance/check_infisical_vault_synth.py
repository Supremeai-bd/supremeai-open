#!/usr/bin/env python3
"""Weekly synthetic check: Infisical RAW vault contract (issue #434).

বাংলা: প্রোডাকশন ব্যাকএন্ড v3 RAW API (/api/v3/secrets/raw/...) ব্যবহার করে —
স্ট্যান্ডার্ড v1 listSecrets রুটে vendor blind-index বাগ আছে (404/empty)।
এই চেক প্রমাণ করে: (১) universal-auth লগইন, (২) raw লিস্টিং ≥100 সিক্রেট,
(৩) বুট-ক্রিটিকাল কী raw get-by-key-তে পাওয়া যাচ্ছে। Raw পথ ভাঙলে
ব্যর্থতা — Sep-14 crash-loop-এর আগেই সতর্কতা।

English: read-only weekly guard. Exits 0 only when the LIVE production path
(v3 raw) lists >= 100 prod secrets and serves the boot-critical probe keys.
The v1 standard route's status is reported informationally (documented vendor
bug in #434) — informational only, so the weekly signal stays meaningful.

Usage:
  INFISICAL_CLIENT_ID=... INFISICAL_CLIENT_SECRET=... INFISICAL_PROJECT_ID=... \
      python scripts/maintenance/check_infisical_vault_synth.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

API = "https://app.infisical.com"
RAW_API = f"{API}/api/v3/secrets/raw"
MIN_EXPECTED_SECRETS = 100
# Boot-critical keys required at startup (proven live on the raw path).
PROBE_KEYS = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")


def _login() -> str:
    body = json.dumps({
        "clientId": os.environ.get("INFISICAL_CLIENT_ID", ""),
        "clientSecret": os.environ.get("INFISICAL_CLIENT_SECRET", ""),
    }).encode()
    req = urllib.request.Request(
        f"{API}/api/v1/auth/universal-auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["accessToken"]


def _get_json(url: str, token: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except Exception as exc:  # noqa: BLE001 — transient 5xx retry
            last_exc = exc
            time.sleep(2)
    raise RuntimeError(f"GET {url} failed after retries: {last_exc}")


def main() -> int:
    cid = os.environ.get("INFISICAL_CLIENT_ID", "")
    csec = os.environ.get("INFISICAL_CLIENT_SECRET", "")
    wid = os.environ.get("INFISICAL_PROJECT_ID", "")
    if not (cid and csec and wid):
        print("SKIP: INFISICAL_CLIENT_ID/CLIENT_SECRET/PROJECT_ID not all set")
        return 0

    # 1. Login — the same identity production uses.
    try:
        token = _login()
        print("PASS: universal-auth login")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: universal-auth login: {type(exc).__name__}: {exc}")
        return 1

    # 2. RAW listing — the backend-visible secret set must stay substantial.
    code, body = _get_json(f"{RAW_API}?workspaceId={wid}&environment=prod", token)
    count = len(body.get("secrets", [])) if code == 200 else 0
    if code == 200 and count >= MIN_EXPECTED_SECRETS:
        print(f"PASS: raw listing -> {count} prod secrets (>= {MIN_EXPECTED_SECRETS})")
    else:
        print(
            f"FAIL: raw listing -> HTTP {code}, {count} secrets "
            f"(expected >= {MIN_EXPECTED_SECRETS}) — production boot path at risk (#434)"
        )
        return 1

    # 3. RAW get-by-key — mirrors the backend boot fetch for boot-critical keys.
    for key in PROBE_KEYS:
        code, body = _get_json(
            f"{RAW_API}/{key}?workspaceId={wid}&environment=prod", token)
        value = (body.get("secret") or {}).get("secretValue") or ""
        if code == 200 and value:
            print(f"PASS: raw get-by-key serves {key} (200, non-empty)")
        else:
            print(
                f"FAIL: raw get-by-key {key} -> HTTP {code}, "
                f"non-empty={bool(value)} — boot fail-closed risk (#434)"
            )
            return 1

    # 4. Standard v1 list route — informational vendor-bug status.
    try:
        code, _body = _get_json(
            f"{API}/api/v1/secrets?workspaceId={wid}&environment=prod", token)
        if code == 200:
            print("INFO: v1 standard listSecrets now returns 200 — vendor may have "
                  "fixed the blind-index; re-run parity and remove the raw-path "
                  "workaround flag deliberately (issue #434 acceptance).")
        else:
            print(f"INFO: v1 standard listSecrets still {code} — known vendor "
                  "blind-index bug (issue #434); v3 raw workaround remains REQUIRED.")
    except Exception as exc:  # noqa: BLE001
        print(f"INFO: v1 standard listSecrets probe error: {exc}")

    print("✅ Infisical RAW vault contract healthy (production parity path).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
