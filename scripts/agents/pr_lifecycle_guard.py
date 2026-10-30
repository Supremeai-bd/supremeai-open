#!/usr/bin/env python3
"""PR Lifecycle Guard (#3516) — PR-bot self-sabotage-এর যান্ত্রিক প্রতিষ্ঠান.

বাংলা মন্তব্য (#3516 root-অডিট, 2026-10-05): PR-bot তিন শ্রেণির আত্মঘাতী আচরণ করেছে —
  ১. HOLD_AND_FIX-ক্লোজ: evaluator-এর "কাজের ভ্যালু আছে" রায়ের পরেও ৫টি PR বন্ধ
     (#3231/#3232/#3235/#3236/#3239)। চুক্তি: HOLD = fix & push, CLOSE নয়।
  ২. ডুপ্লিকেট-যমজ: একই issue-তে ৭ জোড়া PR (lease-gate slot-branch mismatch-এ বট
     পুরনো PR-এ push না করে নতুন branch+PR খোলে)।
  ৩. Freshness self-heal অনুপস্থিতি: Freshness Gate নিজেই `git merge origin/main`
     self-heal নির্দেশ দেয়, কিন্তু অটোমেশন চালায় না → সবুজ PR stale-এ আটকায়।

এই গার্ড তিনটি মোডে চলে (সব লেখা-কল --dry-run ডিফল্টে বন্ধ):
  --heal   : খোলা PR behind হলে update-branch API (server-side merge); 422-conflict
             হলে বাংলা self-heal কমেন্ট + `conflict:needs-manual` লেবেল।
  --guard  : (ক) HOLD_AND_FIX-verdict PR-এর ক্লোজ-শনাক্তকরণ ও পুনর্বাসন (reopen);
             (খ) একই issue-তে >1 খোলা PR → ডুপ্লিকেট-সতর্কতা; (গ) wrongful-closure
             (verdict HOLD + merged যমজ অনুপস্থিত) → reopen + প্রমাণ-কমেন্ট।
  --all    : heal + guard একসাথে।

নিরাপত্তা-চুক্তি:
  - শুধু নিজের লেনের কাজ: reopen/update-branch — কখনো force-push বা কারো PR-এর
    কোড-পরিবর্তন নয়।
  - close করা এই গার্ডের কাজ নয় — শুধু রক্ষা ও পুনর্বাসন।
  - মানুষের (OWNER/MEMBER) PR-এ হস্তক্ষেপ নয় — শুধু বট-লেন (head-ref agent-prefix)।
  - মার্কার-ডিডাপ (`<!-- pr-lifecycle-guard:<kind> -->`) — একই সতর্কতা বারবার নয়।
  - API-ব্যর্থতায় fail-open: এক PR-এর ব্যর্থতা পুরো রান মেরে ফেলবে না (per-PR guard)।

ব্যবহার:
  python scripts/agents/pr_lifecycle_guard.py --dry-run        # রিপোর্ট-only (ডিফল্ট)
  python scripts/agents/pr_lifecycle_guard.py --all            # নিরাময় + রক্ষা প্রয়োগ
  python scripts/agents/pr_lifecycle_guard.py --heal           # শুধু freshness-heal
  python scripts/agents/pr_lifecycle_guard.py --guard          # শুধু রক্ষা/পুনর্বাসন
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

REPO = os.environ.get("GH_REPO", "Supremeai-bd/supremeai-open")
API_BASE = "https://api.github.com"

# বাংলা মন্তব্য: evaluator-এর verdict-মার্কার চুক্তি (ai_pr_evaluator.py:verdict_marker_prefix)
# `<!-- ai-eval:<pr>:<VERDICT>:<hash>-->` — এখানে শুধু verdict-ধরার প্রয়োজন।
AI_EVAL_MARKER_RE = re.compile(r"<!--\s*ai-eval:[^:>]*:([A-Z_]+):")

GUARD_MARKER_PREFIX = "<!-- pr-lifecycle-guard:"

# বাংলা মন্তব্য: বট-লেন শনাক্তকরণ — এই প্রিফিক্সের head-branch মানে এজেন্টের PR
# (মানুষের PR-এ গার্ডের update-branch/reopen হস্তক্ষেপ চলবে না)।
BOT_LANE_PREFIXES = (
    "coder-", "ci-", "planner-", "pr-helper-", "platform-", "browser-",
    "super-", "agent-", "fix/", "feat/", "hotfix/", "perf/", "chore/",
    "test/", "docs/", "refactor/", "ci/", "bridge/",
)

CONFLICT_LABEL = "conflict:needs-manual"
HOLD_PROTECTED_LABEL = "guard:hold-protected"

# বাংলা মন্তব্য: state:in-progress লেবেলযুক্ত issue-তে >1 খোলা PR = যমজ-সন্দেহ।
HAS_PR_LABEL = "has-pr"


# ─────────────────────────── API স্তর (injected) ───────────────────────────

def real_api(endpoint: str, method: str = "GET", payload: dict | None = None) -> Any:
    """GitHub REST কল — মান কখনো লগ নয়, শুধু স্ট্যাটাস।"""
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        try:
            import subprocess
            proc = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
            if proc.returncode == 0:
                token = proc.stdout.strip()
        except Exception:
            pass

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(  # noqa: S310
        f"{API_BASE}/{endpoint.lstrip('/')}",
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            raw = resp.read().decode()
        return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as exc:
        # বাংলা মন্তব্য: HTTPError-এ সদৃশ-আকৃতির dict — caller fail-open করতে পারে
        return {"__http_error": exc.code, "__body__": exc.read().decode(errors="replace")}


# ─────────────────────────── ডেটা-মডেল ───────────────────────────

@dataclass
class GuardAction:
    """এক PR-এ গার্ডের একটি সিদ্ধান্ত — রিপোর্ট ও টেস্ট-অ্যাসার্টের একক।"""
    pr: int
    kind: str  # update_branch | conflict_flag | reopen_wrongful | duplicate_warning | hold_protect | none
    detail: str
    applied: bool = False


@dataclass
class GuardReport:
    """পুরো রানের ফল — dry-run ও apply দুই মোডেই পূরণ হয়।"""
    scanned: int = 0
    actions: list[GuardAction] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, action: GuardAction) -> None:
        self.actions.append(action)


# ─────────────────────────── বিশ্লেষণ-ফাংশন (pure) ───────────────────────────

def latest_verdict(comments: list[dict]) -> str | None:
    """সর্বশেষ ai-eval verdict নির্ণয় — কমেন্ট-তালিকা পুরনো→নতুন ক্রমে আসে।"""
    verdict: str | None = None
    for c in comments or []:
        m = AI_EVAL_MARKER_RE.search(c.get("body") or "")
        if m:
            verdict = m.group(1)
    return verdict


def is_bot_lane(head_ref: str) -> bool:
    """বট/এজেন্ট-লেন branch কি না — মানুষের PR-এ হস্তক্ষেপ-বিরোধী দৈর্ঘ্য।"""
    ref = (head_ref or "").strip()
    return any(ref.startswith(p) for p in BOT_LANE_PREFIXES)


def guard_marker_present(comments: list[dict], kind: str) -> bool:
    """নির্দিষ্ট kind-এর গার্ড-মার্কার আগে পোস্ট হয়েছে কি না (ডিডাপ)।"""
    needle = f"{GUARD_MARKER_PREFIX}{kind}:"
    return any(needle in (c.get("body") or "") for c in comments or [])


def behind_count(comparison: dict) -> int:
    """base...head compare-এ behind_by — অনুপস্থিত হলে 0।"""
    if not isinstance(comparison, dict) or "__http_error" in comparison:
        return 0
    return int(comparison.get("behind_by") or 0)


def primary_issue(pr: dict) -> int | None:
    """PR-এর প্রাথমিক work-issue — শুধু TITLE-থেকে প্রথম রেফারেন্স।

    বাংলা মন্তব্য (#3516-শিক্ষা): body-তে discovery-parent/discovery-issue রেফারেন্স
    থাকে (#3301 শুধু parent #3088-কে টাচ করেও যমজ-সন্দেহ হয়েছিল) — চুক্তি
    '1 Issue = 1 Branch = 1 PR' অনুযায়ী title-এর প্রথম নম্বরই কাজ-ইস্যু।
    """
    refs = extract_issue_refs(pr.get("title", ""))
    return refs[0] if refs else None


def merged_twin_exists(pr_number: int, linked_issues: list[int], all_prs: list[dict]) -> bool:
    """ভুল-ক্লোজ পুনর্বাসনের শর্ত: একই প্রাথমিক issue-র merged যমজ PR আছে কি না।
    merged যমজ থাকলে ক্লোজ সঠিক (superseded) — reopen করা উচিত নয়।"""
    for p in all_prs or []:
        if p.get("number") == pr_number:
            continue
        if not p.get("merged_at"):
            continue
        pi = primary_issue(p)
        if pi is not None and pi in set(linked_issues):
            return True
    return False


ISSUE_REF_RE = re.compile(r"#(\d+)")


def extract_issue_refs(text: str) -> list[int]:
    """টেক্সট থেকে issue-রেফারেন্স সংখ্যাগুলো।"""
    seen: list[int] = []
    for m in ISSUE_REF_RE.finditer(text or ""):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return seen


# ─────────────────────────── মোড ১: freshness heal ───────────────────────────

def heal_freshness(api: Callable, apply: bool, report: GuardReport) -> None:
    """খোলা বট-লেন PR behind হলে update-branch API — Freshness Gate-এর নিজস্ব
    self-heal নির্দেশের অটোমেশন (#3516-শ্রেণি ৩)।"""
    prs = api(f"repos/{REPO}/pulls?state=open&per_page=50") or []
    if isinstance(prs, dict):  # error shape
        report.errors.append(f"open-PR list failed: {str(prs)[:120]}")
        return
    for pr in prs:
        report.scanned += 1
        num = pr["number"]
        head_ref = pr["head"]["ref"]
        if not is_bot_lane(head_ref):
            continue  # মানুষের লেন — হস্তক্ষেপ নয়
        cmp_res = api(f"repos/{REPO}/compare/main...{head_ref}")
        if behind_count(cmp_res) <= 0:
            continue
        if not apply:
            report.add(GuardAction(num, "update_branch", f"behind={behind_count(cmp_res)} (dry-run)"))
            continue
        res = api(
            f"repos/{REPO}/pulls/{num}/update-branch",
            method="PUT",
            payload={"update_method": "merge"},
        )
        if isinstance(res, dict) and "__http_error" in res:
            code = res["__http_error"]
            if code == 422:
                # বাংলা মন্তব্য: merge-conflict — যান্ত্রিকভাবে সমাধানযোগ্য নয়;
                # মানুষ/লেন-এজেন্টের জন্য পতাকা + self-heal পথ।
                _flag_conflict(api, num, report)
            else:
                report.errors.append(f"#{num} update-branch http={code}")
        else:
            report.add(GuardAction(num, "update_branch", "update-branch accepted", applied=True))


def _flag_conflict(api: Callable, num: int, report: GuardReport) -> None:
    """422-কনফ্লিক্ট PR-এ একবারই লেবেল+কমেন্ট (মার্কার-ডিডাপ)।"""
    comments = api(f"repos/{REPO}/issues/{num}/comments?per_page=50") or []
    if guard_marker_present(comments, "conflict"):
        report.add(GuardAction(num, "conflict_flag", "already flagged (dedup)"))
        return
    body = (
        f"{GUARD_MARKER_PREFIX}conflict:{num}-->\n"
        "## 🩹 PR Lifecycle Guard (#3516) — মার্জ-কনফ্লিক্ট\n\n"
        "update-branch ব্যর্থ (422): base ও head-এ বাস্তব কনফ্লিক্ট। "
        "self-heal পথ: `git fetch origin && git merge origin/main` → কনফ্লিক্ট "
        "সমাধান → push। কনফ্লিক্ট মিটলে গেট পুনরায় চলবে।\n\n"
        "বাংলা মন্তব্য: এই কমেন্ট মার্কার-ডিডাপযুক্ত — একই PR-এ বারবার আসবে না।"
    )
    api(f"repos/{REPO}/issues/{num}/comments", method="POST", payload={"body": body})
    api(f"repos/{REPO}/issues/{num}/labels", method="POST", payload={"labels": [CONFLICT_LABEL]})
    report.add(GuardAction(num, "conflict_flag", "conflict comment + label", applied=True))


# ─────────────────────────── মোড ২: guard ───────────────────────────

def guard_lifecycle(api: Callable, apply: bool, report: GuardReport) -> None:
    """(ক) wrongful-closure পুনর্বাসন (খ) ডুপ্লিকেট-সতর্কতা (গ) hold-protection।"""
    prs = api(f"repos/{REPO}/pulls?state=all&sort=updated&direction=desc&per_page=60") or []
    if isinstance(prs, dict):
        report.errors.append(f"all-PR list failed: {str(prs)[:120]}")
        return
    open_prs = [p for p in prs if p.get("state") == "open"]
    closed_unmerged = [
        p for p in prs
        if p.get("state") == "closed" and not p.get("merged_at")
    ]

    # (খ) ডুপ্লিকেট-সন্দেহ: একই প্রাথমিক (title-) issue-তে >1 খোলা PR
    by_issue: dict[int, list[int]] = {}
    for p in open_prs:
        pi = primary_issue(p)
        if pi is None:
            continue
        by_issue.setdefault(pi, []).append(p["number"])
    for issue_n, pr_nums in sorted(by_issue.items()):
        if len(pr_nums) < 2:
            continue
        target = pr_nums[0]  # প্রথম (প্রাচীনতম) খোলা PR-এ সতর্কতা
        comments = api(f"repos/{REPO}/issues/{target}/comments?per_page=50") or []
        if guard_marker_present(comments, "duplicate"):
            report.add(GuardAction(target, "duplicate_warning", "already warned (dedup)"))
            continue
        detail = f"issue #{issue_n} খোলা PR যমজ: {pr_nums}"
        if not apply:
            report.add(GuardAction(target, "duplicate_warning", detail + " (dry-run)"))
            continue
        body = (
            f"{GUARD_MARKER_PREFIX}duplicate:{target}-->\n"
            "## 👯 PR Lifecycle Guard (#3516) — ডুপ্লিকেট-PR সতর্কতা\n\n"
            f"Issue #{issue_n}-কে নির্দেশ করা একাধিক খোলা PR: {', '.join('#' + str(n) for n in pr_nums)}।\n"
            "চুক্তি: 1 Issue = 1 Branch = 1 PR। পুরনো PR-এ push করা হবে নতুন branch "
            "খোলার বদলে — lease-gate slot-branch mismatch হলে lane-লিজ নবায়ন করুন।\n\n"
            "বাংলা মন্তব্য: যমজ-PR হারানো-কাজের ঝুঁকি (#3478-ফাইন্ডিং ৩)।"
        )
        api(f"repos/{REPO}/issues/{target}/comments", method="POST", payload={"body": body})
        report.add(GuardAction(target, "duplicate_warning", detail, applied=True))

    # (ক)+(গ) wrongful-closure পুনর্বাসন: বন্ধ-অবিভক্ত PR-এর সর্বশেষ verdict HOLD_AND_FIX
    # এবং merged যমজ নেই → ক্লোজ ছিল ভুল → reopen।
    for p in closed_unmerged:
        report.scanned += 1
        num = p["number"]
        head_ref = p["head"]["ref"]
        if not is_bot_lane(head_ref):
            continue
        comments = api(f"repos/{REPO}/issues/{num}/comments?per_page=60") or []
        verdict = latest_verdict(comments)
        if verdict != "HOLD_AND_FIX":
            continue
        pi = primary_issue(p)
        linked = [pi] if pi is not None and pi != num else []
        if not linked:
            continue  # primary-issue নেই — পুনর্বাসন-শর্ত অজানা, মানুষের উপরে ছাড়
        if merged_twin_exists(num, linked, prs):
            continue  # superseded-by-merged — ক্লোজ সঠিক
        # বাংলা মন্তব্য (#3116-শিক্ষা): issue বন্ধ হলে কাজ অন্য পথে মিশেছে বা
        # বাতিল — PR reopen করা শব্দ-দূষণ। শুধু খোলা issue = কাজ এখনো দরকার।
        issue_state = api(f"repos/{REPO}/issues/{pi}")
        if not isinstance(issue_state, dict) or issue_state.get("state") != "open":
            continue
        detail = f"verdict=HOLD_AND_FIX merged-যমজ=অনুপস্থিত linked={linked}"
        if not apply:
            report.add(GuardAction(num, "reopen_wrongful", detail + " (dry-run)"))
            continue
        res = api(f"repos/{REPO}/pulls/{num}", method="PATCH", payload={"state": "open"})
        if isinstance(res, dict) and "__http_error" in res:
            report.errors.append(f"#{num} reopen http={res['__http_error']}")
            continue
        body = (
            f"{GUARD_MARKER_PREFIX}reopen_wrongful:{num}-->\n"
            "## ♻️ PR Lifecycle Guard (#3516) — ভুল-ক্লোজ পুনর্বাসন\n\n"
            "সর্বশেষ AI-Evaluator রায় ছিল **HOLD_AND_FIX** (কাজের ভ্যালু আছে) এবং এই "
            "কাজের কোনো merged যমজ PR নেই — ক্লোজ চুক্তি-বিরুদ্ধ (HOLD = fix & push, "
            "CLOSE নয়)। PR পুনর্খোলা হলো; fix-issue-র পথে এগোন।\n\n"
            "বাংলা মন্তব্য: হারানো-কাজ পুনরুদ্ধার — #3478-ফাইন্ডিং ৩-এর যান্ত্রিক প্রতিকার।"
        )
        api(f"repos/{REPO}/issues/{num}/comments", method="POST", payload={"body": body})
        report.add(GuardAction(num, "reopen_wrongful", detail, applied=True))

    # (গ-ক) খোলা HOLD_AND_FIX PR-এ hold-protection লেবেল (ক্লোজ-পূর্ব সংকেত)
    for p in open_prs:
        num = p["number"]
        if not is_bot_lane(p["head"]["ref"]):
            continue
        comments = api(f"repos/{REPO}/issues/{num}/comments?per_page=50") or []
        if latest_verdict(comments) != "HOLD_AND_FIX":
            continue
        # বাংলা মন্তব্য: hold-protect শুধু খোলা work-issue-তে — বন্ধ-issue-র HOLD PR
        # ইতোমধ্যে প্রক্রিয়াধীন (fix-issue/ledger পথ)।
        pi = primary_issue(p)
        if pi is not None:
            issue_state = api(f"repos/{REPO}/issues/{pi}")
            if isinstance(issue_state, dict) and issue_state.get("state") != "open":
                continue
        labels = [l.get("name") for l in (p.get("labels") or [])]
        if HOLD_PROTECTED_LABEL in labels:
            continue
        if not apply:
            report.add(GuardAction(num, "hold_protect", "verdict=HOLD_AND_FIX (dry-run)"))
            continue
        api(f"repos/{REPO}/issues/{num}/labels", method="POST", payload={"labels": [HOLD_PROTECTED_LABEL]})
        report.add(GuardAction(num, "hold_protect", "label added", applied=True))


# ─────────────────────────── মোড ৩: board issue janitor ───────────────────────────

SENTRY_PASS_RE = re.compile(r"^(?:guard\([^)]*\):\s*(?:provider\s+)?sentry\s+pass|sentry:)", re.IGNORECASE)


def find_superseded_sentry_passes(issues: list[dict]) -> list[tuple[int, int]]:
    """ইস্যু বোর্ডের পুরাতন superseded sentry pass শনাক্তকরণ।
    একটি সেন্ট্রি পাস কেবল তখনই superseded গণ্য হবে যদি বোর্ডে তুলনামূলক নতুন
    (উচ্চতর সংখ্যাযুক্ত) কোনো সেন্ট্রি পাস ওপেন থাকে। কোনো অন্ধ সময় বা TTL-ভিত্তিক
    ক্লোজিং নয়; প্রমাণভিত্তিক (evidence-based) প্রতিস্থাপন।
    """
    sentry_rows: list[int] = []
    for iss in issues:
        title = iss.get("title", "")
        if SENTRY_PASS_RE.search(title):
            num = iss.get("number")
            if isinstance(num, int):
                sentry_rows.append(num)
    if not sentry_rows:
        return []
    newest = max(sentry_rows)
    return [(num, newest) for num in sentry_rows if num < newest]


def find_duplicate_issues(issues: list[dict]) -> list[tuple[int, int]]:
    """হুবহু ডুপ্লিকেট ওপেন ইস্যু শনাক্তকরণ (duplicate_number, original_number)।"""
    seen: dict[str, int] = {}
    dups: list[tuple[int, int]] = []
    sorted_issues = sorted(issues, key=lambda x: x.get("number", 0))
    for iss in sorted_issues:
        num = iss.get("number")
        labels = [l.get("name") if isinstance(l, dict) else l for l in iss.get("labels", [])]
        if "anchor-hub" in labels:
            continue
        title = iss.get("title", "").strip().lower()
        if not title:
            continue
        if title in seen:
            dups.append((num, seen[title]))
        else:
            seen[title] = num
    return dups


def clean_board_issues(api: Callable, apply: bool, report: GuardReport) -> None:
    """বোর্ডের অপ্রয়োজনীয়/অপ্রাসঙ্গিক Issue পরিষ্কার:
    (১) প্রমাণভিত্তিক ডুপ্লিকেট Issue শনাক্ত ও ডুপ্লিকেটটি ক্লোজ।
    (২) পুরাতন superseded sentry pass ক্লোজ (যখন বোর্ডে নতুন সেন্ট্রি পাস বিদ্যমান থাকে)।
    * নোট: কোনো অন্ধ TTL বা সময়-ভিত্তিক ক্লোজিং নেই; কেবল প্রমাণভিত্তিক সমাধান।
    """
    issues = api(f"repos/{REPO}/issues?state=open&per_page=100") or []
    if isinstance(issues, dict):
        report.errors.append(f"open-issues list failed: {str(issues)[:120]}")
        return

    # ১. হুবহু ডুপ্লিকেট Issue ক্লোজ
    dups = find_duplicate_issues(issues)
    for dup_num, orig_num in dups:
        detail = f"duplicate of #{orig_num}"
        if not apply:
            report.add(GuardAction(dup_num, "duplicate_issue_close", detail + " (dry-run)"))
            continue
        body = f"<!-- janitor:auto-close:duplicate --> Closed as duplicate of #{orig_num}."
        api(f"repos/{REPO}/issues/{dup_num}/comments", method="POST", payload={"body": body})
        api(f"repos/{REPO}/issues/{dup_num}", method="PATCH", payload={"state": "closed"})
        report.add(GuardAction(dup_num, "duplicate_issue_close", detail, applied=True))

    # ২. পুরাতন superseded sentry pass ক্লোজ (নতুন sentry pass-এর প্রমাণের ভিত্তিতে)
    superseded = find_superseded_sentry_passes(issues)
    for old_num, newest_num in superseded:
        detail = f"superseded by newer sentry pass #{newest_num}"
        if not apply:
            report.add(GuardAction(old_num, "sentry_pass_superseded", detail + " (dry-run)"))
            continue
        body = f"<!-- janitor:auto-close:superseded --> Closed: superseded by newer platform sentry pass #{newest_num}."
        api(f"repos/{REPO}/issues/{old_num}/comments", method="POST", payload={"body": body})
        api(f"repos/{REPO}/issues/{old_num}", method="PATCH", payload={"state": "closed"})
        report.add(GuardAction(old_num, "sentry_pass_superseded", detail, applied=True))


# ─────────────────────────── CLI ───────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PR & Board Issue Lifecycle Guard (#3516)")
    ap.add_argument("--heal", action="store_true", help="freshness self-heal (update-branch)")
    ap.add_argument("--guard", action="store_true", help="wrongful-closure reopen + duplicate warning")
    ap.add_argument("--janitor", action="store_true", help="clean obsolete/duplicate issues and receipts")
    ap.add_argument("--all", action="store_true", help="heal + guard + janitor")
    ap.add_argument("--apply", action="store_true", help="লেখা-কল সম্পন্ন করো (ডিফল্ট dry-run)")
    args = ap.parse_args(argv)

    apply = bool(args.apply)
    do_heal = args.all or args.heal
    do_guard = args.all or args.guard
    do_janitor = args.all or args.janitor
    if not (do_heal or do_guard or do_janitor):
        do_heal = do_guard = do_janitor = True  # মোড না দিলে = --all

    report = GuardReport()
    if do_heal:
        heal_freshness(real_api, apply, report)
    if do_guard:
        guard_lifecycle(real_api, apply, report)
    if do_janitor:
        clean_board_issues(real_api, apply, report)

    out = {
        "mode": "apply" if apply else "dry-run",
        "scanned": report.scanned,
        "actions": [
            {"pr": a.pr, "kind": a.kind, "applied": a.applied, "detail": a.detail[:160]}
            for a in report.actions
        ],
        "errors": report.errors[:20],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    # বাংলা মন্তব্য: errors থাকলেও exit 0 — fail-open; CI-র অন্যান্য ধাপ ভাঙা নিষেধ।
    return 0


if __name__ == "__main__":
    sys.exit(main())
