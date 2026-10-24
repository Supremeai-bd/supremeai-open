#!/usr/bin/env python3
"""Report a System Gate outcome on the PR (label + idempotent comment).

বাংলা: gate BLOCK হলে `gate:blocked` label + remediation নির্দেশসহ PR comment;
pass হলে label সরিয়ে পরিষ্কার status কমেন্ট। Comment গুলো tag-keyed — বারবার
নতুন comment জমে না (idempotent upsert)।

Usage (from CI):
    python report_gate_outcome.py --pr 123 --outcome success|failure \
        --gate "Scope Gate" --remediation "..."
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

COMMENT_TAG = "<!-- SUPREMEAI_SYSTEM_GATES -->"


def gh(*args: str) -> str:
    res = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}… failed: {res.stderr.strip()[:300]}")
    return res.stdout


def upsert_comment(pr: int, body: str) -> None:
    comments = json.loads(
        gh("api", f"repos/{_repo()}/issues/{pr}/comments?per_page=100")
    )
    existing = next(
        (c for c in comments if COMMENT_TAG in (c.get("body") or "")), None
    )
    if existing:
        gh("api", "-X", "PATCH", f"repos/{_repo()}/issues/comments/{existing['id']}",
           "-f", f"body={body}")
    else:
        gh("pr", "comment", str(pr), "--body", body)


def _repo() -> str:
    return os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY", "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--outcome", choices=["success", "failure", "cancelled", "skipped"], required=True)
    parser.add_argument("--gate", required=True)
    parser.add_argument("--remediation", default="")
    args = parser.parse_args()

    blocked = args.outcome == "failure"

    try:
        if blocked:
            gh("pr", "edit", str(args.pr), "--add-label", "gate:blocked")
            emoji, verdict = "⛔", "BLOCKED"
        else:
            gh("pr", "edit", str(args.pr), "--remove-label", "gate:blocked")
            emoji, verdict = "✅", "PASSED"

        body = (
            f"{COMMENT_TAG}\n"
            f"## {emoji} System Gate — {args.gate}: **{verdict}**\n\n"
            + (f"**Fix:** {args.remediation}\n\n" if blocked and args.remediation else "")
            + (
                "> Constitution v2 (`.github/constitution/rules.yml`) — system enforcement, prose নয়। "
                "Maintainer চাইলে branch protection-এ required করে hard-block করা যাবে।"
            )
        )
        upsert_comment(args.pr, body)
        print(f"[OK] reported {args.gate} {verdict} on PR #{args.pr}")
        return 0
    except Exception as err:  # noqa: BLE001 — reporting must never fail the CI lane
        print(f"::warning::gate outcome reporting failed: {err}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
