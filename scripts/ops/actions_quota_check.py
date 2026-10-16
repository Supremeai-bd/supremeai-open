#!/usr/bin/env python3
"""Actions quota guard for the SupremeAI Federation (#68 AC4).

Reads the org billing-usage API and exits 1 when the month's Actions minutes
cross the alert threshold (default: 80% of the Free-plan private budget).

Zero-credential-safe: reads GH_TOKEN / GITHUB_TOKEN from env; prints a single
JSON verdict (machine-parseable) plus a human line on stderr.

Exit codes (verdict integrity): 0 = measured usage under threshold;
1 = measured usage crossed threshold; 2 = operational error (missing token,
HTTP failure, unexpected payload shape). Exit 2 keeps operational failures
from being misread as a quota alert: an alert verdict is only ever emitted
from a measured value, never from a crash or a guessed zero.

Usage:
    GH_TOKEN=ghp_xxx python scripts/ops/actions_quota_check.py
    GH_TOKEN=... python scripts/ops/actions_quota_check.py --year 2026 --month 10 --threshold 0.8
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import urllib.error
import urllib.request

ORG_ID = os.environ.get("SUPREMEAI_ORG_ID", "342164125")
PLAN_MONTHLY_LIMIT = 2000.0  # Free org: 2,000 Actions minutes/month (private repos)


def main() -> int:
    ap = argparse.ArgumentParser(description="SupremeAI Actions quota guard (#68)")
    ap.add_argument("--year", type=int, default=_dt.datetime.now(_dt.timezone.utc).year)
    ap.add_argument("--month", type=int, default=_dt.datetime.now(_dt.timezone.utc).month)
    ap.add_argument("--threshold", type=float, default=0.8, help="alert ratio (default 0.8 = 80%%)")
    args = ap.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        print("❌ [quota-guard] GH_TOKEN/GITHUB_TOKEN missing in env — fail-closed.", file=sys.stderr)
        return 2

    url = f"https://api.github.com/organizations/{ORG_ID}/settings/billing/usage?year={args.year}&month={args.month}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "SupremeAI-quota-guard",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
        # Operational failure must not wear the alert exit code: a machine
        # parser would read exit 1 as "quota crossed" with zero evidence.
        print(f"❌ [quota-guard] billing API unreachable/unreadable — no verdict issued: {exc}", file=sys.stderr)
        print(json.dumps({"error": f"billing API unreachable/unreadable: {exc}", "month": f"{args.year}-{args.month:02d}"}, indent=2))
        return 2

    if not isinstance(payload, dict) or not isinstance(payload.get("usageItems"), list):
        # A 200 response without usageItems proves nothing about usage — a
        # fabricated 0.0 would read as a clean "ok" verdict on shape drift.
        shape = type(payload).__name__
        print(f"❌ [quota-guard] unexpected billing payload shape ({shape}, no usageItems list) — no verdict issued.", file=sys.stderr)
        print(json.dumps({"error": "unexpected billing payload shape (no usageItems list)", "month": f"{args.year}-{args.month:02d}"}, indent=2))
        return 2

    minutes = sum(
        float(u.get("quantity", 0.0))
        for u in payload.get("usageItems", [])
        if u.get("product") == "actions" and u.get("unitType") == "Minutes"
    )
    ratio = minutes / PLAN_MONTHLY_LIMIT
    alert = ratio >= args.threshold
    verdict = {
        "month": f"{args.year}-{args.month:02d}",
        "minutes_used": round(minutes, 1),
        "plan_limit": PLAN_MONTHLY_LIMIT,
        "ratio": round(ratio, 4),
        "threshold": args.threshold,
        "alert": alert,
    }
    print(f"[quota-guard] {verdict['month']}: {verdict['minutes_used']}/{int(PLAN_MONTHLY_LIMIT)} min "
          f"({verdict['ratio'] * 100:.1f}%) — {'⚠️ ALERT' if alert else 'ok'}", file=sys.stderr)
    print(json.dumps(verdict, indent=2))
    return 1 if alert else 0


if __name__ == "__main__":
    sys.exit(main())
