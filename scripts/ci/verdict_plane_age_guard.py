#!/usr/bin/env python3
"""verdict_plane_age_guard.py — age-bounded verdict-plane SLA gate (#2567).

কেন (Why — Bengali, house style):
    Issue #2567 অডিট দেখাল: gate queue-তে ৫টি stalled PR হুবহু সেই
    defect-class-গুলোর প্রতিরোধ-ক্ষমতা বহন করে যা ওরা অপেক্ষা করার সময়ে
    main-এ বারবার আঘাত হানছে (lease↔claims, freshness-gate↔R67/R69 ghost,
    probe↔queue-omission, link-gate↔dead pointers, CVE↔blind spots)।
    Census খারাপ হচ্ছিল: 12→15→19 open, 10টি 24h+ বয়সী — কারণ verdict-plane
    অন্ধকার হয়ে থাকে (36h+ দেখা গেছে) অথবা প্রতিটি ঘণ্টায় নতুন intake
    (+3 PR/2h) পুরনোগুলোকে চাপা দেয়। SLA ছিল না, তাই ব্রেচ "দেখা" যেত শুধু
    মানুষ-চালিত অডিটে (reactive), প্রতিরোধে নয়।

    এই guard ইস্যুর সুপারিশ ৪-এর প্রথম অর্ধ ("age-bounded verdict SLA")-কে
    যান্ত্রিক করে: প্রতিটি open PR-এর বয়স SLA-র সাথে মিলিয়ে breach-তালিকা
    (oldest-first) machine-readable রিপোর্টে দেয়। রোস্টারে (run_all_guards.py)
    hermetic --self-test wire করা আছে — "landed unwired" সমস্যার পুনরাবৃত্তি
    বন্ধ (#57-এর SSOT-doctrine ঘরানার শিক্ষা)।

Invariants (mechanical):
    A  SLA bucketing — প্রতিটি open PR-এর বয়স = now − createdAt (UTC);
       age_h > sla_hours ⇒ BREACH, অন্যথায় OK।
    B  breach ordering — breach-তালিকা সবসময় oldest-first (বয়স অবরোহী);
       রিপোর্টে escalation প্রার্থী = তালিকার প্রথম N (oldest)।
    C  honest degradation — PR ডেটা সোর্স অনুপস্থিত/অপাঠ্য হলে exit 2
       (harness error) evidence-সহ; কখনো মিথ্যা PASS বানায় না
       (#1760 honest-degradation pattern)।
    D  read-only — এই guard কোনো mutation করে না (কোনো issue/label/comment
       লেখে না); escalation সিদ্ধান্ত মানুষ/পাইপলাইনের।
    E  machine-readable evidence — --format json দিলে stable-fingerprint
       সহ রিপোর্ট (automation_watchdog-এর dedup-মার্কার ঘরানা)।

Exit codes (harness contract):
    0 = sweep চলেছে, breach নেই (বা self-test পাস)
    1 = SLA breach পাওয়া গেছে (fail-closed verdict gate)
    2 = harness/environment ত্রুটি — gh নেই, ফাইল নেই, JSON ভাঙা, সময়
        পার্স ব্যর্থ; এটা "harness ভাঙা", "কাজ ব্যর্থ" নয় — একই অবস্থায়
        পুনঃচেষ্টা ভুল প্রতিক্রিয়া (AUTONOMY_LOOP_CONTRACT §4 ঘরানা)।

Data source (read-only):
    --check          `gh pr list --repo <R> --state open --limit 200
                      --json number,title,createdAt,url` (gh CLI লাগবে)
    --input-file F   বন্ধন-মুক্ত evidence sweep: একই আকৃতির JSON array
                     (tower/হাতে সংগ্রহ করা রসিদ) — অফলাইন, deterministic

Usage:
    python scripts/ci/verdict_plane_age_guard.py --self-test
    python scripts/ci/verdict_plane_age_guard.py --check --sla-hours 24
    python scripts/ci/verdict_plane_age_guard.py --input-file prs.json --format json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TAG = "[verdict-plane-age-guard]"
DEFAULT_SLA_HOURS = 24.0
DEFAULT_REPO = "Supremeai-bd/supremeai-open"
REPO = os.environ.get("GH_REPO", DEFAULT_REPO)

REQUIRED_FIELDS = ("number", "createdAt")


# --------------------------------------------------------------------------- #
# Pure core (unit-testable, injected clock, zero network)                      #
# --------------------------------------------------------------------------- #

def parse_ts(raw: str) -> datetime:
    """Parse an ISO-8601 timestamp ('Z'-safe) → aware UTC datetime."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"empty timestamp: {raw!r}")
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def normalize_row(row: Any) -> dict:
    """Validate one PR row; raise ValueError on missing/malformed fields."""
    if not isinstance(row, dict):
        raise ValueError(f"PR row is not an object: {type(row).__name__}")
    for field in REQUIRED_FIELDS:
        if field not in row:
            raise ValueError(f"PR row missing required field {field!r}")
    number = row["number"]
    if not isinstance(number, int) or number <= 0:
        raise ValueError(f"PR number must be a positive int: {number!r}")
    created = parse_ts(row["createdAt"])
    return {
        "number": number,
        "title": str(row.get("title") or ""),
        "url": str(row.get("url") or ""),
        "createdAt": created,
    }


