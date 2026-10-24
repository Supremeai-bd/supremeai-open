#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Priority-Wise Sequential PR Merger (স্মার্ট প্রায়োরিটি-ভিত্তিক একক-মার্জার)
================================================================================
"টুলস ও টেকনিশিয়ান আগে" (Tools & Technician First) নীতির ভিত্তিতে ওপেন PR-গুলোকে
সঠিক ডিপেন্ডেন্সি অর্ডারে সাজিয়ে এক-এক করে স্বয়ংক্রিয়ভাবে ও নিরাপদে মার্জ করার ইঞ্জিন।

উন্নত ফিচারসমূহ (Enterprise Features):
1. GitHub App অথেনটিকেশন সাপোর্ট (Personal Access Token-এর বিকল্প হিসেবে হাই-রেট লিমিট ও বট আইডেন্টিটি)।
2. রিয়েল-টাইম ডাইনামিক রি-চেক (১ মার্জের পর ২-এর তাজা মার্জ-যোগ্যতা ও এসিঙ্ক ক্যাশ হ্যান্ডলিং)।
3. স্টপ-অন-কনফ্লিক্ট সেফটি গার্ড (কম্পাউন্ড কনফ্লিক্ট ও চেইন ব্রেক প্রতিরোধ)।
4. ইডেমপোটেন্ট ব্লকার ইস্যু হ্যান্ডলার (ডুপ্লিকেট ইস্যু স্প্যামিং প্রতিরোধ)।
5. মেইনে পোস্ট-মার্জ রিয়েল ফেচ ও ফাস্ট স্মোক ভেরিফিকেশন।

ব্যবহার:
    python scripts/ci/smart_priority_merger.py --plan
    python scripts/ci/smart_priority_merger.py --audit-evidence
    python scripts/ci/smart_priority_merger.py --dry-run [--limit 5]
    python scripts/ci/smart_priority_merger.py --execute [--limit 5] [--release-holds] [--app-auth]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# বাংলা মন্তব্য: উইন্ডোজ এবং সিআই-তে ইউনিকোড/বাংলা আউটপুট নিশ্চিত করতে utf-8 রিকনফিগারেশন
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("SmartMerger")


# ── প্রায়োরিটি স্তর সংজ্ঞা (Priority Tier Architecture) ────────────────────────
# বাংলা মন্তব্য: tier scores এখন config/merge_policy_registry.json থেকে load হয়।
# JSON না পাওয়া গেলে hardcoded fallback ব্যবহার হয় — module কখনো crash করে না।
_TIER_DEFAULTS: dict[str, int] = {
    "TIER_0_TOOLS_GOVERNANCE": 1000,
    "TIER_1_CONTRACTS_TYPES": 800,
    "TIER_2_DB_MIGRATIONS": 600,
    "TIER_3_CORE_BACKEND": 400,
    "TIER_4_FRONTEND_UI": 200,
    "TIER_5_JANITOR_CLEANUP": 100,
    "TIER_6_DEPENDENCIES": 50,
}


def _load_tier_scores() -> dict[str, int]:
    """মার্জ পলিসি registry JSON থেকে tier scores load করে।

    বাংলা মন্তব্য: SSOT নীতি — tier scores একটাই জায়গায় থাকবে।
    CI বা ops engineer JSON edit করলেই সব merger-এ effect পড়বে।
    """
    try:
        policy_path = REPO_ROOT / "config" / "merge_policy_registry.json"
        if not policy_path.exists():
            return _TIER_DEFAULTS.copy()
        import json as _json
        data = _json.loads(policy_path.read_text(encoding="utf-8"))
        tiers = data.get("tiers", {})
        scores = {k: int(v["score"]) for k, v in tiers.items() if "score" in v}
        # fallback: যে key JSON-এ নেই সেটা hardcoded default থেকে নেওয়া হয়
        return {**_TIER_DEFAULTS, **scores}
    except Exception as _e:
        logger.debug(f"merge_policy_registry.json tier load skipped: {_e}")
        return _TIER_DEFAULTS.copy()


_TIER_SCORES = _load_tier_scores()

# বাংলা মন্তব্য: #2571 — merge-before-gates রোধের মূল চুক্তি: এই গেটগুলো সবাই
# `completed && SUCCESS` না হলে merge নিষিদ্ধ। skipped/pending/missing — কোনোটাই green
# নয়। নাম হুবহু pr.yml-এর job name থেকে নেওয়া; গেট rename করলে এই তালিকাও আপডেট
# করতে হবে (এটাই স্পষ্ট required-gates চুক্তির উদ্দেশ্য)। Ops escape hatch:
# MERGE_TRAIN_REQUIRED_CHECKS=off দিলে নিষ্ক্রিয় (Admin-এর স্পষ্ট সিদ্ধান্তেই কেবল)।
_DEFAULT_REQUIRED_CHECKS = (
    "🚦 Unified PR Gate (Security, Scope & Policy Orchestrator)",
    "🧪 Test & Build Verification",
    "🛡️ Constitutional System Gates",
    "🔍 Resolve PR Context",
    "Branch Naming Guard",
)


def _required_check_names() -> List[str]:
    """বাংলা মন্তব্য: required-gates তালিকা — env override সমর্থন সহ।

    বিভাজক `|` — কারণ গেটের নামে নিজেই কমা থাকে (যেমন "Gate (Security, Scope...)"),
    কমা-বিভাজন নাম ভেঙে দেয়।
    """
    raw = (os.getenv("MERGE_TRAIN_REQUIRED_CHECKS") or "").strip()
    if raw.lower() in ("off", "none", "disabled"):
        return []
    if raw:
        return [n.strip() for n in raw.split("|") if n.strip()]
    return list(_DEFAULT_REQUIRED_CHECKS)


# বাংলা মন্তব্য: #2630 — "১০০% নিরাপদ auto-merge" চুক্তির মূল নিশ্চয়তা: অটোমেশন
# নিজের নিয়ম নিজে বদলাতে পারবে না (privilege-escalation প্রতিরোধ)। এই পাথগুলো
# স্পর্শ করা PR সব-সবুজ হলেও অ্যাডমিন-সিদ্ধান্তে থাকবে। registry-র
# `auto_merge.protected_paths` থেকে override করা যায়; ফলব্যাক hardcoded।
_PROTECTED_PATHS_FALLBACK = (
    ".github/workflows/*",
    ".github/constitution/*",
    ".github/scripts/*",
    "AGENTS.md",
    "config/merge_policy_registry.json",
)


def _load_protected_paths() -> List[str]:
    """registry থেকে auto_merge.protected_paths লোড — না থাকলে fallback।"""
    try:
        policy_path = REPO_ROOT / "config" / "merge_policy_registry.json"
        if policy_path.exists():
            import json as _json

            payload = _json.loads(policy_path.read_text(encoding="utf-8"))
            paths = (payload.get("auto_merge") or {}).get("protected_paths")
            if isinstance(paths, list) and paths:
                return [str(p) for p in paths if str(p).strip()]
    except (OSError, ValueError):  # noqa: BLE001 — policy ফাইল ভাঙলেও merger বন্ধ হবে না
        pass
    return list(_PROTECTED_PATHS_FALLBACK)


_PROTECTED_PATHS = _load_protected_paths()


def find_protected_path_hits(paths: List[str], patterns: List[str]) -> List[str]:
    """পরিবর্তিত ফাইল-পাথের মধ্যে protected-path স্পর্শ শনাক্ত করে (pure ফাংশন)।

    বাংলা মন্তব্য: fnmatch প্যাটার্ন ম্যাচিং — case-insensitive (GitHub পাথ
    case-sensitive হলেও রক্ষণাবেক্ষণে ভুল-ধরা গুরুত্বপূর্ণ)। স্পর্শ হলে hit
    পাথগুলোই ফেরত — evaluate_pr_checks এটাকে block-reason বানায়।
    """
    import fnmatch

    hits: List[str] = []
    for path in paths or []:
        lowered = str(path).strip().lower()
        if not lowered:
            continue
        for pattern in patterns or []:
            if fnmatch.fnmatch(lowered, str(pattern).strip().lower()):
                hits.append(str(path))
                break
    return hits

TIER_0_TOOLS_GOVERNANCE = _TIER_SCORES["TIER_0_TOOLS_GOVERNANCE"]
TIER_1_CONTRACTS_TYPES  = _TIER_SCORES["TIER_1_CONTRACTS_TYPES"]
TIER_2_DB_MIGRATIONS    = _TIER_SCORES["TIER_2_DB_MIGRATIONS"]
TIER_3_CORE_BACKEND     = _TIER_SCORES["TIER_3_CORE_BACKEND"]
TIER_4_FRONTEND_UI      = _TIER_SCORES["TIER_4_FRONTEND_UI"]
TIER_5_JANITOR_CLEANUP  = _TIER_SCORES["TIER_5_JANITOR_CLEANUP"]
TIER_6_DEPENDENCIES     = _TIER_SCORES["TIER_6_DEPENDENCIES"]

# গ্লোবাল অথ টোকেন ক্যাশ (GitHub App টোকেন থাকলে এখানে সংরক্ষিত হবে)
_ACTIVE_APP_TOKEN: Optional[str] = None


@dataclass
class PROrderItem:
    number: int
    title: str
    branch: str
    author: str
    tier_name: str
    priority_score: int
    mergeable: str
    labels: List[str]
    created_at: str
    additions: int
    deletions: int
    checks_summary: str = "PENDING"
    is_ready_to_merge: bool = False
    is_held: bool = False
    evidence_status: str = "UNKNOWN"
    block_reasons: List[str] = field(default_factory=list)


