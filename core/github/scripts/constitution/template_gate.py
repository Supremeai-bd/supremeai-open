#!/usr/bin/env python3
"""Template Conformance Gate (#2912) — fixed template mandate, সব agent-এর জন্য।

Founder directive: "sob kajer jonno fixed template kore daowa… issue ki korom
hobe… sob agents same template follow korbe" — advisory template নয়, enforced
chain। Red-team audit-এর প্রতিকার (V3/V4/V6):

  V3 — GitHub issue-template শুধু web UI-তে auto-apply হয়; agent-রা API
       (`gh issue create --body`) দিয়ে freeform issue খুলত — Touching Files /
       Verification চুক্তি অদৃশ্য।
  V4 — PR template `gh pr create --body`-তে replace হয়ে যেত — একলাইন body-তে
       valid PR।
  V6 — `create_issue.py`-এর blocker/discovery formatter template-বহির্ভূত।

দুই মোড:
  --issue N : issue-টেমপ্লেট যাচাই + self-heal (label/comment) —
              `.github/workflows/issue-template-guard.yml` (issues: opened/edited)
  --pr N    : PR-টেমপ্লেট যাচাই (BLOCKING) + linked-issue chain-যাচাই —
              `.github/workflows/pr.yml` → system-gates

চেইন-ডকট্রিন (poka-yoke — ভুল জন্মানোর আগেই থামানো):
  template:violating issue → claim অবৈধ → branch ব্লক (branch_creation_guard)
  → PR ব্লক (এই গেট)। ফলে agent ভুল করতে চাইলেও চেইনের কোনো ধাপ পার হতে
  পারবে না — "any agent cannot make mistakes by mistake."

Identity default-deny (#2912 V1): actor-শ্রেণি নির্ধারণ এখানেই canonical —
  human_allowlist-এ থাকলে human, trusted_bot_actors-এ থাকলে trusted-bot,
  **বাকি সবাই agent** (অজানা পরিচয় = বিশ্বাস নয়)। branch_creation_guard-ও
  এই ফাংশন রিইউজ করে — দুই গেটে একই SSOT-সংজ্ঞা।

Policy SSOT: rules.yml → template_policy + identity_policy (DEFAULT fallback)।
API-down → সৎ fail-open (SKIP, false-block নয়) — এটা শৃঙ্খলা-গার্ড; কিন্তু
--pr মোডে validation সম্ভব হলে ফলাফল কঠোর (BLOCK)।
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gates import find_linked_issue_numbers  # noqa: E402 — same-dir import (branch_creation_guard-প্যাটার্ন)

RULES_PATH = (
    Path(__file__).resolve().parents[3] / ".github" / "constitution" / "rules.yml"
)

# বাংলা মন্তব্য: DEFAULT policy — rules.yml-এর template_policy/identity_policy
# থাকলে সেটিই জেতে (SSOT); এটি fallback, যাতে rules.yml না পাওয়া গেলেও গেট সৎভাবে চলে।
DEFAULT_TEMPLATE_POLICY: dict = {
    "enabled": True,
    # identity (default-deny — #2912 V1): মানুষ শুধু allowlist-এ, বাকি সব actor = agent
    "human_allowlist": ["SaifulHaqueNiloy"],
    "trusted_bot_actors": [
        "dependabot[bot]",
        "app/dependabot",
        "github-actions[bot]",
        "renovate[bot]",
    ],
    "issue": {
        # enforce_from-এর আগের issue grandfathered (লাইভ fleet-কে রাতারাতি ভাঙা নয়)
        "enforce_from": "2026-10-01T20:00:00Z",
        "violating_label": "template:violating",
        # ops-telemetry — কাজ-ইস্যু নয়, template-ও লাগে না
        "exempt_labels": ["type:ledger", "type:platform-alert", "template:exempt"],
        "exempt_body_markers": ["<!-- SUPREMEAI_PRIORITY_QUEUE_LEDGER"],
        "required_title_regex": r"^(feat|fix|chore|docs|refactor|test|perf|audit|ops|task)\([^)]+\): .+",
        # প্রতিটি key: কোনো না কোনো heading-লাইনে (#{1,6}) case-insensitive থাকতে হবে
        "required_sections": ["Mission", "Touching Files", "Verification"],
        # Priority: body-তে P0-critical/P1-high/P2-medium/P3-low টোকেন অথবা লেবেল
        "priority_regex": r"P[0-3]-(critical|high|medium|low)",
    },
    "pr": {
        "enforce_from": "2026-10-01T20:00:00Z",
        # প্রতিটি গ্রুপের যেকোনো একটি বিকল্প যথেষ্ট (Linked Issue/Related Issue, Rollback/রোলব্যাক)
        "required_sections": [
            ["Summary"],
            ["Linked Issue", "Related Issue"],
            ["Rollback", "রোলব্যাক"],
        ],
    },
}

HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*#*\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Policy loading (SSOT: rules.yml)
# ---------------------------------------------------------------------------
def _deep_merge(base: dict, override: dict) -> dict:
    """দুই স্তরের nested-merge — DEFAULT fallback + rules.yml override।"""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_template_policy(rules_path: Path = RULES_PATH) -> dict:
    """rules.yml → template_policy + identity_policy (DEFAULT-মার্জ)।"""
    pol = dict(DEFAULT_TEMPLATE_POLICY)
    try:
        import yaml

        data = yaml.safe_load(Path(rules_path).read_text(encoding="utf-8")) or {}
        cfg = data.get("template_policy")
        if isinstance(cfg, dict):
            pol = _deep_merge(pol, cfg)
        # identity_policy আলাদা ব্লকে থাকলে সেটি একই policy-তে উঠে আসে (canonical)
        ident = data.get("identity_policy")
        if isinstance(ident, dict):
            pol["human_allowlist"] = (
                ident.get("human_allowlist") or pol["human_allowlist"]
            )
            pol["trusted_bot_actors"] = (
                ident.get("trusted_bot_actors") or pol["trusted_bot_actors"]
            )
    except Exception as exc:  # noqa: BLE001 — সৎ fallback, নীরবে মরা নয়
        print(f"⚠️ rules.yml load failed ({exc}) — DEFAULT template policy fallback")
    return pol


# ---------------------------------------------------------------------------
# Identity (default-deny — canonical, branch_creation_guard-ও রিইউজ করে)
# ---------------------------------------------------------------------------
def normalize_login(actor: str) -> str:
    """`app/supremeai-planner` / `supremeai-planner[bot]` → `supremeai-planner`।"""
    a = (actor or "").strip()
    a = a.removesuffix("[bot]")
    a = a.removeprefix("app/")
    return a


def actor_category(actor: str, policy: dict) -> str:
    """Actor-শ্রেণি: "human" | "trusted_bot" | "agent"।

    #2912 V1 ROOT-CAUSE FIX: আগে agent-ডিটেকশন ছিল allowlist-of-prefixes
    (``supremeai-`` দিয়ে শুরু হলে agent) — অজানা/নতুন বট (`niloy-helper-bot`)
    "human" বলে ফাঁকি দিত। এখন default-deny: মানুষ শুধু human_allowlist-এ,
    পরিচিত infra-bot trusted_bot_actors-এ, **বাকি সব পরিচয় = agent** (enforced)।
    """
    a = (actor or "").strip()
    if not a:
        return "agent"  # অজানা/খালি = কখনো human নয়
    norm = normalize_login(a)
    humans = {normalize_login(h) for h in (policy.get("human_allowlist") or [])}
    if norm in humans or a in humans:
        return "human"
    trusted = set(policy.get("trusted_bot_actors") or [])
    if a in trusted or norm in {normalize_login(t) for t in trusted}:
        return "trusted_bot"
    return "agent"


def is_agent_actor(actor: str, policy: dict) -> bool:
    """Backward-compatible wrapper — branch_creation_guard-এর পুরনো নাম।"""
    return actor_category(actor, policy) == "agent"


# ---------------------------------------------------------------------------
# Validation helpers (pure — injectable-api ছাড়াই টেস্টযোগ্য)
# ---------------------------------------------------------------------------
def _headings(body: str) -> list:
    return [m.group(1).casefold() for m in HEADING_RE.finditer(body or "")]


def _has_section(body: str, key: str) -> bool:
    return any(key.casefold() in h for h in _headings(body))


def _labels_of(issue_or_pr: dict) -> set:
    out = set()
    for lb in issue_or_pr.get("labels") or []:
        out.add(lb.get("name") if isinstance(lb, dict) else str(lb))
    return {x for x in out if x}


def _at_or_after(created_at: str, enforce_from: str) -> bool:
    """created_at >= enforce_from? (ISO-8601 Z-ফরম্যাট — parse-fallback string-compare)।"""
    try:
        c = _dt.datetime.fromisoformat((created_at or "").replace("Z", "+00:00"))
        e = _dt.datetime.fromisoformat((enforce_from or "").replace("Z", "+00:00"))
        return c >= e
    except ValueError:
        return str(created_at or "") >= str(enforce_from or "")


def validate_issue(issue: dict, policy: dict) -> tuple:
    """Issue-টেমপ্লেট যাচাই। Return (status, missing, reason) — status ∈
    {compliant, violating, skip}।

    skip-কারণ: disabled / human / trusted_bot / exempt / grandfathered।
    violating-কারণ: title-convention বা বাধ্যতামূলক সেকশন (Mission / Touching
    Files / Verification / Priority) অনুপস্থিত — agent_task + group_sequence
    উভয় টেমপ্লেটের অভিন্ন চুক্তি।
    """
    if not policy.get("enabled", True):
        return "skip", [], "policy disabled"
    ip = policy.get("issue") or {}

    author = (
        (issue.get("user") or {}).get("login", "")
        if isinstance(issue.get("user"), dict)
        else str(issue.get("user") or "")
    )
    cat = actor_category(author, policy)
    if cat != "agent":
        return "skip", [], f"author '{author}' is {cat} — advisory only"

    labels = _labels_of(issue)
    exempt_labels = set(ip.get("exempt_labels") or [])
    if labels & exempt_labels:
        hit = sorted(labels & exempt_labels)[0]
        return "skip", [], f"exempt label '{hit}' (ops telemetry / explicit override)"

    body = issue.get("body") or ""
    for marker in ip.get("exempt_body_markers") or []:
        # startswith-সিম্যান্টিক্স (#2912 self-red-team): ledger-এর body মার্কার
        # দিয়েই *শুরু* হয়। substring-match হলে যেকোনো ডকুমেন্টেশন-ইস্যু যেটি
        # মার্কার-টেক্সট উদ্ধৃত করে (যেমন এই ফিক্সের নিজের issue!) false-exempt হতো।
        if body.lstrip().startswith(marker):
            return "skip", [], f"exempt body marker ({marker[:44]}…)"

    created = issue.get("created_at") or ""
    enforce_from = ip.get("enforce_from") or ""
    if enforce_from and not _at_or_after(created, enforce_from):
        return (
            "skip",
            [],
            f"grandfathered (created {created} < enforce_from {enforce_from})",
        )

    missing: list = []
    title = (issue.get("title") or "").strip()
    if not re.match(
        ip.get(
            "required_title_regex",
            DEFAULT_TEMPLATE_POLICY["issue"]["required_title_regex"],
        ),
        title,
    ):
        missing.append("title-convention (type(scope): description)")

    for section in ip.get("required_sections") or []:
        if not _has_section(body, str(section)):
            missing.append(f"section '{section}'")

    prio_re = ip.get(
        "priority_regex", DEFAULT_TEMPLATE_POLICY["issue"]["priority_regex"]
    )
    if not (re.search(prio_re, body) or any(re.search(prio_re, lb) for lb in labels)):
        missing.append("priority tier (P0-critical/P1-high/P2-medium/P3-low)")

    if missing:
        return "violating", missing, f"template চুক্তি অসম্পূর্ণ: {', '.join(missing)}"
    return "compliant", [], "fixed-template contract satisfied"


def validate_pr(pr: dict, linked_issues: list, policy: dict) -> tuple:
    """PR-টেমপ্লেট যাচাই + linked-issue chain-যাচাই। Return (status, missing, reason)।

    chain-ডকট্রিন: agent-PR শুধু নিজের template নয় — যে issue-কে রেফার করছে
    সেই issue-টিও (agent-authored, non-exempt, post-enforce_from) compliant
    হতে হবে; নইলে template:violating issue দিয়ে কাজ পাস করার পথ খোলা থাকত।
    """
    if not policy.get("enabled", True):
        return "skip", [], "policy disabled"
    pp = policy.get("pr") or {}

    author = (
        (pr.get("user") or {}).get("login", "")
        if isinstance(pr.get("user"), dict)
        else str(pr.get("user") or "")
    )
    cat = actor_category(author, policy)
    if cat != "agent":
        return "skip", [], f"author '{author}' is {cat} — advisory only"

    created = pr.get("created_at") or ""
    enforce_from = pp.get("enforce_from") or ""
    if enforce_from and not _at_or_after(created, enforce_from):
        return (
            "skip",
            [],
            f"grandfathered (created {created} < enforce_from {enforce_from})",
        )

    body = pr.get("body") or ""
    missing: list = []
    for group in pp.get("required_sections") or []:
        if not any(_has_section(body, str(alt)) for alt in group):
            missing.append(f"section '{group[0]}'")

    # চেইন-যাচাই: violating linked-issue → PR-ও violating
    for li in linked_issues or []:
        if not isinstance(li, dict):
            continue
        li_status, li_missing, _ = validate_issue(li, policy)
        if li_status == "violating":
            missing.append(
                f"linked issue #{li.get('number')} template-অসম্পূর্ণ ({', '.join(li_missing)})"
            )

    if missing:
        return "violating", missing, f"PR template চুক্তি অসম্পূর্ণ: {'; '.join(missing)}"
    return "compliant", [], "fixed-template contract satisfied (PR + linked issues)"


# ---------------------------------------------------------------------------
# Self-heal (issue mode): label + corrective comment + un-label on fix
# ---------------------------------------------------------------------------
VIOLATING_COMMENT = """## 📋 Template Guard — এই issue-টি fixed template মানছে না (`template:violating`)

