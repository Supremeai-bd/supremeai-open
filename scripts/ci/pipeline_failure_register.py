#!/usr/bin/env python3
"""Pipeline Failure Register v2 (#2928 → #2935) — ডায়নামিক ট্র্যাকিং + এক-গ্রুপ-প্রতি-ব্যর্থতা-ইস্যু।

# বাংলা মন্তব্য (v2 পরিবর্তনের কারণ — অ্যাডমিন-নির্দেশ, 2026-10-01):
#   ১) "keep everything always dynamic so that any new pipeline added we
#      dont need to update again" → v1-এ workflows_watched-এ ৩টি নাম
#      হার্ডকোড ছিল; v2-তে ডিফল্ট ["*"] = সব workflow স্বয়ংক্রিয় ট্র্যাকড
#      (নতুন pipeline যোগ হলে এক লাইনও বদলাতে হবে না; exclude_workflows
#      দিয়ে শুধু নিজেকে-রেজিস্টার-করা recursion আটকানো হয়)।
#   ২) "all failure in one group but not in a single issue… so that one
#      agents dont have to fix all" → v1-এ সব সারি একটিমাত্র ledger-ইস্যুতে
#      ছিল (এক claimer-এর পুরো বোঝা); v2-তে প্রতিটি অ্যাকশনেবল ব্যর্থতার
#      নিজস্ব claimable ইস্যু (group:pipeline-failures লেবেলে এক গ্রুপ) —
#      register-ইস্যু = গ্রুপের সূচি/ড্যাশবোর্ড।
#   ৩) "hold kore daowa gulo karon soho issue te add korte hobe" →
#      pr-rebuild (held PR) রুট এখন কারণসহ per-PR fix-issue জন্ম দেয়:
#      কোন গেট লাল, কোন ফাইল সন্দেহভাজন, claim/template/freshness কী ঠিক
#      করতে হবে — ci-fixer এজেন্টরা আলাদাভাবে claim করে সারাতে পারবে।
#   ৪) হীল হলে ইস্যু auto-close — গ্রুপ-ইস্যু সবসময় অ্যাকশনেবল-সারি নিয়ে
#      দাঁড়ায়, ভুতুড়া ইস্যু জমে না।
#
# শেয়ার্ড চুক্তি ai_pr_evaluator.py (#2935)-এর সাথে: per-PR fix-issue
# মার্কার `<!-- pfr-fix:pr:{N} -->` — দুই স্ক্রিপ্ট একই ইস্যু খুঁজে/জন্ম
# দেয়, ডুপ্লিকেট হয় না।
#
# Poka-yoke নকশা-নীতি (v1 থেকে অক্ষুণ্ণ):
#   - fingerprint-dedup (workflow @ branch) — প্রতি-স্ক্যান ডুপ্লিকেট নয়
#   - main-red হলে অন্ধ "main আগে ঠিক করো" নয় — merge-first ক্যান্ডিডেট
#     আগে (নতুন PR-ই main ঠিক করতে পারে; ডুপ্লিকেট fix নয়)
#   - ব্যর্থতা সেরে গেলে auto-resolve (হীল)
#
# v2.2 (#2983 — stale re-file লুপ রোধ): লাইভ-ঘটনা পরিবার — #2972-76 বন্ধ →
# #2979-82 পুনর্জন্ম → বন্ধ → #2989 আবার পুনর্জন্ম (একই fingerprint-কী, পুরনো SHA,
# বর্তমান main সবুজ থাকা অবস্থায়)। দুটি জন্মগত ফাঁক বন্ধ:
#   ৫) fresh-tip gate — "RED on main" ফাইল করার আগে ব্যর্থ run-এর SHA আর
#      বর্তমান main HEAD মিলবে কি না দেখা হয়; না মিললে stale-tip পর্যবেক্ষণ-
#      সারি (fix-issue নয়) — মিথ্যা "RED on main" সংকেত বন্ধ
#   ৬) closed-history dedupe — একই marker-এ সাম্প্রতিক (উইন্ডো-ভেতরে) বন্ধ
#      হওয়া ইস্যু থাকলে পুনরায় ফাইল নয় (close → re-file → close চক্র বন্ধ)
#
# Smart routing ladder (context-derived, workflow-নাম-নিরপেক্ষ):
#   merge-first > new-fix > pr-rebuild > enforced > watching
#
# Usage:
#   python scripts/ci/pipeline_failure_register.py --scan           # পূর্ণ রি-স্ক্যান
#   python scripts/ci/pipeline_failure_register.py --event          # workflow_run-handler পথ
#   python scripts/ci/pipeline_failure_register.py --dry-run        # নেটওয়ার্ক-লেখা শূন্য
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

REPO = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")
RULES_PATH = Path(__file__).resolve().parents[2] / ".github" / "constitution" / "rules.yml"

# ── Policy SSOT (rules.yml pipeline_failure_policy) + DEFAULT fallback ────────
DEFAULT_POLICY: dict[str, Any] = {
    "enabled": True,
    "register_title_prefix": "🚨 [PIPELINE-FAILURE-REGISTER]",
    "register_labels": ["pipeline-failure", "type:ledger", "area:ci", "group:pipeline-failures"],
    "fix_labels": ["P1-high", "area:ci", "type:bug", "ci-failure", "group:pipeline-failures"],
    "comment_marker_prefix": "<!-- pfr:fp:",
    "merge_first_marker_prefix": "<!-- pfr-merge-first:",
    "fix_marker_prefix": "<!-- pfr-fix:",
    "state_marker": "<!-- pfr-state",
    "scan_window_runs": 30,
    "max_log_bytes": 60000,
    "max_pr_files": 120,
    "merge_first": True,
    # v2 (#2935): সমান্তরাল-স্ক্যান race-পরবর্তী পুনর্মিলন — orphan ইস্যু-GCর
    # grace-উইন্ডো (মিনিট): এর কম বয়সী ইস্যু কখনো GC হবে না (concurrent
    # scan-এর check-then-create জানালা রক্ষা)।
    "orphan_grace_minutes": 30,
    # v2.1 (#2960): claimed+in-progress ইস্যুর claim-সুরক্ষা-উইন্ডো (ঘণ্টা) —
    # এই উইন্ডোর ভেতরের সাম্প্রতিক Atomic-Claim থাকলে orphan-GC স্পর্শ করবে
    # না (লাইভ-ঘটনা: GC claimed #2960 বন্ধ করেছিল → guard কাজ-চলা branch মুছেছিল)।
    "orphan_claim_protect_hours": 6,
    # v2 (#2935): ডায়নামিক ট্র্যাকিং — ["*"] = সব workflow (নতুন pipeline
    # যোগ হলে এখানে কিছু বদলাতে হয় না)। জরুরি-অপারেশনে নির্দিষ্ট নামের
    # allowlist দিলে সেটিই লাগবে; exclude_workflows সবসময় কার্যকর।
    "workflows_watched": ["*"],
    "exclude_workflows": [],
    # v2.2 (#2983): main-branch ব্যর্থতায় fresh-tip gate — ব্যর্থ run-এর SHA
    # বর্তমান main HEAD না মিললে "RED on main" fix-issue জন্মায় না (stale-tip
    # পর্যবেক্ষণ-সারি)। ব্যতিক্রম: ওই workflow-র সর্বশেষ main-রান বর্তমান tip-এই
    # লাল = সত্যিকারের main-red — তখনই ফাইল হবে।
    "fresh_tip_gate": True,
    # v2.2 (#2983): closed-history dedupe — এই দিন-সংখ্যার ভেতরে বন্ধ হওয়া
    # একই marker-এর ইস্যু থাকলে পুনরায় ফাইল হবে না।
    "stale_refile_window_days": 7,
    # v2 (#2935): এক-গ্রুপ-কিন্তু-আলাদা-ইস্যু — কোন রুট নিজস্ব claimable ইস্যু পায়
    "issueable_routes": ["new-fix", "merge-first", "pr-rebuild", "watching"],
    "group_label": "group:pipeline-failures",
    "auto_close_on_heal": True,
    # রুট-অনুযায়ী লেবেল-সেট (প্রায়োরিটি-টোকেন body-তেও থাকে — টেমপ্লেট-চুক্তি)
    "route_issue_labels": {
        "new-fix": ["P1-high", "area:ci", "type:bug", "ci-failure", "group:pipeline-failures"],
        "merge-first": ["P1-high", "area:ci", "type:bug", "ci-failure", "group:pipeline-failures"],
        "pr-rebuild": ["P2-medium", "area:ci", "type:bug", "ci-failure", "group:pipeline-failures"],
        "watching": ["P3-low", "area:ci", "type:bug", "ci-failure", "group:pipeline-failures"],
    },
}

HEADING = "# 🚨 Pipeline Failure Register — সব pipeline-ব্যর্থতা এক গ্রুপে (auto-maintained)"

ROUTE_LABELS = {
    "merge-first": "🎯 merge-first",
    "new-fix": "🆕 new-fix",
    "already-tracked": "♻️ tracked",
    "pr-rebuild": "⏳ pr-hold",
    "enforced": "🛡️ enforced",
    "watching": "👀 watching",
    "stale-tip": "🕰️ stale-tip",
}

ROUTE_ACTIONS = {
    "merge-first": "এই PR মার্জ করলেই main সবুজ — per-failure issue নির্দেশনা দেয়",
    "new-fix": "per-failure fix-issue তৈরি — ফ্লিট আলাদাভাবে claim করবে",
    "already-tracked": "আগের fix-issue-ই চলছে — নতুন জন্মানো হয়নি",
    "pr-rebuild": "কারণসহ per-PR fix-issue — ci-fixer claim করে সারাবে",
    "enforced": "guard/automation-ই ব্যবস্থা নিয়েছে (comment/delete) — দৃশ্যমানতা-সারি",
    "watching": "PR-হীন branch — per-branch issue (resurrect-না-হলে cleanup)",
    "stale-tip": "পুরনো tip-এর ব্যর্থতা (#2983) — বর্তমান main-HEAD-এ নয়; fix-issue নয়, পর্যবেক্ষণ-সারি",
}

# ফাইল-পাথ নিষ্কাশন: repo-relative পথ দেখতে হবে (runner-পথ নয়)।
FILE_PATH_RE = re.compile(r"(?<![\w/.-])((?:[\w.-]+/){1,6}[\w.-]+\.(?:py|ts|tsx|js|mjs|yml|yaml|json|toml|sql|sh|cfg|ini))\b")
RUNNER_NOISE_RE = re.compile(r"/home/runner|/usr/lib|/opt/hostedtoolcache|site-packages|_temp/")


def load_policy(rules_path: Path = RULES_PATH) -> dict[str, Any]:
    """rules.yml → pipeline_failure_policy (DEFAULT-merge)। ফাইল না থাকলে DEFAULT।"""
    pol = dict(DEFAULT_POLICY)
    try:
        import yaml  # noqa: PLC0415 — lazy: CI-রানারে সবসময় থাকে, লোকালে ছাড় না

        data = yaml.safe_load(Path(rules_path).read_text(encoding="utf-8")) or {}
        override = data.get("pipeline_failure_policy") or {}
        for key, val in override.items():
            if key in pol:
                pol[key] = val
    except Exception:  # noqa: BLE001 — policy-লোড ব্যর্থতা স্ক্যান থামাবে না
        pass
    return pol


def fingerprint(name: str, branch: str) -> str:
    """workflow @ branch → স্থিতিশীল hash (নতুন push-এও একই ব্যর্থতা-ইনস্ট্যান্স)।"""
    return hashlib.md5(f"{name} @ {branch}".encode()).hexdigest()[:12]  # noqa: S324 — dedup-key, নিরাপত্তা নয়


def pr_issue_key(pr_number: int) -> str:
    """per-PR fix-issue-কী — ai_pr_evaluator.py-র সাথে শেয়ার্ড চুক্তি (#2935)।"""
    return f"pr:{pr_number}"


def branch_issue_key(branch: str) -> str:
    """per-branch (watching) issue-কী।"""
    return f"branch:{branch}"


def now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ── ইনজেক্টেবল GitHub-স্তর (tests: FakeApi/FakeGh) ────────────────────────────

def real_api(endpoint: str, method: str = "GET", payload: dict | None = None) -> Any:
    """REST কল — token সর্বদা GH_TOKEN প্রথম (workflow-চুক্তি), GITHUB_TOKEN fallback।"""
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    req = urllib.request.Request(  # noqa: S310 — github.com API-ই কল-হয়
        f"https://api.github.com/{endpoint.lstrip('/')}",
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        raw = resp.read().decode()
    return json.loads(raw) if raw.strip() else None


def real_gh(*args: str) -> str:
    """gh CLI র‍্যাপার — stdout স্ট্রিং ফেরত (run-list/pr-view/log-failed)।"""
    res = subprocess.run(
        ["gh", *args], capture_output=True, text=True, timeout=60, check=False
    )
    if res.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}… failed: {res.stderr[:200]}")
    return res.stdout


Api = Callable[..., Any]
Gh = Callable[..., str]


# ── রান-স্ক্যান (ডায়নামিক — কোনো নাম হার্ডকোড নয়) ───────────────────────────

def watched_workflow_filter(pol: dict) -> set[str] | None:
    """None = সব workflow (ডায়নামিক) · অন্যথায় allowlist-সেট।"""
    watched = pol.get("workflows_watched") or ["*"]
    if "*" in watched:
        return None
    return set(watched)


def excluded_workflows(pol: dict) -> set[str]:
    """exclude-set + নিজেকে-রেজিস্টার recursion-guard (GITHUB_WORKFLOW env)।"""
    exclude = set(pol.get("exclude_workflows") or [])
    self_wf = os.environ.get("GITHUB_WORKFLOW")
    if self_wf:
        exclude.add(self_wf)
    return exclude


def list_failed_runs(gh: Gh, pol: dict, limit: int | None = None) -> list[dict]:
    """সামপ্রতিক ব্যর্থ রান — সব branch, সব workflow (নতুন pipeline স্বয়ংক্রিয়)।

    #3035 root-cause fix: আগে শুধু --status failure খুঁজত → timed_out এবং
    startup_failure অদৃশ্য থাকত। এখন --status completed দিয়ে সব completed run
    আনা হয়, তারপর Python-এ filter: {failure, timed_out, startup_failure}।
    """
    # #3035: scan all completed runs, filter by conclusion in Python
    out = gh(
        "run", "list", "--repo", REPO, "--status", "completed",
        "--limit", str(limit or pol["scan_window_runs"]), "--json",
        "databaseId,name,headBranch,headSha,event,createdAt,url,conclusion",
    )
    runs = json.loads(out or "[]")
    allow = watched_workflow_filter(pol)
    exclude = excluded_workflows(pol)
    # #3035: accept failure + timed_out + startup_failure (config-driven)
    failure_conclusions = set(pol.get("failure_conclusions", ["failure", "timed_out", "startup_failure"]))
    return [
        r for r in runs
        if (allow is None or r.get("name") in allow)
        and r.get("name") not in exclude
        and r.get("conclusion") in failure_conclusions
    ]


def latest_run(gh: Gh, workflow: str, branch: str) -> dict | None:
    """সর্বশেষ রান (conclusion + headSha) — হীলিং-সনাক্তকরণ + #2983 fresh-tip।"""
    try:
        out = gh(
            "run", "list", "--repo", REPO, "--workflow", workflow,
            "--branch", branch, "--limit", "1", "--json", "conclusion,headSha",
        )
        rows = json.loads(out or "[]")
        return rows[0] if rows else None
    except Exception:  # noqa: BLE001 — API-down হলে হীল দাবি করা অন্যায়
        return None


def latest_conclusion(gh: Gh, workflow: str, branch: str) -> str | None:
    """ওই workflow+branch-এর সর্বশেষ রানের ফলাফল (হীলিং-সনাক্তকরণ)।"""
    run = latest_run(gh, workflow, branch)
    return run.get("conclusion") if run else None


# ── PR/branch-স্তর ───────────────────────────────────────────────────────────

def list_open_prs(api: Api) -> list[dict]:
    return api(f"repos/{REPO}/pulls?state=open&per_page=50") or []


def find_open_pr(api: Api, branch: str) -> dict | None:
    owner = REPO.split("/")[0]
    prs = api(f"repos/{REPO}/pulls?head={owner}:{branch}&state=open") or []
    return prs[0] if prs else None


def branch_exists(api: Api, branch: str) -> bool:
    """branch এখনো আছে? (guard-ডিলিট/ক্লিনআপ-সনাক্তকরণ — v2: workflow-নাম-নিরপেক্ষ)।"""
    try:
        api(f"repos/{REPO}/branches/{branch}")
        return True
    except Exception:  # noqa: BLE001 — 404/অন্য কিছু হলে নেই-ই ধরা
        return False


def pr_files(api: Api, pr_number: int, pol: dict) -> set[str]:
    try:
        files = api(f"repos/{REPO}/pulls/{pr_number}/files?per_page={pol['max_pr_files']}") or []
        return {f.get("filename", "") for f in files if f.get("filename")}
    except Exception:  # noqa: BLE001
        return set()


def pr_checks_green(gh: Gh, pr_number: int) -> bool:
    """PR-এর সর্বশেষ চেক-রোলআপ: সবুজ ও সম্পূর্ণ (in-progress → ক্যান্ডিডেট নয়)।"""
    try:
        out = gh("pr", "view", str(pr_number), "--repo", REPO, "--json", "statusCheckRollup")
        checks = (json.loads(out or "{}")).get("statusCheckRollup") or []
        if not checks:
            return False
        # বাংলা মন্তব্য: চলমান (conclusion খালি) চেক থাকলে রায় স্থগিত — ক্যান্ডিডেট নয়।
        if any(not c.get("conclusion") for c in checks):
            return False
        ok = {"SUCCESS", "SKIPPED", "NEUTRAL"}
        has_success = any(c.get("conclusion") == "SUCCESS" for c in checks)
        return has_success and all(c.get("conclusion") in ok for c in checks)
    except Exception:  # noqa: BLE001
        return False


def failed_check_names(gh: Gh, pr_number: int) -> list[str]:
    """PR-এর লাল চেকগুলোর নাম — hold-issue-র কারণ-তালিকায় ব্যবহার (ডায়নামিক)।"""
    try:
        out = gh("pr", "view", str(pr_number), "--repo", REPO, "--json", "statusCheckRollup")
        checks = (json.loads(out or "{}")).get("statusCheckRollup") or []
        ok = {"SUCCESS", "SKIPPED", "NEUTRAL"}
        return [c.get("name", "?") for c in checks if c.get("conclusion") and c["conclusion"] not in ok]
    except Exception:  # noqa: BLE001
        return []


def extract_failed_files(gh: Gh, run_id: int, pol: dict) -> set[str]:
    """ব্যর্থ-লগ থেকে repo-relative ফাইল-সংকেত (ক্যাপড — লগ বিশাল হতে পারে)।"""
    try:
        raw = gh("run", "view", str(run_id), "--repo", REPO, "--log-failed")
    except Exception:  # noqa: BLE001 — লগ মুছে গেলে/বিশাল হলে সৎ-খালি
        return set()
    raw = raw[: pol["max_log_bytes"]]
    files: set[str] = set()
    for line in raw.splitlines():
        if RUNNER_NOISE_RE.search(line):
            continue
        files.update(FILE_PATH_RE.findall(line))
    return files


# ── স্মার্ট রাউটিং (blind main-first নয়) ─────────────────────────────────────

def merge_first_candidates(
    api: Api, gh: Gh, run: dict, pol: dict, dry_run: bool = False
) -> list[int]:
    """main-red-এর সস্তা সমাধান: diff ব্যর্থ-ফাইল ছুঁয়েছে + প্রার্থীর গেট সবুজ।"""
    if not pol.get("merge_first"):
        return []
    fail_files = extract_failed_files(gh, int(run["databaseId"]), pol)
    if not fail_files:
        return []
    cands: list[int] = []
    for pr in list_open_prs(api):
        num = int(pr["number"])
        if pr_files(api, num, pol) & fail_files and pr_checks_green(gh, num):
            cands.append(num)
    return sorted(cands)


def find_existing_fix_issue(api: Api, issue_key: str, pol: dict) -> int | None:
    """একই ব্যর্থতার fix-issue আগে থেকেই খোলা? (duplicate-জন্ম রোধ)

    # বাংলা মন্তব্য: issue_key এখন fp (main-red) / pr:{N} / branch:{name} —
    # ai_pr_evaluator.py-এর জন্ম-দেওয়া per-PR ইস্যুও একই মার্কারে মিলবে।
    """
    issues = api(f"repos/{REPO}/issues?state=open&labels=ci-failure&per_page=100") or []
    marker = f"{pol['fix_marker_prefix']}{issue_key}-->"
    for issue in issues:
        if marker in (issue.get("body") or ""):
            return int(issue["number"])
    return None


def main_head_sha(api: Api, branch: str = "main") -> str | None:
    """#2983: বর্তমান main HEAD sha — fresh-tip gate-এর সত্যের উৎস।"""
    try:
        data = api(f"repos/{REPO}/branches/{branch}")
        return ((data or {}).get("commit") or {}).get("sha")
    except Exception:  # noqa: BLE001 — API-down হলে gate-ই স্কিপ (fail-open, পুরনো আচরণ)
        return None


def find_recently_closed_fix_issue(api: Api, issue_key: str, pol: dict) -> int | None:
    """#2983: একই marker-এ সাম্প্রতিক-বন্ধ ইস্যু আছে কি? (close→re-file→close লুপ রোধ)

    লাইভ-ঘটনা (#2983 evidence): #2972-76 বন্ধ → #2979-82 একই কীতে পুনর্জন্ম →
    বন্ধ → #2989 আবার। find_existing_fix_issue শুধু state=open দেখে — বন্ধ
    হওয়ার পর ইতিহাস-স্মৃতি হারায়। এখানে closed-history-ও দেখা হয় (উইন্ডো =
    stale_refile_window_days); শুধু main-red fingerprint-কীতে প্রযোজ্য —
    pr:N/branch:X কী নয় (PR/branch-এর নতুন ব্যর্থতা = বৈধ নতুন ইস্যু)।
    """
    try:
        issues = api(
            f"repos/{REPO}/issues?state=closed&labels=ci-failure"
            "&sort=updated&direction=desc&per_page=100"
        ) or []
    except Exception:  # noqa: BLE001 — ইতিহাস-পাঠ ব্যর্থ হলে দমন-নয় (সৎ-ফাইল)
        return None
    marker = f"{pol['fix_marker_prefix']}{issue_key}-->"
    window_days = int(pol.get("stale_refile_window_days", 7) or 7)
    cutoff = (
        _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=window_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    for issue in issues:
        body = issue.get("body") or ""
        if marker not in body:
            continue
        # বডি-টেক্সটে marker-উল্লেখ (উদ্ধৃতি) ≠ নিজের মার্কার — প্রথম-লাইন চুক্তি
        if not body.lstrip().startswith(pol["fix_marker_prefix"]):
            continue
        closed_at = str(issue.get("closed_at") or "")
        if closed_at and closed_at >= cutoff:
            return int(issue["number"])
    return None


def create_fix_issue(api: Api, run: dict, issue_key: str, pol: dict, suspects: set[str]) -> int:
    """টেমপ্লেট-সম্মত fix-issue (Mission/Touching Files/Verification + P1 টোকেন)।"""
    name = run.get("name", "unknown")
    branch = run.get("headBranch", "?")
    sha = (run.get("headSha") or "")[:12]
    run_id = run.get("databaseId", "?")
    url = run.get("url", "")
    suspects_line = ", ".join(sorted(suspects)[:5]) if suspects else "TBD (root-cause করে claimer ঘোষণা করবে)"
    title = f"fix(ci): [ci-fail:{issue_key}] {name} RED on {branch} ({sha}) — auto-filed"
    body = (
        f"{pol['fix_marker_prefix']}{issue_key}-->\n"
        f"## Mission\n\n"
        f"**{name}** workflow লাল — branch `{branch}` (commit `{sha}`)।\n\n"
        f"| Field | Value |\n|---|---|\n| Workflow | `{name}` |\n| Branch | `{branch}` |\n"
        f"| Run | [{run_id}]({url}) |\n\n"
        f"### Reproduction\n```bash\ngh run view {run_id} --repo {REPO} --log-failed\n```\n\n"
        f"## Touching Files\n\n"
        f"```text\nTouching files: {suspects_line}\n```\n"
        f"(ব্যর্থ-লগের সন্দেহভাজন ফাইল — চূড়ান্ত ঘোষণা claim-কমেন্টে করতে হবে)\n\n"
        f"## Verification\n\n"
        f"1. `gh run view {run_id} --log-failed` → root-cause\n"
        f"2. লোকাল রিপ্রো + ফিক্স\n"
        f"3. PR-এ গেট-সবুজ প্রমাণ (Test Evidence)\n\n"
        f"**Priority:** P1-high\n"
    )
    issue = api(
        f"repos/{REPO}/issues", method="POST",
        payload={"title": title, "body": body, "labels": pol["route_issue_labels"].get("new-fix", pol["fix_labels"])},
    )
    return int(issue["number"])


def create_pr_hold_issue(
    api: Api, pr_number: int, failed_workflows: list[str], check_names: list[str],
    suspects: set[str], pol: dict,
) -> int:
    """per-PR hold-issue — কারণসহ (অ্যাডমিন-নির্দেশ: held PR-গুলোর কারণ ইস্যুতে)।"""
    key = pr_issue_key(pr_number)
    suspects_line = ", ".join(sorted(suspects)[:6]) if suspects else "gh pr view থেকে claimer ঘোষণা করবে"
    checks_line = ", ".join(check_names[:6]) if check_names else "(রোলআপ থেকে নেওয়া হয়নি)"
    body = (
        f"{pol['fix_marker_prefix']}{key}-->\n"
        f"## Mission\n\n"
        f"**PR #{pr_number}** pipeline-ব্যর্থতায় **hold** — নিচের প্রতিটি কারণ আলাদাভাবে "
        f"সমাধানযোগ্য (এক গ্রুপ `group:pipeline-failures`, আলাদা claimable ইস্যু — এক agent-কে সব করতে হয় না)।\n\n"
        f"### Hold-কারণ (কারণসহ — ci-fixer এখান থেকেই সারাবে)\n"
        f"- [ ] ❌ ব্যর্থ workflow: {', '.join(failed_workflows[:6]) if failed_workflows else '(স্ক্যান-উইন্ডোতে নাম পাওয়া যায়নি)'}\n"
        f"- [ ] ❌ লাল চেক: {checks_line}\n"
        f"- [ ] ⚠️ claim-chain: linked issue অবশ্যই claimed + template-compliant হতে হবে (No Claim, No Code)\n"
        f"- [ ] ⚠️ freshness: `git fetch origin && git merge origin/main` → push (নতুন main-এর সাথে sync — #2935 Freshness Gate)\n\n"
        f"### PR-প্রসঙ্গ\n"
        f"| Field | Value |\n|---|---|\n| PR | [#{pr_number}](https://github.com/{REPO}/pull/{pr_number}) |\n"
        f"| Register | [Pipeline Failure Register](https://github.com/{REPO}/issues?q=label%3Apipeline-failure) |\n\n"
        f"## Touching Files\n\n"
        f"```text\nTouching files: {suspects_line}\n```\n"
        f"(ব্যর্থ-লগের সন্দেহভাজন ফাইল — চূড়ান্ত ঘোষণা claim-কমেন্টে)\n\n"
        f"## Verification\n\n"
        f"1. প্রতিটি hold-কারণ সারিয়ে চেকবক্স টিক + প্রমাণ\n"
        f"2. PR-গেট সবুজ (Unified + Constitutional + Test)\n"
        f"3. `python scripts/ci/ai_pr_evaluator.py --pr {pr_number}` → AUTO_MERGE রায়\n\n"
        f"**Priority:** P2-medium\n"
    )
    issue = api(
        f"repos/{REPO}/issues", method="POST",
        payload={
            "title": f"fix(ci): [hold:{pr_number}] PR #{pr_number} — pipeline-ব্যর্থতা কারণসহ (ci-fixer claim করবে)",
            "body": body, "labels": pol["route_issue_labels"].get("pr-rebuild", pol["fix_labels"]),
        },
    )
    return int(issue["number"])


def create_branch_watch_issue(api: Api, branch: str, failed_workflows: list[str], pol: dict) -> int:
    """per-branch watching-issue — PR-হীন ব্যর্থ branch: resurrect-না-কি-cleanup সিদ্ধান্ত।"""
    key = branch_issue_key(branch)
    body = (
        f"{pol['fix_marker_prefix']}{key}-->\n"
        f"## Mission\n\n"
        f"branch `{branch}`-এ pipeline-ব্যর্থতা, কিন্তু কোনো open PR নেই — কাজটি পরিত্যক্ত/অনাথ হয়ে আছে। "
        f"সিদ্ধান্ত দরকার: **resurrect** (linked issue claim করে PR খুলবে) নাকি **cleanup** (branch মুছে ফেলবে)।\n\n"
        f"### ব্যর্থ workflow-সারি: {', '.join(failed_workflows[:6]) if failed_workflows else '(স্ক্যান-উইন্ডোতে নাম নেই)'}\n\n"
        f"## Touching Files\n\n"
        f"```text\nTouching files: TBD (branch-diff দেখে claimer ঘোষণা করবে)\n```\n\n"
        f"## Verification\n\n"
        f"1. `git log origin/{branch} --oneline -5` — কাজের অবস্থা দেখুন\n"
        f"2. resurrect-হলে: linked issue + claim + PR (টেমপ্লেট-চুক্তি)\n"
        f"3. cleanup-হলে: branch delete + এই ইস্যু close (কারণসহ)\n\n"
        f"**Priority:** P3-low\n"
    )
    issue = api(
        f"repos/{REPO}/issues", method="POST",
        payload={
            "title": f"fix(ci): [watch:{key}] branch `{branch}` — অনাথ ব্যর্থতা (resurrect বা cleanup)",
            "body": body, "labels": pol["route_issue_labels"].get("watching", pol["fix_labels"]),
        },
    )
    return int(issue["number"])


def route_failure(api: Api, gh: Gh, run: dict, pol: dict, dry_run: bool = False) -> dict:
    """একটি ব্যর্থ রানের সস্তা-সমাধান-পথ নির্ণয় (v2: context-derived, নাম-নিরপেক্ষ)।"""
    name = run.get("name", "unknown")
    branch = run.get("headBranch", "?")
    fp = fingerprint(name, branch)
    row: dict[str, Any] = {
        "fp": fp, "workflow": name, "branch": branch,
        "run_id": run.get("databaseId"), "url": run.get("url", ""),
        "pr": None, "fix": None, "route": "watching", "detail": "",
        "issue_key": None,
    }

    pr = find_open_pr(api, branch)
    if pr:
        row["pr"] = int(pr["number"])

    if branch in ("main", "master"):
        # ── #2983 fresh-tip gate: ব্যর্থতা বর্তমান tip-এ ঘটেছে তো? ──────────
        # বাংলা মন্তব্য (root-cause): পুরনো SHA-র ব্যর্থ রান "RED on main"
        # হিসেবে ফাইল হতো অথচ বর্তমান main সবুজ (#2979-82, #2989 — লাইভ-প্রমাণ)।
        # নিয়ম: ব্যর্থ-SHA ≠ বর্তমান HEAD হলে দমন (stale-tip পর্যবেক্ষণ-সারি) —
        # সম্পূর্ণ ব্যতিক্রম: ওই workflow-র সর্বশেষ main-রান বর্তমান tip-এই লাল
        # (তখন main সত্যিই লাল — ভিন্ন রান উইন্ডো-বাইরে থাকলেও ফাইল হবে)।
        if pol.get("fresh_tip_gate", True):
            # #3035: accept timed_out/startup_failure as red (not just failure)
            failure_conclusions = set(pol.get("failure_conclusions", ["failure", "timed_out", "startup_failure"]))
            head = (run.get("headSha") or "").strip()
            tip = main_head_sha(api, branch)
            # #3035: scheduled/dispatch runs (nightly-ops, deep-audit) take 30-180 min;
            # by completion main has advanced — SHA≠tip is expected, not stale.
            run_event = run.get("event", "")
            is_scheduled = run_event in ("schedule", "workflow_dispatch")
            if head and tip and head[:12] != tip[:12] and not is_scheduled:
                latest = latest_run(gh, name, branch) or {}
                tip_red = (
                    str(latest.get("headSha") or "")[:12] == tip[:12]
                    and latest.get("conclusion") in failure_conclusions
                )
                if not tip_red:
                    row["route"] = "stale-tip"
                    row["detail"] = (
                        f"ব্যর্থ SHA {head[:12]} ≠ বর্তমান {branch} HEAD {tip[:12]} — "
                        "পুরনো tip-এর ব্যর্থতা; বর্তমান tip-এ নতুন রান লাল হলে সেটিই জন্মাবে"
                    )
                    row["issue_key"] = fp
                    return row

        # ── main-red: প্রথমে merge-first সন্ধান — নতুন PR-ই main ঠিক করতে পারে
        cands = merge_first_candidates(api, gh, run, pol, dry_run=dry_run)
        if cands:
            row["route"] = "merge-first"
            row["detail"] = f"PR #{cands[0]}" + (f" (+{len(cands)-1}টি)" if len(cands) > 1 else "")
            row["issue_key"] = fp
            return row
        existing = find_existing_fix_issue(api, fp, pol)
        if existing:
            row["route"] = "already-tracked"
            row["fix"] = existing
            row["issue_key"] = fp
            return row
        # ── #2983 closed-history dedupe: একই ব্যর্থতা ইতিমধ্যে ইস্যু-হয়ে বন্ধ? ──
        closed_prev = find_recently_closed_fix_issue(api, fp, pol)
        if closed_prev:
            row["route"] = "already-tracked"
            row["fix"] = closed_prev
            row["detail"] = (
                f"closed-history #{closed_prev} — {pol.get('stale_refile_window_days', 7)} দিনের "
                "ভেতরে একই ব্যর্থতা ইস্যু-হয়ে বন্ধ হয়েছে (re-file লুপ রোধ, #2983)"
            )
            row["issue_key"] = fp
            return row
        if dry_run:
            row["route"] = "new-fix"
            row["detail"] = "dry-run: issue তৈরি হতো"
            row["issue_key"] = fp
            return row
        suspects = extract_failed_files(gh, int(run.get("databaseId", 0)), pol)
        num = create_fix_issue(api, run, fp, pol, suspects)
        row["route"] = "new-fix"
        row["fix"] = num
        row["issue_key"] = fp
        return row

    if row["pr"]:
        # ── PR-branch ব্যর্থতা: held PR — কারণসহ per-PR fix-issue (v2)
        row["route"] = "pr-rebuild"
        row["issue_key"] = pr_issue_key(row["pr"])
        return row

    # ── PR নেই: branch আছে কি? (guard-ডিলিট হলে enforcement-ই সম্পন্ন)
    if branch_exists(api, branch):
        row["route"] = "watching"
        row["issue_key"] = branch_issue_key(branch)
        return row

    row["route"] = "enforced"
    row["detail"] = "branch আর নেই — automation (guard/cleanup) ইতোমধ্যে ব্যবস্থা নিয়েছে"
    return row


# ── Register-issue (গ্রুপ-সূচি) ──────────────────────────────────────────────

def find_register(api: Api, pol: dict) -> dict | None:
    """#3031: search state=all (not just open) — closed registers reopen instead of duplicate."""
    # বাংলা মন্তব্য (#3031 root-cause fix): আগে শুধু state=open খুঁজত → closed register
    # খুঁজে পেত না → নতুন duplicate register জন্মাতো। এখন state=all দিয়ে খুঁজি;
    # closed হলে reopen করা হয় (find_or_create-এ নিচে লজিক আছে)।
    issues = api(f"repos/{REPO}/issues?state=all&labels={pol['register_labels'][0]}&per_page=20") or []
    # বাংলা মন্তব্য: oldest-first (created asc) — priority_queue_ledger.py-এর মতো
    # "oldest is canonical" invariant। find_register আগে created desc নিত → newest-wins
    # (non-deterministic)। এখন oldest open register ক্যানোনিকাল।
    matches = [i for i in issues if str(i.get("title", "")).startswith(pol["register_title_prefix"])]
    if not matches:
        return None
    # Prefer open registers first; if only closed → return closed (will be reopened)
    open_matches = [m for m in matches if m.get("state") == "open"]
    if open_matches:
        # Sort by created_at asc → oldest is canonical
        open_matches.sort(key=lambda i: i.get("created_at", ""))
        return open_matches[0]
    # All closed → return oldest closed (will be reopened by caller)
    matches.sort(key=lambda i: i.get("created_at", ""))
    return matches[0]


def create_register(api: Api, pol: dict) -> dict:
    body = render_body([], [], pol)
    return api(
        f"repos/{REPO}/issues", method="POST",
        payload={
            "title": f"{pol['register_title_prefix']} লাইভ pipeline-ব্যর্থতা বোর্ড — auto-maintained",
            "body": body,
            "labels": pol["register_labels"],
        },
    )


def _reconcile_duplicate_registers(api: Api, pol: dict, keep_number: int | None = None) -> int:
    """#3031: post-create reconciliation — if >1 open register exists, keep oldest (or keep_number),
    close the rest with a reconciliation comment. Returns count of duplicates closed.

    বাংলা মন্তব্য (#3031 root-cause): concurrent scan producers একই সময়ে find=None
    দেখে দুটো register তৈরি করতে পারে। এই function create_register-এর পরেই call
    হয় — সব open register list করে, keep_number (বা oldest) ছাড়া বাকিগুলো close
    করে reconciliation comment সহ। priority_queue_ledger.py-এর "oldest is canonical"
    invariant এখানে পোর্ট করা হয়েছে।
    """
    issues = api(f"repos/{REPO}/issues?state=open&labels={pol['register_labels'][0]}&per_page=20") or []
    matches = [i for i in issues if str(i.get("title", "")).startswith(pol["register_title_prefix"])]
    if len(matches) <= 1:
        return 0  # no duplicates
    # Sort by created_at asc → oldest is canonical
    matches.sort(key=lambda i: i.get("created_at", ""))
    # Determine which to keep: prefer keep_number, else oldest
    if keep_number:
        keep = next((m for m in matches if m.get("number") == keep_number), matches[0])
    else:
        keep = matches[0]
    duplicates = [m for m in matches if m.get("number") != keep.get("number")]
    closed = 0
    for dup in duplicates:
        api(f"repos/{REPO}/issues/{dup['number']}/comments", "POST", payload={
            "body": f"🔄 Duplicate register closed by reconciliation (#3031)। "
                    f"Canonical register: #{keep['number']}। "
                    f"এই duplicate-টি concurrent create race-এ জন্মেছিল।"
        })
        api(f"repos/{REPO}/issues/{dup['number']}", "PATCH", payload={"state": "closed"})
        print(f"🔄 Closed duplicate register #{dup['number']} (canonical: #{keep['number']}) — #3031")
        closed += 1
    return closed


def parse_state(body: str, pol: dict) -> dict[str, dict]:
    """register-body-র machine-ব্লক (<!-- pfr-state … -->) → আগের সারি-স্টেট।"""
    state: dict[str, dict] = {}
    if pol["state_marker"] not in body:
        return state
    block = body.split(pol["state_marker"], 1)[1]
    block = block.split("-->", 1)[0]
    for line in block.strip().splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        fp, _, rest = line.partition(":")
        # বাংলা মন্তব্য: প্রতিটি অংশ strip — নইলে " Main CI/CD"-এর মতো
        # স্পেস-সহ মান healing-সনাক্তকরণে workflow-ম্যাচ ভেঙে দেয়।
        parts = [p.strip() for p in rest.split("|")]
        if len(parts) < 6 or not parts[0]:
            continue
        state[fp.strip()] = {
            "workflow": parts[0], "branch": parts[1], "route": parts[2],
            "count": int(parts[3]) if parts[3].isdigit() else 1,
            "first": parts[4], "last": parts[5],
            "pr": int(parts[6]) if len(parts) > 6 and parts[6].isdigit() else None,
            "fix": int(parts[7]) if len(parts) > 7 and parts[7].isdigit() else None,
        }
    return state


def render_state(active: list[dict]) -> str:
    lines = ["<!-- pfr-state"]
    for r in active:
        lines.append(
            f"{r['fp']}: {r['workflow']}|{r['branch']}|{r['route']}|{r.get('count', 1)}|"
            f"{r.get('first', '')}|{r.get('last', '')}|{r.get('pr') or ''}|{r.get('fix') or ''}"
        )
    lines.append("-->")
    return "\n".join(lines)


def render_body(active: list[dict], healed: list[dict], pol: dict) -> str:
    """register-body — machine-state ব্লক + মানব-পাঠযোগ্য গ্রুপ-সূচি।"""
    parts = [HEADING, ""]
    parts.append(
        "> **এক গ্রুপ, প্রতি-ব্যর্থতা আলাদা claimable ইস্যু** (`group:pipeline-failures`) — "
        "এক agent-কে সব ঠিক করতে হয় না; যে কেউ একটি সারি claim করে সারাতে পারে। "
        "ডায়নামিক ট্র্যাকিং: যেকোনো নতুন pipeline স্বয়ংক্রিয়ভাবে এখানে আসবে। "
        "মেশিন-মেইনটেইনড — হাতে সম্পাদনা নিষিদ্ধ (`pipeline_failure_register.py`)।\n"
    )
    parts.append(f"সর্বশেষ হালনাগাদ: **{now_utc()}**\n")
    if active:
        parts.append("## 🔴 Active — smart-routed (প্রতি সারির নিজস্ব ইস্যু)\n")
        parts.append("| Route | Workflow | Branch | PR | Fix issue | Count | Last seen | পরবর্তী পদক্ষেপ |")
        parts.append("|---|---|---|---|---|---|---|---|")
        for r in active:
            label = ROUTE_LABELS.get(r["route"], r["route"])
            pr_cell = f"[#{r['pr']}](https://github.com/{REPO}/pull/{r['pr']})" if r.get("pr") else "—"
            if r.get("fix"):
                fix_cell = f"[#{r['fix']}](https://github.com/{REPO}/issues/{r['fix']})"
            elif r["route"] == "enforced":
                fix_cell = "_(auto-resolved)_"
            else:
                fix_cell = "—"
            action = ROUTE_ACTIONS.get(r["route"], "")
            if r["route"] == "merge-first" and r.get("detail"):
                action = f"merge {r['detail']} — main-ও সবুজ হবে"
            parts.append(
                f"| {label} | `{r['workflow']}` | `{r['branch']}` | {pr_cell} | {fix_cell} | "
                f"{r.get('count', 1)} | {r.get('last', '')} | {action} |"
            )
        parts.append("")
    else:
        parts.append("## ✅ সব pipeline সবুজ — কোনো সক্রিয় ব্যর্থতা নেই\n")
    if healed:
        parts.append("## ✅ Recently healed (ইস্যু auto-close হয়েছে)\n")
        parts.append("| Workflow | Branch | Healed | Closed issue |")
        parts.append("|---|---|---|---|")
        for r in healed[-8:]:
            closed = f"#{r.get('fix')}" if r.get("fix") else "—"
            parts.append(f"| `{r['workflow']}` | `{r['branch']}` | {r.get('healed_at', '')} | {closed} |")
        parts.append("")
    parts.append(
        "---\n"
        "**স্মার্ট রাউটিং-নীতি (blind main-first নয়):**\n"
        "1. 🎯 **merge-first** — main-red হলে আগে খোলা PR-ক্যান্ডিটেট (diff-overlap + গেট-সবুজ); PR-ই main ঠিক করে\n"
        "2. 🆕 **new-fix** — ক্যান্ডিডেট শূন্য হলে per-failure fix-issue (P1)\n"
        "3. ⏳ **pr-hold** — held PR: কারণসহ per-PR fix-issue (P2) — কোন গেট লাল, কী ঠিক করতে হবে\n"
        "4. 🛡️ **enforced** — branch আর নেই: guard/cleanup-ই ব্যবস্থা নিয়েছে (ইস্যু লাগে না)\n"
        "5. 👀 **watching** — PR-হীন branch: per-branch issue (P3) — resurrect বা cleanup\n"
        "\n**ডায়নামিজম:** `workflows_watched: [\"*\"]` — নতুন pipeline যোগ হলে ট্র্যাকিং নিজে থেকেই চলে; "
        "হীল হলে ইস্যু auto-close। শেয়ার্ড চুক্তি `ai_pr_evaluator.py` (#2935)-এর সাথে: per-PR মার্কার একই।\n"
        "\n_একক-ফানেল #2928+#2935: `pipeline_failure_register.py` (workflow_run-handler + লুপ-চেক) · `ai_pr_evaluator.py` (2-ক্রাইটেরিয়া Merge/Hold/Close)_"
    )
    return "\n".join(parts) + "\n" + render_state(active)


def already_commented(api: Api, register_number: int, fp: str, pol: dict) -> bool:
    marker = f"{pol['comment_marker_prefix']}{fp}-->"
    comments = api(f"repos/{REPO}/issues/{register_number}/comments?per_page=100") or []
    return any(marker in (c.get("body") or "") for c in comments)


def comment_failure(api: Api, register_number: int, row: dict, pol: dict) -> None:
    """নতুন fingerprint-এ একবারই কমেন্ট (dedup-marker) — প্রতি-স্ক্যান স্প্যাম নয়।"""
    label = ROUTE_LABELS.get(row["route"], row["route"])
    links = []
    if row.get("run_id"):
        links.append(f"[run {row['run_id']}]({row['url']})")
    if row.get("pr"):
        links.append(f"PR #{row['pr']}")
    if row.get("fix"):
        links.append(f"fix #{row['fix']}")
    body = (
        f"{pol['comment_marker_prefix']}{row['fp']}-->\n"
        f"## {label} — `{row['workflow']}` লাল @ `{row['branch']}`\n\n"
        f"{' · '.join(links)}\n\n"
        f"**পরবর্তী পদক্ষেপ:** {ROUTE_ACTIONS.get(row['route'], '')}\n"
        + (f"**ক্যান্ডিডেট:** {row['detail']}\n" if row.get("detail") else "")
        + "\n_স্মার্ট-রাউটিং #2928+#2935 — বিস্তারিত টেবিল উপরে_"
    )
    api(f"repos/{REPO}/issues/{register_number}/comments", method="POST", payload={"body": body})


def comment_merge_first(api: Api, pr_number: int, row: dict, pol: dict) -> None:
    """ক্যান্ডিডেট PR-তে একবারই নির্দেশনা — merge-first পথ।"""
    marker = f"{pol['merge_first_marker_prefix']}{row['fp']}-->"
    try:
        comments = api(f"repos/{REPO}/issues/{pr_number}/comments?per_page=100") or []
        if any(marker in (c.get("body") or "") for c in comments):
            return
    except Exception:  # noqa: BLE001 — dedup-চেক ব্যর্থ হলে কমেন্ট এড়িয়ে যাও (স্প্যাম-নিরাপদ)
        return
    body = (
        f"{marker}\n"
        f"## 🎯 merge-first নির্দেশনা (#2928)\n\n"
        f"এই PR-এর diff main-এর বর্তমান লাল `{row['workflow']}`-এর ব্যর্থ-ফাইলগুলো ছুঁয়েছে এবং গেট সবুজ — "
        f"**এই PR মার্জ করলেই main সম্ভবত সবুজ হবে।** নতুন ডুপ্লিকেট fix-issue জন্মানো হয়নি।\n\n"
        f"রেজিস্টার-সারি: `{row['branch']}` · [run {row['run_id']}]({row['url']})\n"
    )
    api(f"repos/{REPO}/issues/{pr_number}/comments", method="POST", payload={"body": body})


# ── হীল-ইস্যু auto-close (#2935: গ্রুপ সবসময় অ্যাকশনেবল রাখো) ─────────────────

def close_healed_issue(api: Api, issue_number: int, row: dict, pol: dict) -> None:
    """হীল হওয়া ব্যর্থতার fix-issue বন্ধ — কারণ-কমেন্টসহ (ভুতুড়া ইস্যু জমা বন্ধ)।"""
    body = (
        f"## ✅ Auto-resolved (Pipeline Failure Register)\n\n"
        f"`{row.get('workflow', '?')}` @ `{row.get('branch', '?')}` এখন সবুজ "
        f"(সর্বশেষ রান success, {now_utc()}) — এই fix-issue-র কারণ আর অবশিষ্ট নেই।\n\n"
        f"_হীল-সনাক্তকরণ: সর্বশেষ রান-ই গণ্য; register সারি অবচ্ছেদন করা হয়েছে।_"
    )
    try:
        api(f"repos/{REPO}/issues/{issue_number}/comments", method="POST", payload={"body": body})
        api(f"repos/{REPO}/issues/{issue_number}", method="PATCH",
            payload={"state": "closed", "state_reason": "completed"})
    except Exception:  # noqa: BLE001 — close-ব্যর্থতা স্ক্যান থামাবে না (পরের স্ক্যানে আবার চেষ্টা)
        pass


# ── পুনর্মিলন (#2935): সমান্তরাল-স্ক্যান race + orphan GC ────────────────────

def _pr_still_open(api: Api, pr_number: int) -> bool:
    """PR #N এখনো open কি না — pr:N-মার্কার ইস্যুর GC-রক্ষার শর্ত।"""
    try:
        pr = api(f"repos/{REPO}/pulls/{pr_number}")
        return bool(pr) and pr.get("state") == "open"
    except Exception:  # noqa: BLE001 — 404 = PR নেই → GC-অনুমোদিত
        return False


def _close_reconciled(api: Api, issue: dict, why: str, key: str) -> None:
    body = (
        f"## 🧹 Reconciled (Pipeline Failure Register v2)\n\n"
        f"এই ইস্যুটি বন্ধ হচ্ছে — **{why}** (marker: `{key}`)।\n\n"
        f"_পুনর্মিলন-নীতি #2935: একই marker-এ প্রাচীনতম ইস্যুই ক্যানোনিকাল; "
        f"সক্রিয় কোনো ব্যর্থতা-সারি রেফার না করা ইস্যু grace-উইন্ডো পার হলে auto-GC।_"
    )
    try:
        api(f"repos/{REPO}/issues/{issue['number']}/comments", method="POST", payload={"body": body})
        api(f"repos/{REPO}/issues/{issue['number']}", method="PATCH",
            payload={"state": "closed", "state_reason": "completed"})
    except Exception:  # noqa: BLE001 — পরের স্ক্যানে আবার চেষ্টা
        pass


def _claimed_recently(api: Api, issue: dict, pol: dict, now=None) -> bool:
    """#2960: active-claim-সুরক্ষা — in-progress ইস্যু GC-হবে না।

    লাইভ-ঘটনা (2026-10-02 01:43): orphan-GC একটি **claimed + status:in-progress**
    ইস্যু (#2960) বন্ধ করেছিল — claim করা agent তখনো root-cause ফিক্সে কাজ করছিল;
    ইস্যু বন্ধ হওয়ায় Branch Creation Guard পরে তার work-branch-ই মুছে ফেলেছিল
    ("issue is closed")। শর্ত: in-progress লেবেল + সাম্প্রতিক (উইন্ডো-ভিতরে)
    Atomic-Claim কমেন্ট — লেবেল-একা নয়, কারণ পরিত্যক্ত claim-এ লেবেল আটকে
    থাকতে পারে; claim-বয়স-উইন্ডো সেটাই আটকায়।
    """
    labels = {
        str(l.get("name", "")) for l in issue.get("labels") or [] if isinstance(l, dict)
    }
    if "status:in-progress" not in labels:
        return False
    num = int(issue.get("number") or 0)
    if not num:
        return True  # অজানা ইস্যু — সৎ-সংরক্ষণ
    try:
        comments = api(f"repos/{REPO}/issues/{num}/comments?per_page=100") or []
    except Exception:  # noqa: BLE001 — পড়তে না পারলে ভুল-GC নয়
        return True
    claim_re = re.compile(r"Atomic\s*Claim", re.IGNORECASE)
    newest_claim = ""
    for c in comments:
        if claim_re.search(c.get("body") or ""):
            ts = str(c.get("created_at") or "")
            if ts > newest_claim:
                newest_claim = ts
    if not newest_claim:
        return True  # লেবেল আছে কিন্তু কমেন্ট-ইতিহাস নেই — সৎ-সংরক্ষণ
    try:
        claimed = _dt.datetime.fromisoformat(newest_claim.replace("Z", "+00:00"))
    except ValueError:
        return True
    now = now or _dt.datetime.now(_dt.timezone.utc)
    hours = float(pol.get("orphan_claim_protect_hours", 6) or 6)
    return (now - claimed).total_seconds() < hours * 3600


def reconcile_fix_issues(api: Api, pol: dict, active: list[dict]) -> dict[str, list[int]]:
    """check-then-create race-পরবর্তী পুনর্মিলন — লাইভ-ঘটনা #2935-থেকে শেখা।

    # বাংলা মন্তব্য (লাইভ ঘটনা, 2026-10-01 22:33): দুটি সমান্তরাল স্ক্যান
    # (CI-loop + অ্যাডমিন-অটোমেশন) একই fingerprint-এ ৯-সেকেন্ড ব্যবধানে দুটি
    # ইস্যু জন্ম দিয়েছিল (#2939/#2940) — find_existing উভয়ের কাছে খালি ছিল।
    # GitHub-এ conditional-create নেই; তাই সমাধান = post-create reconciliation:
    #   ১) dedup — একই marker-এ একাধিক open ইস্যু → প্রাচীনতম বাঁচবে, বাকি close
    #   ২) orphan-GC — কোনো সক্রিয় সারি রেফার করছে না + grace পার → close
    #      (pr:N ইস্যু ব্যতিক্রম: PR open থাকা পর্যন্ত বাঁচবে — held-PR কারণ
    #      এখনো অ্যাকশনেবল হতে পারে)
    """
    issues = api(f"repos/{REPO}/issues?state=open&labels=ci-failure&per_page=100") or []
    marker_re = re.compile(re.escape(pol["fix_marker_prefix"]) + r"([A-Za-z0-9:._/-]+?)-->")
    by_marker: dict[str, list[dict]] = {}
    for issue in issues:
        match = marker_re.search(issue.get("body") or "")
        if match:
            by_marker.setdefault(match.group(1), []).append(issue)

    active_fix_nums = {r.get("fix") for r in active if r.get("fix")}
    grace_minutes = int(pol.get("orphan_grace_minutes", 30))
    now = _dt.datetime.now(_dt.timezone.utc)
    closed_dupes: list[int] = []
    closed_orphans: list[int] = []

    for key, group in by_marker.items():
        # ১) dedup — race-জাত নকল
        if len(group) > 1:
            group = sorted(group, key=lambda i: i.get("created_at") or "")
            for dup in group[1:]:
                _close_reconciled(api, dup, "একই marker-এ প্রাচীনতম ইস্যু ক্যানোনিকাল — এটি নকল (সমান্তরাল-স্ক্যান race)", key)
                closed_dupes.append(int(dup["number"]))
            group = [group[0]]
        # ২) orphan-GC — grace-উইন্ডো পার হয়েছে এমন অনাথ
        keep = group[0]
        num = int(keep["number"])
        if num in active_fix_nums:
            continue
        try:
            created = _dt.datetime.fromisoformat((keep.get("created_at") or "").replace("Z", "+00:00"))
            age_ok = (now - created).total_seconds() >= grace_minutes * 60
        except ValueError:
            age_ok = False  # তারিখ পড়া না গেলে GC নয় — সৎ-সংরক্ষণ
        if not age_ok:
            continue
        if key.startswith("pr:"):
            pr_num = key.split(":", 1)[1]
            if pr_num.isdigit() and _pr_still_open(api, int(pr_num)):
                continue  # held-PR ইস্যু — PR খোলা থাকতে বাঁচবে
        # #2960: claimed + in-progress ইস্যু — agent কাজ করছে; বন্ধ করলে
        # তার work-branch-ই guard মুছে দেবে ("issue is closed") — GC নয়।
        if _claimed_recently(api, keep, pol, now=now):
            continue
        _close_reconciled(api, keep, "কোনো সক্রিয় ব্যর্থতা-সারি আর এই ইস্যুকে রেফার করছে না (healed/excluded)", key)
        closed_orphans.append(num)

    return {"closed_dupes": closed_dupes, "closed_orphans": closed_orphans}


# ── মূল স্ক্যান ──────────────────────────────────────────────────────────────

def scan(
    api: Api = real_api,
    gh: Gh = real_gh,
    pol: dict | None = None,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """পূর্ণ রি-স্ক্যান → register হালনাগাদ + per-failure ইস্যু-নিশ্চিতকরণ।"""
    pol = pol or load_policy()
    if not pol.get("enabled", True):
        return {"skipped": "policy disabled"}

    failed = list_failed_runs(gh, pol, limit)
    by_fp: dict[str, list[dict]] = {}
    for run in failed:
        by_fp.setdefault(fingerprint(run.get("name", "?"), run.get("headBranch", "?")), []).append(run)

    # register খোঁজো/জন্ম দাও (গ্রুপ-সূচি)
    register = find_register(api, pol)
    register_created = False
    if register is None:
        if dry_run:
            register = {"number": -1, "body": ""}
        else:
            register = create_register(api, pol)
            register_created = True
            # #3031: post-create reconciliation — concurrent producers may have
            # also created a register. Re-list; if >1 open → keep oldest, close rest.
            _reconcile_duplicate_registers(api, pol, keep_number=register.get("number"))
    elif register.get("state") == "closed":
        # #3031: closed register found → reopen instead of creating duplicate
        if not dry_run:
            api(f"repos/{REPO}/issues/{register['number']}/comments", "POST",
                payload={"body": "🔄 Register reopened by pipeline-failure-register scan (#3031 — "
                       "state=all search prevents duplicate creation)"})
            api(f"repos/{REPO}/issues/{register['number']}", "PATCH", payload={"state": "open"})
            print(f"🔄 Reopened existing register #{register['number']} (was closed — #3031)")
        register["state"] = "open"

    prev = parse_state(register.get("body") or "", pol)

    # ── v2.1 (#2960): উইন্ডো-ভেতরেই হীল — সর্বশেষ রান সবুজ হলে সারি নিষ্ক্রিয় ──
    # বাংলা মন্তব্য (root-cause): আগে হীল-চেক শুধু উইন্ডো-বাইরে যাওয়া fp-এর
    # জন্যই চলত — উইন্ডো-ভেতরে থাকা fp সর্বশেষ রান সবুজ হলেও "active" থেকে
    # যেত, ফলে সেরে-যাওয়া ব্যর্থতার fix-ইস্যু অযথা খোলা পড়ে থাকত (#2960:
    # Issue Template Guard main-এ পরে সবুজ, তবু P1 ইস্যু জীবিত)। এখন প্রতিটি
    # সক্রিয় fp-এর workflow+branch-এর সর্বশেষ রান দেখা হয়: সবুজ হলে সাথে
    # সাথে healed (fix-ইস্যু auto-close) — flaky-পুনরাবৃত্তি হলে fp আবার active
    # হয়ে ফেরে (prev-state উত্তরাধিকার), তাই মিথ্যা-হীলের ঝুঁকি নেই।
    healed: list[dict] = []
    for fp in list(by_fp.keys()):
        runs = by_fp[fp]
        newest = max(runs, key=lambda r: r.get("createdAt", ""))
        verdict = latest_conclusion(
            gh, newest.get("name", "?"), newest.get("headBranch", "?")
        )
        if verdict == "success":
            old = prev.get(fp) or {}
            healed.append({
                **old,
                "fp": fp,
                "workflow": newest.get("name", "?"),
                "branch": newest.get("headBranch", "?"),
                "run_id": newest.get("databaseId"),
                "url": newest.get("url", ""),
                "pr": None,
                "fix": old.get("fix"),
                "route": old.get("route", "new-fix"),
                "count": old.get("count", len(runs)) or len(runs),
                "first": old.get("first") or newest.get("createdAt", "")[:16],
                "last": newest.get("createdAt", "")[:16],
                "healed_at": now_utc(),
            })
            del by_fp[fp]

    active: list[dict] = []
    created_fixes: list[int] = []
    for fp, runs in by_fp.items():
        newest = max(runs, key=lambda r: r.get("createdAt", ""))
        row = route_failure(api, gh, newest, pol, dry_run=dry_run)
        old = prev.get(fp) or {}
        # বাংলা মন্তব্য: কাউন্ট বাড়ে নতুন run-id-তে (প্রতি-স্ক্যান ফোলাবে না)।
        same_run = str(old.get("last_run_id")) == str(newest.get("databaseId"))
        row["count"] = (old.get("count", 0) if same_run else old.get("count", 0) + 1) or 1
        row["first"] = old.get("first") or newest.get("createdAt", "")[:16]
        row["last"] = newest.get("createdAt", "")[:16]
        row["last_run_id"] = newest.get("databaseId")
        # আগের fix ধরে রাখো — ensure-ধাপে নতুন জন্ম এড়াতে (per-PR/per-branch শেয়ার্ড)
        if not row.get("fix") and old.get("fix"):
            row["fix"] = old["fix"]
        active.append(row)

    # ── v2: per-PR / per-branch ইস্যু-একত্রীকরণ — এক PR-এর সব ব্যর্থ workflow
    # একই ইস্যুতে কারণ-তালিকা হিসেবে যায় (evaluator-শেয়ার্ড মার্কার)।
    pr_rows: dict[int, list[dict]] = {}
    branch_rows: dict[str, list[dict]] = {}
    for row in active:
        if row["route"] == "pr-rebuild" and row.get("pr"):
            pr_rows.setdefault(row["pr"], []).append(row)
        elif row["route"] == "watching":
            branch_rows.setdefault(row["branch"], []).append(row)

    if not dry_run:
        for pr_number, rows in pr_rows.items():
            key = pr_issue_key(pr_number)
            existing = find_existing_fix_issue(api, key, pol)
            if existing:
                for row in rows:
                    row["fix"] = existing
                continue
            # বাংলা মন্তব্য: state-উত্তরাধিকারী fix (আগের স্ক্যানের একই ইস্যু) —
            # marker-সন্ধান সাময়িকভাবে ব্যর্থ হলেও নতুন ইস্যু জন্মানো হবে না।
            inherited = next((r["fix"] for r in rows if r.get("fix")), None)
            if inherited:
                for row in rows:
                    row["fix"] = inherited
                continue
            workflows = [r["workflow"] for r in rows]
            checks = failed_check_names(gh, pr_number)
            suspects: set[str] = set()
            for r in rows:
                if r.get("run_id"):
                    suspects |= extract_failed_files(gh, int(r["run_id"]), pol)
            num = create_pr_hold_issue(api, pr_number, workflows, checks, suspects, pol)
            created_fixes.append(num)
            for row in rows:
                row["fix"] = num
        for branch, rows in branch_rows.items():
            key = branch_issue_key(branch)
            existing = find_existing_fix_issue(api, key, pol)
            if existing:
                for row in rows:
                    row["fix"] = existing
                continue
            inherited = next((r["fix"] for r in rows if r.get("fix")), None)
            if inherited:
                for row in rows:
                    row["fix"] = inherited
                continue
            num = create_branch_watch_issue(api, branch, [r["workflow"] for r in rows], pol)
            created_fixes.append(num)
            for row in rows:
                row["fix"] = num
        # merge-first সারির নিজস্ব নির্দেশনা-ইস্যু (main-red অ্যাকশনেবল থাকে)
        for row in active:
            if row["route"] == "merge-first" and not row.get("fix") and row.get("issue_key"):
                existing = find_existing_fix_issue(api, row["issue_key"], pol)
                if existing:
                    row["fix"] = existing
                else:
                    num = create_fix_issue(
                        api,
                        {"name": row["workflow"], "headBranch": row["branch"],
                         "headSha": "", "databaseId": row.get("run_id"),
                         "url": row.get("url", "")},
                        row["issue_key"], pol, set(),
                    )
                    created_fixes.append(num)
                    row["fix"] = num

    # হীলিং: আগে ট্র্যাক করা, এখন উইন্ডো-বাইরে — সর্বশেষ রান সবুজ হলে resolved
    active_fps = {r["fp"] for r in active}
    active_fix_nums = {r.get("fix") for r in active if r.get("fix")}
    # v2.1 (#2960): উইন্ডো-ভেতরে হীল-হওয়া fp এখানে আবার হীল হবে না (ডাবল-এন্ট্রি)
    healed_fps = {h["fp"] for h in healed}
    for fp, old in prev.items():
        if fp in active_fps or fp in healed_fps:
            continue
        verdict = latest_conclusion(gh, old.get("workflow", ""), old.get("branch", ""))
        if verdict == "success":
            healed.append({**old, "fp": fp, "healed_at": now_utc()})
        elif verdict == "failure":
            # উইন্ডো-বাইরে কিন্তু এখনো লাল — সক্রিয় সারিই থাকবে
            active.append({**old, "fp": fp, "count": old.get("count", 1), "last": old.get("last", "")})

    order = {"merge-first": 0, "new-fix": 1, "already-tracked": 2, "pr-rebuild": 3, "watching": 4, "stale-tip": 5, "enforced": 6}
    active.sort(key=lambda r: order.get(r["route"], 9))

    reconciled: dict[str, list[int]] = {}
    if not dry_run:
        # হীল-ইস্যু auto-close: কোনো সক্রিয় সারি যে ইস্যুটি ধরে নেইনি, সেটিই বন্ধ
        if pol.get("auto_close_on_heal", True):
            for row in healed:
                fix_num = row.get("fix")
                if fix_num and fix_num not in active_fix_nums:
                    close_healed_issue(api, int(fix_num), row, pol)
        # v2 (#2935): পুনর্মিলন — সমান্তরাল-স্ক্যান race-জাত নকল + অনাথ ইস্যু-GC
        # (লাইভ-ঘটনা #2939/#2940 থেকে শেখা; pr:N ইস্যু PR-খোলা থাকতে সুরক্ষিত)
        reconciled = reconcile_fix_issues(api, pol, active)

        body = render_body(active, healed, pol)
        api(f"repos/{REPO}/issues/{register['number']}", method="PATCH", payload={"body": body})
        for row in active:
            if not already_commented(api, int(register["number"]), row["fp"], pol):
                comment_failure(api, int(register["number"]), row, pol)
            if row["route"] == "merge-first" and row.get("pr"):
                comment_merge_first(api, int(row["pr"]), row, pol)

    return {
        "register": register.get("number"),
        "register_created": register_created,
        "active": len(active),
        "healed": len(healed),
        "created_fixes": sorted(set(created_fixes)),
        "reconciled": reconciled,
        "routes": {r["fp"]: r["route"] for r in active},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline Failure Register v2 (#2928+#2935)")
    parser.add_argument("--scan", action="store_true", help="পূর্ণ রি-স্ক্যান (default)")
    parser.add_argument(
        "--event", action="store_true",
        help="workflow_run-handler পথ — প্রেক্ষাপট-env (FAILED_*) লগ-এ ব্যবহৃত, পথ একটিই",
    )
    parser.add_argument("--dry-run", action="store_true", help="নেটওয়ার্ক-লেখা শূন্য")
    parser.add_argument("--limit", type=int, default=None, help="স্ক্যান-উইন্ডো override")
    args = parser.parse_args()

    if args.event:
        print(
            f"📋 Registering pipeline failure: "
            f"{os.environ.get('FAILED_WORKFLOW', '?')} @ "
            f"{os.environ.get('FAILED_BRANCH', '?')} "
            f"(run {os.environ.get('FAILED_RUN_ID', '?')})"
        )
    summary = scan(dry_run=args.dry_run, limit=args.limit)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    # বাংলা মন্তব্য: বুককিপিং-সফলতা = exit 0 — ব্যর্থতা রেজিস্টার-হওয়াই এই জব-এর কাজ।
    return 0


if __name__ == "__main__":
    sys.exit(main())