# ── GitHub App অথেনটিকেশন হেল্পার (Token Minter) ──────────────────────────────
def mint_github_app_token(app_id: str, installation_id: str, private_key_pem: str) -> Optional[str]:
    """
    বাংলা মন্তব্য: GitHub App-এর App ID ও Private Key দিয়ে একটি স্বল্পমেয়াদি
    Installation Access Token তৈরি করা (যা ১ ঘণ্টা মেয়াদি এবং এতে হাই-রেট লিমিট থাকে)।
    """
    try:
        import urllib.request
        try:
            import jwt  # PyJWT
        except ImportError:
            logger.warning("PyJWT লাইব্রেরি নেই। GitHub App টোকেন মিন্ট করতে 'pip install pyjwt cryptography' প্রয়োজন।")
            return None

        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 600, "iss": app_id}
        encoded_jwt = jwt.encode(payload, private_key_pem, algorithm="RS256")

        url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
        req = urllib.request.Request(
            url,
            method="POST",
            headers={
                "Authorization": f"Bearer {encoded_jwt}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "SupremeAI-SmartMerger",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
            token = data.get("token")
            if token:
                logger.info("🔑 GitHub App Installation Token সফলভাবে জেনারেট করা হয়েছে!")
                return token
        return None
    except Exception as e:
        logger.error(f"GitHub App টোকেন তৈরিতে ব্যর্থ: {e}")
        return None


def get_cmd_env() -> Dict[str, str]:
    """বাংলা মন্তব্য: GitHub App টোকেন সক্রিয় থাকলে GH_TOKEN এনভায়রনমেন্ট ভ্যারিয়েবলে ইনজেক্ট করা।"""
    env = os.environ.copy()
    if _ACTIVE_APP_TOKEN:
        env["GH_TOKEN"] = _ACTIVE_APP_TOKEN
    return env


def run_gh_json(cmd: List[str]) -> Any:
    """বাংলা মন্তব্য: gh CLI কমান্ড রান করে JSON আউটপুট পার্স করা।"""
    try:
        res = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=get_cmd_env(),
            check=False,
        )
        if res.returncode != 0:
            return None
        return json.loads(res.stdout) if res.stdout.strip() else None
    except Exception as e:
        logger.error(f"Error executing gh json command: {e}")
        return None


def run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    """বাংলা মন্তব্য: জেনেরিক শেল কমান্ড এক্সিকিউট করা।"""
    res = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=get_cmd_env(),
        check=False,
    )
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def calculate_pr_tier(pr: Dict[str, Any]) -> Tuple[int, str]:
    """
    বাংলা মন্তব্য: 'টুলস ও টেকনিশিয়ান আগে' নীতির পরিমার্জিত স্তর বিন্যাস।
    """
    title = (pr.get("title") or "").lower()
    author = (pr.get("author", {}).get("login") or "").lower()
    labels = [l.get("name", "").lower() for l in pr.get("labels") or []]
    files = [f.get("path", "").lower() for f in pr.get("files") or []]

    # ১. স্তর ৬: থার্ড পার্টি ডিপেন্ডেন্সি বাম্প (Dependabot / 43 updates)
    if author in ("app/dependabot", "dependabot[bot]") or "bump the backend-dependencies" in title or ("dependencies" in title and "bump" in title):
        return TIER_6_DEPENDENCIES, "Tier 6 (External Dependencies)"

    # ২. স্তর ৫: ডেড কোড, ডকুমেন্ট প্রুনিং ও ক্লিনআপ (আগে চেক করা যাতে Tier 0 তে না যায়)
    is_prune_title = any(term in title for term in ("prune 27 dead", "delete 33 dead", "delete 10 dead", "delete 5 dead", "chore(cleanup)"))
    is_cleanup_label = any(lbl in ("cleanup", "area:cleanup") for lbl in labels)
    if is_prune_title or is_cleanup_label:
        return TIER_5_JANITOR_CLEANUP, "Tier 5 (Pruning & Cleanup)"

    # ৩. স্তর ০: টুলস ও টেকনিশিয়ান (Governance, Agent Fleet, CI Rules & Constitution)
    is_governance = any(lbl in ("type:governance", "area:ci", "constitution", "charter") for lbl in labels)
    is_governance_title = any(prefix in title for prefix in ("feat(governance)", "fix(governance)", "fix(ci)", "chore(governance)", "refactor(tooling)", "fix(deploy-train)"))
    is_governance_code_files = any(
        f.startswith(".github/workflows/")
        or f.startswith(".github/scripts/")
        or f.startswith(".github/constitution/")
        or f.startswith("scripts/agents/")
        or f.startswith("scripts/ci/")
        or f == "agents.md"
        or f == ".github/constitution/rules.yml"
        for f in files
        if not f.endswith(".md") or f == "agents.md"
    )
    if is_governance or is_governance_title or is_governance_code_files:
        return TIER_0_TOOLS_GOVERNANCE, "Tier 0 (Tools & Technician Governance)"

    # ৪. স্তর ১: কন্ট্রাক্ট, স্কিমা ও ইন্টারফেস
    is_contract = any("contracts" in f or "schemas" in f or "types" in f or "interfaces" in f for f in files)
    is_contract_title = any(term in title for term in ("contract", "schema", "interface", "leaf contract", "truth-sync", "test isolation"))
    if is_contract or is_contract_title:
        return TIER_1_CONTRACTS_TYPES, "Tier 1 (Contracts & Types)"

    # ৫. স্তর ২: ডাটাবেজ স্কিমা ও মাইগ্রেশন
    is_migration = any("alembic_migrations" in f or "migration" in f for f in files)
    if is_migration or "migration" in title or "মাইগ্রেশন" in title:
        return TIER_2_DB_MIGRATIONS, "Tier 2 (Database Migrations)"

    # ৬. স্তর ৪: ফ্রন্টএন্ড ও ইউআই
    is_frontend = any(lbl == "area:frontend" for lbl in labels) or any(f.startswith("frontend/") for f in files) or "fix(frontend)" in title
    if is_frontend:
        return TIER_4_FRONTEND_UI, "Tier 4 (Frontend & UI)"

    # ৭. স্তর ৩: কোর ব্যাকএন্ড ও বিজনেস লজিক (Default)
    return TIER_3_CORE_BACKEND, "Tier 3 (Backend Core & Logic)"


def check_pr_evidence(body: str) -> Tuple[bool, str]:
    """
    বাংলা মন্তব্য: সংবিধানের Verification Gate অনুযায়ী PR বডিতে Test Evidence ও
    ভ্যালিড মার্কার (passed, pytest, unittest, ইত্যাদি) আছে কি না যাচাই করা।
    """
    if not body or not body.strip():
        return False, "Body is empty"

    names = ["Test Evidence", "Tests", "পরীক্ষা", "টেস্ট এভিডেন্স"]
    pattern = re.compile(rf"^#+\s*(?:.*)?({'|'.join(re.escape(n) for n in names)}).*$", re.IGNORECASE | re.MULTILINE)
    m = pattern.search(body)
    if not m:
        return False, "Missing '## Test Evidence' heading"

    section_text = body[m.end():]
    next_heading = re.search(r"^#+\s+", section_text, re.MULTILINE)
    if next_heading:
        section_text = section_text[:next_heading.start()]

    text = section_text.strip().lower()
    if len(text) < 40:
        return False, f"Evidence text too short ({len(text)} < 40 chars)"

    # বাংলা মন্তব্য (#3032 P0): সাবস্ট্রিং মার্কার ম্যাচ বিপজ্জনক ছিল —
    # "0 failed" "10 failed"-এর ভেতরে ম্যাচ করত, "passed" "not passed"/"0 passed"-এও
    # ম্যাচ করত। word-boundary + negative lookbehind রেজেক্সে সংশোধিত;
    # এবং বাক্স-তৈরি "Automated verification evidence" লাইন কখনও প্রমাণ গণ্য হবে না।
    text = "\n".join(
        ln for ln in text.splitlines()
        if "automated verification evidence:" not in ln
    ).strip()
    marker_patterns = [
        re.compile(r"(?<!not )(?<!\b0 )\bpassed\b", re.IGNORECASE),
        re.compile(r"\bpytest\b", re.IGNORECASE),
        re.compile(r"\bunittest\b", re.IGNORECASE),
        re.compile(r"\bbun test\b", re.IGNORECASE),
        re.compile(r"\bvitest\b", re.IGNORECASE),
        re.compile(r"\b0 failed\b", re.IGNORECASE),
    ]
    # বাংলা মন্তব্য (#3032): স৆কশনে ব্যর্থ গণনা (N>0 failed)
    # থাকলে অন্য মার্কার থাকলেও এটা প্রমাণ নয় — লাল আউটপুট কখনও সবুজ নয়।
    m_fail = re.search(r"\b[1-9]\d* failed\b", text, re.IGNORECASE)
    if m_fail:
        return False, f"Evidence shows failing tests ('{m_fail.group(0)}') — paste a green run"

    matched = [pat.pattern for pat in marker_patterns if pat.search(text)]
    if matched:
        return True, f"Valid Test Evidence found (marker: {matched[0]})"

    return False, "Missing output markers (needs real test output: 'N passed', '0 failed', pytest/unittest command log)"


def heal_pr_body_evidence(body: str) -> str:
    """
    #3032 (P0) — non-mutating no-op (বাংলা মন্তব্য):
    আগে এই ফাংশন PR বডিতে কাল্পনিক "pytest passed" evidence লাইন
    বসিয়ে Verification Gate ফাঁকি দিত — এটা ছিল
    সিস্টেম-ইন্টিগ্রিটির ভাঙ্গন। এবার থেকে evidence
    কখনও আর তৈরি হয় না — বডি অপরিবর্তিত
    ফেরত দেয়; বাস্তব evidence PR লেখক/এজেন্টকেই
    পেস্ট করতে হবে (auto_heal_pr_evidence এখন
    রিমাইন্ডার কমেন্ট পোস্ট করে)।
    """
    return body



def auto_heal_pr_evidence(pr_num: int, current_body: str, rollup: Optional[List[Dict[str, Any]]] = None) -> bool:
    """
    বাংলা মন্তব্য (#3032 P0): পূর্বে এই ফাংশন বডিতে ভুয়া evidence
    লেখে Verification Gate পাস করাত — বডি-ইন্টেগ্রিটি দূষিত হত।
    নতুন আচরণ: বডি কখনও লেখা হয় না; evidence অপূর্ণ
    হলে রিমাইন্ডার কমেন্ট পোস্ট হয় (কমেন্ট gate
    সন্তুষ্ট করে না) এবং False রিটার্ন হয় —
    ফলে মার্জার এই PR HOLD করবে।
    """
    has_ev, msg = check_pr_evidence(current_body)
    if has_ev:
        return False

    logger.warning(
        f"🚫 PR #{pr_num}-এর Test Evidence অপূর্ণ ({msg}) — "
        "বডি আর স্বয়ংক্রিয়ভাবে সম্পাদনা হবে না (#3032); "
        "রিমাইন্ডার কমেন্ট পোস্ট করা হচ্ছে।"
    )

    comment_body = (
        "## 🧪 Test Evidence প্রয়োজন\n\n"
        "এই PR-এর Test Evidence সেকশনে সনাক্তযোগ্য টেস্ট-আউটপুট নেই। "
        "সত্যিকার টেস্ট চালিয়ে আউটপুট "
        "(কমান্ড + ফলাফল সারি) `## Test Evidence` "
        "সেকশনে পেস্ট করুন।\n\n"
        "_নোট: বডি অটো-এডিট করে ভুয়া evidence "
        "যোগ করা বন্ধ হয়েছে (#3032) — "
        "সত্য evidence ছাড়া এই PR মার্জ হবে না।_"
    )
    try:
        import tempfile
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".md") as tmp:
            tmp.write(comment_body)
            tmp_path = tmp.name

        res = subprocess.run(
            ["gh", "pr", "comment", str(pr_num), "--body-file", tmp_path],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=get_cmd_env(),
        )
        if res.returncode != 0:
            logger.error(f"❌ PR #{pr_num} রিমাইন্ডার কমেন্ট পোস্ট ব্যর্থ: {res.stderr.strip()}")
    except Exception as exc:  # noqa: BLE001 — হিল ব্যর্থ মার্জ-পাইপলাইন ভাঙ্বে না
        logger.error(f"❌ রিমাইন্ডার কমেন্ট ব্যর্থ: {exc}")

    return False



def heal_all_fleet_evidence(prs: List[Dict[str, Any]]) -> int:
    """
    বাংলা মন্তব্য: বহরের সমস্ত ওপেন PR স্ক্যান করে যাদের এভিডেন্স অপূর্ণ, তাদের একযোগে হিল করা।
    """
    logger.info("🩹 Scanning fleet for PRs requiring Test Evidence healing...")
    healed_count = 0
    for pr in prs:
        pr_num = pr.get("number")
        body = pr.get("body") or ""
        rollup = pr.get("statusCheckRollup") or []
        has_ev, _ = check_pr_evidence(body)
        if not has_ev:
            success = auto_heal_pr_evidence(pr_num, body, rollup=rollup)
            if success:
                healed_count += 1
                time.sleep(1)  # GitHub API রেট লিমিট প্রটেকশন
    logger.info(f"✨ মোট {healed_count}টি PR-এর এভিডেন্স সফলভাবে অটো-হিল ও সিআই রি-রান করা হয়েছে!")
    return healed_count



def evaluate_pr_checks(pr: Dict[str, Any], allow_holds: bool = False) -> Tuple[str, bool, bool, str, List[str]]:
    """
    বাংলা মন্তব্য: CI চেক রোলআপ, queue:hold এবং এভিডেন্স পরীক্ষা করা।
    """
    reasons: List[str] = []
    labels = [l.get("name", "").lower() for l in pr.get("labels") or []]
    is_held = "queue:hold" in labels
    no_checks = False

    if pr.get("isDraft"):
        reasons.append("PR is Draft")

    mergeable = pr.get("mergeable", "UNKNOWN")
    if mergeable == "CONFLICTING":
        reasons.append("Merge Conflict")

    body = pr.get("body") or ""
    has_ev, ev_msg = check_pr_evidence(body)
    evidence_status = "PASS" if has_ev else f"FAIL ({ev_msg})"
    if not has_ev:
        reasons.append(f"Evidence: {ev_msg}")

    if is_held and not allow_holds:
        reasons.append("queue:hold active (group sequence)")

    rollup = pr.get("statusCheckRollup") or []
    checks_map = {c.get("name"): (c.get("conclusion") or c.get("status")) for c in rollup}

    failing = [name for name, status in checks_map.items() if status in ("FAILURE", "ACTION_REQUIRED", "TIMED_OUT")]
    pending = [name for name, status in checks_map.items() if status in ("IN_PROGRESS", "QUEUED", "PENDING", None)]

    summary = "GREEN"
    if failing:
        summary = f"FAILED ({len(failing)})"
        reasons.append(f"CI Failing ({failing[0][:20]})")
    elif pending:
        summary = f"IN_PROGRESS ({len(pending)})"
        reasons.append("CI in-progress")
    elif not rollup:
        summary = "NO_CHECKS"
        no_checks = True
        # বাংলা মন্তব্য: #2571 — আগে এখানে কোনো reason যোগ হতো না, ফলে zero-check PR
        # "ready" হয়ে যেত (merge-before-gates ফাঁক)। এখন স্পষ্টভাবে ব্লক।
        reasons.append("NO_CHECKS (no gate results — nothing is proven green)")

    # বাংলা মন্তব্য: #2571 — required-gates চুক্তি: missing/skipped/pending/failed — সবই
    # non-green। SKIPPED আগে নীরবে green ধরা হতো; এখন কেবল SUCCESS-ই পাস করে।
    missing_required = [
        name
        for name in _required_check_names()
        if checks_map.get(name) != "SUCCESS"
    ]
    if missing_required and not no_checks:
        preview = ", ".join(missing_required[:3])
        if len(missing_required) > 3:
            preview += f" +{len(missing_required) - 3} more"
        reasons.append(f"Required gates not all-passed: {preview}")
        if summary == "GREEN":
            summary = "REQUIRED_GATES_INCOMPLETE"

    # বাংলা মন্তব্য: #2630 — protected-paths গার্ড: নিজের নিয়ম নিজে বদলানো নিষিদ্ধ।
    # সব গেট সবুজ হলেও এই পাথ স্পর্শ করলে অ্যাডমিন-সিদ্ধান্ত ছাড়া merge নয়।
    changed_paths = [f.get("path", "") for f in pr.get("files") or []]
    protected_hits = find_protected_path_hits(changed_paths, _PROTECTED_PATHS)
    if protected_hits:
        preview = ", ".join(protected_hits[:3])
        if len(protected_hits) > 3:
            preview += f" +{len(protected_hits) - 3} more"
        reasons.append(f"Protected paths (admin decision): {preview}")
        if summary == "GREEN":
            summary = "PROTECTED_PATHS"

    is_ready = len(reasons) == 0 and mergeable == "MERGEABLE"
    return summary, is_ready, is_held, evidence_status, reasons


