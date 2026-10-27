#!/usr/bin/env python3
"""AI PR Evaluator (#2935, seq:1) — 2-criteria decision engine.

# বাংলা মন্তব্য: #2930-এর Instant Auto-Merge ডকট্রিন + ci-fixer-এর
# 2-ক্রাইটেরিয়া সিম্পল-ক্লিন ডিসিশন ম্যাট্রিক্সের ইঞ্জিন-বাস্তবায়ন:
#
#   ক্রাইটেরিয়া ১ (Value)      = PR কি বাস্তব সমস্যা সমাধান করে?
#   ক্রাইটেরিয়া ২ (Safety)     = রিগ্রেশন-মুক্ত? (গেট-সবুজ + conflict-শূন্য +
#                                 নতুন main-এর সাথে synced + claim-chain বৈধ)
#
#   Value ✅ + Safety ✅ → AUTO_MERGE    (Instant Auto-Merge candidate)
#   Value ✅ + Safety ❌ → HOLD_AND_FIX  (state:hold — কারণসহ fix-issue, ci-fixer সারাবে)
#   Value ❌ (যেকোনো)   → CLOSE         (কারণসহ — অকেজো/প্রক্রিয়া-বহির্ভূত)
#
# অ্যাডমিন-নির্দেশ (2026-10-01): "hold kore daowa gulo karon soho issue te
# add korte hobe… so that ci fixer pr er issue gulo solve korte pare" —
# HOLD_AND_FIX রায়ের প্রতিটি কারণ per-PR fix-issue-তে লেখা হয়
# (group:pipeline-failures গ্রুপে — এক গ্রুপ, আলাদা ইস্যু, যাতে এক agent-কে
# সব ঠিক করতে না হয়)। pipeline_failure_register.py-র সাথে শেয়ার্ড মার্কার-
# চুক্তি: `<!-- pfr-fix:pr:{N} -->` — দুই স্ক্রিপ্ট একই ইস্যু খুঁজে/জন্ম দেয়,
# ডুপ্লিকেট হয় না।
#
# ডায়নামিজম (অ্যাডমিন-নির্দেশ: "any new pipeline added we dont need to
# update again"): কোনো workflow-নাম হার্ডকোড নেই — statusCheckRollup-এর
# সব চেক, compare-API-র freshness, claim-chain — সবই জেনেরিক সংকেত।
# নতুন pipeline যোগ হলে স্বয়ংক্রিয়ভাবে "checks green" হিসাবে গণ্য হবে।
#
# LLM-enrichment: ইন্টারফেস প্লাগেবল (evaluate_enrichment) — ডিফল্ট
# deterministic-evidence স্কোরিং (CI-তে সর্বদা চলে, বাইরের নির্ভরতা শূন্য)।
# ভবিষ্যতে SupremeAI LLM/Guardian বা CodeRabbit-সামারি এখানে জুড়ে দেওয়া
# যাবে — verdict-চুক্তি অপরিবর্তিত থাকবে।
#
# Usage:
#   python scripts/ci/ai_pr_evaluator.py --pr 2926                # এক PR
#   python scripts/ci/ai_pr_evaluator.py --pr 2926 --apply        # verdict-কমেন্ট + hold-issue
#   python scripts/ci/ai_pr_evaluator.py --scan --apply           # সব open PR
#   python scripts/ci/ai_pr_evaluator.py --pr 2926 --strict-exit  # টেস্ট: exit=verdict
#
# Exit codes (default: bookkeeping-সফলতা = 0, রায় যাই হোক):
#   --strict-exit হলে: 0=AUTO_MERGE · 3=HOLD_AND_FIX · 4=CLOSE · 5=PENDING
#
# #3207 (P0, weapon-first): মূল্যায়ন-অস্ত্র আপগ্রেড —
#   ১. CI In-Progress ≠ Broken: চেক-চলাকালীন PENDING রায় (মিথ্যা HOLD-issue
#      জন্ম নয়, অসম্পূর্ণ CI-তে auto-merge-ও নয়); regression-flag শুধুই
#      প্রকৃত gate-failure-এ।
#   ২. evaluate_enrichment এখন বাস্তব: diff-risk বিশ্লেষণ (risky-path,
#      secret-প্যাটার্ন, test-coverage) + LLM সেমান্টিক রিভিউ (Groq→Gemini→
#      OpenRouter কী-পুল, round-robin failover, fail-soft)। কী না থাকলে
#      বা সব provider ব্যর্থ হলে deterministic-evidence-এ সৎ fallback
#      (U2: llm-unavailable ≠ llm-enriched)। Verdict-ওভাররাইড নিষিদ্ধ —
#      enrichment শুধু confidence/summary/risk যোগ করে।
#   ৩. Dependabot/Renovate-এর synthetic `Refs #N` লাগে না — bot-PR-এর ভ্যালু
#      dependency-bump নিজেই; safety বিচার হয় CI-gate দিয়ে (#2948-শিক্ষা:
#      --pr মোডেও exempt-check এখন evaluate_pr-এর ভেতরেই)।
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
import urllib.request
from pathlib import Path
from typing import Any, Callable

REPO = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")
RULES_PATH = Path(__file__).resolve().parents[2] / ".github" / "constitution" / "rules.yml"

# ── Policy SSOT (rules.yml ai_pr_evaluation_policy) + DEFAULT fallback ────────
DEFAULT_POLICY: dict[str, Any] = {
    "enabled": True,
    # শেয়ার্ড চুক্তি pipeline_failure_policy-র সাথে (একই per-PR ইস্যু-মার্কার)
    "hold_marker_prefix": "<!-- pfr-fix:",
    "verdict_marker_prefix": "<!-- ai-eval:",
    "group_label": "group:pipeline-failures",
    "hold_labels": ["P2-medium", "area:ci", "type:bug", "ci-failure", "group:pipeline-failures"],
    # কোন PR মূল্যায়ন থেকে বাদ — trusted bots-এর নিজস্ব লেন
    "exempt_authors": ["dependabot[bot]", "app/dependabot", "renovate[bot]"],
    "comment_on_auto_merge": True,
    "max_reasons": 12,
}

VERDICTS = ("AUTO_MERGE", "PENDING", "HOLD_AND_FIX", "CLOSE")
EXIT_CODES = {"AUTO_MERGE": 0, "HOLD_AND_FIX": 3, "CLOSE": 4, "PENDING": 5}

OK_CONCLUSIONS = {"SUCCESS", "SKIPPED", "NEUTRAL"}
CLAIM_LABELS = {"status:claimed", "status:in-progress"}
VIOLATING_LABEL = "template:violating"

TITLE_RE = re.compile(r"^(feat|fix|chore|docs|refactor|test|perf|audit|ops|task)\([^)]+\): .+")
REFS_RE = re.compile(r"(?:\bRefs\s*#(\d+)|\(#(\d+)\)\s*$)", re.IGNORECASE)

# #4222: PR-টেমপ্লেট সেকশন-শনাক্তের SSOT হলো .github/scripts/constitution/template_gate.py
# (HEADING_RE: যেকোনো #{1,6} হেডিং + case-insensitive substring)। নিচের হেল্পারগুলো
# সেই গেটের _headings/_has_section-চুক্তির হুবহু প্রতিলিপি — আগের কঠোর
# `^##\s*Summary\b` রেগেক্স ক্যানোনিক্যাল গেট COMPLIANT দেওয়া body-কেও ভুল gap-বলত
# (`## Mission & Summary`, `### Summary` ইত্যাদি) → ভুয়া Safety ❌ → ghost
# pipeline-issue (#4219-শ্রেণি)। tests/test_ai_pr_evaluator.py-র contract-test দুই
# পাশ বাঁধে — ভবিষ্যতে drift হলে টেস্ট লাল হবে, প্রোডাকশনে নয় (P6 poka-yoke)।
PR_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*#*\s*$", re.MULTILINE)


def _pr_headings(body: str) -> list[str]:
    """template_gate._headings()-প্রতিলিপি — সব হেডিং-টেক্সট casefold করে।"""
    return [m.group(1).casefold() for m in PR_HEADING_RE.finditer(body or "")]


def _has_summary_section(body: str) -> bool:
    """template_gate._has_section(body, "Summary")-প্রতিলিপি — SSOT-সংগত শনাক্ত।"""
    return any("summary" in h for h in _pr_headings(body))


# #3207: diff-risk বিশ্লেষণের সিগন্যাল-টেবিল — নাম-ই রিপোর্ট হয়, মান কখনো নয়
SECRET_PATTERNS: tuple[tuple[str, str], ...] = (
    ("aws-access-key", r"AKIA[0-9A-Z]{16}"),
    ("private-key-block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("github-token", r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    ("slack-token", r"\bxox[bpars]-[A-Za-z0-9-]{10,}\b"),
    ("google-api-key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
)
RISKY_PATH_MARKERS = (".github/workflows/", "scripts/ci/", "scripts/agents/",
                      "auth", "credential", "secret", "security", "permission")


def is_exempt_author(author: str, pol: dict) -> bool:
    """#3207: exempt/bot-লেখক চেনা — scan ও --pr উভয় মোডে একই চুক্তি।

    বাংলা: আগে exempt_authors শুধু scan()-এ দেখা হতো; --pr মোডে না দেখায়
    Dependabot-PR synthetic `Refs #N`-এর জন্য CLOSE খেয়েছিল (#2948)।
    """
    return (author or "") in set(pol.get("exempt_authors") or [])


def load_policy(rules_path: Path = RULES_PATH) -> dict[str, Any]:
    """rules.yml → ai_pr_evaluation_policy (DEFAULT-merge)।"""
    pol = dict(DEFAULT_POLICY)
    try:
        import yaml  # noqa: PLC0415 — lazy: CI-রানারে সবসময় থাকে

        data = yaml.safe_load(Path(rules_path).read_text(encoding="utf-8")) or {}
        override = data.get("ai_pr_evaluation_policy") or {}
        for key, val in override.items():
            if key in pol:
                pol[key] = val
    except Exception:  # noqa: BLE001 — policy-লোড ব্যর্থতা মূল্যায়ন থামাবে না
        pass
    return pol


def now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ── ইনজেক্টেবল GitHub-স্তর (tests: FakeApi/FakeGh) ────────────────────────────

def real_api(endpoint: str, method: str = "GET", payload: dict | None = None) -> Any:
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    req = urllib.request.Request(  # noqa: S310
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
    res = subprocess.run(
        ["gh", *args], capture_output=True, text=True, timeout=60, check=False
    )
    if res.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}… failed: {res.stderr[:200]}")
    return res.stdout


def _check_runs_rest(repo: str, sha: str, token: str) -> list[dict]:
    """#4291 fallback: REST check-runs → statusCheckRollup-shape (GraphQL parity).

    conclusion mapping: completed+conclusion → UPPER (OK_CONCLUSIONS parity);
    in-progress/queued → conclusion=None (checks_pending() চুক্তি: falsy=চলছে)।
    """
    req = urllib.request.Request(  # noqa: S310
        f"https://api.github.com/repos/{repo}/commits/{sha}/check-runs?per_page=100",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        data = json.loads(resp.read().decode())
    out: list[dict] = []
    for c in data.get("check_runs", []):
        completed = c.get("status") == "completed"
        concl = (c.get("conclusion") or "").upper() or None
        out.append({
            "name": c.get("name", "?"),
            "status": c.get("status"),
            "conclusion": concl if completed else None,
        })
    return out


Api = Callable[..., Any]
Gh = Callable[..., str]


# ── সংকেত-সংগ্রহ (সবই ডায়নামিক — কোনো workflow-নাম হার্ডকোড নেই) ─────────────

def fetch_pr(gh: Gh, pr_number: int, api: Api | None = None,
             fallback_token: str | None = None) -> dict:
    # বাংলা মন্তব্য (#3191): `files` ফিল্ড যোগ — patch-text সহ প্রতিটি পরিবর্তিত
    # ফাইলের path/additions/deletions একই কলে আসে। এতে diff-aware value-scoring
    # (security close-protection + file-alignment + keyword-anchors) চালানো যায়
    # কোনো অতিরিক্ত API-call ছাড়াই।
    fields = ("number,title,body,author,headRefName,baseRefName,isDraft,mergeable,"
              "statusCheckRollup,additions,deletions,changedFiles,files")
    try:
        out = gh("pr", "view", str(pr_number), "--repo", REPO, "--json", fields)
        return json.loads(out or "{}")
    except RuntimeError as exc:
        # #4291 (repo went PRIVATE mid-project): ফাইন-গ্রেইনড PAT
        # (SELF_HEAL_PAT)-এ checks:read নেই → GraphQL statusCheckRollup 403 →
        # পুরো fetch মরে যায় → evaluator ক্র্যাশ → merge gate সব PR HOLD।
        # Degradation চুক্তি (fail-honest, কোনো verdict-মিথ্যা নয়):
        #   1. statusCheckRollup বাদে পুনরায় fetch (contents read এখনো চলে)
        #   2. checks = REST check-runs (GH_FALLBACK_TOKEN = github.token)
        #   3. REST-ও ব্যর্থ হলে raise (fail-closed — কখনো মিথ্যা সবুজ নয়)
        # যেকোনো gh-ব্যর্থতা (permission/expired-PAT/rate-limit) fallback-ই নেয়;
        # api ইনজেক্ট না করা হলে production-default real_api (tests যারা
        # fetch_pr-কে প্যাচ করে তারা এই পথে ঢুকবেই না; FakeGh ব্যর্থ হয় না)।
        api = api or real_api
        base_fields = ("number,title,body,author,headRefName,baseRefName,isDraft,"
                       "mergeable,headRefOid,additions,deletions,changedFiles,files")
        out = gh("pr", "view", str(pr_number), "--repo", REPO, "--json", base_fields)
        pr = json.loads(out or "{}")
        sha = pr.get("headRefOid") or ""
        if not sha:
            raise RuntimeError("evaluator fallback: no headRefOid — cannot fetch checks") from exc
        token = (fallback_token or os.environ.get("GH_FALLBACK_TOKEN") or "").strip() \
            or (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
        if not token:
            raise RuntimeError("evaluator fallback: no token available for REST checks") from exc
        pr["statusCheckRollup"] = _check_runs_rest(REPO, sha, token)
        return pr


def fetch_freshness(api: Api, head_ref: str, base_ref: str = "main") -> dict:
    """compare-API → behind_by/status — নতুন main-এর সাথে sync কি না (#2935)।"""
    try:
        cmp = api(f"repos/{REPO}/compare/{base_ref}...{head_ref}") or {}
        return {
            "behind_by": int(cmp.get("behind_by") or 0),
            "status": cmp.get("status", "unknown"),
        }
    except Exception:  # noqa: BLE001 — #3037: fail-closed (behind_by=999, not 0)
        # বাংলা মন্তব্য (#3037 root-cause): আগে behind_by=0 return করত → "fresh" →
        # AUTO_MERGE on stale PR (API blip এ ভুল রায়)। এখন behind_by=999 → "stale"
        # → HOLD (safe default যখন তথ্য অনুপস্থিত)।
        return {"behind_by": 999, "status": "unknown", "error": True}


def parse_linked_issue(body: str, title: str) -> int | None:
    """body-র `Refs #N` (টেমপ্লেট-চুক্তি) বা title-এর শেষ `(#N)` — claim-chain শিকল।"""
    # বাংলা মন্তব্য (#3191): এখন বহু-ইস্যু সমর্থনের জন্য parse_linked_issues-এর
    # ওপর ডেলিগেট করে, প্রথমটি ফেরত দেয় (backward-compat — একক-ইস্যু চুক্তি)।
    nums = parse_linked_issues(body, title)
    return nums[0] if nums else None


def parse_linked_issues(body: str, title: str) -> list[int]:
    """body-র সব `Refs #N #M #K` + title-এর শেষ `(#N)` — বহু-ইস্যু চুক্তি (#3191)।

    বাংলা: PR #3176-এর মতো `Refs #3159 #3163` রূপের জন্য — এক PR একাধিক ইস্যু
    সমাধান করতে পারে। প্রতিটি ইস্যুর বিপরীতে value-alignment আলাদাভাবে মূল্যায়িত
    হয়; যেকোনো একটির সাথে diff সংগত হলেই ভ্যালু নিশ্চিত।
    """
    nums: list[int] = []
    seen: set[int] = set()
    # বাংলা: greedy span — "Refs #N #M #K ..." এর সব #N একসাথে ধরে (#3191)।
    # আগের REFS_RE শুধু প্রথম #N ধরত → #3176-এ #3163 হারিয়ে যেত।
    for span in re.finditer(r"\bRefs\b\s*((?:#\d+\s*)+)", body or "", re.IGNORECASE):
        for n in re.finditer(r"#(\d+)", span.group(1)):
            num = int(n.group(1))
            if num not in seen:
                seen.add(num)
                nums.append(num)
    # fallback: একক "Refs #N" (span-বহির্ভূত, যেমন "Refs #5\ntext") + "(#N)" title-এ
    for match in REFS_RE.finditer(body or ""):
        for grp in (match.group(1), match.group(2)):
            if grp:
                num = int(grp)
                if num not in seen:
                    seen.add(num)
                    nums.append(num)
    title_match = re.search(r"\(#(\d+)\)\s*$", title or "")
    if title_match:
        num = int(title_match.group(1))
        if num not in seen:
            nums.append(num)
    return nums


def fetch_issue(api: Api, number: int) -> dict | None:
    try:
        return api(f"repos/{REPO}/issues/{number}")
    except Exception:  # noqa: BLE001 — #3037: return None but caller must check error flag
        # বাংলা মন্তব্য (#3037): আগে None return করত → caller "issue বন্ধ" ভাবত →
        # false CLOSE verdict। এখন caller _fetch_error flag check করে HOLD করবে
        # যখন issue fetch-এ API error হয় (বন্ধ নয়, অজানা)।
        return None


# ── #3191: diff-aware value signals — security close-protection ──────────────
#
# বাংলা মন্তব্য: আগে শুধু metadata (title/linked-issue/template/diff-stats)
# দিয়ে ভ্যালু বিচার হতো → PR #3176-এর মতো আসল security fix শুধু টাইটেল-ফরম্যাট
# কারণে CLOSE হয়ে যেত। এখন diff-content পরীক্ষা করে:
#   ১. file-alignment — changed files ∩ linked issue-র "Touching Files"
#   ২. keyword-anchors — linked issue-র "Evidence"-র identifier patch-এ আছে কিনা
#   ৩. security-signal — destructive-flag removal / tenant-scope addition ইত্যাদি
#   ৪. substantive — সত্যিকারের কোড-সংযোজন (whitespace/index-only নয়)
# security-signal থাকলে verdict কখনো CLOSE নয় — অন্তত HOLD (human review)।

SECURITY_DIFF_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    # destructive-flag removal — বিপজ্জনক ফ্ল্যাগ সরানো হলে security value
    ("destructive-flag-removal: --accept-data-loss",
     re.compile(r"^-[^\n]*--accept-data-loss", re.MULTILINE)),
    ("destructive-flag-removal: --force",
     re.compile(r"^-[^\n]*\s--force\b", re.MULTILINE)),
    # eval removal
    ("eval-removal", re.compile(r"^-[^\n]*\beval\s*\(", re.MULTILINE)),
    # tenant-scope addition — cross-tenant data-leak prevention
    ("tenant-scope-addition",
     re.compile(r"^\+[^\n]*\.eq\(\s*['\"]tenant_id['\"]", re.MULTILINE)),
    ("tenant-scope-addition",
     re.compile(r"^\+[^\n]*\btenant_id\s*==", re.MULTILINE)),
    ("tenant-scope-addition",
     re.compile(r"^\+[^\n]*\btenantId\s*[=,)]", re.MULTILINE)),
    # auth / permission check addition
    ("auth-check-addition",
     re.compile(r"^\+[^\n]*\b(require_auth|authorize|permission_required|@login_required)", re.MULTILINE)),
    # hardcoded secret removal
    ("secret-removal",
     re.compile(r"^-[^\n]*\b(change-me|password\s*=\s*['\"]|secret\s*=\s*['\"])", re.MULTILINE)),
]


def _find_issue_section(body: str, keyword: str) -> str:
    r"""#4222 U9-sweep: gate-চুক্তি-সংগত সেকশন-বের করা (যেকোনো #{1,6} লেভেল +
    case-insensitive substring) — template_gate._has_section-এর একই অর্থ।

    বাংলা: আগের কঠোর `^##\s*<Keyword>\b` শুধু লেভেল-২-এক্যাক্ট-স্টার্ট ধরত —
    গেট COMPLIANT দেওয়া issue (`### Touching Files` ইত্যাদি) evaluator-এর
    value-signal-এ অদৃশ্য হয়ে যেত (সেইম drift-শ্রেণি)। section-body =
    নির্বাচিত হেডিং থেকে পরবর্তী যেকোনো-লেভেল হেডিং পর্যন্ত।
    """
    if not body:
        return ""
    needle = keyword.casefold()
    for m in PR_HEADING_RE.finditer(body):
        if needle in m.group(1).casefold():
            rest = body[m.end():]
            nxt = re.search(r"^\s{0,3}#{1,6}\s", rest, re.MULTILINE)
            return rest[: nxt.start()] if nxt else rest
    return ""


def _extract_touching_files(issue_body: str) -> set[str]:
    """linked issue-র `## Touching Files` সেকশন থেকে declared paths (#3191)।

    #4222: হেডিং-শনাক্ত এখন template_gate-চুক্তি অনুযায়ী (যেকোনো লেভেল,
    substring) — `### Touching Files`-জাতীয় বৈচিত্র্যও ধরা পড়ে।
    """
    section = _find_issue_section(issue_body, "Touching Files")
    if not section:
        return set()
    paths: set[str] = set()
    # backtick-quoted paths: `path/to/file.py` (canonical — atomic_claim.sh format)
    for pm in re.finditer(r"`([^`]+\.[a-zA-Z]\w*)`", section):
        paths.add(pm.group(1).strip().lstrip("./"))
    # bare paths under bullets: - path/to/file.py (backtick বাদ দিয়ে)
    for pm in re.finditer(r"^\s*[-*]\s+([^\s`]+\.[a-zA-Z]\w*)", section, re.MULTILINE):
        paths.add(pm.group(1).strip().lstrip("./"))
    return paths


def _extract_evidence_text(issue_body: str) -> str:
    """linked issue-র `## Evidence` সেকশনের টেক্সট — keyword-anchor সোর্স (#3191)।

    #4222: হেডিং-শনাক্ত gate-চুক্তিতে একাত্ম (যেকোনো লেভেল + substring)।
    """
    return _find_issue_section(issue_body, "Evidence")


def _diff_value_signals(files: list, issues_data: list,
                        pr_body: str = "") -> dict[str, Any]:
    """বহু-সংকেত diff-value স্কোরিং (#3191 — smart evaluator)।

    বাংলা: চারটে স্বাধীন সংকেত যেকোনো একটি হলেই diff-এ আসল ভ্যালু আছে —
    metadata-গ্যাপ থাকলেও verdict CLOSE নয়, HOLD_AND_FIX। security-signal
    থাকলে close-protection ON — কখনো CLOSE নয়।
    """
    changed_paths: set[str] = set()
    patch_text = ""
    real_additions = 0
    for f in files or []:
        path = (f.get("path") or "").strip().lstrip("./")
        if path:
            changed_paths.add(path)
        patch_text += "\n" + (f.get("patch") or "")
        real_additions += int(f.get("additions") or 0)

    # ১. file-alignment — changed files ∩ any linked issue-র Touching Files
    all_touching: set[str] = set()
    aligned_issue: int | None = None
    for issue in issues_data or []:
        touching = _extract_touching_files(issue.get("body") or "")
        if touching:
            all_touching |= touching
            if aligned_issue is None and (changed_paths & touching):
                aligned_issue = int(issue.get("number") or 0)
    file_alignment = bool(changed_paths & all_touching) if all_touching else False

    # ২. keyword-anchors — Evidence-র identifier patch-এ আছে কিনা
    keyword_anchors = False
    for issue in issues_data or []:
        evidence = _extract_evidence_text(issue.get("body") or "")
        if not evidence:
            continue
        tokens: set[str] = set()
        # CLI flags: --accept-data-loss, --force
        for tm in re.finditer(r"--?[a-zA-Z][\w-]*", evidence):
            tokens.add(tm.group(0))
        # file paths: foo/bar.py
        for tm in re.finditer(r"[a-zA-Z_][\w./-]*\.(py|ts|js|tsx|jsx|yml|yaml|json|sh)",
                              evidence):
            tokens.add(tm.group(0))
        # backtick-quoted identifiers
        for tm in re.finditer(r"`([^`]{3,60})`", evidence):
            tokens.add(tm.group(1))
        for token in tokens:
            # বাংলা: শুধু ৪+ অক্ষরের token — short token false-positive এড়াতে
            if len(token) >= 4 and token in patch_text:
                keyword_anchors = True
                break
        if keyword_anchors:
            break

    # ৩. security patterns
    security_matches: list[str] = []
    for label, pattern in SECURITY_DIFF_PATTERNS:
        if pattern.search(patch_text):
            security_matches.append(label)
    security_signal = bool(security_matches)

    # ৪. substantive — সত্যিকারের কোড-সংযোজন (whitespace/index-only নয়)
    substantive = real_additions > 0 and bool(changed_paths)

    return {
        "file_alignment": file_alignment,
        "aligned_issue": aligned_issue,
        "keyword_anchors": keyword_anchors,
        "security_signal": security_signal,
        "security_matches": security_matches,
        "substantive": substantive,
        "changed_files": sorted(changed_paths)[:10],
    }


def checks_verdict(pr: dict) -> tuple[bool, list[str]]:
    """statusCheckRollup → (সবুজ?, ব্যর্থ-চেকের নাম) — ডায়নামিক, যেকোনো নতুন গেটসহ।

    #3207: conclusion-শূন্য চেক (in-progress) আর ব্যর্থতা নয় — চেক চলছে মাত্র;
    মিথ্যা "CI গেট লাল" hold-issue জন্ম নেয়নি (#3213/#3210-র মূল-কারণ)।
    """
    checks = pr.get("statusCheckRollup") or []
    if not checks:
        return False, ["কোনো CI-check রান হয়নি (গেট-প্রমাণ শূন্য)"]
    failed = [c.get("name", "?") for c in checks
              if c.get("conclusion") and c["conclusion"] not in OK_CONCLUSIONS]
    return (not failed), failed


def checks_pending(pr: dict) -> bool:
    """#3207: অন্তত একটি চেক এখনো চলছে (conclusion শূন্য) — In-Progress ≠ Broken।"""
    return any(not c.get("conclusion") for c in (pr.get("statusCheckRollup") or []))


# ── 2-ক্রাইটেরিয়া মূল্যায়ন ───────────────────────────────────────────────────

def evaluate_pr(pr: dict, api: Api = real_api, pol: dict | None = None) -> dict[str, Any]:
    """একটি PR-এর 2-ক্রাইটেরিয়া রায় — diff-aware (smart, #3191)।

    বাংলা: আগে শুধু metadata দিয়ে ভ্যালু বিচার হতো। এখন diff-content-ও দেখে —
    যদি diff-এ আসল ভ্যালু থাকে (file-alignment / keyword-anchor / security-signal /
    substantive+linked), তাহলে metadata-গ্যাপ থাকলেও verdict CLOSE নয়, HOLD_AND_FIX।
    security-signal থাকলে close-protection ON — কখনো CLOSE নয়।
    """
    pol = pol or load_policy()
    number = int(pr.get("number") or 0)
    title = pr.get("title") or ""
    body = pr.get("body") or ""
    author = ((pr.get("author") or {}).get("login")) or ""

    value_reasons: list[str] = []
    safety_reasons: list[str] = []
    metadata_gaps: list[str] = []  # #3191: metadata-only gaps (diff ভ্যালু থাকলে CLOSE-নয়)

    # ── ক্রাইটেরিয়া ১: Value — metadata + diff-content (smart) ──
    linked_list = parse_linked_issues(body, title)
    linked = linked_list[0] if linked_list else None  # primary (backward-compat)

    # বহু-ইস্যু fetch (#3191) — প্রতিটির বিপরীতে alignment আলাদা
    issues_data: list[dict] = []
    fetch_error = False
    for num in linked_list:
        issue = fetch_issue(api, num)
        if issue is None:
            fetch_error = True
        else:
            issues_data.append(issue)
    primary_issue = issues_data[0] if issues_data else None

    # metadata-gaps সংগ্রহ (এখনই fatal নয় — diff দেখে ঠিক করবে)
    # #3207: exempt/bot-লেখক (Dependabot/Renovate) synthetic `Refs #N`-মুক্ত —
    # টেমপ্লেট-গ্যাপ নয় (#2948-শিক্ষা: --pr মোডেও একই চুক্তি, evaluate_pr-এর ভেতরে)।
    exempt = is_exempt_author(author, pol)
    if exempt:
        pass  # ভ্যালু-চুক্তি: dependency-bump নিজেই; safety বিচার CI-gate দিয়ে
    else:
        if not linked_list:
            metadata_gaps.append("কোনো linked issue নেই — `Refs #N` (PR-টেমপ্লেট) বাধ্যতামূলক; কাজ-ইস্যু ছাড়া ভ্যালু প্রমাণ-অযোগ্য")
        elif fetch_error and not primary_issue:
            # #3037: issue fetch failed (API error) — HOLD, not CLOSE (don't punish for infra blip)
            metadata_gaps.append(f"linked issue #{linked} fetch failed (API error) — HOLD for safety (#3037)")
            safety_reasons.append("issue fetch error — cannot evaluate, holding (#3037)")
        elif primary_issue and primary_issue.get("state") != "open":
            metadata_gaps.append(f"linked issue #{linked} বন্ধ — সম্ভবত আগের আংশিক ফিক্সে বন্ধ; diff-alignment চেক করা হচ্ছে (#3191)")

        # #4222: Summary-শনাক্ত এখন template_gate-চুক্তি অনুযায়ী (যেকোনো হেডিং-লেভেল,
        # substring-match) — আর Refs #N পার্সার-চুক্তির (parse_linked_issues) সাথেই সংগত।
        if not _has_summary_section(body) or "Refs #" not in body:
            metadata_gaps.append("PR-টেমপ্লেট v2 অসম্পূর্ণ (## Summary + Refs #N লাগবে) — ইচ্ছার ঘোষণা যাচাই-যোগ্য নয়")

        if not TITLE_RE.match(title):
            metadata_gaps.append(f"টাইটেল কনভেনশনাল-ফরম্যাটে নয়: `type(scope): description` — পাওয়া গেছে: {title[:60]!r}")

    additions = int(pr.get("additions") or 0)
    deletions = int(pr.get("deletions") or 0)
    changed = int(pr.get("changedFiles") or 0)
    if changed == 0 or (additions == 0 and deletions > 0):
        metadata_gaps.append(f"অর্থবহ diff নেই (files={changed}, +{additions}/-{deletions}) — revert-only/খালি PR")

    # বাংলা (#4250): টাইটেল-গ্যাপ এখন শুধু guard-এর ভেতরে একবার সংগ্রহ হয় —
    # (১) non-exempt লেখকের খারাপ টাইটেলে আগে একই এন্ট্রি দুইবার append হতো
    # (gap_summary-তে কসমেটিক ডুপ্লিকেট); (২) exempt/bot লেখকের টাইটেল
    # conventional হয়ই না (#3207: dependency-bump নিজেই ভ্যালু-চুক্তি) —
    # guard-বাইরের append-site তাদের ভুয়া metadata-gap → ভুয়া HOLD দিত।

    # ── #3191: diff-aware value signals — smart scoring ──
    files = pr.get("files") or []
    signals = _diff_value_signals(files, issues_data, body)
    has_diff_value = (
        signals["file_alignment"]
        or signals["keyword_anchors"]
        or signals["security_signal"]
        or (signals["substantive"] and bool(linked_list))
    )
    close_protection = signals["security_signal"]

    metadata_clean = not metadata_gaps
    value_ok = metadata_clean or has_diff_value

    # diff-এ ভ্যালু থাকলে metadata-gaps → safety reason (HOLD, পেশাদার সারানোর জন্য)
    if has_diff_value and metadata_gaps:
        gap_summary = "; ".join(metadata_gaps[:3])
        safety_reasons.append(f"মেটাডেটা-গ্যাপ (diff-এ ভ্যালু নিশ্চিত — মেটাডেটা সারলে AUTO_MERGE): {gap_summary}")
    if signals["security_signal"]:
        sec_list = ", ".join(signals["security_matches"][:3])
        if not metadata_clean:
            safety_reasons.append(f"🔒 security-signal শনাক্ত — close-protection ON (CLOSE নয়): {sec_list}")
    if signals["file_alignment"] and signals["aligned_issue"]:
        # বাংলা: informative — diff linked issue-র Touching Files-এর সাথে সংগত
        if not metadata_clean:
            safety_reasons.append(f"diff linked issue #{signals['aligned_issue']}-এর Touching Files-এর সাথে সংগত — ভ্যালু নিশ্চিত")

    # value_reasons শুধু তখনই ভরা যখন diff-এ কোনো ভ্যালু নেই (CLOSE-প্রার্থী)
    if not has_diff_value:
        value_reasons = list(metadata_gaps)

    # ── ক্রাইটেরিয়া ২: Safety — রিগ্রেশন-মুক্ত + প্রক্রিয়া-বৈধ? (pending-বাদ, #3207)
    green, failed_checks = checks_verdict(pr)
    if not green:
        safety_reasons.append("CI গেট লাল: " + ", ".join(failed_checks[:6]) + ("…" if len(failed_checks) > 6 else ""))

    if pr.get("mergeable") is False:
        safety_reasons.append("main-এর সাথে merge-conflict — rebase/merge দরকার")

    fresh = fetch_freshness(api, pr.get("headRefName") or "", pr.get("baseRefName") or "main")
    if fresh.get("behind_by", 0) > 0:
        safety_reasons.append(
            f"PR-head সর্বশেষ main-এর {fresh['behind_by']} commit পেছনে — old-code-push ঝুঁকি "
            "(#2935 Freshness Gate-এ root-ব্লক); `git fetch origin && git merge origin/main` করুন"
        )

    # claim-chain check — প্রাথমিক ইস্যু + যেকোনো লিংকড ইস্যুতে claim আছে কিনা
    for issue in (issues_data or [primary_issue]):
        if not issue:
            continue
        labels = {lab.get("name", "") for lab in (issue.get("labels") or [])}
        issue_num = int(issue.get("number") or 0)
        if VIOLATING_LABEL in labels:
            safety_reasons.append(f"linked issue #{issue_num} `template:violating` — Mission/Priority/Touching Files/Verification সেকশন ঠিক না করলে claim-চেইন খোলা হবে না")
            break  # বাংলা: একটি violating ইস্যু যথেষ্ট — ডুপ্লিকেট কারণ এড়াতে
        if not (labels & CLAIM_LABELS) and not (issue.get("assignees") or []):
            safety_reasons.append(f"linked issue #{issue_num} এখনো unclaimed — atomic claim ছাড়া কাজ অস্বীকৃত (No Claim, No Code)")
            break

    safety_ok = not safety_reasons

    # ── রায় (founder-ম্যাট্রিক্স + #3191 close-protection)
    if value_ok and safety_ok:
        verdict = "AUTO_MERGE"
    elif value_ok and not safety_ok:
        verdict = "HOLD_AND_FIX"
    elif close_protection:
        # বাংলা (#3191): security-signal থাকা অবস্থায় value_ok False হলেও CLOSE নয় —
        # human review-এ HOLD। security fix চুপচাপ বন্ধ করা বিপজ্জনক।
        verdict = "HOLD_AND_FIX"
        safety_reasons.append("🔒 #3191 close-protection: diff-এ security-relevant পরিবর্তন শনাক্ত — "
                              "CLOSE এড়িয়ে human review (HOLD_AND_FIX)")
    else:
        verdict = "CLOSE"

    # #3207: In-Progress ≠ Broken — চেক-চলাকালীন premature auto-merge আটকাও,
    # কিন্তু মিথ্যা hold-issue/কমেন্ট জন্ম না করে। PENDING শুধু AUTO_MERGE-কেই
    # ধরে (প্রকৃত value/safety ত্রুটি থাকলে সেই সৎ রায়ই থাকে)।
    pending = checks_pending(pr)
    if pending and verdict == "AUTO_MERGE":
        verdict = "PENDING"

    return {
        "pr": number,
        "title": title,
        "author": author,
        "verdict": verdict,
        "criterion_1_value": value_ok,
        "criterion_2_safe": safety_ok,
        "value_reasons": value_reasons[: pol["max_reasons"]],
        "safety_reasons": safety_reasons[: pol["max_reasons"]],
        "checks_green": green,
        "fresh": fresh.get("behind_by", 0) == 0,
        "mergeable": pr.get("mergeable") is not False,
        "linked_issue": linked,
        "linked_issues": linked_list,  # #3191 — বহু-ইস্যু
        "value_signals": signals,  # #3191 — diff-aware signals
        "close_protection": close_protection,  # #3191 — security close-protection flag
        "checks_pending": pending,  # #3207 — In-Progress রায়-স্থগিত, regression নয়
        "exempt_author": exempt,  # #3207 — bot/exempt লেখক (Refs-মুক্ত লেন)
        "evaluated_at": now_utc(),
    }


# ── #3207: enrichment — diff-risk বিশ্লেষণ + LLM সেমান্টিক রিভিউ (fail-soft) ──

LLM_TIMEOUT_SECS = 20
DIFF_SNIPPET_LIMIT = 6000


def _llm_providers() -> list[dict[str, str]]:
    """কী-পুল (env) — Groq→Gemini→OpenRouter রাউন্ড-রবিন; কী না থাকলে খালি।

    বাংলা: কী শুধুই approved credential broker/env থেকে — কখনো hardcode নয়
    (AGENTS.md house doctrine)। CI-তে কী না থাকলে deterministic-evidence-ই সত্য।
    """
    providers: list[dict[str, str]] = []
    if os.getenv("GROQ_API_KEY"):
        providers.append({
            "name": "groq", "key": os.environ["GROQ_API_KEY"],
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "model": os.getenv("EVALUATOR_GROQ_MODEL") or "llama-3.3-70b-versatile",
        })
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
    if gemini_key:
        gem_model = os.getenv("EVALUATOR_GEMINI_MODEL") or "gemini-2.5-flash"
        providers.append({
            "name": "gemini", "key": gemini_key,
            "url": "https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{gem_model}:generateContent",
            "model": gem_model,
        })
    if os.getenv("OPENROUTER_API_KEY"):
        providers.append({
            "name": "openrouter", "key": os.environ["OPENROUTER_API_KEY"],
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "model": os.getenv("EVALUATOR_OPENROUTER_MODEL") or "openai/gpt-4o-mini",
        })
    return providers


def _llm_call(provider: dict[str, str], prompt: str) -> str | None:
    """এক provider-কল (নেটওয়ার্ক I/O); যেকোনো ব্যর্থতা → None (fail-soft)।"""
    try:
        if provider["name"] == "gemini":
            payload: dict[str, Any] = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 700},
            }
            headers = {"Content-Type": "application/json",
                       "x-goog-api-key": provider["key"]}
        else:  # groq/openrouter — OpenAI-compatible chat-completions
            payload = {
                "model": provider["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0, "max_tokens": 700,
            }
            headers = {"Authorization": f"Bearer {provider['key']}",
                       "Content-Type": "application/json"}
            if provider["name"] == "openrouter":
                headers["HTTP-Referer"] = f"https://github.com/{REPO}"
        req = urllib.request.Request(  # noqa: S310
            provider["url"], data=json.dumps(payload).encode(),
            method="POST", headers=headers,
        )
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECS) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        if provider["name"] == "gemini":
            return data["candidates"][0]["content"]["parts"][0]["text"]
        return data["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001 — provider ব্যর্থতা পাইপলাইন ভাঙবে না
        return None


def _parse_llm_json(raw: str | None) -> dict | None:
    """উত্তর থেকে STRICT-JSON অবজেক্ট পার্স (মার্কডাউন-ফেন্স সহ); ব্যর্থ → None।"""
    if not raw:
        return None
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _diff_risk_analysis(files: list) -> dict:
    """diff-risk সিগন্যাল — নাম-ই রিপোর্ট হয়, কখনো মান নয় (U2: রায় নয়, প্রমাণ)।

    বাংলা: secret-হিটে শুধু প্যাটার্ন-নাম+পাথ — ক্যাপচার-করা মান কোথাও যায় না।
    """
    risky_paths: list[str] = []
    secret_hits: list[str] = []
    test_files = 0
    source_files = 0
    for f in files or []:
        # বাংলা (#3207): runtime ফাইল-পে-লোডের চাবি `path` (gh pr view --json files,
        # _diff_value_signals-এর মতোই); `filename` REST-শেপ fallback।
        path = f.get("path") or f.get("filename") or ""
        if any(marker in path for marker in RISKY_PATH_MARKERS):
            risky_paths.append(path)
        if re.match(r"^(tests?/|test_[^/]+\.py$)|_test\.py$|\.test\.[jt]sx?$", path):
            test_files += 1
        else:
            source_files += 1
        patch = f.get("patch") or ""
        for name, pattern in SECRET_PATTERNS:
            if re.search(pattern, patch):
                secret_hits.append(f"{name}:{path}")
    return {
        "risky_paths": risky_paths[:8],
        "secret_pattern_hits": secret_hits[:8],
        "test_files": test_files,
        "source_files": source_files,
        "test_coverage_signal": test_files > 0 and source_files > 0,
        "large_diff": len(files or []) > 50,
    }


def _llm_review(title: str, analysis: dict, files: list) -> dict | None:
    """প্রোভাইডার-চেইন রাউন্ড-রবিন — প্রথম সফল STRICT-JSON-ই চূড়ান্ত; সব ব্যর্থ → None।"""
    providers = _llm_providers()
    if not providers:
        return None
    diff_chunks = []
    for f in files or []:
        patch = f.get("patch") or ""
        if patch:
            diff_chunks.append(f"--- {f.get('path') or f.get('filename')}\n{patch}")
    diff_text = "\n".join(diff_chunks)[:DIFF_SNIPPET_LIMIT]
    risky = ", ".join(analysis.get("risky_paths") or []) or "none"
    secrets = ", ".join(analysis.get("secret_pattern_hits") or []) or "none"
    prompt = (
        "You are a strict PR reviewer. Analyze the pull request diff for REAL regressions, "
        "security risks and scope drift. Respond with ONLY a JSON object, no prose:\n"
        '{"regression_risk": "low|medium|high", "summary": "<one-sentence value summary>", '
        '"concerns": ["<max 3 short concerns>"]}\n\n'
        f"PR title: {title}\n"
        f"Known risky paths: {risky}\n"
        f"Secret-pattern hits (names only): {secrets}\n"
        f"Diff (truncated):\n{diff_text}"
    )
    for provider in providers:
        data = _parse_llm_json(_llm_call(provider, prompt))
        if data and data.get("regression_risk") in ("low", "medium", "high"):
            return {
                "provider": provider["name"],
                "model": provider["model"],
                "regression_risk": str(data.get("regression_risk")),
                "summary": str(data.get("summary") or "")[:300],
                "concerns": [str(c)[:120] for c in (data.get("concerns") or [])[:3]],
            }
    return None


def _deterministic_summary(result: dict, analysis: dict) -> str:
    """কী-হীন/ব্যর্থ-পুল fallback — প্রমাণ-ভিত্তিক এক-লাইন সারাংশ (সৎ, বিনা-রায়)।"""
    bits: list[str] = []
    signals = result.get("value_signals") or {}
    if signals.get("security_signal"):
        bits.append("security-relevant diff (close-protection ON)")
    if signals.get("file_alignment"):
        bits.append(f"diff aligned with issue #{signals.get('aligned_issue')}")
    if analysis.get("test_coverage_signal"):
        bits.append("includes tests")
    if analysis.get("secret_pattern_hits"):
        bits.append(f"secret-pattern hits: {len(analysis['secret_pattern_hits'])}")
    if analysis.get("large_diff"):
        bits.append("large diff (>50 files)")
    if not bits:
        bits.append("metadata + gate evidence only")
    return "; ".join(bits[:3])


def evaluate_enrichment(result: dict, pr: dict) -> dict:
    """LLM-enrichment হুক — #3207 বাস্তব রূপ (interface অপরিবর্তিত)।

    বাংলা: verdict ওভাররাইড নিষিদ্ধ (আগের চুক্তিই) — enrichment শুধু confidence/
    summary/diff_analysis/llm_review যোগ করে। কী-পুল শূন্য → deterministic-
    evidence; সব provider ব্যর্থ → llm-unavailable (U2: সৎ-সংকেত, ভুয়া নয়)।
    """
    files = pr.get("files") or []
    analysis = _diff_risk_analysis(files)
    result["diff_analysis"] = analysis
    review = _llm_review(result.get("title") or "", analysis, files)
    if review:
        result["confidence"] = "llm-enriched"
        result["llm_review"] = review
        result["summary"] = review["summary"]
    else:
        if _llm_providers():
            result["confidence"] = "llm-unavailable"
        else:
            result["confidence"] = "deterministic-evidence"
        result["summary"] = _deterministic_summary(result, analysis)
    return result


# ── --apply: verdict-কমেন্ট + hold-issue (কারণসহ) ────────────────────────────

def verdict_marker(result: dict, pol: dict) -> str:
    """রায়+কারণ-ফিঙ্গারপ্রিন্ট — রায় বদলালে নতুন কমেন্ট, নাহলে dedup।"""
    digest = hashlib.md5(  # noqa: S324 — dedup-key, নিরাপত্তা নয়
        json.dumps([result["verdict"], result["value_reasons"], result["safety_reasons"]]).encode()
    ).hexdigest()[:12]
    return f"{pol['verdict_marker_prefix']}{result['pr']}:{result['verdict']}:{digest}-->"


def already_commented(api: Api, pr_number: int, marker: str) -> bool:
    comments = api(f"repos/{REPO}/issues/{pr_number}/comments?per_page=100") or []
    return any(marker in (c.get("body") or "") for c in comments)


VERDICT_BADGES = {
    "AUTO_MERGE": "🚀 **AUTO_MERGE** — Instant Auto-Merge candidate",
    "PENDING": "⏳ **PENDING** — CI checks চলছে (in-progress ≠ broken, #3207)",
    "HOLD_AND_FIX": "⏳ **HOLD_AND_FIX** — কাজের ভ্যালু আছে, সুরক্ষা-সারি লাগবে",
    "CLOSE": "🛑 **CLOSE** — ভ্যালু-প্রমাণ অপর্যাপ্ত",
}


def render_verdict_comment(result: dict, pol: dict) -> str:
    lines = [
        verdict_marker(result, pol),
        f"## 🤖 AI PR Evaluator (#2935) — {VERDICT_BADGES[result['verdict']]}",
        "",
        f"**2-ক্রাইটেরিয়া ম্যাট্রিক্স** · মূল্যায়ন: {result['evaluated_at']} · "
        f"কনফিডেন্স: `{result.get('confidence', 'deterministic-evidence')}`",
        "",
        f"| ক্রাইটেরিয়া | ফল |",
        f"|---|---|",
        f"| ১ — Value (বাস্তব সমস্যা সমাধান) | {'✅' if result['criterion_1_value'] else '❌'} |",
        f"| ২ — Safety (রিগ্রেশন-মুক্ত + প্রক্রিয়া-বৈধ) | {'✅' if result['criterion_2_safe'] else '❌'} |",
    ]
    # #3191: diff-aware signals section — smart evaluator-র প্রমাণ
    signals = result.get("value_signals") or {}
    if signals:
        sig_flags = []
        if signals.get("security_signal"):
            sig_flags.append(f"🔒 security ({', '.join(signals['security_matches'][:3])})")
        if signals.get("file_alignment"):
            sig_flags.append(f"📂 file-alignment #{signals.get('aligned_issue')}")
        if signals.get("keyword_anchors"):
            sig_flags.append("🔗 keyword-anchors")
        if signals.get("substantive"):
            sig_flags.append("✏️ substantive")
        if sig_flags:
            lines.append("")
            lines.append("**Diff-সংকেত (#3191 smart scan):** " + " · ".join(sig_flags))
            if result.get("close_protection"):
                lines.append("_🔒 close-protection ON — diff-এ security-relevant পরিবর্তন → CLOSE নয়_")
    # #3207: enrichment-সেকশন — সৎ-সংকেত (summary + risk); রায় কখনো নয়
    if result.get("summary"):
        lines.append("")
        lines.append(f"**AI-সারাংশ ({result.get('confidence', 'deterministic-evidence')}):** {result['summary']}")
        review = result.get("llm_review") or {}
        if review:
            lines.append(f"**LLM regression-risk:** `{review.get('regression_risk')}` · "
                         f"provider: {review.get('provider')}/{review.get('model')}")
            lines += [f"- ⚠️ {c}" for c in review.get("concerns") or []]
        analysis = result.get("diff_analysis") or {}
        risk_bits = []
        if analysis.get("risky_paths"):
            risk_bits.append("risky-paths: " + ", ".join(analysis["risky_paths"][:3]))
        if analysis.get("secret_pattern_hits"):
            risk_bits.append(f"secret-patterns: {len(analysis['secret_pattern_hits'])} (নাম-মাত্র)")
        if analysis.get("test_coverage_signal"):
            risk_bits.append("tests-included")
        if risk_bits:
            lines.append("**Diff-risk:** " + " · ".join(risk_bits))
    if result["value_reasons"]:
        lines.append("\n**Value-কারণ (Criterion 1):**")
        lines += [f"- ❌ {r}" for r in result["value_reasons"]]
    if result["safety_reasons"]:
        lines.append("\n**Safety-কারণ (Criterion 2):**")
        lines += [f"- ⚠️ {r}" for r in result["safety_reasons"]]
    if result["verdict"] == "AUTO_MERGE":
        lines.append(
            "\n🚀 সব সংকেত সবুজ — Instant Auto-Merge candidate। "
            "এক্সিকিউশন-লুপ (seq:2) চালু হলে স্বয়ংক্রিয়ভাবে main-এ যাবে।"
        )
    elif result["verdict"] == "HOLD_AND_FIX":
        lines.append(
            "\n⏳ এই PR **Hold**-এ — প্রতিটি কারণ সহ একটি fix-issue "
            f"(`{pol['group_label']}` গ্রুপে) তৈরি/হালনাগাদ করা হয়েছে — ci-fixer এজেন্টরা "
            "সেখান থেকে claim করে সারাতে পারবে। সব কারণ সবুজ হলেই রায় বদলে AUTO_MERGE হবে।"
        )
    elif result["verdict"] == "PENDING":
        lines.append(
            "\n⏳ CI চেকগুলো এখনো চলছে (in-progress ≠ broken, #3207) — রায় স্থগিত; "
            "এটি কোনো regression নয়। চেক শেষ হলে পরবর্তী মূল্যায়নে চূড়ান্ত রায় আসবে।"
        )
    else:
        lines.append(
            "\n🛑 প্রস্তাবিত রায় CLOSE — কারণগুলো সারানোর পথ খোলা: linked issue + Refs + "
            "টেমপ্লেট + অর্থবহ diff যোগ করলে পুনরায় মূল্যায়নে রায় বদলাবে।"
        )
    lines.append("\n_#2935 seq:1 (ইঞ্জিন) — #3191 diff-aware + #3207 LLM-enrichment; মন্তব্য dedup: রায়/কারণ বদলালেই নতুন কমেন্ট।_")
    return "\n".join(lines)


def pr_issue_marker(pr_number: int, pol: dict) -> str:
    """pipeline_failure_register.py-র সাথে শেয়ার্ড চুক্তি — একই per-PR ইস্যু।"""
    return f"{pol['hold_marker_prefix']}pr:{pr_number}-->"


def find_pr_fix_issue(api: Api, pr_number: int, pol: dict) -> int | None:
    marker = pr_issue_marker(pr_number, pol)
    issues = api(f"repos/{REPO}/issues?state=open&labels=ci-failure&per_page=100") or []
    for issue in issues:
        if marker in (issue.get("body") or ""):
            return int(issue["number"])
    return None


def render_hold_issue_body(result: dict, pol: dict) -> str:
    """টেমপ্লেট-সম্মত hold-issue (Mission/Touching Files/Verification + P-টোকেন)।"""
    pr_number = result["pr"]
    linked = result.get("linked_issue")
    reasons = result["safety_reasons"] or result["value_reasons"] or ["(মূল্যায়ন-কারণ দেখুন)"]
    return (
        f"{pr_issue_marker(pr_number, pol)}\n"
        f"## Mission\n\n"
        f"**PR #{pr_number}** — HOLD_AND_FIX রায় (AI PR Evaluator #2935): কাজের ভ্যালু আছে, "
        f"কিন্তু নিচের কারণগুলো সারা না হওয়া পর্যন্ত merge-অযোগ্য। প্রতিটি কারণ আলাদাভাবে "
        f"সমাধানযোগ্য — একটিমাত্র এজেন্টের পুরো PR-মালিকার দরকার নেই।\n\n"
        f"### Hold-কারণ (আলাদা আলাদা সমাধানযোগ্য)\n"
        + "\n".join(f"- [ ] ⚠️ {r}" for r in reasons)
        + "\n\n"
        f"### PR-প্রসঙ্গ\n"
        f"| Field | Value |\n|---|---|\n"
        f"| PR | [#{pr_number}](https://github.com/{REPO}/pull/{pr_number}) |\n"
        f"| Linked issue | {f'#{linked}' if linked else '— (Refs #N যোগ করতে হবে)'} |\n"
        f"| Verdict | `{result['verdict']}` @ {result['evaluated_at']} |\n\n"
        f"## Touching Files\n\n"
        f"```text\n"
        f"Touching files: PR #{pr_number}-এর ফাইল-সেট (gh pr view {pr_number} --json files) — "
        f"কারণ-নির্দিষ্ট ফাইল claim-কমেন্টে ঘোষণা করতে হবে\n"
        f"```\n\n"
        f"## Verification\n\n"
        f"1. প্রতিটি hold-কারণ সারা হলে চেকবক্স টিক দিন + প্রমাণ-লিংক\n"
        f"2. `python scripts/ci/ai_pr_evaluator.py --pr {pr_number}` → AUTO_MERGE রায় নিশ্চিত\n"
        f"3. PR-গেট সবুজ + Freshness Gate PASS (নতুন main-এর সাথে synced)\n\n"
        f"**Priority:** P2-medium\n"
    )


def ensure_hold_issue(api: Api, result: dict, pol: dict) -> int:
    """HOLD_AND_FIX → per-PR fix-issue (শেয়ার্ড মার্কার-চুক্তি, dedup-সৃষ্টি)।"""
    existing = find_pr_fix_issue(api, result["pr"], pol)
    if existing:
        return existing
    issue = api(
        f"repos/{REPO}/issues", method="POST",
        payload={
            "title": f"fix(ci): [hold:{result['pr']}] PR #{result['pr']} HOLD_AND_FIX — কারণসহ self-heal তালিকা",
            "body": render_hold_issue_body(result, pol),
            "labels": pol["hold_labels"],
        },
    )
    return int(issue["number"])


def apply_verdict(api: Api, result: dict, pol: dict) -> dict[str, Any]:
    """রায় প্রয়োগ: PR-কমেন্ট (dedup) + HOLD → hold-issue জন্ম/হালনাগাদ।"""
    actions: dict[str, Any] = {"commented": False, "hold_issue": None}
    marker = verdict_marker(result, pol)
    if result["verdict"] == "PENDING":
        # #3207: PENDING-এ নয়েজ-মুক্ত — চেক চলাকালীন কোনো কমেন্ট/hold-issue নয়;
        # comment_on_auto_merge সেটিং-এর খাতিরেও কমেন্ট ফেরানো হয় না।
        wants_comment = False
    else:
        wants_comment = (
            result["verdict"] != "AUTO_MERGE"
            or pol.get("comment_on_auto_merge", True)
        )
    if wants_comment and not already_commented(api, result["pr"], marker):
        api(f"repos/{REPO}/issues/{result['pr']}/comments", method="POST",
            payload={"body": render_verdict_comment(result, pol)})
        actions["commented"] = True
    if result["verdict"] == "HOLD_AND_FIX":
        actions["hold_issue"] = ensure_hold_issue(api, result, pol)
    return actions


# ── স্ক্যান (সব open PR — ডায়নামিক) ──────────────────────────────────────────

def list_open_prs(api: Api) -> list[dict]:
    return api(f"repos/{REPO}/pulls?state=open&per_page=50") or []


def scan(api: Api = real_api, gh: Gh = real_gh, pol: dict | None = None,
         apply: bool = False) -> dict[str, Any]:
    """সব open PR মূল্যায়ন → verdict-map (+ --apply হলে কমেন্ট/hold-issue)।"""
    pol = pol or load_policy()
    if not pol.get("enabled", True):
        return {"skipped": "policy disabled"}
    results = []
    skipped = []
    for pr in list_open_prs(api):
        number = int(pr.get("number") or 0)
        author = ((pr.get("user") or {}).get("login")) or ""
        if pr.get("draft"):
            skipped.append({"pr": number, "why": "draft"})
            continue
        if author in set(pol["exempt_authors"]):
            skipped.append({"pr": number, "why": f"exempt author {author}"})
            continue
        try:
            detail = fetch_pr(gh, number)  # fallback internally (#4291)
            result = evaluate_enrichment(evaluate_pr(detail, api=api, pol=pol), detail)
            if apply:
                result["actions"] = apply_verdict(api, result, pol)
            results.append(result)
        except Exception as exc:  # noqa: BLE001 — এক PR-ব্যর্থতা পুরো স্ক্যান থামাবে না
            skipped.append({"pr": number, "why": f"error: {str(exc)[:120]}"})
    return {
        "evaluated": len(results),
        "verdicts": {r["pr"]: r["verdict"] for r in results},
        # বাংলা মন্তব্য: on_hold = রায়-ভিত্তিক (apply-নির্বিশেষে); hold_issues =
        # apply-করা স্ক্যানে জন্ম/পুনঃব্যবহৃত ইস্যু-নম্বর।
        "on_hold": [r["pr"] for r in results if r["verdict"] == "HOLD_AND_FIX"],
        "hold_issues": {r["pr"]: r["actions"]["hold_issue"] for r in results
                        if r.get("actions", {}).get("hold_issue")},
        "skipped": skipped,
        "results": results,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="AI PR Evaluator (#2935) — 2-criteria Merge/Hold/Close")
    parser.add_argument("--pr", type=int, default=None, help="একটি PR মূল্যায়ন")
    parser.add_argument("--scan", action="store_true", help="সব open PR মূল্যায়ন")
    parser.add_argument("--apply", action="store_true", help="verdict-কমেন্ট + hold-issue (নেটওয়ার্ক-লেখা)")
    # #3015: instant-merge জব (ai-pr-evaluation.yml) --pr N --json কল করে —
    # ফ্ল্যাগটি না থাকায় argparse exit-2 → verdict চির-খালি → চির-নিষ্ক্রিয় merge।
    # --pr মোডে stdout আগেই JSON; ফ্ল্যাগটি চুক্তিটিকে বাস্তব+ডকুমেন্টেড করে।
    parser.add_argument("--json", action="store_true", help="stdout-এ JSON-আউটপুট (--pr মোডের ডিফল্ট; স্পষ্টতার জন্য)")
    parser.add_argument("--strict-exit", action="store_true",
                        help="exit-code = verdict (0=AUTO_MERGE, 5=PENDING, 3=HOLD_AND_FIX, 4=CLOSE) — টেস্ট/CI-চুক্তি")
    args = parser.parse_args()

    pol = load_policy()
    if not pol.get("enabled", True):
        print(json.dumps({"skipped": "policy disabled"}, ensure_ascii=False))
        return 0

    if args.pr:
        detail = fetch_pr(real_gh, args.pr)  # fallback internally (#4291)
        result = evaluate_enrichment(evaluate_pr(detail, pol=pol), detail)
        if args.apply:
            result["actions"] = apply_verdict(real_api, result, pol)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"\n🤖 PR #{result['pr']} → {VERDICT_BADGES[result['verdict']]}", file=sys.stderr)
        return EXIT_CODES[result["verdict"]] if args.strict_exit else 0

    if args.scan:
        summary = scan(apply=args.apply, pol=pol)
        compact = {k: summary[k] for k in ("evaluated", "verdicts", "on_hold", "hold_issues", "skipped")}
        print(json.dumps(compact, ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
