#!/usr/bin/env python3
"""Auto-close ghost PRs on Claim Gate failure (#2892).

বাংলা: Claim Gate ব্যর্থ হলে agent-লেখকের PR স্বয়ংক্রিয়ভাবে বন্ধ হয় —
stranded ghost-PR ফাইল-লক (Cross-PR Collision) ও priority-queue বিভ্রান্তি
বন্ধ করতে। Root-cause: gate ব্যর্থ হলেও PR অনির্দিষ্টকাল খোলা থাকত।

নকশা-সীমাবদ্ধতা (issue #2892-র সেশন-নোট — বন্ধ PR #2897-এর বিপজ্জনক
যেকোনো-ব্যর্থতায়-বন্ধ পদ্ধতির শিক্ষা):
  ১. Claim-Gate-নির্দিষ্ট — fresh verdict এখানেই re-run করা হয়
     (gates.run_claim_gate), log-parse নয়। ফ্লেকি-টেস্ট/ট্রানজিয়েন্ট
     ব্যর্থতা কখনো close-এর কারণ নয়; শুধু claim-violation
     (কাঠামোগত — re-run-এ ঠিক হয় না) close-যোগ্য।
  ২. Agent-author নির্দিষ্ট — মানুষ (OWNER/MEMBER/COLLABORATOR) পান
     Bangla advisory, close নয় (Claim Gate-এর association চুক্তির সমতা)।
  ৩. Newest-run race-guard — PR-এর বর্তমান head-SHA এই রানের মূল্যায়নকৃত
     SHA-র সাথে না মিললে abort (নতুন কমিট → নতুন রান বিচার করবে)।
  ৪. Bangla কমেন্ট — সঠিক পথ (atomic_claim.sh) নির্দেশ করে; কোনো
     `|| true` silent-swallow নয়।

ব্যবহার (pr.yml auto-close job):
    PYTHONPATH=.github/scripts python .github/scripts/constitution/\\
        auto_close_on_failure.py --pr 123 --expected-head-sha <sha>

ঘরের নিয়ম: CI API uptime-এর ওপর hard-depend করে না — PR-metadata আনতে
ব্যর্থ হলে fail-open (কিছু না করে বেরিয়ে যায়)।
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # constitution pkg

from constitution.gates import (
    RULES_PATH,
    find_linked_issue_numbers,
    gh_api,
    load_policies,
    run_claim_gate,
)

# ─────────────────────────────── Outcomes ───────────────────────────────


class Outcomes:
    """প্রতিটি সিদ্ধান্ত-পথের নাম — পরীক্ষা ও লগ-উভয়ের চুক্তি।"""

    CLOSED_AGENT = "closed-agent"
    ADVISORY_HUMAN = "advisory-human"
    SKIP_EXEMPT = "skip-exempt"
    RACE_GUARD_ABORT = "race-guard-abort"
    ALREADY_CLOSED = "already-closed"
    NO_CLAIM_FAILURE = "no-claim-failure"
    ABORTED_API = "aborted-api"


# ──────────────────────────── কমেন্ট-টেমপ্লেট ────────────────────────────

CLOSE_COMMENT_TEMPLATE = """## 🔒 PR স্বয়ংক্রিয়ভাবে বন্ধ — Claim Gate ব্যর্থ (No Claim, No PR)

