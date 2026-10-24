#!/usr/bin/env python3
"""Universal Issue Fingerprint + Duplicate Guard (#3088 §3)।
========================================================
# বাংলা মন্তব্য (#3088): pipeline-failure register-এর প্রমাণিত fingerprint-
# চুক্তি (marker-in-body + open-search + closed-window) এখন **সব কাজ-ইস্যুর**
# জন্য সাধারণীকৃত। লক্ষ্য: "শুধু title keyword-এর উপর নির্ভর নয়" — সেমান্টিক
# fingerprint-ই duplicate-নিরাপত্তার শেষ-জাল (group-first lookup প্রথম লাইন)।

fingerprint = md5(primary_group | normalized_problem | affected_scope | root_cause_class)[:12]

চুক্তি (register-চুক্তির সাথে সামঞ্জস্যপূর্ণ, নতুন মার্কার-নেমস্পেস):
  - ইস্যু-বডির **প্রথম লাইনে** `<!-- task-fp:<fp> -->` মার্কার
  - খোলা ইস্যুতে একই মার্কার → duplicate: link/update, create নয়
  - সাম্প্রতিক-বন্ধ (ডিফল্ট ৭ দিন) একই মার্কার → suppressed: re-file নিষিদ্ধ
    (#2983 close→re-file→close লুপ-প্যাটার্নের সাধারণীকরণ)
  - `--allow-duplicate` escape hatch (কারণসহ ম্যানুয়াল ব্যতিক্রম)

Usage (CLI):
    python scripts/agents/issue_fingerprint.py --group pipeline \
        --problem "register race reconciliation" --scope "scripts/ci/pipeline_failure_register.py" \
        --root-cause concurrency
    python scripts/agents/issue_fingerprint.py --check <fp> [--closed-window 7]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_REPO = "SaifulHaqueNiloy/supremeai"

# মার্কার-চুক্তি — বডির প্রথম লাইন (register-এর pfr-fix চুক্তির আদলে, #2983)।
FINGERPRINT_MARKER_RE = re.compile(r"<!--\s*task-fp:([0-9a-f]{12})\s*-->")
DEFAULT_CLOSED_WINDOW_DAYS = 7
ROOT_CAUSE_CLASSES = (
    "concurrency",      # race/duplicate-window/lock-churn
    "logic",            # ভুল শর্ত/অ্যালগরিদম
    "wiring",           # dead-code/unwired/missing-caller
    "contract",         # চুক্তি-মিসম্যাচ (marker/regex/API-shape)
    "stale-state",      # expired/old-push/missing-freshness
    "hardcoding",       # hardcoded list/URL/branch
    "security",         # auth/secrets/exposure
    "reliability",      # liveness/watchdog/fail-open
    "unspecified",      # শ্রেণী এখনো নির্ধারিত নয়
)


def normalize_token(text: str) -> str:
    """fingerprint-উপাদান স্বাভাবিকীকরণ — ছোটহাতে, বিন্দুবিচ্ছিন্ন, ফাঁকা-সংকুচিত।

    # বাংলা মন্তব্য: "Register Race Reconciliation!" ↔ "register race
    reconciliation" একই হতে হবে — punctuation/case-পার্থক্য fingerprint-কে
    বদলাবে না (false-negative duplicate)।
    """
    lowered = (text or "").strip().lower()
    # শুধু word-character + স্পেস রাখি; বাকি সব স্পেসে
    cleaned = re.sub(r"[^a-z0-9\u0980-\u09ff]+", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def fingerprint(
    primary_group: str,
    problem: str,
    affected_scope: str,
    root_cause_class: str = "unspecified",
) -> str:
    """#3088 §3 — normalized fingerprint (stable, 12-hex, register-চুক্তির মতো)।"""
    parts = "|".join(
        normalize_token(p)
        for p in (primary_group, problem, affected_scope, root_cause_class)
    )
    return hashlib.md5(parts.encode("utf-8")).hexdigest()[:12]


def marker(fp: str) -> str:
    """ইস্যু-বডির প্রথম লাইনে বসানোর মার্কার।"""
    return f"<!-- task-fp:{fp} -->"


