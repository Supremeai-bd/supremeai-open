#!/usr/bin/env python3
"""Freshness Gate (#2935) — root-level old-code-push prevention.

# বাংলা মন্তব্য (লাইভ ঘটনা, 2026-10-01): planner-এর PR #2924/#2926 পুরনো
# main-base-এ জন্মেছিল (merge-base main-এর HEAD-এর অনেক পেছনে)। main এগিয়ে
# যাওয়ার পর সেগুলো merge করলে নতুন main-এর কোড (rules.yml, pr.yml,
# AGENT_RULES.md…) চুপচাপ মুছে যেত — অ্যাডমিনের ভাষায় "old code push"।
# অ্যাডমিন-নির্দেশ: "next time ai rokom error root theke block korar
# behostha koro… new main er sathe mil thakle e push hobe" — অর্থাৎ PR-এর
# head সর্বশেষ main না ধরলে push/merge হতেই পারবে না।
#
# এনফোর্সমেন্ট-বিন্দু = pr.yml system-gates (required check) — এটাই merge-এর
# রুট-গেট; ভাঙা PR এখানেই আটকাবে, main-এ পৌঁছানোর আগে।
#
# মোড (rules.yml freshness_policy.mode, SSOT):
#   strict  (default) — merge-base ≠ main-HEAD হলেই BLOCK (overlap নির্বিশেষে):
#                       সরল, অনুমান-মুক্ত, অ্যাডমিন-ডকট্রিনের হুবহু অনুবাদ।
#   overlap — main-পাশের বদলানো ফাইল ∩ PR-এর ফাইল শূন্য হলে কেবল WARNING।
#   advisory — কখনো BLOCK নয়, শুধু WARNING (জরুরি-অপারেশন উইন্ডোর জন্য)।
#
# Exemption: freshness_policy.exempt_actors (trusted bots — dependabot নিজেই
# rebase করে; auto-merge lane আটকাবে না)। PR-API থেকে author পড়া হয় (--pr)।
#
# Self-heal নির্দেশনা প্রতিটি BLOCK-আউটপুটে দেওয়া থাকে — agent কপি-পেস্ট
# করলেই সারানো (fetch → merge main → push → gate re-run)।
#
# Usage:
#   python .github/scripts/constitution/freshness_gate.py --pr 123
#   python .github/scripts/constitution/freshness_gate.py --mode overlap
#   python .github/scripts/constitution/freshness_gate.py --json   # machine output
#
# Exit codes: 0 = PASS/WARN · 1 = BLOCK
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable

RULES_PATH = Path(__file__).resolve().parents[3] / ".github" / "constitution" / "rules.yml"

DEFAULT_POLICY: dict[str, Any] = {
    "mode": "strict",  # strict | overlap | advisory
    "main_ref": "origin/main",
    "exempt_actors": [
        "dependabot[bot]",
        "app/dependabot",
        "renovate[bot]",
        "github-actions[bot]",
    ],
}

OK = {"SUCCESS", "SKIPPED", "NEUTRAL"}


def load_policy(rules_path: Path = RULES_PATH) -> dict[str, Any]:
    """rules.yml → freshness_policy (DEFAULT-merge) — gates.py-প্যাটার্ন।"""
    pol = dict(DEFAULT_POLICY)
    try:
        import yaml  # noqa: PLC0415 — lazy: CI-রানারে থাকে, লোকালে ছাড়

        data = yaml.safe_load(Path(rules_path).read_text(encoding="utf-8")) or {}
        override = data.get("freshness_policy") or {}
        for key, val in override.items():
            if key in pol:
                pol[key] = val
    except Exception:  # noqa: BLE001 — policy-লোড ব্যর্থতা গেট থামাবে না
        pass
    return pol


# ── ইনজেক্টেবল স্তর (tests: fake git/API) ────────────────────────────────────

def real_git(*args: str) -> str:
    res = subprocess.run(["git", *args], capture_output=True, text=True, timeout=60, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])}… failed: {res.stderr[:200]}")
    return res.stdout.strip()


Git = Callable[..., str]


def real_api(endpoint: str) -> Any:
    """REST GET — author-সমৃদ্ধির জন্যই (গেটের মূল যুক্তি git-ভিত্তিক)।"""
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    req = urllib.request.Request(  # noqa: S310
        f"https://api.github.com/{endpoint.lstrip('/')}",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        raw = resp.read().decode()
    return json.loads(raw) if raw.strip() else None


Api = Callable[..., Any]


# ── মূল যুক্তি ────────────────────────────────────────────────────────────────

def pr_author(api: Api, repo: str, pr_number: int | None) -> str | None:
    """PR author (exemption-চেকের জন্য)। API না পারলে env-fallback।"""
    if not pr_number:
        return os.environ.get("GITHUB_ACTOR")
    try:
        pr = api(f"repos/{repo}/pulls/{pr_number}")
        return ((pr or {}).get("user") or {}).get("login")
    except Exception:  # noqa: BLE001 — enrichment-ব্যর্থতা গেট ভাঙবে না
        return os.environ.get("GITHUB_ACTOR")


def changed_files(git: Git, rev_range: str) -> set[str]:
    """`git diff --name-only <range>` → ফাইল-সেট।"""
    out = git("diff", "--name-only", rev_range)
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


def evaluate(
    git: Git = real_git,
    pol: dict | None = None,
    pr_number: int | None = None,
    repo: str | None = None,
    api: Api = real_api,
) -> dict[str, Any]:
    """একটি PR-head-এর freshness-রায়। রিটার্ন: {verdict, behind, overlap, reasons…}।"""
    pol = pol or load_policy()
    repo = repo or os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY", "")

    main_ref = pol["main_ref"]
    head = git("rev-parse", "HEAD")
    main_sha = git("rev-parse", main_ref)
    base = git("merge-base", "HEAD", main_ref)

    result: dict[str, Any] = {
        "verdict": "PASS",
        "mode": pol["mode"],
        "head": head[:12],
        "main": main_sha[:12],
        "merge_base": base[:12],
        "synced": base == main_sha,
        "overlap": [],
        "reasons": [],
        "warnings": [],
        "exempt": False,
    }

    # ── exemption: trusted bots (নিজস্ব rebase-অটোমেশন আছে)
    actor = pr_author(api, repo, pr_number)
    if actor and actor in set(pol["exempt_actors"]):
        result["exempt"] = True
        result["warnings"].append(f"actor {actor} exempt (trusted bot — self-rebasing automation)")
        return result

    if result["synced"]:
        # ── synced: advisory-only — PR-এ মুছে-ফেলা ফাইল আছে কি? (ইচ্ছাকৃত-অপসারণের
        # যুক্তি Scope/Verification Gate যাচাই করবে; এখানে সতর্কতা-সংকেত)
        stat = git("diff", "--name-status", f"{base}..HEAD")
        deleted = {ln.split("\t", 1)[1].strip() for ln in stat.splitlines() if ln.startswith("D")}
        if deleted:
            result["warnings"].append(
                f"PR {len(deleted)}টি ফাইল মুছছে: {', '.join(sorted(deleted)[:5])} — "
                "Scope/Verification Gate-এ ইচ্ছাকৃত-অপসারণের যুক্তি দিন"
            )
        return result

    # ── behind main: old-code-push ঝুঁকি
    result["verdict"] = "BEHIND"
    main_side = changed_files(git, f"{base}..{main_ref}")
    pr_side = changed_files(git, f"{base}..HEAD")
    overlap = sorted(main_side & pr_side)
    result["overlap"] = overlap
    behind_count = git("rev-list", "--count", f"HEAD..{main_ref}")
    result["behind_by"] = int(behind_count) if behind_count.isdigit() else -1

    if pol["mode"] == "advisory":
        result["verdict"] = "WARN"
        result["warnings"].append("freshness_policy.mode=advisory — BLOCK নয়, তবে sync দৃঢ়ভাবে প্রস্তাবিত")
        return result

    if pol["mode"] == "overlap" and not overlap:
        result["verdict"] = "WARN"
        result["warnings"].append(
            "main এগিয়ে গেছে কিন্তু ফাইল-ওভারল্যাপ শূন্য — merge-safe সম্ভাবনা বেশি (mode=overlap)"
        )
        return result

    # ── BLOCK: strict-মোড, বা overlap-মোডে সংঘর্ষ-ঝুঁকি
    result["verdict"] = "BLOCK"
    reason = (
        f"PR-head সর্বশেষ main-এর পেছনে ({result['behind_by']} commit) — "
        f"merge করলে main-এর নতুন কোড পুরনো অবস্থায় ফেরত যেতে পারে (old-code push)।"
    )
    result["reasons"].append(reason)
    if overlap:
        result["reasons"].append(
            f"দ্বৈত-পরিবর্তিত ফাইল ({len(overlap)}টি): {', '.join(overlap[:8])}"
            + ("…" if len(overlap) > 8 else "")
        )
    result["reasons"].append(
        "Self-heal: `git fetch origin && git merge origin/main` (বা rebase) → সংঘর্ষ সমাধান → "
        "push → gate পুনরায় চলবে। অ্যাডমিন-ডকট্রিন #2935: 'new main er sathe mil thakle e push hobe'।"
    )
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Freshness Gate (#2935) — old-code-push root-block")
    parser.add_argument("--pr", type=int, default=None, help="PR number (author-exemption enrichment)")
    parser.add_argument("--mode", choices=["strict", "overlap", "advisory"], default=None,
                        help="rules.yml-override (সাধারণত দরকার হয় না)")
    parser.add_argument("--json", action="store_true", help="machine-readable JSON আউটপুট")
    args = parser.parse_args()

    pol = load_policy()
    if args.mode:
        pol["mode"] = args.mode

    result = evaluate(pol=pol, pr_number=args.pr)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        print(f"🧊 Freshness Gate (#2935) — {stamp}")
        print(f"   head={result['head']} merge-base={result['merge_base']} main={result['main']} → "
              f"{'SYNCED ✅' if result['synced'] else 'BEHIND ❌'} (mode={result['mode']})")
        for warn in result["warnings"]:
            print(f"   ⚠️  {warn}")
        for reason in result["reasons"]:
            print(f"   ❌ {reason}")

    if result["verdict"] == "BLOCK":
        print("   → BLOCK: PR সর্বশেষ main-এর সাথে sync না হওয়া পর্যন্ত merge হবে না।")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