def fetch_open_prs(limit: int = 100) -> List[Dict[str, Any]]:
    """বাংলা মন্তব্য: গিটহাব থেকে বিস্তারিত ফিল্ডসহ ওপেন PR-এর তালিকা ফেচ করা।"""
    fields = (
        "number,title,headRefName,author,mergeable,labels,createdAt,"
        "additions,deletions,statusCheckRollup,files,isDraft,body"
    )
    data = run_gh_json(["gh", "pr", "list", "--state", "open", "--limit", str(limit), "--json", fields])
    return data or []


def fetch_single_pr_fresh(pr_num: int, retries: int = 3) -> Optional[Dict[str, Any]]:
    """
    বাংলা মন্তব্য: মার্জের ঠিক পূর্বে কোনো PR-এর রিয়েল-টাইম লাইভ অবস্থা ফেচ করা।
    GitHub API-এর অ্যাসিঙ্ক ক্যাশ বাফার সামলাতে 'UNKNOWN' থাকলে ৩ বার রিট্রাই করবে।
    """
    fields = (
        "number,title,headRefName,author,mergeable,labels,createdAt,"
        "additions,deletions,statusCheckRollup,files,isDraft,body,state"
    )
    for attempt in range(1, retries + 1):
        data = run_gh_json(["gh", "pr", "view", str(pr_num), "--json", fields])
        if not data:
            return None
        mergeable = data.get("mergeable", "UNKNOWN")
        if mergeable != "UNKNOWN" or attempt == retries:
            return data
        logger.info(f"⏳ PR #{pr_num} mergeable is 'UNKNOWN' (GitHub calculating). Waiting 3s (attempt {attempt}/{retries})...")
        time.sleep(3)
    return data


def plan_priority_sequence(prs: List[Dict[str, Any]], allow_holds: bool = False) -> List[PROrderItem]:
    """বাংলা মন্তব্য: ওপেন PR-গুলোকে স্তর এবং স্কোর অনুযায়ী নিখুঁত সিকোয়েন্সে সাজানো।"""
    ordered_items: List[PROrderItem] = []

    for pr in prs:
        score_base, tier_name = calculate_pr_tier(pr)
        labels = [l.get("name", "") for l in pr.get("labels") or []]
        bonus = 0
        if "P0-critical" in labels or "type:blocker" in labels:
            bonus += 50
        elif "P1-high" in labels:
            bonus += 20

        additions = pr.get("additions", 0)
        deletions = pr.get("deletions", 0)
        if (additions + deletions) < 50:
            bonus += 5

        total_score = score_base + bonus
        summary, is_ready, is_held, ev_status, reasons = evaluate_pr_checks(pr, allow_holds=allow_holds)

        item = PROrderItem(
            number=pr["number"],
            title=pr["title"],
            branch=pr.get("headRefName", ""),
            author=pr.get("author", {}).get("login", ""),
            tier_name=tier_name,
            priority_score=total_score,
            mergeable=pr.get("mergeable", "UNKNOWN"),
            labels=labels,
            created_at=pr.get("createdAt", ""),
            additions=additions,
            deletions=deletions,
            checks_summary=summary,
            is_ready_to_merge=is_ready,
            is_held=is_held,
            evidence_status=ev_status,
            block_reasons=reasons,
        )
        ordered_items.append(item)

    ordered_items.sort(key=lambda x: (-x.priority_score, x.created_at))
    return ordered_items


def audit_evidence_fleet(items: List[PROrderItem]) -> None:
    """বাংলা মন্তব্য: সমস্ত PR-এর এভিডেন্স অবস্থা বিস্তারিত প্রদর্শন করা।"""
    print("\n" + "=" * 110)
    print("🔎 PR Test Evidence Health Audit (সংবিধান Verification Gate নিরীক্ষা)")
    print("=" * 110)
    print(f"{'PR #':<6} | {'Tier Name':<35} | {'Evidence':<25} | {'Title'}")
    print("-" * 110)
    for it in items:
        status_str = "✅ PASS" if it.evidence_status == "PASS" else f"❌ {it.evidence_status}"
        title_snip = it.title[:40] + "..." if len(it.title) > 40 else it.title
        print(f"#{it.number:<5} | {it.tier_name:<35} | {status_str:<25} | {title_snip}")
    print("=" * 110 + "\n")


def print_plan_table(items: List[PROrderItem]) -> None:
    """বাংলা মন্তব্য: কনসোলে নিখুঁত ও বিস্তারিত প্ল্যান টেবিল প্রিন্ট করা।"""
    print("\n" + "=" * 135)
    print("🏆 'টুলস ও টেকনিশিয়ান আগে' — স্মার্ট প্রায়োরিটি সিকোয়েন্স প্ল্যান (Sequential Merge Queue)")
    print("=" * 135)
    print(f"{'Rank':<5} | {'PR #':<6} | {'Tier Name':<32} | {'Score':<5} | {'Mergeable':<10} | {'State':<11} | {'Primary Blocker / Action':<35} | {'Title'}")
    print("-" * 135)

    for idx, item in enumerate(items, 1):
        if item.mergeable == "CONFLICTING":
            state_flag = "💥 CONFLICT"
            primary_reason = "Git conflict (rebase with main)"
        elif item.is_ready_to_merge:
            state_flag = "🟢 READY"
            primary_reason = "✅ All checks pass (ready to merge)"
        elif item.is_held:
            state_flag = "⏸️ HELD"
            primary_reason = item.block_reasons[0] if item.block_reasons else "queue:hold active"
        else:
            state_flag = "🔴 BLOCKED"
            primary_reason = item.block_reasons[0] if item.block_reasons else "CI checks failing"

        if len(primary_reason) > 34:
            primary_reason = primary_reason[:31] + "..."

        title_snippet = item.title[:24] + "..." if len(item.title) > 24 else item.title
        print(f"{idx:<5} | #{item.number:<5} | {item.tier_name:<32} | {item.priority_score:<5} | {item.mergeable:<10} | {state_flag:<11} | {primary_reason:<35} | {title_snippet}")

    print("=" * 135)
    total_ready = sum(1 for i in items if i.is_ready_to_merge)
    total_held = sum(1 for i in items if i.is_held)
    conflicts = sum(1 for i in items if i.mergeable == "CONFLICTING")
    print(f"📊 মোট PR: {len(items)} | মার্জের জন্য প্রস্তুত: {total_ready} | হোল্ডে আছে: {total_held} | কনফ্লিক্টযুক্ত: {conflicts}\n")


def list_open_issues_via_rest(max_pages: int = 3) -> Optional[List[Dict[str, Any]]]:
    """
    বাংলা মন্তব্য (#2603): REST /issues লিস্টিং — search-index নয়।
    `--search` GitHub-এর eventually-consistent search index ব্যবহার করে —
    নতুন issue তৈরির পর index-এ দৃশ্যমান হতে ~১০–৬০s লাগে (লাইভ প্রমাণ:
    #2599 + #2600, একই PR-এ হুবহু দুটি issue, ১৯s ব্যবধানে)। REST list
    endpoint read-your-writes consistent — এই ক্লাসের race মূলেই বন্ধ।
    ব্যর্থ হলে None (calling code fail-closed হবে)।
    """
    repo_slug = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")
    collected: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        batch = run_gh_json([
            "gh", "api",
            f"repos/{repo_slug}/issues?state=open&per_page=100&page={page}",
        ])
        if not isinstance(batch, list):
            return None if page == 1 else collected
        collected.extend(batch)
        if len(batch) < 100:
            break
    return collected


def match_open_conflict_issue(
    issues: Optional[List[Dict[str, Any]]], pr_num: int
) -> Optional[int]:
    """
    বাংলা মন্তব্য (#2603): deterministic Python-side ম্যাচ — একই strongly-
    consistent REST রেসপন্স থেকে দুই সিগন্যাল:
      (a) body marker `conflict-of: PR #<n>` — নতুন ফরম্যাট (machine-readable,
          টাইটেল-স্ট্রিং চুক্তির উপর নির্ভরশীল নয়)
      (b) title প্রিফিক্স `fix(conflict): PR #<n> ` — legacy ইস্যুর জন্য
          (label-যুগের আগে ফাইল হয়েছিল, #2599/#2600 প্যাটার্ন)
    PR এন্ট্রি (REST /issues-এ pull_request-ও আসে) বাদ; খুঁজে পেলে ইস্যু-নম্বর,
    না পেলে None।
    """
    if not issues:
        return None
    prefix = f"fix(conflict): PR #{pr_num} "
    marker = f"conflict-of: PR #{pr_num}"
    for item in issues:
        if not isinstance(item, dict) or "pull_request" in item:
            continue
        title = item.get("title") or ""
        body = item.get("body") or ""
        if title.startswith(prefix) or marker in body:
            num = item.get("number") or 0
            try:
                return int(num)
            except (TypeError, ValueError):
                continue
    return None


def is_conflict_issue_already_open(pr_num: int) -> bool:
    """
    বাংলা মন্তব্য: ইডেমপোটেন্সি চেক — এই PR-এর জন্য ইতিমধ্যে কোনো খোলা ইস্যু আছে কিনা যাচাই।
    এটি বারবার স্ক্রিপ্ট রান করলেও ডুপ্লিকেট ইস্যু স্প্যাম বন্ধ করে।

    (#2603) পুরনো `--search` (search-index, eventually-consistent) বাদ —
    REST লিস্ট + Python-side ম্যাচ। REST ব্যর্থ হলে fail-closed: সত্যি
    অবস্থা জানা নেই বলে তৈরির দাবিতে 'আছে' ধরে নিই (ডুপ্লিকেট রিস্ক >
    miss রিস্ক; পরের merger-রান আবার চেষ্টা করবে)।
    """
    issues = list_open_issues_via_rest()
    if issues is None:
        logger.error(
            "conflict-dedup (#2603): REST issue listing failed — "
            "fail-closed (skip create, alert পরের রানে ফাইল হবে)"
        )
        return True
    existing = match_open_conflict_issue(issues, pr_num)
    if existing:
        logger.info(f"ℹ️ conflict-dedup (#2603): existing issue #{existing} matched for PR #{pr_num}")
    return existing is not None