def extract_fingerprint(body: str) -> str | None:
    """ইস্যু-বডি থেকে fingerprint-মার্কার উদ্ধার (প্রথম ম্যাচ)।"""
    m = FINGERPRINT_MARKER_RE.search(body or "")
    return m.group(1) if m else None


def prepend_marker(body: str, fp: str) -> str:
    """বডির শুরুতে মার্কার-লাইন যোগ (ইতিমধ্যে থাকলে অপরিবর্তিত)।"""
    if extract_fingerprint(body or ""):
        return body
    return f"{marker(fp)}\n{body or ''}"


def _gh_issues(state: str, label: str | None, limit: int, repo_dir: Path) -> list[dict]:
    # বাংলা মন্তব্য: এক জায়গায় gh-কল — test-এ monkeypatch-সুবিধার জন্য আলাদা helper।
    args = [
        "gh", "issue", "list", "--repo", DEFAULT_REPO, "--state", state,
        "--limit", str(limit), "--json", "number,title,labels,closedAt,body",
    ]
    if label:
        args.extend(["--label", label])
    res = subprocess.run(
        args, cwd=str(repo_dir), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=40,
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip()[:200] or f"gh exit {res.returncode}")
    return json.loads(res.stdout or "[]")


def find_active_duplicate(
    fp: str,
    primary_group: str | None = None,
    repo_dir: Path = ROOT_DIR,
    limit: int = 100,
) -> dict | None:
    """একই fingerprint-মার্কার-বিশিষ্ট open ইস্যু (group-scoped, fallback সর্বজনীন)।

    # বাংলা মন্তব্য: group-first — প্রথমে শুধু একই group-এর open ইস্যু স্ক্যান;
    ফাঁকা গেলে (বা group অজানা) সব open ইস্যুতে মার্কার-খোঁজা (marker 12-hex,
    collision-ঝুঁকি নগণ্য)। API-down → None + caller-এ সতর্কতা (fail-open
    প্রথা — চালু কাজ আটকাবেনা)।
    """
    searches: list[tuple[str | None, int]] = []
    if primary_group:
        searches.append((f"group:{primary_group}", 60))
    searches.append((None, limit))
    for label, search_limit in searches:
        try:
            for iss in _gh_issues("open", label, search_limit, repo_dir):
                if extract_fingerprint(iss.get("body") or "") == fp:
                    return {"number": iss.get("number"), "title": iss.get("title"), "state": "open"}
        except (subprocess.SubprocessError, RuntimeError, OSError, json.JSONDecodeError):
            continue
    return None