এই PR-এর লেখক এজেন্ট (`{author}`) লিংকড issue-তে বৈধ claim ধারণ করেনি —
Claim Gate (#2644) BLOCK করেছে। Claim-violation কাঠামোগত ত্রুটি — re-run-এ
ঠিক হয় না; ghost-PR হিসেবে ঝুলে থেকে অন্য PR-এর ফাইল-লক করে (#2892)।

**সঠিক পথ:** `scripts/ci/atomic_claim.sh` দিয়ে লিংকড issue-তে claim জিতুন →
তারপর নতুন branch থেকে PR খুলুন। লিংকড issue থেকে `has-pr` লেবেল সরানো
হয়েছে — পরের claimer এগোতে পারবেন।

(স্বয়ংক্রিয় — auto_close_on_failure.py, নতুন-রান race-guard সক্রিয়)"""

ADVISORY_COMMENT_TEMPLATE = """## ⚠️ Advisory — লিংকড issue-তে claim পাওয়া যায়নি

মানুষ-লেখক ({author}, {association}) হিসেবে এটি শুধু পরামর্শ: PR Gate-এর
Claim Gate লিংকড issue-তে আপনার claim যাচাই করতে পারেনি। কাজ শুরুর আগে
issue-তে claim (assign/Atomic Claim) করলে ট্র্যাকিং সুসংগত থাকবে।
**এই PR বন্ধ করা হয়নি।**

(স্বয়ংক্রিয় — auto_close_on_failure.py)"""


# ──────────────────────────── Side-effect চুক্তি ────────────────────────────


class AutoCloseEffects:
    """বাস্তব GitHub side-effects — পরীক্ষায় Recorder দ্বারা প্রতিস্থাপিত।"""

    def __init__(self, token: str | None = None):
        self._token = token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""

    def _request(self, method: str, endpoint: str, payload: dict | None = None) -> object:
        url = f"https://api.github.com/{endpoint.lstrip('/')}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else None

    def close_pr(self, pr_number: int, comment_body: str) -> None:
        # বাংলা মন্তব্য: আগে কমেন্ট, পরে close — close-এর পর কমেন্ট আটকে
        # গেলে বন্ধ-কারণ অজানা থেকে যায়।
        self._request(
            "POST", f"repos/{_repo_slug()}/issues/{pr_number}/comments",
            {"body": comment_body},
        )
        self._request(
            "PATCH", f"repos/{_repo_slug()}/pulls/{pr_number}",
            {"state": "closed"},
        )

    def comment_only(self, pr_number: int, comment_body: str) -> None:
        self._request(
            "POST", f"repos/{_repo_slug()}/issues/{pr_number}/comments",
            {"body": comment_body},
        )

    def remove_has_pr(self, issue_number: int) -> None:
        try:
            self._request(
                "DELETE", f"repos/{_repo_slug()}/issues/{issue_number}/labels/has-pr",
            )
        except Exception as err:  # noqa: BLE001 — লেবেল-সরানো best-effort
            print(f"::warning::has-pr label remove failed on issue "
                  f"#{issue_number} ({err}) — reconciler backstop থাকবে")


def _repo_slug() -> str:
    env = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY")
    if not env:
        raise RuntimeError("cannot determine GH repo (set GH_REPO)")
    return env


# ─────────────────────────────── Core ───────────────────────────────


def run_auto_close(
    pr_number: int,
    expected_head_sha: str,
    policy: dict,
    api=None,
    effects=None,
) -> str:
    """Claim-Gate-ব্যর্থ PR বন্ধের সিদ্ধান্ত-চক্র — injectable (পরীক্ষাযোগ্য)।

    সব সিদ্ধান্ত-পথ Outcomes-এর নাম ফেরত দেয়; CLI-স্তর exit-code নির্ধারণ করে।
    """
    api = api or gh_api
    effects = effects or AutoCloseEffects()

    # ── ধাপ ১: PR metadata (fail-open — API নিচু হলে কিছু না করা নিরাপদ) ──
    try:
        pr = api(f"repos/{_repo_slug()}/pulls/{pr_number}") or {}
    except Exception as err:  # noqa: BLE001 — ঘরের নিয়ম: fail-open
        print(f"::warning::PR #{pr_number} metadata fetch failed ({err}) — fail-open")
        return Outcomes.ABORTED_API

    if (pr.get("state") or "").lower() != "open":
        print(f"PR #{pr_number} already {pr.get('state')} — noop")
        return Outcomes.ALREADY_CLOSED

    # ── ধাপ ২: newest-run race-guard (সীমাবদ্ধতা ৩) ──
    actual_sha = (pr.get("head") or {}).get("sha") or ""
    if expected_head_sha and actual_sha != expected_head_sha:
        print(f"race-guard: PR head {actual_sha[:12]} != run anchor "
              f"{expected_head_sha[:12]} — নতুন রান বিচার করবে, abort")
        return Outcomes.RACE_GUARD_ABORT

    author = (pr.get("user") or {}).get("login", "")
    association = pr.get("author_association", "NONE")
    title = pr.get("title") or ""
    body = pr.get("body") or ""

    # ── ধাপ ৩: exempt লেখক (dependabot ইত্যাদি) কখনো স্পর্শ নয় ──
    exempt = set(policy.get("exempt_authors") or [])
    if author in exempt:
        print(f"author '{author}' exempt — noop")
        return Outcomes.SKIP_EXEMPT

    # ── ধাপ ৪: fresh claim verdict (সীমাবদ্ধতা ১ — log-parse নয়, re-run) ──
    # বাংলা মন্তব্য: run_claim_gate-এর stdout ধরা হয় — gate-এর স্থায়ী চুক্তি-স্ট্রিং
    # ("advisory: human author … unclaimed") দিয়ে warn-only-মানুষ-পথ আলাদা করা হয়;
    # rc-একা অনুপস্থিত-claim-warn (rc=0) আর সত্যিকারের সবুজ (rc=0) আলাদা করতে পারে না।
    verdict_io = io.StringIO()
    with contextlib.redirect_stdout(verdict_io):
        rc = run_claim_gate(
            pr_number, author=author, title=title, body=body,
            association=association, policy=policy, api=api,
        )
    verdict_text = verdict_io.getvalue()

    prefixes = tuple(p for p in (policy.get("agent_author_prefixes") or []) if p)
    is_agent = bool(author.startswith(prefixes)) if prefixes else False

    if rc == 0 and "advisory: human author" in verdict_text:
        # warn-only-মানুষ: claim অনুপস্থিত কিন্তু gate সবুজ — advisory-ই সমতুল্য প্রতিক্রিয়া
        print(f"::warning::human author '{author}' ({association}) claim-বিহীন — "
              f"advisory only (close নয়)")
        effects.comment_only(
            pr_number,
            ADVISORY_COMMENT_TEMPLATE.format(author=author, association=association),
        )
        return Outcomes.ADVISORY_HUMAN
    if rc == 0:
        print("Claim Gate এখন সবুজ — ব্যর্থতা claim-বহির্ভূত (transient/অন্য gate); "
              "close করা হবে না")
        return Outcomes.NO_CLAIM_FAILURE

    # ── ধাপ ৫: rc==1 — agent → close; মানুষ → advisory (সীমাবদ্ধতা ২) ──
    if not is_agent:
        print(f"::warning::human author '{author}' ({association}) claim-বিহীন — "
              f"advisory only (close নয়)")
        effects.comment_only(
            pr_number,
            ADVISORY_COMMENT_TEMPLATE.format(author=author, association=association),
        )
        return Outcomes.ADVISORY_HUMAN

    # agent-author + claim ব্যর্থ → close + has-pr ছাড়া (সীমাবদ্ধতা ৪: Bangla)
    effects.close_pr(pr_number, CLOSE_COMMENT_TEMPLATE.format(author=author))
    print(f"PR #{pr_number} closed (agent claim-violation) — ghost decongested")

    for num in find_linked_issue_numbers(title, body):
        effects.remove_has_pr(num)

    return Outcomes.CLOSED_AGENT


# ─────────────────────────────── CLI ───────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="#2892 — auto-close PR on Claim Gate failure (agent authors)",
    )
    parser.add_argument("--pr", type=int, required=True, help="PR number")
    parser.add_argument(
        "--expected-head-sha", default="",
        help="রান-ট্রিগারকৃত head SHA (race-guard anchor; খালি হলে চেক স্কিপ)",
    )
    parser.add_argument("--rules", default=str(RULES_PATH), help="rules.yml path")
    args = parser.parse_args()

    policies = load_policies(Path(args.rules))
    policy = policies.get("claim_policy") or {}

    outcome = run_auto_close(args.pr, args.expected_head_sha, policy)
    print(f"auto-close outcome: {outcome}")
    # বাংলা মন্তব্য: সব সিদ্ধান্ত-পথই সাফল্য — এই job লাল মানে নিজের অভ্যন্তরীণ
    # ত্রুটি, যা দৃশ্যমান থাকতে হবে (silent-swallow নয়)। fail-open শুধু
    # নির্দিষ্ট API-down পথে, সেটিও outcome-হিসেবে প্রকাশিত।
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