def handle_conflict_pr(pr_num: int, branch: str, title: str, author: str, trigger_pr_num: Optional[int] = None) -> None:
    """
    বাংলা মন্তব্য: কনফ্লিক্ট দেখা দিলে PR-এ queue:hold লাগানো এবং ইডেমপোটেন্ট উপায়ে GitHub Issue তৈরি করা।
    """
    logger.warning(f"⚠️ PR #{pr_num} has conflict! Adding 'queue:hold'...")

    # ১. queue:hold লেবেল যুক্ত করা
    subprocess.run(
        ["gh", "pr", "edit", str(pr_num), "--add-label", "queue:hold"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        env=get_cmd_env(),
    )

    # ২. ইডেমপোটেন্সি চেক — ইতিমধ্যে ইস্যু খোলা থাকলে ডুপ্লিকেট করবে না
    if is_conflict_issue_already_open(pr_num):
        logger.info(f"ℹ️ PR #{pr_num}-এর জন্য ইতিমধ্যে একটি কনফ্লিক্ট ইস্যু ওপেন রয়েছে। ডুপ্লিকেট স্কিপ করা হলো।")
        return

    prev_str = f"after merging PR #{trigger_pr_num}" if trigger_pr_num else "with current main branch"
    issue_title = f"fix(conflict): PR #{pr_num} has merge conflict {prev_str}"
    issue_body = (
        f"### Merge Conflict Alert\n\n"
        f"- **Conflicting PR**: #{pr_num} (`{branch}`)\n"
        f"- **Title**: {title}\n"
        f"- **Author**: @{author}\n"
        f"- **Trigger**: Dynamic conflict detected {prev_str}\n\n"
        f"#### Required Action:\n"
        f"১. লোকাল ব্রাঞ্চে মেইন সিঙ্ক করুন: `git checkout {branch} && git pull origin main`\n"
        f"২. কনফ্লিক্ট সমাধান করে ৩-স্তর টেস্ট যাচাই সম্পন্ন করুন।\n"
        f"৩. পুশ করুন ও `queue:hold` লেবেল রিমুভ করুন।\n\n"
        f"---\n"
        f"conflict-of: PR #{pr_num}"
    )
    # (#2603) বাংলা মন্তব্য: body-marker `conflict-of: PR #<n>` —
    # issue-filer-এর প্রস্তাবিত label `conflict:pr-<n>`-এর বদলে body-marker:
    # প্রতি PR-এ নতুন label = লেবেল-নেমস্পেস স্প্রল (#2596 ghost-state ক্লাস —
    # ইস্যু বন্ধ হলেও label ঝুলে থাকে, কেউ সরায় না)। একই REST রেসপন্সে
    # body আসে — determinism একই, স্প্রল শূন্য। লেগেসি title-প্রিফিক্স
    # ম্যাচও রাখা (marker-পূর্ববর্তী ইস্যু, যেমন #2633-প্যাটার্ন)।

    issue_res = subprocess.run(
        [
            "gh", "issue", "create",
            "--title", issue_title,
            "--body", issue_body,
            "--label", "type:blocker,area:ci",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=get_cmd_env(),
    )
    if issue_res.returncode == 0:
        logger.info(f"✅ Created conflict issue: {issue_res.stdout.strip()}")
    else:
        logger.error(f"❌ Failed to create conflict issue: {issue_res.stderr.strip()}")


def run_fast_smoke_check() -> bool:
    """
    বাংলা মন্তব্য: মার্জের পর মেইনে ৫-১০ সেকেন্ডের 'ছোট রান' (Fast Smoke Test)।
    প্রথমে রিমোট মেইন ফেচ করে নিশ্চিত করে যে টেস্টটি আসল মার্জ হওয়া কোড টেস্ট করছে।
    """
    logger.info("🧪 Fetching latest origin/main and running fast post-merge smoke check...")
    # ১. রিমোট মেইনের তাজা অবস্থা ফেচ করা
    run_cmd(["git", "fetch", "origin", "main"])

    # ২. স্মোক টেস্ট এক্সিকিউশন — রুট প্যাকেজ ও ব্যাকএন্ড ইমপোর্ট ভ্যালিডেশন
    cmd = [
        sys.executable,
        "-c",
        "import sys, os, backend, scripts; print('[OK] Fast Smoke: Core packages (backend, scripts) boot healthy.')",
    ]
    code, out, err = run_cmd(cmd)
    if code != 0:
        logger.error(f"❌ Fast smoke check FAILED on main! {err}")
        return False
    logger.info(out)
    return True


def execute_single_merge(pr_num: int, title: str, tier_name: str, labels: List[str]) -> bool:
    """বাংলা মন্তব্য: ১টি নির্দিষ্ট PR নিরাপদে মার্জ করা (Squash Merge)।"""
    logger.info(f"🚀 Merging PR #{pr_num}: '{title}' ({tier_name})...")

    # যদি queue:hold থাকে তবে মার্জের আগে সাময়িকভাবে তা খুলে দেওয়া
    if "queue:hold" in [l.lower() for l in labels]:
        subprocess.run(
            ["gh", "pr", "edit", str(pr_num), "--remove-label", "queue:hold"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            env=get_cmd_env(),
        )

    code, out, err = run_cmd(["gh", "pr", "merge", str(pr_num), "--squash"])
    if code != 0:
        code, out, err = run_cmd(["gh", "pr", "merge", str(pr_num), "--squash", "--auto"])

    if code == 0:
        logger.info(f"✅ Successfully merged PR #{pr_num}!")
        return True
    else:
        logger.error(f"❌ Failed to merge PR #{pr_num}: {err or out}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# #2645: Fully Intelligent Auto-Merge Engine (সম্পূর্ণ বুদ্ধিমান অটো-মার্জ ইঞ্জিন)
# ═══════════════════════════════════════════════════════════════════════════════
# বাংলা মন্তব্য: এই সেকশনের ৫টি স্তম্ভ (Pillar) — টেক্সট-কনফ্লিক্ট ছাড়াও লজিক্যাল
# (সিমান্টিক) কনফ্লিক্ট ধরা, AI-নিরাপত্তা-পর্যালোচনা, ভার্চুয়াল স্টেজিং সিমুলেশন,
# সেলফ-হিলিং ও ফ্ল্যাকি টেস্ট ট্রায়াজ। নকশা-নীতি:
#   ১. Fail-safe ডিফল্ট — প্রতিটি ফিচার env কিল-সুইচ দিয়ে বন্ধ করা যায়
#      (MERGE_TRAIN_SENTINEL / MERGE_TRAIN_SPECULATIVE / MERGE_TRAIN_AUTO_HEAL /
#       MERGE_TRAIN_FLAKY_RERUN — মান "off" হলে নিষ্ক্রিয়)।
#   ২. কী (API key) না থাকলে ফিচার নিঃশব্দে SKIPPED — কখনো crash নয়।
#   ৩. Pure লজিক ও I/O আলাদা — টেস্ট নেটওয়ার্ক ছাড়াই চলে (repo টেস্ট-চুক্তি)।
#   ৪. Ecosystem-First — বিদ্যমান run_cmd/run_gh_json/_PROTECTED_PATHS পুনঃব্যবহার।

# বাংলা মন্তব্য: সংবিধান-স্বীকৃত কোর মডিউল — এগুলোতে সিগনেচার-ড্রিপ্ট = HIGH রিস্ক
_SEMANTIC_CRITICAL_DIRS = (
    "backend/auth",
    "backend/payments",
    "backend/alembic_migrations",
    "backend/core/db",
)

# বাংলা মন্তব্য: সিগনেচার লাইন শনাক্তকারী regex — diff patch-এ +/- লাইন থেকে
# def/class সিগনেচার বের করা হয় (AST-বিকল্প হালকা পথ; patch-এ কনটেক্সট সীমিত)。
_SIGNATURE_LINE_RE = re.compile(
    r"^([+-])\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)\s*(\([^)]*\))?\s*[:=]?"
)


class SemanticRiskClassifier:
    """সিমান্টিক রিস্ক ও ডিপেন্ডেন্সি শ্রেণিবিন্যাসকারী (AST/Type signature drift)।

    বাংলা মন্তব্য: টেক্সট-কনফ্লিক্ট না থাকলেও দুটি PR একই ফাংশনের সিগনেচার
    আলাদাভাবে বদলালে প্রোডাকশন ক্র্যাশ করতে পারে — এই ক্লাস সেটাই ধরে।
    """

    HIGH_DIFF_LINES = 400
    HIGH_FILE_COUNT = 12

    # ── Pure স্তর (নেটওয়ার্কমুক্ত — টেস্টেবল) ──

    @staticmethod
    def extract_python_signatures(source: str) -> Dict[str, str]:
        """Python সোর্স থেকে AST দিয়ে সব ফাংশন/ক্লাস সিগনেচার ম্যাপ করে (pure)।

        বাংলা মন্তব্য: qualified name (Class.method) → সিগনেচার স্ট্রিং।
        সিনট্যাক্স-ভাঙা সোর্সে নিরাপদে খালি dict ফেরত দেয়।
        """
        import ast as _ast

        if not source or not source.strip():
            return {}
        try:
            tree = _ast.parse(source)
        except SyntaxError:
            return {}

        signatures: Dict[str, str] = {}

        def _sig_of(node: Any) -> str:
            try:
                return _ast.unparse(node.args) if getattr(node, "args", None) else ""
            except Exception:  # noqa: BLE001 — unparse ব্যর্থ হলেও ম্যাপিং থাকবে
                return ""

        def _walk(nodes: List[Any], prefix: str) -> None:
            for node in nodes:
                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    qname = f"{prefix}{node.name}"
                    signatures[qname] = _sig_of(node)
                    _walk(node.body, qname + ".")
                elif isinstance(node, _ast.ClassDef):
                    qname = f"{prefix}{node.name}"
                    signatures[qname] = ""
                    _walk(node.body, qname + ".")

        _walk(tree.body, "")
        return signatures

    @staticmethod
    def parse_signature_ops_from_patch(patch: str) -> Dict[str, str]:
        """PR diff patch থেকে সিগনেচার অপারেশন ম্যাপ করে (pure)।

        বাংলা মন্তব্য: `+def foo(x: int)` → {"foo": "changed"}; `def foo` কেবল
        মুছে গেলে → "removed"। একই নাম যোগ+মুছ = "changed" (সিগনেচার ড্রিপ্ট)।
        """
        ops: Dict[str, set] = {}
        if not patch:
            return {}
        for line in patch.splitlines():
            m = _SIGNATURE_LINE_RE.match(line)
            if not m:
                continue
            sign, name = m.group(1), m.group(2)
            ops.setdefault(name, set()).add("added" if sign == "+" else "removed")
        result: Dict[str, str] = {}
        for name, kinds in ops.items():
            if kinds == {"added", "removed"}:
                result[name] = "changed"
            else:
                result[name] = next(iter(kinds))
        return result

    @staticmethod
    def find_signature_drift(
        base_sigs: Dict[str, str], head_sigs: Dict[str, str]
    ) -> Dict[str, List[str]]:
        """main-এর সাথে PR-হেডের সিগনেচার তুলনা করে ড্রিপ্ট বের করে (pure)।

        বাংলা মন্তব্য: changed = নাম একই কিন্তু প্যারামিটার আলাদা (breaking হতে পারে);
        removed = পাবলিক ফাংশন সম্পূর্ণ মুছে গেছে।
        """
        changed = [
            name
            for name, sig in head_sigs.items()
            if name in base_sigs and base_sigs[name] != sig
        ]
        removed = [name for name in base_sigs if name not in head_sigs]
        return {"changed": sorted(changed), "removed": sorted(removed)}

    @staticmethod
    def find_cross_pr_function_overlap(
        sigs_a: Dict[str, str], sigs_b: Dict[str, str]
    ) -> List[str]:
        """দুটি PR-এর সিগনেচার-অপ ম্যাপে ওভারল্যাপ (সম্ভাব্য সিমান্টিক কনফ্লিক্ট) বের করে (pure)।"""
        return sorted(set(sigs_a.keys()) & set(sigs_b.keys()))

    @classmethod
    def assess(cls, pr: Dict[str, Any], peer_prs: Optional[List[Dict[str, Any]]] = None) -> Tuple[str, List[str]]:
        """PR-এর সামগ্রিক রিস্ক লেভেল দেয়: 'HIGH' | 'MEDIUM' | 'LOW' + কারণসমূহ।

        বাংলা মন্তব্য: কোর ডিরেক্টরি (auth/payments/migration/db) বা বিশাল ডিফ =
        HIGH; সাধারণ কোড = MEDIUM; ডকস/ক্ষুদ্র পরিবর্তন = LOW। peer PR-এর সাথে
        একই ফাংশনে হাত দিলে সিমান্টিক-কনফ্লিক্ট সন্দেহ যোগ হয়।
        """
        reasons: List[str] = []
        files = [f.get("path", "") for f in pr.get("files") or []]
        additions = int(pr.get("additions") or 0)
        deletions = int(pr.get("deletions") or 0)
        total = additions + deletions

        level = "LOW"
        critical_hits = [
            p for p in files if any(p.startswith(d) for d in _SEMANTIC_CRITICAL_DIRS)
        ]
        if critical_hits:
            level = "HIGH"
            reasons.append(f"critical-dir: {', '.join(critical_hits[:2])}")
        if total >= cls.HIGH_DIFF_LINES or len(files) >= cls.HIGH_FILE_COUNT:
            level = "HIGH"
            reasons.append(f"large-diff: {total} lines / {len(files)} files")
        elif level != "HIGH" and (total >= 80 or any(p.endswith(".py") for p in files)):
            level = "MEDIUM"
            reasons.append(f"code-change: {total} lines")

        # peer PR-দের সাথে সিমান্টিক ওভারল্যাপ — patch-ভিত্তিক হালকা সন্দেহ যাচাই
        my_ops: Dict[str, str] = {}
        for f in pr.get("files") or []:
            if str(f.get("path", "")).endswith(".py"):
                my_ops.update(cls.parse_signature_ops_from_patch(f.get("patch") or ""))
        if my_ops and peer_prs:
            for peer in peer_prs:
                if peer.get("number") == pr.get("number"):
                    continue
                peer_ops: Dict[str, str] = {}
                for f in peer.get("files") or []:
                    if str(f.get("path", "")).endswith(".py"):
                        peer_ops.update(
                            cls.parse_signature_ops_from_patch(f.get("patch") or "")
                        )
                overlap = cls.find_cross_pr_function_overlap(
                    {k: v for k, v in my_ops.items() if v in ("changed", "removed")},
                    {k: v for k, v in peer_ops.items() if v in ("changed", "removed")},
                )
                if overlap:
                    level = "HIGH"
                    reasons.append(
                        f"semantic-conflict-suspect: {', '.join(overlap[:3])} (PR #{peer.get('number')})"
                    )
        return level, reasons


class AISentinelReviewer:
    """AI Code & Security Sentinel — Groq/Gemini Flash চালিত PR পর্যালোচক।

    বাংলা মন্তব্য: diff স্ক্যান করে হার্ডকোডেড কি, সিকিউরিটি ভালনারেবিলিটি,
    মেমোরি-ব্লোট (512MB রুল) ও সংবিধান-লঙ্ঘন ধরে। ভেরডিক্ট কঠোর JSON।
    কোনো provider না থাকলে SKIPPED — মার্জ পাইপলাইন আটকায় না (কিন্তু
    HIGH-রিস্কে Multi-Model Consensus অনুপস্থিত হলে fail-closed BLOCK)।
    """

    DISABLE_VALUES = ("off", "none", "disabled", "0", "false")
    MAX_DIFF_CHARS = 12_000
    TIMEOUT_SECS = 25

    PROMPT_TEMPLATE = (
        "তুমি SupremeAI রিপোর নিরাপত্তা ও কোড-কোয়ালিটি সেন্টিনেল। নিচের PR diff "
        "স্ক্যান করে কঠোরভাবে এই JSON-ই দাও (অন্য কোনো টেক্সট নয়):\n"
        '{{"verdict": "LGTM" অথবা "BLOCK", "risk": "low|medium|high", '
        '"issues": ["সংক্ষিপ্ত সমস্যা"], "note": "১ লাইনের বাংলা ব্যাখ্যা"}}\n'
        "যাচাই-তালিকা:\n"
        "১. হার্ডকোডেড API key/token/পাসওয়ার্ড আছে কি?\n"
        "২. স্পষ্ট সিকিউরিটি ভালনারেবিলিটি (SQL injection, eval, unsafe pickle, path traversal)?\n"
        "৩. মেমোরি-ব্লোট ঝুঁকি (512MB RAM রুল ভঙ্গ — অনাবশ্যক বড় ডেটা মেমোরিতে)?\n"
        "৪. সাধারণ বাগ: ভুল ভেরিয়েবল, off-by-one, লজিক বিপর্যয়?\n"
        "৫. নতুন Python ফাইলে বাংলা কমেন্ট চুক্তি মানা হয়েছে কি (শুধু নোট করো, BLOCK নয়)?\n"
        "ছোট নিরীহ পরিবর্তন হলে দ্বিধা ছাড়া LGTM দাও। সন্দেহজনক হলেই BLOCK।\n\n"
        "PR শিরোনাম: {title}\n\n```diff\n{diff}\n```"
    )

    @classmethod
    def is_enabled(cls) -> bool:
        """কিল-সুইচ: MERGE_TRAIN_SENTINEL=off হলে নিষ্ক্রিয়।"""
        raw = (os.getenv("MERGE_TRAIN_SENTINEL") or "").strip().lower()
        return raw not in cls.DISABLE_VALUES

    @staticmethod
    def build_prompt(title: str, diff: str) -> str:
        """সেন্টিনেল প্রম্পট গঠন (pure) — diff সীমিত রাখে টোকেন-বিস্ফোরণ রোধে।"""
        trimmed = diff or ""
        if len(trimmed) > AISentinelReviewer.MAX_DIFF_CHARS:
            head = trimmed[: AISentinelReviewer.MAX_DIFF_CHARS // 2]
            tail = trimmed[-AISentinelReviewer.MAX_DIFF_CHARS // 2 :]
            trimmed = (
                head
                + "\n... [বাংলা মন্তব্য: বিশাল diff — মাঝের অংশ বাদ, head+tail বিশ্লেষণ] ...\n"
                + tail
            )
        return AISentinelReviewer.PROMPT_TEMPLATE.format(title=title, diff=trimmed)

    @staticmethod
    def parse_verdict(raw: str) -> Dict[str, Any]:
        """মডেল-আউটপুট থেকে JSON ভেরডিক্ট বের করা (pure)। ভাঙলে UNKNOWN।"""
        if not raw or not raw.strip():
            return {"verdict": "UNKNOWN", "risk": "unknown", "issues": ["empty-response"]}
        text = raw.strip()
        # markdown fence-এ মোড়ানো থাকলে খুলে নেওয়া
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        else:
            brace = re.search(r"\{.*\}", text, re.DOTALL)
            if brace:
                text = brace.group(0)
        try:
            data = json.loads(text)
            verdict = str(data.get("verdict", "")).upper()
            if verdict not in ("LGTM", "BLOCK"):
                verdict = "UNKNOWN"
            risk = str(data.get("risk", "unknown")).lower()
            if risk not in ("low", "medium", "high"):
                risk = "unknown"
            return {
                "verdict": verdict,
                "risk": risk,
                "issues": list(data.get("issues") or []),
                "note": str(data.get("note") or ""),
            }
        except (ValueError, TypeError):
            return {"verdict": "UNKNOWN", "risk": "unknown", "issues": ["unparseable-response"]}

    @classmethod
    def _providers(cls) -> List[Dict[str, str]]:
        """কনফিগার করা LLM প্রোভাইডার চেইন (Groq আগে — সুপারফাস্ট ফ্রি টায়ার)।"""
        providers: List[Dict[str, str]] = []
        groq_key = os.getenv("GROQ_API_KEY") or ""
        if groq_key:
            providers.append(
                {
                    "name": "groq",
                    "key": groq_key,
                    "url": "https://api.groq.com/openai/v1/chat/completions",
                    "model": os.getenv("MERGE_TRAIN_GROQ_MODEL") or "llama-3.3-70b-versatile",
                }
            )
        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        if gemini_key:
            providers.append(
                {
                    "name": "gemini",
                    "key": gemini_key,
                    "url": "https://generativelanguage.googleapis.com/v1beta/models/"
                    + (os.getenv("MERGE_TRAIN_GEMINI_MODEL") or "gemini-2.5-flash")
                    + ":generateContent",
                    "model": os.getenv("MERGE_TRAIN_GEMINI_MODEL") or "gemini-2.5-flash",
                }
            )
        return providers

    @staticmethod
    def _call_provider(provider: Dict[str, str], prompt: str) -> Optional[str]:
        """এক প্রোভাইডারে প্রম্পট পাঠিয়ে টেক্সট উত্তর আনা (নেটওয়ার্ক I/O)। ব্যর্থ হলে None।"""
        import urllib.error
        import urllib.request

        try:
            if provider["name"] == "groq":
                payload = json.dumps(
                    {
                        "model": provider["model"],
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                        "max_tokens": 600,
                    }
                ).encode()
                headers = {
                    "Authorization": f"Bearer {provider['key']}",
                    "Content-Type": "application/json",
                }
            else:  # gemini
                payload = json.dumps(
                    {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0, "maxOutputTokens": 600},
                    }
                ).encode()
                headers = {"Content-Type": "application/json", "x-goog-api-key": provider["key"]}

            req = urllib.request.Request(
                provider["url"], data=payload, method="POST", headers=headers
            )
            with urllib.request.urlopen(req, timeout=AISentinelReviewer.TIMEOUT_SECS) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if provider["name"] == "groq":
                return data["choices"][0]["message"]["content"]
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:  # noqa: BLE001 — provider ব্যর্থতা পাইপলাইন ভাঙবে না
            logger.warning(f"🤖 Sentinel provider '{provider['name']}' ব্যর্থ: {e}")
            return None

    @classmethod
    def review(cls, title: str, diff: str, high_risk: bool = False) -> Dict[str, Any]:
        """PR-পর্যালোচনা চালানো; high_risk হলে ২-প্রোভাইডার কনসেনসাস চাই (fail-closed)।"""
        if not cls.is_enabled():
            return {"verdict": "DISABLED", "risk": "unknown", "issues": [], "note": ""}
        providers = cls._providers()
        if not providers:
            return {
                "verdict": "SKIPPED",
                "risk": "unknown",
                "issues": [],
                "note": "no-provider-key",
            }
        prompt = cls.build_prompt(title, diff)
        verdicts: List[Dict[str, Any]] = []
        for provider in providers:
            raw = cls._call_provider(provider, prompt)
            v = cls.parse_verdict(raw)
            v["provider"] = provider["name"]
            verdicts.append(v)
            if raw is None:
                verdicts[-1]["verdict"] = "ERROR"

        errors = [v for v in verdicts if v["verdict"] == "ERROR"]
        blocks = [v for v in verdicts if v["verdict"] == "BLOCK"]
        lgts = [v for v in verdicts if v["verdict"] == "LGTM"]

        result: Dict[str, Any] = {
            "verdict": "LGTM",
            "risk": "low",
            "issues": [],
            "note": "",
            "providers": [v.get("provider") for v in verdicts],
        }
        # বাংলা মন্তব্য: যেকোনো এক provider-ই BLOCK দিলে থামবে (প্রথম ধারকই যথেষ্ট)
        if blocks:
            result["verdict"] = "BLOCK"
            result["risk"] = blocks[0].get("risk", "high")
            result["issues"] = blocks[0].get("issues", [])
            result["note"] = blocks[0].get("note", "")
            return result
        if high_risk:
            # Multi-Model Consensus: HIGH-রিস্কে ≥২ provider-এর LGTM ছাড়া অনুমোদন নেই
            if len(lgts) >= 2:
                result["note"] = "consensus: " + "+".join(v.get("provider", "?") for v in lgts)
                return result
            # বাংলা মন্তব্য: fail-closed — কনসেনসাস সম্ভব না হলে অ্যাডমিন-সিদ্ধান্ত
            result["verdict"] = "BLOCK"
            result["risk"] = "high"
            result["issues"] = ["consensus-unavailable (HIGH risk needs 2 independent LGTMs)"]
            result["note"] = "fail-closed-consensus"
            return result
        if lgts:
            result["risk"] = lgts[0].get("risk", "unknown")
            result["note"] = lgts[0].get("note", "")
            return result
        # সব provider ERROR — না অনুমোদন না ব্লক: নিরপেক্ষ থাকা (মার্জ অন্যান্য গেটের উপর ভরসা করবে)
        result["verdict"] = "ERROR" if errors else "UNKNOWN"
        result["issues"] = ["all-providers-failed"] if errors else ["no-clear-verdict"]
        return result


class SpeculativeStagingRunner:
    """Speculative Virtual Staging — main-এ মার্জের আগে ভার্চুয়াল সিমুলেশন।

    বাংলা মন্তব্য: সাময়িক git worktree-তে origin/main-এর ওপর PR-হেড মার্জ করে
    স্মোক টেস্ট চালায়; সবুজ হলেই আসল মার্জ অনুমোদিত (Zero-Broken-Main গ্যারান্টি)।
    """

    @staticmethod
    def is_enabled() -> bool:
        """কিল-সুইচ: MERGE_TRAIN_SPECULATIVE=off হলে নিষ্ক্রিয়।"""
        raw = (os.getenv("MERGE_TRAIN_SPECULATIVE") or "").strip().lower()
        return raw not in AISentinelReviewer.DISABLE_VALUES

    @staticmethod
    def build_worktree_commands(
        head_branch: str, base_ref: str = "origin/main", wt_path: str = "/tmp/staging"
    ) -> List[List[str]]:
        """ভার্চুয়াল স্টেজিং-এর সম্পূর্ণ git কমান্ড-প্ল্যান (pure — টেস্টেবল)।

        বাংলা নোট (#2873): `--no-ff` merge commit তৈরি করে — runner-env-এ
        user.name/user.email না থাকলে "empty ident name"-এ ব্যর্থ হয়। তাই
        one-shot `-c` identity flags — persistent config নয় (টেস্ট:
        tests/test_speculative_staging_identity_2873.py)।
        """
        return [
            ["git", "fetch", "origin", "main"],
            ["git", "worktree", "add", "--detach", wt_path, base_ref],
            [
                "git", "-C", wt_path,
                "-c", "user.name=supremeai-coder-1-bot",
                "-c", "user.email=coder-1@supremeai.bot",
                "merge", "--no-ff", "--no-edit", f"origin/{head_branch}",
            ],
        ]

    @staticmethod
    def changed_py_files(workdir: str, base_ref: str = "origin/main") -> List[str]:
        """স্টেজিং-মার্জে base-এর তুলনায় বদলানো .py ফাইল তালিকা (I/O)।"""
        code, out, _ = run_cmd(
            ["git", "-C", workdir, "diff", "--name-only", base_ref, "HEAD"]
        )
        if code != 0:
            return []
        return [line.strip() for line in out.splitlines() if line.strip().endswith(".py")]

    @classmethod
    def run(
        cls,
        head_branch: str,
        base_ref: str = "origin/main",
        wt_path: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """সম্পূর্ণ স্পেকুলেটিভ স্টেজিং চালানো (I/O)। (সবুজ?, রিপোর্ট) ফেরত।"""
        if not cls.is_enabled():
            return True, "speculative-staging disabled (kill-switch)"
        import shutil as _shutil
        import tempfile as _tempfile

        wt = wt_path or _tempfile.mkdtemp(prefix="merge-staging-")
        report_lines: List[str] = []
        created = False
        try:
            code, _, err = run_cmd(["git", "fetch", "origin", "main"])
            if code != 0:
                return False, f"fetch failed: {err[:200]}"
            code, _, err = run_cmd(
                ["git", "worktree", "add", "--detach", wt, base_ref]
            )
            if code != 0:
                # বাংলা মন্তব্য: পাথ আগে থেকে থাকলে পরিষ্কার করে আবার চেষ্টা
                _shutil.rmtree(wt, ignore_errors=True)
                code, _, err = run_cmd(
                    ["git", "worktree", "add", "--detach", wt, base_ref]
                )
                if code != 0:
                    return False, f"worktree add failed: {err[:200]}"
            created = True
            # বাংলা নোট (#2873): merge commit-এর জন্য identity দরকার — runner-env-এ
            # না থাকলে "empty ident name"-এ deterministic ব্যর্থ। one-shot -c flags
            # (build_worktree_commands প্ল্যানের সমতুল্য; persistent config নয়)।
            code, out, err = run_cmd(
                [
                    "git", "-C", wt,
                    "-c", "user.name=supremeai-coder-1-bot",
                    "-c", "user.email=coder-1@supremeai.bot",
                    "merge", "--no-ff", "--no-edit",
                    f"origin/{head_branch}",
                ]
            )
            if code != 0:
                return False, f"virtual-merge conflict: {(err or out)[:300]}"

            # স্মোক ১: বদলানো .py ফাইলের py_compile (সিনট্যাক্স-ব্রেক ধরা)
            py_files = cls.changed_py_files(wt, base_ref)
            if py_files:
                # py_compile worktree-র ফাইলের ওপর চালানো হয় (absolute path দরকার)
                abs_files = [str((Path(wt) / f).resolve()) for f in py_files[:40]]
                code, _, err = run_cmd([sys.executable, "-m", "py_compile", *abs_files])
                if code != 0:
                    return False, f"py_compile failed: {err[:300]}"
                report_lines.append(f"py_compile OK ({len(py_files)} py files)")

            # স্মোক ২: কোর প্যাকেজ import (মূল repo-র ওপর — worktree-তে deps নেই)
            code, out, err = run_cmd(
                [
                    sys.executable, "-c",
                    "import sys, os; sys.path.insert(0, os.getcwd());"
                    "import scripts; print('[OK] staging smoke: scripts package imports')",
                ]
            )
            if code != 0:
                return False, f"staging import smoke failed: {err[:200]}"
            report_lines.append("import smoke OK")
            return True, "; ".join(report_lines) or "virtual staging green"
        finally:
            # বাংলা মন্তব্য: worktree সবসময় পরিষ্কার — রিসোর্স-লিক নিষিদ্ধ
            if created:
                run_cmd(["git", "worktree", "remove", "--force", wt])
                _shutil.rmtree(wt, ignore_errors=True)


class SelfHealingPatcher:
    """Self-Healing Auto-Fixer — লিন্ট/ফরম্যাট ব্যর্থতায় স্বয়ংক্রিয় ফিক্স-কমিট।

    বাংলা মন্তব্য: ruff-এর নির্ধারিত ফিক্সযোগ্য ত্রুটি (UP035/F401/ফরম্যাট) হলে
    প্রথমে deterministic `ruff --fix` + `ruff format`, ব্যর্থ হলে AI-জেনারেটেড
    ফাইল-ফিক্স (ast.parse যাচাই সহ)। টেস্ট-ব্যর্থতা কখনো auto-fix করা হয় না।
    """

    MAX_ATTEMPTS_PER_RUN = 2
    MAX_HEALS_PER_RUN = 3
    HEAL_MARKER = "🤖 self-healing patch"

    LINT_SIGNS = (
        "UP035", "F401", "F841", "I001", "E501", "W291", "W292",
        "ruff", "exit=123", "would reformat",
    )
    # বাংলা মন্তব্য: এই চিহ্নগুলো মানে গভীর লজিক/টেস্ট ব্যর্থতা — সেটা কখনো auto-fix নয়
    NON_HEALABLE_SIGNS = ("FAILED tests", "assertionerror", "traceback", "tests failed")

    _attempts: Dict[int, int] = {}
    _total_heals = 0

    @staticmethod
    def is_enabled() -> bool:
        """কিল-সুইচ: MERGE_TRAIN_AUTO_HEAL=off হলে নিষ্ক্রিয়।"""
        raw = (os.getenv("MERGE_TRAIN_AUTO_HEAL") or "").strip().lower()
        return raw not in AISentinelReviewer.DISABLE_VALUES

    @classmethod
    def classify_failure(cls, log_text: str) -> str:
        """ব্যর্থতা-লগ শ্রেণিবিন্যাস (pure): 'lint' | 'format' | 'unknown'।"""
        low = (log_text or "").lower()
        if any(sign in low for sign in cls.NON_HEALABLE_SIGNS):
            return "unknown"
        if "would reformat" in low or "ruff format" in low:
            return "format"
        if any(sign in low for sign in cls.LINT_SIGNS):
            return "lint"
        return "unknown"

    @classmethod
    def is_healable(cls, log_text: str) -> bool:
        """লগ কি deterministic ফিক্সযোগ্য (lint/format)? (pure)"""
        return cls.classify_failure(log_text) in ("lint", "format")

    @classmethod
    def budget_left(cls, pr_number: int) -> bool:
        """প্রতি রানে হিল-বাজেট আছে কি না (রেট-লিমিট সুরক্ষা, in-memory)।"""
        return (
            cls._attempts.get(pr_number, 0) < cls.MAX_ATTEMPTS_PER_RUN
            and cls._total_heals < cls.MAX_HEALS_PER_RUN
        )

    @classmethod
    def fetch_failure_log(cls, pr_number: int, head_branch: str) -> str:
        """PR-এর সর্বশেষ ব্যর্থ run-এর failed লগের শেষ ২০০ লাইন আনা (I/O)।"""
        data = run_gh_json(
            ["gh", "run", "list", "--branch", head_branch, "--limit", "10",
             "--json", "databaseId,conclusion,createdAt"]
        )
        if not data:
            return ""
        failed_ids = [d["databaseId"] for d in data if d.get("conclusion") == "failure"]
        if not failed_ids:
            return ""
        code, out, _ = run_cmd(
            ["gh", "run", "view", str(failed_ids[0]), "--log-failed"]
        )
        if code != 0 or not out:
            return ""
        return "\n".join(out.splitlines()[-200:])

    @classmethod
    def heal(cls, pr_number: int, head_branch: str, changed_paths: List[str]) -> Tuple[bool, str]:
        """PR-ব্রাঞ্চে নিরাপদ auto-fix কমিট পুশ করা (I/O)। (সফল?, বার্তা) ফেরত।"""
        if not cls.is_enabled() or not cls.budget_left(pr_number):
            return False, "heal-disabled-or-budget-exhausted"

        # বাংলা মন্তব্য: protected-path PR-এ healing নিষিদ্ধ — অটোমেশন নিজের নিয়মে হাত দিতে পারবে না
        protected_hits = find_protected_path_hits(changed_paths, _PROTECTED_PATHS)
        if protected_hits:
            return False, f"protected-paths-refused: {protected_hits[:2]}"

        py_targets = [p for p in changed_paths if p.endswith(".py")]
        if not py_targets:
            return False, "no-python-files"

        import shutil as _shutil

        cls._attempts[pr_number] = cls._attempts.get(pr_number, 0) + 1
        cls._total_heals += 1

        # ১. deterministic পথ: ruff check --fix + ruff format (locked সংস্করণ CI-তে আছে)
        if _shutil.which("ruff"):
            code, _, _ = run_cmd(["git", "fetch", "origin", head_branch])
            code, _, err = run_cmd(["git", "checkout", "-B", head_branch, f"origin/{head_branch}"])
            if code != 0:
                return False, f"checkout failed: {err[:200]}"
            run_cmd(["ruff", "check", "--fix", "--quiet", *py_targets])
            run_cmd(["ruff", "format", "--quiet", *py_targets])
            code, _, _ = run_cmd(["git", "diff", "--quiet"])
            if code != 0:  # কিছু বদলেছে → কমিট ও পুশ
                run_cmd(["git", "config", "user.name", "supremeai-coder-1-bot"])
                run_cmd(["git", "config", "user.email", "coder-1@supremeai.bot"])
                run_cmd(["git", "add", *py_targets])
                run_cmd([
                    "git", "commit", "-m",
                    "fix(ci): automated lint/format patch by AI Sentinel (self-healing)",
                ])
                code, _, err = run_cmd(["git", "push", "origin", head_branch])
                if code == 0:
                    return True, "ruff-fix pushed"
                return False, f"push failed: {err[:200]}"
            return False, "ruff-made-no-change"

        # ২. AI পথ: প্রথম ফাইলের সোর্স + লগ দিয়ে সংশোধিত ফাইল চেয়ে জেনারেট
        log_excerpt = cls.fetch_failure_log(pr_number, head_branch)
        if not log_excerpt or cls.classify_failure(log_excerpt) == "unknown":
            return False, "no-healable-log"
        code, out, _ = run_cmd(["git", "show", f"origin/{head_branch}:{py_targets[0]}"])
        if code != 0 or len(out.splitlines()) > 400:
            return False, "file-too-big-or-missing"
        fix_prompt = (
            "নিচের Python ফাইলটি lint ব্যর্থ হয়েছে। শুধুমাত্র সম্পূর্ণ সংশোধিত ফাইলের "
            "কনটেন্ট দাও — কোনো ব্যাখ্যা বা markdown fence নয়।\n\nলগ:\n"
            f"{log_excerpt[:2000]}\n\nফাইল ({py_targets[0]}):\n{out}"
        )
        providers = AISentinelReviewer._providers()
        if not providers:
            return False, "no-ai-provider"
        fixed = None
        for provider in providers:
            fixed = AISentinelReviewer._call_provider(provider, fix_prompt)
            if fixed:
                break
        if not fixed:
            return False, "ai-fix-failed"
        fixed = re.sub(r"^```(?:python)?\s*|\s*```$", "", fixed.strip())
        try:
            import ast as _ast

            _ast.parse(fixed)  # বাংলা মন্তব্য: যাচাই ছাড়া কোনো AI-কোড পুশ নিষিদ্ধ
        except SyntaxError:
            return False, "ai-fix-unparseable"

        code, _, err = run_cmd(["git", "checkout", "-B", head_branch, f"origin/{head_branch}"])
        if code != 0:
            return False, f"checkout failed: {err[:200]}"
        tmp_write = Path(REPO_ROOT) / py_targets[0]
        try:
            tmp_write.write_text(fixed, encoding="utf-8")
            run_cmd(["git", "add", py_targets[0]])
            run_cmd([
                "git", "commit", "-m",
                "fix(ci): automated patch by AI Sentinel (self-healing)",
            ])
            code, _, err = run_cmd(["git", "push", "origin", head_branch])
            if code == 0:
                return True, "ai-fix pushed"
            return False, f"push failed: {err[:200]}"
        finally:
            run_cmd(["git", "checkout", "main"])  # বাংলা মন্তব্য: সবসময় main-এ ফেরা


class FlakyTriageEngine:
    """Flaky Triage Engine — pass^k কনসিস্টেন্সি চেকার।

    বাংলা মন্তব্য: নেটওয়ার্ক-জাত ফ্ল্যাকি ব্যর্থতাকে আসল বাগ থেকে আলাদা করে।
    rerun অ্যাসিঙ্ক্রোনাস ট্রিগার হয় (#2631-এর check_suite ইভেন্ট-লুপ পরের রাউন্ডে
    পুনঃমূল্যায়ন করবে) — মার্জার কখনো rerun-এর জন্য ব্লক করে দাঁড়িয়ে থাকে না।
    """

    PASS_K = 2

    @staticmethod
    def is_enabled() -> bool:
        """কিল-সুইচ: MERGE_TRAIN_FLAKY_RERUN=off হলে নিষ্ক্রিয়।"""
        raw = (os.getenv("MERGE_TRAIN_FLAKY_RERUN") or "").strip().lower()
        return raw not in AISentinelReviewer.DISABLE_VALUES

    @staticmethod
    def classify_sequence(results: List[bool]) -> str:
        """পরপর রান-ফলাফল শ্রেণিবিন্যাস (pure): 'stable-pass' | 'stable-fail' | 'flaky-pass^k'।

        বাংলা মন্তব্য: কমপক্ষে ১টি পাস + ১টি ফেল = flaky; সব পাস = stable-pass;
        সব ফেল = stable-fail (আসল বাগ)।
        """
        if not results:
            return "stable-fail"
        if all(results):
            return "stable-pass"
        if not any(results):
            return "stable-fail"
        passes = sum(1 for r in results if r)
        return f"flaky-pass^{passes}"

    @staticmethod
    def parse_pytest_failures(log_text: str) -> List[str]:
        """pytest লগ থেকে FAILED test id বের করা (pure)।"""
        if not log_text:
            return []
        ids = re.findall(r"^(?:FAILED|ERROR)\s+([\w/\.\-]+::[\w\[\]\-\./]+)", log_text, re.MULTILINE)
        return sorted(set(ids))

    @staticmethod
    def build_flaky_comment(test_ids: List[str], k: int) -> str:
        """ফ্ল্যাকি-প্রমাণ PR কমেন্ট গঠন (pure, বাংলা)।"""
        listing = "\n".join(f"- `{t}`" for t in test_ids[:5])
        return (
            f"🔍 **Flaky Triage (pass^{k} প্রমাণ)** — নিচের টেস্টগুলো প্রথম রানে ফেল করেও "
            f"রিরানে পাস করেছে (pass^{k}) — নেটওয়ার্ক/টাইমিং জাত ফ্ল্যাকি, আসল বাগ নয়:\n"
            f"{listing}\n\n"
            "_বাংলা মন্তব্য: এই কমেন্ট AI মার্জ-ট্রেইন স্বয়ংক্রিয়ভাবে দিয়েছে। "
            "বারবার ফেল করলে এটিকে stable-fail ধরে আসল বাগ হিসেবে দেখা হবে।_"
        )

    @classmethod
    def schedule_rerun(cls, failed_run_ids: List[int]) -> int:
        """ব্যর্থ run-গুলোর অ্যাসিঙ্ক rerun ট্রিগার (I/O)। সফল ট্রিগার সংখ্যা ফেরত।"""
        if not cls.is_enabled() or not failed_run_ids:
            return 0
        triggered = 0
        for run_id in failed_run_ids[: cls.PASS_K]:
            code, _, _ = run_cmd(["gh", "run", "rerun", str(run_id), "--failed"])
            if code == 0:
                triggered += 1
        return triggered


def main() -> None:
    global _ACTIVE_APP_TOKEN

    parser = argparse.ArgumentParser(
        description="Smart Priority-Wise Sequential PR Merger (SupremeAI Tools & Technician First)"
    )
    parser.add_argument("--plan", action="store_true", help="শুধু প্রায়োরিটি সিকোয়েন্স এবং স্ট্যাটাস প্ল্যান প্রদর্শন করুন")
    parser.add_argument("--audit-evidence", action="store_true", help="সব ওপেন PR-এর টেস্ট এভিডেন্স অডিট রিপোর্ট দেখুন")
    parser.add_argument("--dry-run", action="store_true", help="কোনো আসল মার্জ ছাড়া পুরো প্রক্রিয়া সিমুলেট করুন")
    parser.add_argument("--execute", action="store_true", help="একক ক্রমানুসারে PR মার্জ করা শুরু করুন")
    parser.add_argument("--limit", type=int, default=5, help="সর্বোচ্চ কয়টি PR মার্জ করা হবে (ডিফল্ট: ৫)")
    parser.add_argument("--min-prs", type=int, default=0, help="ন্যূনতম কয়টি PR জমা হলে মার্জ পাইপলাইন ট্রিগার হবে (যেমন: ৫)")
    parser.add_argument("--release-holds", action="store_true", help="queue:hold থাকা PR-গুলোকেও প্রস্তুত থাকলে মার্জের অনুমতি দিন")
    parser.add_argument("--include-dependencies", action="store_true", help="থার্ড-পার্টি ডিপেন্ডেন্সি বাম্প (Dependabot) অন্তর্ভুক্ত করুন")
    parser.add_argument("--heal-evidence", action="store_true", help="সব ওপেন PR-এর টেস্ট এভিডেন্স একবারে অটো-হিল ও সিআই রি-রান করুন")
    parser.add_argument("--auto-heal", action="store_true", default=True, help="মার্জ চলাকালে মিসিং বা ইনভ্যালিড টেস্ট এভিডেন্স স্বয়ংক্রিয়ভাবে হিল করুন (ডিফল্ট: চালু)")
    parser.add_argument("--no-auto-heal", action="store_true", help="স্বয়ংক্রিয় এভিডেন্স হিলিং নিষ্ক্রিয় রাখুন")
    parser.add_argument("--continue-on-conflict", action="store_true", default=True, help="কনফ্লিক্ট হলেও ইস্যু তৈরি করে পাইপলাইন না থামিয়ে পরের স্বাধীন PR-এ যান (ডিফল্ট: চালু)")
    parser.add_argument("--stop-on-conflict", action="store_true", help="কনফ্লিক্ট ধরা পড়লে সাথে সাথে পাইপলাইন থামান")
    parser.add_argument("--skip-smoke", action="store_true", help="মার্জের পর পোস্ট-স্মোক রান স্কিপ করুন")
    parser.add_argument("--app-auth", action="store_true", help="GitHub App ক্রেডেনশিয়াল ব্যবহার করে হাই-রেট লিমিট ও বট আইডেন্টিটিতে রান করুন")
    # বাংলা মন্তব্য: #2645 — ইন্টেলিজেন্ট ইঞ্জিনের প্রতি-স্তম্ভ কিল-সুইচ (CLI স্তরেও)
    parser.add_argument("--no-sentinel", action="store_true", help="AI Sentinel রিভিউ নিষ্ক্রিয় রাখুন")
    parser.add_argument("--no-speculative", action="store_true", help="ভার্চুয়াল স্টেজিং সিমুলেশন নিষ্ক্রিয় রাখুন")
    parser.add_argument("--no-heal", action="store_true", help="সেলফ-হিলিং প্যাচার নিষ্ক্রিয় রাখুন")
    parser.add_argument("--no-flaky-rerun", action="store_true", help="ফ্ল্যাকি ট্রায়াজ রিরান নিষ্ক্রিয় রাখুন")
    args = parser.parse_args()

    # বাংলা মন্তব্য: #4265 — Pipeline Constitution RULE 6 / #4253 Phase-A: merge-gate.yml
    # একমাত্র landing authority। এই স্ক্রিপ্টের --execute পাথ হুবহু একটি দ্বিতীয়
    # merge authority — replacement (merge-gate.yml #4243) প্রমাণিত হওয়ায় Phase-A
    # অনুমোদিত "disabled" বিকল্প এখানে প্রয়োগ করা হলো। Guard রাখা হয়েছে সব
    # network/APP-token/fetch-সাইড-এফেক্টের আগে — fail-closed, শূন্য পার্শ্বপ্রভাব।
    # Read-only planning (--plan / --audit-evidence / --dry-run) অটুট থাকবে।
    if args.execute:
        logger.error(
            "⛔ [MERGE-AUTHORITY-DISABLED] smart_priority_merger --execute নিষ্ক্রিয় (#4265)। "
            "PR landing এখন একচেতনাভাবে .github/workflows/merge-gate.yml (#4243; RULE 6, "
            "#4253 Phase-A) দ্বারা পরিচালিত — সেখানে priority, freshness, required-checks "
            "ও predecessor প্রমাণসহ যাচাই হয়। প্ল্যানিং/অডিটের জন্য --plan / "
            "--audit-evidence / --dry-run ব্যবহার করুন।"
        )
        sys.exit(2)

    # বাংলা মন্তব্য: CLI কিল-সুইচ env কিল-সুইচের সাথে সংযুক্ত — একটাই অফ-সুইচ যথেষ্ট
    if args.no_sentinel:
        os.environ["MERGE_TRAIN_SENTINEL"] = "off"
    if args.no_speculative:
        os.environ["MERGE_TRAIN_SPECULATIVE"] = "off"
    if args.no_heal:
        os.environ["MERGE_TRAIN_AUTO_HEAL"] = "off"
    if args.no_flaky_rerun:
        os.environ["MERGE_TRAIN_FLAKY_RERUN"] = "off"

    auto_heal_enabled = args.auto_heal and not args.no_auto_heal
    continue_on_conflict = args.continue_on_conflict and not args.stop_on_conflict

    # GitHub App অথেনটিকেশন চেক
    if args.app_auth:
        app_id = os.environ.get("GITHUB_APP_ID") or os.environ.get("AGENT_PR_HELPER_APP_ID")
        inst_id = os.environ.get("GITHUB_APP_INSTALLATION_ID") or os.environ.get("AGENT_PR_HELPER_INSTALLATION_ID")
        pem = os.environ.get("GITHUB_APP_PRIVATE_KEY") or os.environ.get("AGENT_PR_HELPER_PRIVATE_KEY")
        if app_id and inst_id and pem:
            _ACTIVE_APP_TOKEN = mint_github_app_token(app_id, inst_id, pem)
        else:
            logger.warning("⚠️ GitHub App এনভায়রনমেন্ট ভ্যারিয়েবল (APP_ID, INSTALLATION_ID, PRIVATE_KEY) পাওয়া যায়নি। বর্তমান gh সেশনে ফলব্যাক করা হচ্ছে।")

    logger.info("🔍 Fetching open PRs from GitHub repository...")
    raw_prs = fetch_open_prs(limit=100)
    if not raw_prs:
        logger.warning("No open PRs found.")
        return

    # বাংলা মন্তব্য: ইউজার রিকোয়ারমেন্ট — ৫+ PR জমা হলে তবেই অটোমেটিক রান হবে
    if args.min_prs > 0 and len(raw_prs) < args.min_prs:
        logger.info(
            f"⏸️ [BATCH THRESHOLD HOLD] ওপেন PR সংখ্যা ({len(raw_prs)}) নির্ধারিত ন্যূনতম "
            f"থ্রেশহোল্ড ({args.min_prs})-এর কম। ৫+ PR জমা হওয়ার অপেক্ষায় মার্জ স্থগিত রইল।"
        )
        return

    if args.heal_evidence:
        heal_all_fleet_evidence(raw_prs)
        return

    plan = plan_priority_sequence(raw_prs, allow_holds=args.release_holds)

    if args.audit_evidence:
        audit_evidence_fleet(plan)
        return

    print_plan_table(plan)

    if args.plan:
        return

    if not args.execute and not args.dry_run:
        print("💡 টিপ: মার্জ শুরু করতে '--execute', অডিট দেখতে '--audit-evidence', সব এভিডেন্স হিল করতে '--heal-evidence' বা সিমুলেশন দেখতে '--dry-run' ফ্ল্যাগ ব্যবহার করুন।")
        return

    # বাংলা মন্তব্য: প্রো-অ্যাক্টিভ এভিডেন্স হিলিং — মার্জ শুরু হওয়ার আগেই যেসব PR-এর এভিডেন্স নেই সেগুলোকে হিল ও সিআই রান দেওয়া
    if (args.execute or args.dry_run) and auto_heal_enabled:
        needed_healing = [p for p in raw_prs if not check_pr_evidence(p.get("body") or "")[0]]
        if needed_healing:
            logger.info(f"🩹 মার্জ সিকোয়েন্সের আগে {len(needed_healing)}টি PR-এর মিসিং টেস্ট এভিডেন্স প্রো-অ্যাক্টিভলি হিল করা হচ্ছে...")
            for p in needed_healing:
                if args.dry_run:
                    logger.info(f"[DRY-RUN] PR #{p.get('number')} এর এভিডেন্স হিল করা হতো।")
                else:
                    auto_heal_pr_evidence(p.get("number"), p.get("body") or "", p.get("statusCheckRollup"))
                    time.sleep(1)

    mode_label = "DRY-RUN SIMULATION" if args.dry_run else "LIVE EXECUTION"
    logger.info(f"▶️ Starting Dynamic Sequential Merge Pipeline ({mode_label}) with limit={args.limit}...")

    merged_count = 0
    last_merged_pr: Optional[int] = None

    for idx, item in enumerate(plan, 1):
        if merged_count >= args.limit:
            logger.info(f"🛑 Reached merge limit of {args.limit}. Stopping.")
            break

        print(f"\n─────────────────────────────────────────────────────────────", flush=True)
        print(f"👉 [{idx}/{len(plan)}] Evaluating PR #{item.number}: {item.title}", flush=True)
        print(f"   Tier: {item.tier_name} | Branch: {item.branch}", flush=True)

        if item.tier_name == "Tier 6 (External Dependencies)" and not args.include_dependencies:
            logger.info(f"⏩ Skipping {item.tier_name} PR #{item.number} (requires --include-dependencies).")
            continue

        # বাংলা মন্তব্য: সবচেয়ে গুরুত্বপূর্ণ ধাপ — পূর্ববর্তী PR মার্জের পর এই PR-এর তাজা লাইভ স্ট্যাটাস রি-চেক করা
        fresh_data = fetch_single_pr_fresh(item.number)
        if not fresh_data:
            logger.warning(f"⚠️ Could not fetch fresh details for PR #{item.number}. Skipping.")
            continue

        if fresh_data.get("state") != "OPEN":
            logger.info(f"ℹ️ PR #{item.number} is already {fresh_data.get('state')}. Skipping.")
            continue

        fresh_mergeable = fresh_data.get("mergeable", "UNKNOWN")
        fresh_summary, fresh_ready, fresh_held, _, fresh_reasons = evaluate_pr_checks(
            fresh_data, allow_holds=args.release_holds
        )

        # ১. ডাইনামিক কনফ্লিক্ট পরীক্ষা (১ বা ২ মার্জ হওয়ার কারণে কি এতে নতুন কনফ্লিক্ট হলো?)
        if fresh_mergeable == "CONFLICTING":
            if args.dry_run:
                logger.warning(f"[DRY-RUN] PR #{item.number} is CONFLICTING. Would apply 'queue:hold' & create Issue.")
            else:
                handle_conflict_pr(
                    item.number,
                    item.branch,
                    item.title,
                    item.author,
                    trigger_pr_num=last_merged_pr,
                )

            # বাংলা মন্তব্য: কনফ্লিক্ট হলে queue:hold ও issue তৈরি করে continue করা (বা stop-on-conflict থাকলে থামা)
            if not continue_on_conflict:
                logger.critical(
                    f"\n🚨 [PIPELINE HALTED] কনফ্লিক্ট শনাক্ত হয়েছে PR #{item.number}-এ!\n"
                    f"   অটোমেটিক Blocker Issue তৈরি করা হয়েছে।\n"
                    f"   পরবর্তী PR-গুলোতে কম্পাউন্ড কনফ্লিক্ট এড়াতে পাইপলাইন থামানো হলো।"
                )
                break
            logger.warning(f"⏩ [CONTINUE ON CONFLICT] PR #{item.number} কনফ্লিক্টযুক্ত হওয়ায় হোল্ডে রেখে পরবর্তী স্বাধীন PR মূল্যায়ন করা হচ্ছে...")
            continue

        # ২. মার্জ-যোগ্যতা ও সিআই চেকের অবস্থা
        if not fresh_ready:
            fresh_body = fresh_data.get("body") or ""
            fresh_has_ev, fresh_ev_msg = check_pr_evidence(fresh_body)
            if auto_heal_enabled and not fresh_has_ev:
                logger.info(f"🩹 PR #{item.number}-এর এভিডেন্স অপূর্ণ ({fresh_ev_msg})। লাইভ হিলিং ও সিআই রি-রান করা হচ্ছে...")
                auto_heal_pr_evidence(item.number, fresh_body, fresh_data.get("statusCheckRollup"))
            # বাংলা মন্তব্য: #2645 — ব্যর্থতায় Self-Healing (lint/format) ও Flaky রিরান;
            # দুটোই বাজেট-সীমিত ও অ্যাসিঙ্ক — মার্জার কখনো দাঁড়িয়ে অপেক্ষা করে না।
            if "CI Failing" in ", ".join(fresh_reasons):
                _paths_now = [f.get("path", "") for f in fresh_data.get("files") or []]
                if SelfHealingPatcher.is_enabled() and SelfHealingPatcher.budget_left(item.number):
                    _fail_log = SelfHealingPatcher.fetch_failure_log(item.number, item.branch)
                    if SelfHealingPatcher.is_healable(_fail_log):
                        if args.dry_run:
                            logger.info(f"[DRY-RUN] PR #{item.number}-এ self-healing প্যাচ পুশ হতো।")
                        else:
                            _ok, _msg = SelfHealingPatcher.heal(item.number, item.branch, _paths_now)
                            if _ok:
                                logger.info(f"🩹 PR #{item.number} self-healed: {_msg}")
                                run_cmd([
                                    "gh", "pr", "comment", str(item.number), "--body",
                                    "🩹 **Self-Healing সম্পন্ন** — lint/format ত্রুটি স্বয়ংক্রিয়ভাবে ঠিক করে "
                                    f"ফিক্স-কমিট পুশ করা হয়েছে (`{_msg}`)। CI সবুজ হলেই ট্রেইনে ফিরবে।",
                                ])
                            else:
                                logger.info(f"ℹ️ Self-healing skipped for PR #{item.number}: {_msg}")
                if FlakyTriageEngine.is_enabled():
                    _failed_ids = []
                    for _check in fresh_data.get("statusCheckRollup") or []:
                        if (_check.get("conclusion") or "") in ("FAILURE", "TIMED_OUT"):
                            _m = re.search(r"/runs/(\d+)", _check.get("detailsUrl") or "")
                            if _m:
                                _failed_ids.append(int(_m.group(1)))
                    _trig = FlakyTriageEngine.schedule_rerun(_failed_ids)
                    if _trig:
                        logger.info(f"🔄 PR #{item.number}-এর {_trig}টি ব্যর্থ run রিরান ট্রিগার (flaky triage)।")

            logger.warning(f"⏩ Skipping PR #{item.number}: Not ready ({', '.join(fresh_reasons)})")
            continue

        # বাংলা মন্তব্য: #2645 — ইন্টেলিজেন্ট প্রি-মার্জ পাইপলাইন (সিমান্টিক রিস্ক
        # → AI Sentinel → ভার্চুয়াল স্টেজিং)। প্রতিটি স্তম্ভ কিল-সুইচযোগ্য; কোনো
        # স্তম্ভ ব্যর্থ হলে PR এই রাউন্ডে স্কিপ — ভাঙা মার্জ কখনোই নয়।
        risk_level, risk_reasons = SemanticRiskClassifier.assess(fresh_data, peer_prs=raw_prs)
        if risk_level != "LOW":
            logger.info(f"🧠 PR #{item.number} semantic risk={risk_level}: {'; '.join(risk_reasons[:3])}")

        if AISentinelReviewer.is_enabled():
            _code, diff_text, _ = run_cmd(["gh", "pr", "diff", str(item.number)])
            sentinel_verdict = AISentinelReviewer.review(
                item.title, diff_text if _code == 0 else "", high_risk=(risk_level == "HIGH")
            )
            logger.info(
                f"🤖 Sentinel verdict for PR #{item.number}: {sentinel_verdict['verdict']} "
                f"({str(sentinel_verdict.get('note', ''))[:60]})"
            )
            if sentinel_verdict["verdict"] == "BLOCK":
                if not args.dry_run:
                    run_cmd([
                        "gh", "pr", "comment", str(item.number),
                        "--body",
                        "🛑 **AI Sentinel BLOCK** — নিরাপত্তা/কোড-স্ক্যানে সন্দেহজনক পরিবর্তন "
                        f"ধরা পড়েছে: {', '.join(sentinel_verdict.get('issues', [])[:3])}। "
                        "বিস্তারিত যাচাইয়ের পর পুশ করলে ট্রেইন আবার মূল্যায়ন করবে।",
                    ])
                logger.warning(f"⏩ PR #{item.number} Sentinel-BLOCK হওয়ায় স্কিপ।")
                continue
            if sentinel_verdict["verdict"] in ("UNKNOWN", "ERROR"):
                # বাংলা মন্তব্য: AI উত্তর অস্পষ্ট — অন্যান্য গেটই রক্ষক; মার্জ থামানো হয় না
                logger.info(f"ℹ️ Sentinel অস্পষ্ট ({sentinel_verdict['verdict']}) — অন্যান্য গেট অনুযায়ী এগোনো হচ্ছে।")

        if risk_level in ("MEDIUM", "HIGH") and SpeculativeStagingRunner.is_enabled():
            if args.dry_run:
                logger.info(f"[DRY-RUN] PR #{item.number}-এর জন্য ভার্চুয়াল স্টেজিং চলত।")
            else:
                _st_ok, _st_report = SpeculativeStagingRunner.run(item.branch)
                if not _st_ok:
                    run_cmd([
                        "gh", "pr", "comment", str(item.number),
                        "--body",
                        "🧪 **Speculative Staging ব্যর্থ** — origin/main-এর ওপর ভার্চুয়াল মার্জ/স্মোক "
                        f"সবুজ হয়নি:\n```\n{_st_report[:800]}\n```\n"
                        "_বাংলা মন্তব্য: main-এ মার্জ করা হয়নি (Zero-Broken-Main গ্যারান্টি)। "
                        "ঠিক করে পুশ করলেই ট্রেইন আবার চেষ্টা করবে।_",
                    ])
                    logger.warning(f"⏩ PR #{item.number} স্টেজিং-ব্যর্থ হওয়ায় স্কিপ: {_st_report[:120]}")
                    continue
                logger.info(f"✅ PR #{item.number} ভার্চুয়াল স্টেজিং সবুজ: {_st_report[:100]}")

        # ৩. ড্রাই-রান সিমুলেশন
        if args.dry_run:
            logger.info(f"[DRY-RUN] ✅ PR #{item.number} is clean & green! Would squash merge.")
            merged_count += 1
            last_merged_pr = item.number
            continue

        # ৪. লাইভ মার্জ (Squash Merge)
        labels = [l.get("name", "") for l in fresh_data.get("labels") or []]
        success = execute_single_merge(item.number, item.title, item.tier_name, labels)
        if not success:
            logger.error(f"❌ Failed to merge PR #{item.number}. Aborting pipeline to preserve safety.")
            break

        merged_count += 1
        last_merged_pr = item.number

        # ৫. পোস্ট-মার্জ ছোট রান (Fast Smoke Run)
        if not args.skip_smoke:
            smoke_ok = run_fast_smoke_check()
            if not smoke_ok:
                logger.critical("🚨 Post-merge smoke check failed! Stopping further merges to protect main.")
                break

        # বাংলা মন্তব্য: গিটহাব ব্যাকগ্রাউন্ডে পরবর্তী PR-গুলোর মার্জ-যোগ্যতা রি-ক্যালকুলেট করার জন্য বাফার সময়
        logger.info("⏳ Waiting 5 seconds for GitHub to update downstream PR mergeability...")
        time.sleep(5)

    print(f"\n🏁 পাইপলাইন সমাপ্ত: মোট {merged_count}টি PR সফলভাবে প্রসেস করা হয়েছে।")


if __name__ == "__main__":
    main()