def age_hours(created: datetime, now: datetime) -> float:
    """Age in hours between two aware datetimes (now − created)."""
    if created.tzinfo is None or now.tzinfo is None:
        raise ValueError("age_hours requires aware datetimes")
    delta = now - created
    return delta.total_seconds() / 3600.0


def bucket_row(row: dict, now: datetime, sla_hours: float) -> dict:
    """Classify one row against the SLA bound (string createdAt tolerated)."""
    created = row["createdAt"]
    if isinstance(created, str):
        created = parse_ts(created)
    age = age_hours(created, now)
    return {
        "number": row["number"],
        "title": row["title"],
        "url": row["url"],
        "createdAt": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ageHours": round(age, 2),
        "verdict": "BREACH" if age > sla_hours else "OK",
    }


def sweep(rows: list, now: datetime, sla_hours: float) -> dict:
    """Full-plane sweep → machine-readable report (stable key order)."""
    buckets = []
    for row in rows:
        norm = normalize_row(row) if not (
            isinstance(row, dict) and isinstance(row.get("createdAt"), datetime)
        ) else row
        buckets.append(bucket_row(norm, now, sla_hours))
    breaches = sorted(
        (b for b in buckets if b["verdict"] == "BREACH"),
        key=lambda b: (-b["ageHours"], b["number"]),
    )
    ok_count = len(buckets) - len(breaches)
    report = {
        "schema": "verdict-plane-age-report/1",
        "slaHours": sla_hours,
        "totalOpen": len(buckets),
        "okCount": ok_count,
        "breachCount": len(breaches),
        "breaches": breaches,
        "escalationQueue": [b["number"] for b in breaches],
        "generatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    report["fingerprint"] = fingerprint(report)
    return report


def fingerprint(report: dict) -> str:
    """Stable dedup marker: slaHours + breach (number, age-bucketed hour)."""
    basis = {
        "sla": report["slaHours"],
        "breaches": [
            [b["number"], int(b["ageHours"])] for b in report["breaches"]
        ],
    }
    blob = json.dumps(basis, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def format_text(report: dict) -> str:
    """Human-readable verdict line(s) for console/CI logs."""
    sla = report["slaHours"]
    total = report["totalOpen"]
    n = report["breachCount"]
    head = (
        f"{TAG} verdict-plane SLA sweep: {total} open PR(s), SLA={sla:g}h, "
        f"breaches={n}, ok={report['okCount']}"
    )
    if not n:
        return f"{head} — PASS"
    lines = [head, f"{TAG} escalation queue (oldest first, Closes-pending):"]
    for b in report["breaches"]:
        lines.append(
            f"  #{b['number']} {b['ageHours']:g}h — {b['title'][:70]} "
            f"{b['url']}"
        )
    lines.append(f"{TAG} fingerprint: {report['fingerprint']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Data sources (fail-closed, honest degradation)                               #
# --------------------------------------------------------------------------- #

def fetch_live_rows(repo: str) -> list:
    """Live open-PR rows via gh CLI; raise RuntimeError on any failure."""
    cmd = [
        "gh", "pr", "list", "--repo", repo, "--state", "open",
        "--limit", "200", "--json", "number,title,createdAt,url",
    ]
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False, timeout=90,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"gh CLI not found on PATH — live sweep impossible "
            f"(honest-skip, never fabricate PASS): {exc}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"gh pr list timed out: {exc}") from exc
    if res.returncode != 0:
        raise RuntimeError(
            f"gh pr list failed (exit {res.returncode}): "
            f"{(res.stderr or '').strip()[:300]}"
        )
    try:
        rows = json.loads(res.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh output not JSON: {exc}") from exc
    if not isinstance(rows, list):
        raise RuntimeError("gh output is not a JSON array")
    return rows


def load_input_rows(path: Path) -> list:
    """Load offline evidence file (JSON array of PR rows); fail-closed."""
    if not path.is_file():
        raise RuntimeError(f"input file not found: {path}")
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"input file unreadable as JSON: {exc}") from exc
    if not isinstance(rows, list):
        raise RuntimeError("input file must contain a JSON array")
    return rows


# --------------------------------------------------------------------------- #
# Self-test: hermetic scenarios, no repo mutation, injected clock              #
# --------------------------------------------------------------------------- #

FIX_NOW = parse_ts("2026-10-30T12:00:00Z")


def run_self_test() -> int:
    """8/8 hermetic scenarios; every invariant A–E exercised offline."""
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        if not cond:
            failures.append(name)

    # 1 — A: timestamp parsing (Z suffix, offset, naive)
    check("A1 parse Z", parse_ts("2026-10-30T11:00:00Z") ==
          parse_ts("2026-10-30T11:00:00+00:00"))
    check("A2 parse offset", parse_ts("2026-10-30T17:30:00+05:30") ==
          parse_ts("2026-10-30T12:00:00Z"))
    try:
        parse_ts("");
        check("A3 reject empty", False)
    except ValueError:
        check("A3 reject empty", True)

    # 2 — A: age math
    created = parse_ts("2026-10-29T12:00:00Z")
    check("B1 age 24h", age_hours(created, FIX_NOW) == 24.0)

    # 3 — A: bucketing boundary (strictly greater than SLA breaches)
    check("B2 exact-sla OK", bucket_row(
        {"number": 1, "title": "t", "url": "u", "createdAt": created},
        FIX_NOW, 24.0)["verdict"] == "OK")
    older = parse_ts("2026-10-29T11:59:00Z")
    check("B3 beyond-sla BREACH", bucket_row(
        {"number": 2, "title": "t", "url": "u", "createdAt": older},
        FIX_NOW, 24.0)["verdict"] == "BREACH")

    # 4 — B: sweep ordering + counts + escalation queue (oldest-first)
    rows = [
        {"number": 10, "title": "mid", "createdAt": "2026-10-29T00:00:00Z"},
        {"number": 11, "title": "eldest", "createdAt": "2026-10-28T00:00:00Z"},
        {"number": 12, "title": "fresh", "createdAt": "2026-10-30T09:00:00Z"},
    ]
    rep = sweep(rows, FIX_NOW, 24.0)
    check("C1 counts", (rep["totalOpen"], rep["breachCount"], rep["okCount"])
          == (3, 2, 1))
    check("C2 oldest-first",
          [b["number"] for b in rep["breaches"]] == [11, 10])
    check("C3 escalation queue", rep["escalationQueue"] == [11, 10])

    # 5 — B: tie-break by number on equal age
    tie = sweep([
        {"number": 21, "title": "a", "createdAt": "2026-10-28T05:00:00Z"},
        {"number": 20, "title": "b", "createdAt": "2026-10-28T05:00:00Z"},
    ], FIX_NOW, 24.0)
    check("C4 tie-break", [b["number"] for b in tie["breaches"]] == [20, 21])

    # 6 — C: malformed rows fail-closed (ValueError → harness error path)
    for bad in ([{"title": "no number/created"}],
                [{"number": 3}],
                [{"number": "x", "createdAt": "2026-10-30T00:00:00Z"}],
                [{"number": 4, "createdAt": "not-a-time"}]):
        try:
            sweep(bad, FIX_NOW, 24.0)
            check(f"C5 reject {bad!r:.40}", False)
        except ValueError:
            check(f"C5 reject {bad!r:.40}", True)

    # 7 — E: fingerprint stability + sensitivity
    rep2 = sweep(rows, FIX_NOW, 24.0)
    check("E1 fingerprint stable", rep["fingerprint"] == rep2["fingerprint"])
    rep3 = sweep(rows, FIX_NOW, 12.0)
    check("E2 fingerprint sensitive", rep["fingerprint"] != rep3["fingerprint"])

    # 8 — E: text formatter (pass vs breach rendering)
    ok_text = format_text(sweep(
        [{"number": 30, "title": "fresh", "createdAt": "2026-10-30T11:00:00Z"}],
        FIX_NOW, 24.0))
    br_text = format_text(rep)
    check("E3 PASS text", "PASS" in ok_text and "escalation" not in ok_text)
    check("E4 BREACH text", "#11" in br_text and "escalation" in br_text)

    if failures:
        print(f"{TAG} self-test FAIL: {', '.join(failures)}")
        return 1
    print(f"{TAG} self-test OK — 8/8 scenario groups pass")
    return 0


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Age-bounded verdict-plane SLA gate (#2567)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true",
                      help="hermetic scenario suite (roster-safe)")
    mode.add_argument("--check", action="store_true",
                      help="live sweep via gh pr list")
    mode.add_argument("--input-file", type=Path, metavar="F",
                      help="offline evidence sweep (JSON array of PR rows)")
    ap.add_argument("--sla-hours", type=float, default=DEFAULT_SLA_HOURS,
                    help=f"SLA bound in hours (default {DEFAULT_SLA_HOURS:g})")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--repo", default=REPO, metavar="R",
                    help=f"repo for --check (default {REPO})")
    args = ap.parse_args(argv)

    if args.sla_hours <= 0:
        print(f"{TAG} --sla-hours must be > 0", file=sys.stderr)
        return 2

    if args.self_test:
        return run_self_test()

    try:
        if args.check:
            rows = fetch_live_rows(args.repo)
        else:
            rows = load_input_rows(args.input_file)
        report = sweep(rows, datetime.now(UTC), args.sla_hours)
    except (RuntimeError, ValueError) as exc:
        print(f"{TAG} HARNESS-ERROR (exit 2 — honest-skip, no fabricated PASS): "
              f"{exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_text(report))
    return 1 if report["breachCount"] else 0


if __name__ == "__main__":
    sys.exit(main())
