#!/usr/bin/env python3
"""scripts/agents/claim_ttl_expirer.py — Smart Autonomous Claim Expirer (Internal System Agent).

Monitors open issues on Supremeai-bd/supremeai-open for stale claims.
Invariants:
  - If an issue carries 'status:claimed' but has seen zero PRs or updates
    for > TTL_HOURS (default 3 hours), it releases the claim automatically.
  - Leaves an explanatory comment so agents and humans have full audit trail.
  - Removes 'status:claimed' and ensures 'status:unclaimed' is present.
  - Excludes permanent 14 Anchor Hubs.

Fail-closed contract (destructive watchdog):
  - unknown != empty: a failed/malformed `gh issue list` payload aborts the
    scan with exit 1 and releases nothing (same class as the #4470
    cleanup_stale_branches fix — an error payload like
    {"message": "Bad credentials"} is also unknown, not empty).
  - Per-issue isolation: one unparseable/missing updatedAt keeps that claim
    (never release on uncertain identity) and never kills the whole scan —
    a crash here would take the self-healing board watchdog fully offline.
  - Honest audit: the state change (`gh issue edit` label swap) runs FIRST;
    the release comment is posted only after the edit succeeded. A failed
    edit posts no lying "released" comment; a failed comment is reported
    as released-without-audit. Any failure exits 1 (the wired `|| true`
    absorbs it in CI, but the log and exit code stay truthful).
  - TTL SSOT (#57): the default comes from claim_thresholds.
    CLAIM_IDLE_RELEASE_HOURS — no local hardcode.

Self-test: python3 claim_ttl_expirer.py --self-test
Test face: tests/test_claim_ttl_expirer.py (hermetic, offline).
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

UPSTREAM_REPO = "Supremeai-bd/supremeai-open"
try:
    from scripts.ci.federation_anchors import ANCHOR_HUBS as _AH
    ANCHOR_HUBS = set(_AH.values())
except Exception:
    ANCHOR_HUBS = {749, 750, 751, 752, 753, 754, 755, 756, 757, 758, 759, 760, 761, 762}

# #57 SSOT: the number lives in claim_thresholds.py; this module must not
# hardcode it (the exact dual-SSOT class #57 was created to end).
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:
    from claim_thresholds import CLAIM_IDLE_RELEASE_HOURS as _SSOT_TTL_HOURS
    DEFAULT_TTL_HOURS = int(_SSOT_TTL_HOURS)
except Exception:  # pragma: no cover - standalone fallback keeps parity with SSOT value
    DEFAULT_TTL_HOURS = 3


def run_cmd(args: list[str]) -> tuple[int, str, str]:
    try:
        res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as e:  # gh binary missing — the #1 sandbox failure mode; clean fail-closed, no traceback
        return 127, "", str(e)
    return res.returncode, res.stdout, res.stderr


def parse_iso_utc(date_str: str) -> datetime.datetime:
    clean = date_str.replace("Z", "+00:00")
    return datetime.datetime.fromisoformat(clean)


def collect_expired(issues: list, now: datetime.datetime, ttl_hours: float, anchors: set) -> list:
    """Pure release-decision pass over a claimed-issues snapshot (data-only).

    Deterministic: same (issues, now, ttl) -> same plan. Fail-safe per item:
    a malformed row is SKIPPED (kept), never released and never fatal — an
    unknown identity must never reach the destructive release path.
    Each due item is {"number", "title", "idle_hours"}.
    """
    due = []
    for issue in issues or []:
        if not isinstance(issue, dict):
            continue
        num = issue.get("number")
        if not isinstance(num, int) or num <= 0:
            continue
        if num in anchors:
            continue
        updated_at_str = issue.get("updatedAt") or ""
        if not updated_at_str:
            continue
        try:
            updated_at = parse_iso_utc(updated_at_str)
            idle_hours = (now - updated_at).total_seconds() / 3600.0
        except (ValueError, TypeError):
            print(f"⚠️ Issue #{num}: unparseable updatedAt {updated_at_str!r} — keeping claim (fail-safe).")
            continue
        if idle_hours >= ttl_hours:
            due.append(
                {"number": num, "title": issue.get("title") or "", "idle_hours": idle_hours}
            )
    return due


def check_and_expire_claims(ttl_hours: int = DEFAULT_TTL_HOURS, dry_run: bool = False) -> int:
    now = datetime.datetime.now(datetime.timezone.utc)
    print(f"🔍 [Claim TTL Watcher] Scanning {UPSTREAM_REPO} for stale claims (TTL: {ttl_hours}h)...")

    code, out, err = run_cmd([
        "gh", "issue", "list",
        "--repo", UPSTREAM_REPO,
        "--state", "open",
        "--label", "status:claimed",
        "--limit", "100",
        "--json", "number,title,updatedAt,comments,labels",
    ])
    if code != 0:
        print(f"❌ Failed to fetch claimed issues: {err.strip()}")
        return 1

    # Fail-closed: unknown payload != empty board (never release on unknown).
    try:
        issues = json.loads(out) if out.strip() else []
    except json.JSONDecodeError as e:
        print(f"❌ Claimed-issues payload is not valid JSON (fail-closed): {e}")
        return 1
    if not isinstance(issues, list):
        print(f"❌ Claimed-issues payload is not a list (fail-closed): {str(issues)[:120]}")
        return 1
    print(f"📊 Found {len(issues)} actively claimed issue(s).")

    due = collect_expired(issues, now, ttl_hours, ANCHOR_HUBS)

    released_count = 0
    failed_releases = 0
    failed_audits = 0
    for item in due:
        num = item["number"]
        idle_hours = item["idle_hours"]
        print(f"⏳ Issue #{num} '{item['title']}' is stale (idle for {idle_hours:.1f}h >= {ttl_hours}h).")
        if dry_run:
            print(f"   [DRY-RUN] Would release claim on #{num}.")
            continue

        # 1) Real state change FIRST: swap the labels. If this fails we must
        #    NOT post the "released" comment — a comment without the state
        #    change is a lie other agents would act on.
        code_e, _, err_e = run_cmd([
            "gh", "issue", "edit", str(num),
            "--repo", UPSTREAM_REPO,
            "--remove-label", "status:claimed",
            "--add-label", "status:unclaimed",
        ])
        if code_e != 0:
            failed_releases += 1
            print(f"   ❌ FAILED to release claim on Issue #{num} (label edit rc={code_e}): {err_e.strip()[:200]}")
            continue

        # 2) Audit comment AFTER the state change actually happened.
        comment_body = (
            f"<!-- atomic-claim-expired: issue #{num} -->\n"
            f"⏳ **Claim Lease Expired**: This issue was claimed but has had zero activity for "
            f"`{idle_hours:.1f} hours` (TTL ceiling: `{ttl_hours} hours`).\n\n"
            f"Per the **Two-Tier Agent Architecture**, the Internal Watchdog has released this claim "
            f"back to the public runway (`status:unclaimed`) so other autonomous agents can complete the task."
        )
        code_c, _, err_c = run_cmd([
            "gh", "issue", "comment", str(num),
            "--repo", UPSTREAM_REPO,
            "--body", comment_body,
        ])
        if code_c != 0:
            failed_audits += 1
            print(f"   ⚠️ Claim on Issue #{num} released, but the audit comment FAILED (rc={code_c}): {err_c.strip()[:200]}")
        else:
            released_count += 1
            print(f"   ✅ Released claim on Issue #{num}.")

    verdict = f"{released_count} stale claim(s) released"
    if failed_releases:
        verdict += f", {failed_releases} release(s) FAILED (state unchanged)"
    if failed_audits:
        verdict += f", {failed_audits} released without audit comment"
    print(f"🎉 [Claim TTL Watcher] Finished scan: {verdict}.")
    return 1 if (failed_releases or failed_audits) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Expire stale issue claims after TTL hours.")
    parser.add_argument("--ttl-hours", type=int, default=DEFAULT_TTL_HOURS, help="TTL in hours before releasing claim")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without modifying issues")
    parser.add_argument("--self-test", action="store_true", help="Run local self-test assertions")
    args = parser.parse_args()

    if args.self_test:
        test_dt = parse_iso_utc("2026-10-26T12:00:00Z")
        assert test_dt.year == 2026 and test_dt.month == 10
        t0 = parse_iso_utc("2026-10-26T00:00:00Z")
        row = {"number": 900, "title": "t", "updatedAt": "2026-10-25T20:00:00Z"}
        anchor = {"number": 749, "title": "a", "updatedAt": "2026-10-01T00:00:00Z"}
        bad = {"number": 901, "title": "b", "updatedAt": "garbage"}
        plan = collect_expired([row, anchor, bad, {"number": "x"}], t0, 3.0, {749})
        assert [p["number"] for p in plan] == [900], f"collect_expired plan drifted: {plan}"
        if "_SSOT_TTL_HOURS" in globals():
            assert DEFAULT_TTL_HOURS == int(_SSOT_TTL_HOURS), "DEFAULT_TTL_HOURS must mirror claim_thresholds.CLAIM_IDLE_RELEASE_HOURS"
        print("✅ claim_ttl_expirer self-test passed.")
        return 0

    return check_and_expire_claims(ttl_hours=args.ttl_hours, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