def find_recently_closed_duplicate(
    fp: str,
    window_days: int = DEFAULT_CLOSED_WINDOW_DAYS,
    repo_dir: Path = ROOT_DIR,
    limit: int = 100,
) -> dict | None:
    """সাম্প্রতিক-বন্ধ একই-মার্কার ইস্যু — window-ভিতরে থাকলে re-file suppressed।

    # বাংলা মন্তব্য (#2983-সাধারণীকরণ): ইচ্ছাকৃতভাবে বন্ধ হওয়া সমস্যা
    ঘুরেফিরে আবার ফাইল হচ্ছে কিনা — ৭ দিনের ভিতরে বন্ধ হয়ে গেলে "already
    fixed/deliberately closed" ধরে নতুন creation আটকায়।
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    try:
        for iss in _gh_issues("closed", None, limit, repo_dir):
            if extract_fingerprint(iss.get("body") or "") != fp:
                continue
            closed_raw = iss.get("closedAt")
            if not closed_raw:
                continue
            try:
                closed_at = datetime.fromisoformat(closed_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            if closed_at.tzinfo is None:
                closed_at = closed_at.replace(tzinfo=timezone.utc)
            if closed_at >= cutoff:
                return {"number": iss.get("number"), "title": iss.get("title"),
                        "closed_at": closed_raw, "state": "closed"}
    except (subprocess.SubprocessError, RuntimeError, OSError, json.JSONDecodeError):
        return None
    return None


@dataclass
class DuplicateVerdict:
    """GUARD-DUPLICATE-রায় — create / update-existing / suppressed-closed।"""

    action: str  # "create" | "update_existing" | "suppressed_closed" | "lookup_failed"
    fingerprint: str
    duplicate_of: int | None = None
    reason: str = ""

    @property
    def blocked(self) -> bool:
        # বাংলা মন্তব্য: update_existing/suppressed_closed = creation-block;
        # lookup_failed = fail-open (advisory) — creation চলবে, সতর্কতাসহ।
        return self.action in ("update_existing", "suppressed_closed")


def duplicate_guard(
    primary_group: str | None,
    problem: str,
    affected_scope: str,
    root_cause_class: str = "unspecified",
    closed_window_days: int = DEFAULT_CLOSED_WINDOW_DAYS,
    repo_dir: Path = ROOT_DIR,
) -> DuplicateVerdict:
    """#3088 §3-এর সম্পূর্ণ duplicate-সিদ্ধান্ত — creator-রা খোলার আগে কল করবে।

    Lookup order (spec §3):
      1. fingerprint গঠন (group+problem+scope+root_cause)
      2. open ইস্যুতে মার্কার-খোঁজা (group-scoped → universal)
      3. closed-window স্ক্যান
      4. সব ফাঁকা → "create"
    """
    fp = fingerprint(primary_group or "ungrouped", problem, affected_scope, root_cause_class)
    try:
        active = find_active_duplicate(fp, primary_group, repo_dir=repo_dir)
    except Exception:  # noqa: BLE001 — guard নিজেই কখনো creator-কে ক্র্যাশ করাবে না
        active = None
    if active:
        return DuplicateVerdict(
            action="update_existing", fingerprint=fp, duplicate_of=active["number"],
            reason=f"active issue #{active['number']} already carries this fingerprint — link/update করুন, নতুন create নয়",
        )
    try:
        closed = find_recently_closed_duplicate(fp, closed_window_days, repo_dir=repo_dir)
    except Exception:  # noqa: BLE001 — closed-স্ক্যানও fail-open (active-পাশের মতো)
        closed = None
    if closed:
        return DuplicateVerdict(
            action="suppressed_closed", fingerprint=fp, duplicate_of=closed["number"],
            reason=f"issue #{closed['number']} ({closed['closed_at']}) সাম্প্রতিক বন্ধ হয়েছে একই fingerprint-এ — re-file নিষিদ্ধ (window={closed_window_days}d)",
        )
    return DuplicateVerdict(action="create", fingerprint=fp, reason="no active/recent duplicate — creation অনুমোদিত")


def main() -> int:
    parser = argparse.ArgumentParser(description="Universal issue fingerprint + duplicate guard (#3088)")
    parser.add_argument("--group", default=None, help="primary group (group-first scope)")
    parser.add_argument("--problem", required=True, help="সমস্যার বর্ণনা (normalized হবে)")
    parser.add_argument("--scope", required=True, help="affected scope (files/component)")
    parser.add_argument("--root-cause", default="unspecified", choices=ROOT_CAUSE_CLASSES)
    parser.add_argument("--closed-window", type=int, default=DEFAULT_CLOSED_WINDOW_DAYS)
    parser.add_argument("--check", metavar="FP", help="প্রদত্ত fingerprint-এর duplicate-অবস্থা যাচাই")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.check:
        fp = args.check.strip()
        active = find_active_duplicate(fp, args.group)
        closed = find_recently_closed_duplicate(fp, args.closed_window)
        verdict = DuplicateVerdict(
            action="update_existing" if active else ("suppressed_closed" if closed else "create"),
            fingerprint=fp,
            duplicate_of=(active or closed or {}).get("number"),
        )
    else:
        verdict = duplicate_guard(
            args.group, args.problem, args.scope, args.root_cause, args.closed_window
        )

    if args.json:
        print(json.dumps(verdict.__dict__, ensure_ascii=False, indent=2))
    else:
        icon = {"create": "✅", "update_existing": "♻️", "suppressed_closed": "🔒"}.get(verdict.action, "⚠️")
        print(f"{icon} [{verdict.action}] fp={verdict.fingerprint} {verdict.reason}")
        if verdict.duplicate_of:
            print(f"   duplicate-of: #{verdict.duplicate_of}")
    return 1 if verdict.blocked else 0


if __name__ == "__main__":
    sys.exit(main())