**Invariant (#2912): সব agent-কাজ একই fixed template-এ হবে — "issue ki korom hobe" এখন চুক্তি।**

- **Author:** `{actor}`
- **অনুপস্থিত:** {missing}

### ঠিক করার নিয়ম (edit করলেই লেবেল সরে যাবে — self-heal)
1. **Title:** `type(scope): description` — যেমন `fix(ci): ...`, `feat(backend): ...`
2. **`### Mission & Problem Statement`** — কী ও কেন (প্রমাণ-চেইনসহ)
3. **`### Priority Tier`** — `P0-critical` / `P1-high` / `P2-medium` / `P3-low`
4. **`### Touching Files (Scope Gate Boundary)`** — যে ফাইলগুলোতে হাত লাগবে (Scope Gate-এর ভিত্তি)
5. **`### 3-Tier Verification Contract`** — reflection / boot / pytest কমান্ড

> টেমপ্লেট: `.github/ISSUE_TEMPLATE/agent_task.yml` · চুক্তি: AGENT_RULES.md ভাগ ১-১৩
> **চেইন-সতর্কতা:** এই লেবেল থাকা অবস্থায় এই issue-র claim দিয়ে branch/PR খোলা যাবে না
> (Branch Creation Guard + Template Gate উভয়ই ব্লক করবে)। 🙏
"""

RESOLVED_COMMENT = """## ✅ Template Guard — template এখন সম্পূর্ণ (`template:violating` সরানো হয়েছে)

Fixed-template চুক্তি পূরণ — এই issue এখন স্বাভাবিকভাবে claim/branch/PR-যোগ্য। 🎉
"""


def apply_issue_verdict(
    issue: dict, verdict: tuple, policy: dict, api, repo: str
) -> list:
    """Verdict প্রয়োগ — violating: label+comment (প্রথমবারই কমেন্ট, স্প্যাম-নয়);
    compliant: লেবেল থাকলে সরানো + একবার রেজলিউশন-কমেন্ট। Return action-তালিকা।"""
    api = api or gh_api
    actions: list = []
    num = issue.get("number")
    if not num:
        return actions
    status, missing, _reason = verdict
    ip = policy.get("issue") or {}
    vlabel = ip.get("violating_label", "template:violating")
    labels = _labels_of(issue)
    actor = (issue.get("user") or {}).get("login", "?")

    if status == "violating":
        if vlabel not in labels:
            try:
                api(
                    f"repos/{repo}/issues/{num}/labels",
                    method="POST",
                    payload={"labels": [vlabel]},
                )
                actions.append(f"label '{vlabel}' added")
            except Exception as exc:  # noqa: BLE001
                actions.append(f"label add FAILED ({exc})")
        # কমেন্ট শুধু transition-এ (লেবেল আগে ছিল না) — প্রতি edit-এ স্প্যাম নয়
        if vlabel not in labels:
            try:
                api(
                    f"repos/{repo}/issues/{num}/comments",
                    method="POST",
                    payload={
                        "body": VIOLATING_COMMENT.format(
                            actor=actor, missing=", ".join(missing or ["?"])
                        )
                    },
                )
                actions.append("corrective comment posted")
            except Exception as exc:  # noqa: BLE001
                actions.append(f"comment FAILED ({exc})")
    elif status == "compliant" and vlabel in labels:
        try:
            api(f"repos/{repo}/issues/{num}/labels/{vlabel}", method="DELETE")
            actions.append(f"label '{vlabel}' removed (self-heal)")
            api(
                f"repos/{repo}/issues/{num}/comments",
                method="POST",
                payload={"body": RESOLVED_COMMENT},
            )
            actions.append("resolution comment posted")
        except Exception as exc:  # noqa: BLE001
            actions.append(f"label remove FAILED ({exc})")
    return actions


# ---------------------------------------------------------------------------
# API (gh CLI প্রথমে, urllib fallback — branch_creation_guard-প্যাটার্ন)
# ---------------------------------------------------------------------------
def gh_api(
    endpoint: str,
    method: str = "GET",
    payload: dict | None = None,
    token: str | None = None,
):
    try:
        cmd = ["gh", "api", endpoint]
        if method != "GET":
            cmd = ["gh", "api", "-X", method, endpoint]
            if payload is not None:
                cmd += ["--input", "-"]
        res = subprocess.run(
            cmd,
            input=json.dumps(payload)
            if (payload is not None and method != "GET")
            else None,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=True,
        )
        return json.loads(res.stdout) if res.stdout.strip() else {}
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError):
        pass
    tok = token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not tok:
        raise RuntimeError(f"no gh CLI and no token for API call: {endpoint}")
    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {tok}")
    req.add_header("Accept", "application/vnd.github+json")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body.strip() else {}


def _linked_issues_for_pr(pr: dict, api, repo: str) -> list:
    """PR title/body → linked issue-নম্বর → issue-dict তালিকা (chain-যাচাইয়ের জন্য)।"""
    nums = find_linked_issue_numbers(pr.get("title") or "", pr.get("body") or "")
    out: list = []
    for n in nums[:5]:  # sanity-cap
        try:
            out.append(api(f"repos/{repo}/issues/{n}"))
        except Exception:  # noqa: BLE001 — একটি issue fetch-ব্যর্থ পুরো গেট ভাঙবে না
            continue
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Template Conformance Gate (#2912)")
    parser.add_argument(
        "--issue", type=int, default=0, help="issue number to validate (self-heal mode)"
    )
    parser.add_argument(
        "--pr", type=int, default=0, help="PR number to validate (blocking mode)"
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable verdict on stdout"
    )
    args = parser.parse_args()

    repo = os.environ.get("GITHUB_REPOSITORY") or os.environ.get("GH_REPO") or ""
    if not repo:
        print("[SKIP] missing GITHUB_REPOSITORY/GH_REPO context")
        return 0
    policy = load_template_policy()

    if args.issue:
        try:
            issue = gh_api(f"repos/{repo}/issues/{args.issue}")
        except Exception as exc:  # noqa: BLE001 — API-down = fail-open skip
            print(f"[SKIP] issue #{args.issue} fetch failed ({exc})")
            return 0
        verdict = validate_issue(issue, policy)
        status, missing, reason = verdict
        actions = apply_issue_verdict(issue, verdict, policy, gh_api, repo)
        line = f"Template Gate (issue #{args.issue}): {status.upper()} — {reason}"
        print(line)
        for a in actions:
            print(f"  ↳ action: {a}")
        if args.json:
            print(
                json.dumps(
                    {
                        "mode": "issue",
                        "number": args.issue,
                        "status": status,
                        "missing": missing,
                        "reason": reason,
                        "actions": actions,
                    }
                )
            )
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(f"### 📋 Template Gate (issue #{args.issue})\n\n- {line}\n")
                for a in actions:
                    fh.write(f"- {a}\n")
        return 1 if status == "violating" else 0

    if args.pr:
        try:
            pr = gh_api(f"repos/{repo}/pulls/{args.pr}")
            linked = _linked_issues_for_pr(pr, gh_api, repo)
        except Exception as exc:  # noqa: BLE001 — API-down = fail-open skip
            print(f"[SKIP] PR #{args.pr} fetch failed ({exc})")
            return 0
        status, missing, reason = validate_pr(pr, linked, policy)
        line = f"Template Gate (PR #{args.pr}): {status.upper()} — {reason}"
        print(line)
        if args.json:
            print(
                json.dumps(
                    {
                        "mode": "pr",
                        "number": args.pr,
                        "status": status,
                        "missing": missing,
                        "reason": reason,
                    }
                )
            )
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(f"### 📋 Template Gate (PR #{args.pr})\n\n- {line}\n")
        if status == "violating":
            # বাংলা মন্তব্য: actionable BLOCK — ঠিক কোথায় কী যোগ করতে হবে বলে দেওয়া
            print(f"::error::TEMPLATE GATE BLOCK — {reason}")
            print(
                "::error::সমাধান: PULL_REQUEST_TEMPLATE.md-এর সেকশনগুলো PR body-তে রাখুন "
                "(## Summary · ## Linked Issue (Refs #N) · ## Rollback Path) এবং linked issue-র "
                "body-তে Mission/Priority/Touching Files/Verification সেকশন যোগ করুন।"
            )
            return 1
        return 0

    print("Template Gate: কিছু করার নেই (--issue N বা --pr N দিন)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
