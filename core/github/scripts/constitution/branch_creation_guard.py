#!/usr/bin/env python3
"""Branch Creation Guard (#2907) — no-branch-without-claim, branch-টাইম enforcement.

Founder directive: "agents can't create branch without creating or claiming issue
… any agent cannot make mistakes by mistake."

PR-টাইম Claim Gate (#2644) ভুল ধরে কিন্তু **দেরিতে** (branch → কাজ → PR → তারপর ব্লক)।
এই guard `on: create` ওয়ার্কফ্লোতে branch-এর জন্মমুহূর্তেই যাচাই করে — violation হলে
branch **delete** + issue-তে বাংলা ব্যাখ্যা-কমেন্ট (self-heal): ভুল branch থেকে কখনো
PR-ই খোলা যাবে না।

যাচাই-চেইন (policy SSOT: rules.yml → branch_creation_policy):
  1. tag → skip (workflow-level; এখানেও ref_type guard)
  2. exempt-প্যাটার্ন (main/group/*/docs/*/dependabot/*…)
  3. slot-registry branch (AGENT_SLOT_REGISTRY.yaml-তালিকাভুক্ত স্লট-ব্রাঞ্চ) → sanctioned
  4. মানুষ (non-agent actor) → advisory-allow (এজেন্ট-পুলিশিং; মানুষ = গভর্নেন্স)
  5. branch-নামে issue-number (≥২ ডিজিট) → না পেলে VIOLATION ("branch without issue")
  6. issue open? → না পেলে/বন্ধ হলে VIOLATION
  7. actor-এর claim ওই issue-তে? (gates.py-র extract_claim_agents + claim_matches
     রিইউজ — #2891 identity-fix সহ) → না পেলে VIOLATION ("no claim, no branch")
     Multi-issue branch (fix/2829-2833-…): যেকোনো একটির claim-ই যথেষ্ট।

Design notes:
  - বিদ্যমান branch-গুলো grandfathered — guard শুধু create-event-এ চলে।
  - API-down → advisory-skip (false-delete নয় — fail-open, কারণ এটা নিরাপত্তা-নয়
    শৃঙ্খলা-গার্ড; PR-টাইম Claim Gate fail-closed থাকে সেতো)।
  - injectable api (session-5 শিক্ষা: টেস্ট-ইনজেকশনে injectable-api প্যারামিটার লাগবেই)।
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gates import claim_matches, extract_claim_agents  # noqa: E402 — same-dir import
from template_gate import actor_category, validate_issue  # noqa: E402 — #2912 chain: identity default-deny + template-যাচাই

# বাংলা মন্তব্য (#2912): নিজের policy-লোডার চাই — identity/template কীগুলো
# (human_allowlist, trusted_bot_actors, template_policy) branch-policy-তে মার্জ করতে হয়।
from template_gate import load_template_policy as _load_template_policy  # noqa: E402

RULES_PATH = (
    Path(__file__).resolve().parents[3] / ".github" / "constitution" / "rules.yml"
)

# বাংলা মন্তব্য: DEFAULT policy — rules.yml-এ branch_creation_policy থাকলে সেটিই জেতে
# (SSOT); এটি শুধু fallback, যাতে rules.yml পাওয়া না গেলেও guard সৎভাবে চলে।
DEFAULT_BRANCH_CREATION_POLICY: dict = {
    "enabled": True,
    # বাংলা মন্তব্য (#2912 V2-প্রতিকার): exempt-তালিকা সংকুচিত — শুধু খাঁটি
    # infra-branch (merge-queue/dependabot/renovate) full-bypass পায়।
    # backport/* ও release/* বাদ পড়ল — এখন সাধারণ branch-এর মতোই issue+claim লাগবে।
    "exempt_branch_patterns": [
        "main",
        "master",
        "develop",
        "dependabot/*",
        "renovate/*",
        "gh-readonly-queue/*",
    ],
    # PR-টাইম Lease Gate-এর এখতিয়ার (#2378 parity) — branch-জন্মে ছাড় দেওয়া হয়,
    # কিন্তু PR-এ Lease Gate অনিবার্য। এগুলো exempt_branch_patterns থেকে আলাদা
    # যাতে শব্দার্থ স্পষ্ট থাকে (full-bypass vs PR-gated)।
    "pr_gated_branch_patterns": [
        "group/*",  # গ্রুপ-গভর্নেন্স lease-gate-এ আলাদা (#2378)
        "docs/*",  # lease-parity: docs_branch_prefix docs/ sanctioned
        # ── Bridge v1 (scripts/bridge/README.md): external-agent land-branch —
        # intake fail-closed validate করার পরেই bridge_intake.py জন্ম দেয়;
        # birth allowed, PR-টাইম gate chain অনিবার্য (group/*-এর মতোই lane-শৃঙ্খলা)।
        "bridge-land/*",
    ],
    # ── #2960: #2950-প্রোটোকল CAS-branch — identity/lock, কাজ-branch নয় ──
    # agent_identity.py git-push-as-CAS দিয়ে `agent/<name>` (persistent identity)
    # ও `role/<role>` (single-agent-per-role lock) branch push করে। এগুলোতে কখনো
    # PR হয় না, claim-ইস্যু থাকে না — কিন্তু আগে "issue number নেই" ভেবে দোষী
    # সাব্যস্ত+মুছে ফেলা হতো: CAS-অবস্থা নষ্ট → identity-collision + lock-churn
    # (প্রমাণ: register-এ role/ci-fixer ২২টি ও agent/glm5.2-coder-1 ১৫টি ব্যর্থ রান)।
    # এখন: agent-actor হলে ALLOW — অজানা actor এখনো violation (default-deny অটুট)।
    "protocol_branch_patterns": [
        "agent/*",  # #2950 persistent identity CAS-branch
        "role/*",   # #2950 single-agent-per-role lock CAS-branch
    ],
    "slot_registry_path": "docs/master_docs/AGENT_SLOT_REGISTRY.yaml",
    "issue_number_min_digits": 2,  # coder-1-2891-x → 2891; slot-সংখ্যা "1" বাদ
    "require_open_issue": True,
    "require_claim": True,
    "delete_violating_branch": True,
    "skip_delete_if_open_pr": True,
    "comment_on_issue": True,
    # ── #2912 identity default-deny (V1-প্রতিকার) ──
    "human_allowlist": ["SaifulHaqueNiloy"],
    "trusted_bot_actors": [
        "dependabot[bot]",
        "app/dependabot",
        "github-actions[bot]",
        "renovate[bot]",
    ],
    # ── #2912 claim-source hygiene (V5-প্রতিকার) ──
    # এই লেবেল/মার্কারযুক্ত issue-র claim দিয়ে branch অনুমোদন নিষিদ্ধ —
    # ledger/ops-telemetry কাজ-ইস্যু নয়; template:violating issue অবৈধ।
    "claim_source_blocked_labels": [
        "type:ledger",
        "type:platform-alert",
        "template:violating",
    ],
    "claim_source_blocked_markers": ["<!-- SUPREMEAI_PRIORITY_QUEUE_LEDGER"],
    # ── #2912 chain: claim-source issue-র inline template-যাচাই (V3-প্রতিকার) ──
    "require_template_compliant_issue": True,
}


def load_branch_policy(rules_path: Path = RULES_PATH) -> dict:
    """rules.yml → branch_creation_policy (DEFAULT fallback-মার্জ)।

    agent_author_prefixes না থাকলে claim_policy থেকে ওঠে (একই SSOT-সংজ্ঞা)।
    #2912: identity/template কীগুলো (human_allowlist, trusted_bot_actors,
    claim_source_blocked_*) rules.yml-এর identity_policy/template_policy থেকেও
    ওঠে — একই SSOT একাধিক ব্লকে সংজ্ঞায়িত হলে বিভাজন নয়।
    """
    pol = dict(DEFAULT_BRANCH_CREATION_POLICY)
    pol["agent_author_prefixes"] = ["supremeai-", "app/supremeai-"]
    try:
        import yaml

        data = yaml.safe_load(Path(rules_path).read_text(encoding="utf-8")) or {}
        cfg = data.get("branch_creation_policy")
        if isinstance(cfg, dict):
            pol.update(cfg)
        if "agent_author_prefixes" not in (cfg or {}):
            cp = data.get("claim_policy") or {}
            if isinstance(cp, dict) and cp.get("agent_author_prefixes"):
                pol["agent_author_prefixes"] = cp["agent_author_prefixes"]
        # #2912 SSOT-সংযোগ: identity_policy → human_allowlist / trusted_bot_actors
        ident = data.get("identity_policy")
        if isinstance(ident, dict):
            for key in ("human_allowlist", "trusted_bot_actors"):
                if ident.get(key) and key not in (cfg or {}):
                    pol[key] = ident[key]
        # #2912 SSOT-সংযোগ: template_policy.issue-এর violating_label → blocked-labels-এ
        tp = data.get("template_policy") or {}
        ti = tp.get("issue") if isinstance(tp, dict) else None
        if isinstance(ti, dict) and ti.get("violating_label"):
            blocked = list(pol.get("claim_source_blocked_labels") or [])
            if ti["violating_label"] not in blocked:
                blocked.append(ti["violating_label"])
            pol["claim_source_blocked_labels"] = blocked
    except Exception as exc:  # noqa: BLE001 — সৎ fallback, নীরবে মরা নয়
        print(f"⚠️ rules.yml load failed ({exc}) — DEFAULT branch policy fallback")
    return pol


def is_agent_actor(actor: str, policy: dict) -> bool:
    """Actor কি agent-enforcement-এর অধীন? (#2912 V1: default-deny)

    আগে: allowlist-of-prefixes (``supremeai-``) — অজানা বট "human" বলে ফাঁকি।
    এখন: human = শুধু human_allowlist; trusted-bot = trusted_bot_actors;
    **বাকি সব পরিচয় = agent** — অজানা নতুন বটও পুরো চেইনের অধীন।
    (canonical implementation: template_gate.actor_category — দুই গেটে এক SSOT।)
    """
    return actor_category(actor, policy) == "agent"


def _tpolicy_with_identity(policy: dict) -> dict:
    """#2912: branch-policy-র identity-কী + rules.yml-এর template_policy → এক সংযুক্ত policy।

    validate_issue() human_allowlist/trusted_bot_actors কী খোঁজে; branch-policy
    থেকে ওঠা মানগুলোই (SSOT-সংযোগ) প্রাধান্য পায় — দুই গেট একই পরিচয়-সংজ্ঞা ব্যবহার করবে।
    """
    tp = _load_template_policy()
    tp["human_allowlist"] = policy.get("human_allowlist") or tp.get("human_allowlist")
    tp["trusted_bot_actors"] = policy.get("trusted_bot_actors") or tp.get(
        "trusted_bot_actors"
    )
    return tp


def _issue_template_blocks(policy: dict, issue: dict) -> str | None:
    """#2912 V3-chain: claim-উৎস issue-র inline template-যাচাই।

    Return None = চেইন পাস (বা payload-অসম্পূর্ণ হওয়ায় sub-check বাদ);
    অন্যথায় ব্লক-কারণ-স্ট্রিং। Label-নির্ভর নয় — label মুছলেও bypass হবে না।
    """
    if not policy.get("require_template_compliant_issue", True):
        return None
    if not issue.get("user") or issue.get("body") is None:
        return None  # পুরনো/অসম্পূর্ণ API-payload — প্রধান চেইন অক্ষুণ্ণ
    t_status, t_missing, _ = validate_issue(issue, _tpolicy_with_identity(policy))
    if t_status == "violating":
        return f"issue #{issue.get('number')} template-অসম্পূর্ণ ({', '.join(t_missing)}) — issue body ঠিক করুন, তারপর branch"
    return None


def is_exempt_branch(branch: str, patterns) -> bool:
    return any(fnmatch.fnmatch(branch or "", str(p)) for p in (patterns or []))


def slot_registry_branches(registry_path: str | Path) -> set:
    """AGENT_SLOT_REGISTRY.yaml-এ তালিকাভুক্ত slot-branch নাম (sanctioned acquisition)।

    ফাইল না পেলে/পার্স-ব্যর্থ → খালি সেট (fail-open — ভুল exemption নয়)।
    """
    try:
        import yaml

        data = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or {}
    except Exception:
        return set()
    out: set = set()
    for s in data.get("slots") or []:
        if isinstance(s, dict) and s.get("branch"):
            out.add(str(s["branch"]))
    return out


def parse_issue_numbers(branch: str, min_digits: int = 2) -> list:
    """Branch-নামের সব issue-number-প্রার্থী (≥ min_digits ডিজিট, বাম থেকে ডান)।

    coder-1-2891-slug → [2891] (slot "1" = ১-ডিজিট, বাদ) · fix/2829-2833-x → [2829, 2833]
    plan-2841-pr2-x → [2841] ("2" বাদ) · agent-8 → [] (কোনো ২-ডিজিট নম্বর নেই)।
    """
    min_len = max(2, int(min_digits or 2))
    return [
        int(m.group(0))
        for m in re.finditer(r"\d+", branch or "")
        if len(m.group(0)) >= min_len
    ]


# বাংলা (#3254): lane-slot pattern enforcement — branch-জন্মেই ধরা।
# আগে শুধু issue-number + claim দেখত → fix/3227-x branch পাস করত, কিন্তু PR-টাইমে
# Lease Gate (bot_branch_regex: ^([a-z0-9]+)-([0-9]+)) ব্লক করত — ৬টি PR ব্লক হওয়ার
# মূল কারণ। এখন branch-জন্মেই lane-slot pattern check → ফেইল হলে VIOLATION।
# SSOT: gates.py-র bot_author_regex + bot_branch_regex রিইউজ (ড্রিফট নিষিদ্ধ)।
_BOT_AUTHOR_REGEX = r"^supremeai-([a-z0-9]+)-([0-9]+)-bot(\[bot\])?$"
_BOT_BRANCH_REGEX = r"^([a-z0-9]+)-([0-9]+)([-_.].+)?$"


def actor_lane_slot(actor: str) -> tuple[str, str] | None:
    """Agent actor-এর lane-slot extract (gates.py bot_author_regex-র সাথে সামঞ্জস্যপূর্ণ)।

    supremeai-coder-1-bot[bot] → ('coder', '1')
    supremeai-planner-bot → ('planner', 'bot')... না, planner-এর slot-সংখ্যা থাকে না,
    তাই None রিটার্ন করবে (planner = issue-output lane, branch_slots: none)।
    """
    m = re.match(_BOT_AUTHOR_REGEX, actor or "")
    if not m:
        return None
    return m.group(1), m.group(2)


def branch_lane_slot(branch: str) -> tuple[str, str] | None:
    """Branch-নাম থেকে lane-slot extract (gates.py bot_branch_regex-র সামঞ্জস্যপূর্ণ)।

    coder-1-3227-ci-false-green → ('coder', '1')
    fix/3227-ci-false-green → None (প্যাটার্ন মেলে না — fix কোনো valid lane নয়)
    """
    # বাংলা: branch-এর প্রথম path-segment নিয়ে check (fix/3227-x → "fix")
    first_seg = (branch or "").split("/")[-1]
    m = re.match(_BOT_BRANCH_REGEX, first_seg)
    if not m:
        return None
    return m.group(1), m.group(2)


def lane_slot_mismatch(actor: str, branch: str) -> str | None:
    """Return reason if actor-এর leased slot-এর সাথে branch pattern মেলে না।

    None = OK (match বা actor অ-এজেন্ট)
    str = VIOLATION reason (branch deleted/commented at creation time)
    """
    als = actor_lane_slot(actor)
    if als is None:
        # অ-এজেন্ট actor — lane-slot check প্রযোজ্য নয়
        return None
    bls = branch_lane_slot(branch)
    if bls is None:
        return (
            f"branch '{branch}' does not match lane-slot pattern "
            f"<lane>-<N>-<slug> (expected: {als[0]}-{als[1]}-<issue>-<slug>) — "
            f"Lease Gate will block this at PR-time (#3254 preventive)"
        )
    if bls != als:
        return (
            f"cross-slot branch: actor '{actor}' leases {als[0]}-{als[1]} "
            f"but branch '{branch}' belongs to {bls[0]}-{bls[1]} (#3254)"
        )
    return None


def gh_api(
    endpoint: str,
    method: str = "GET",
    payload: dict | None = None,
    token: str | None = None,
):
    """REST call — gh CLI প্রথমে, urllib fallback (gates.gh_api-এর GET-only সংস্করণ থেকে বিস্তৃত)।"""
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


def check_branch(
    branch: str, actor: str, policy: dict, api=None, repo: str = ""
) -> tuple:
    """মূল যাচাই। Return (verdict, reason, issue_num) — verdict ∈ {ALLOW, VIOLATION, SKIP}।"""
    api = api or gh_api
    branch = (branch or "").strip()
    actor = (actor or "").strip()

    if not policy.get("enabled", True):
        return "SKIP", "policy disabled — no-op", None
    if not branch:
        return "SKIP", "empty branch name (tag/edge event) — skip", None
    if is_exempt_branch(branch, policy.get("exempt_branch_patterns")):
        return "ALLOW", "exempt branch pattern", None

    registry_path = (
        policy.get("slot_registry_path")
        or DEFAULT_BRANCH_CREATION_POLICY["slot_registry_path"]
    )
    if branch in slot_registry_branches(registry_path):
        return "ALLOW", "slot-registry branch (sanctioned acquisition)", None

    # #2912 V2: PR-টাইম Lease Gate-এর এখতিয়ারে থাকা prefix — branch-জন্মে
    # ছাড়, কিন্তু কারণ-স্পষ্ট (full-bypass নয়; PR-এ Lease Gate অনিবার্য)।
    if is_exempt_branch(branch, policy.get("pr_gated_branch_patterns")):
        return "ALLOW", "PR-gated branch (Lease Gate owns it at PR-time, #2378)", None

    if not is_agent_actor(actor, policy):
        cat = actor_category(actor, policy)
        return "ALLOW", f"actor '{actor}' is {cat} — advisory only", None

    # #2960 root-fix: #2950-প্রোটোকল CAS-branch (agent/<name>, role/<role>) —
    # identity/lock state-branch, কাজ-branch নয়; claim-ইস্যু বলে কিছু নেই।
    # নিরাপত্তা-সীমা: এই ছাড় actor-অগণ্য নয় — ওপরের is_agent_actor চেক পার
    # হয়ে এখানে আসা মানেই actor agent-শ্রেণির। ফাঁকি-পথ বন্ধ: agent/* নামের
    # কাজ-branch খুললেও PR-টাইম Claim Gate + Lease Gate অনিবার্য —
    # branch-জন্মে ছাড় মানে PR-ছাড় নয়।
    if is_exempt_branch(branch, policy.get("protocol_branch_patterns")):
        return (
            "ALLOW",
            "protocol branch (identity/role CAS lock, #2950) — not a work branch",
            None,
        )

    # বাংলা (#3254): lane-slot pattern check — PR-টাইম Lease Gate-এর আগেই ধরা।
    # আগে fix/3227-x branch এখানে পাস করত (issue-number আছে, তাই issue_nums পাওয়া যেত),
    # কিন্তু PR-টাইমে bot_branch_regex মেলে না → ৬টি PR block। এখন এখানেই ধরা।
    # শুধু agent actor-দের জন্য (human/trusted-bot unaffected)।
    if is_agent_actor(actor, policy):
        slot_reason = lane_slot_mismatch(actor, branch)
        if slot_reason is not None:
            return "VIOLATION", slot_reason, None

    issue_nums = parse_issue_numbers(branch, policy.get("issue_number_min_digits", 2))
    if not issue_nums:
        return (
            "VIOLATION",
            "branch name carries no issue number — issue ছাড়া branch নিষিদ্ধ",
            None,
        )

    # বাংলা মন্তব্য: multi-issue branch (fix/2829-2833-x) — প্রথম ম্যাচ-হওয়া
    # issue-ই যথেষ্ট; কোনোটিতেই claim না মিললে তবেই violation।
    # 404 = সত্যিকারের not-found (violation-কারণ); অন্য API-error = fail-open skip।
    last_reason = ""
    for num in issue_nums:
        try:
            issue = api(f"repos/{repo}/issues/{num}")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                last_reason = f"issue #{num} not found (404)"
                continue
            return (
                "SKIP",
                f"issue #{num} lookup failed (HTTP {exc.code}) — advisory skip",
                num,
            )
        except Exception as exc:  # noqa: BLE001 — API-down = সৎ fail-open
            return (
                "SKIP",
                f"issue #{num} lookup failed (API error: {exc}) — advisory skip",
                num,
            )
        if not isinstance(issue, dict) or issue.get("number") is None:
            last_reason = f"issue #{num} not found"
            continue
        if policy.get("require_open_issue", True) and issue.get("state") != "open":
            last_reason = f"issue #{num} is {issue.get('state')}"
            continue
        # ── #2912 claim-source hygiene (V5): এই issue-টি কি claim-source হিসেবে বৈধ? ──
        # ledger/ops-telemetry/template:violating issue-র claim = branch-license নয়।
        issue_labels = {
            lb.get("name") if isinstance(lb, dict) else str(lb)
            for lb in (issue.get("labels") or [])
        }
        issue_labels = {x for x in issue_labels if x}
        blocked_labels = set(policy.get("claim_source_blocked_labels") or [])
        hit_blocked = issue_labels & blocked_labels
        issue_body = issue.get("body") or ""
        # startswith-সিম্যান্টিক্স (#2912 self-red-team শিক্ষা): ledger body মার্কার
        # দিয়ে শুরু হয় — মার্কার-টেক্সট উদ্ধৃত-করা ডকুমেন্টেশন-ইস্যু false-block নয়।
        body_trim = (issue_body or "").lstrip()
        hit_marker = any(
            body_trim.startswith(m)
            for m in (policy.get("claim_source_blocked_markers") or [])
        )
        if hit_blocked or hit_marker:
            why = (
                f"labels {sorted(hit_blocked)}"
                if hit_blocked
                else "ledger/telemetry body-marker"
            )
            last_reason = f"issue #{num} is not a claimable work-issue ({why})"
            continue

        if not policy.get("require_claim", True):
            return "ALLOW", f"claim check disabled — issue #{num} open", num
        # claim-evidence: assignee-login অথবা Atomic Claim comment (gates.py reuse)
        assignees = {
            a.get("login") for a in (issue.get("assignees") or []) if a.get("login")
        }
        if claim_matches(actor, assignees):
            # #2912 V3-chain: assignee-claim পথেও inline template-যাচাই বাধ্যতামূলক
            blocked = _issue_template_blocks(policy, issue)
            if blocked:
                last_reason = blocked
                continue
            return "ALLOW", f"assignee-claim verified on #{num}", num
        try:
            comments = api(f"repos/{repo}/issues/{num}/comments?per_page=100")
        except Exception as exc:  # noqa: BLE001
            return (
                "SKIP",
                f"claim comments fetch failed (API error: {exc}) — advisory skip",
                num,
            )
        claimers = extract_claim_agents(comments if isinstance(comments, list) else [])
        if claim_matches(actor, claimers):
            # #2912 V3-chain: comment-claim পথে inline template-যাচাই (label-bypass-নিরোধ)
            blocked = _issue_template_blocks(policy, issue)
            if blocked:
                last_reason = blocked
                continue
            return "ALLOW", f"Atomic-Claim verified on #{num}", num
        last_reason = f"no claim by '{actor}' on #{num}"
    return (
        "VIOLATION",
        last_reason or "no claimable issue matched",
        (issue_nums[0] if issue_nums else None),
    )


# বাংলা মন্তব্য (#2928): আগে একটিই কমেন্ট-টেমপ্লেট ছিল — শিরোনামে হার্ডকোড করা
# "branch মুছে ফেলা হয়েছে" — অথচ open-PR থাকলে delete স্কিপ হতো; কমেন্ট মিথ্যা
# বলত (প্রমাণ: #2925-এর কমেন্ট বনাম রান-লগ "delete skipped")। এখন দুটি টেমপ্লেট —
# প্রকৃত অ্যাকশন অনুযায়ী সৎ প্রতিবেদন।
VIOLATION_COMMENT_DELETED = """## 🌿 Branch Creation Guard — violation: branch মুছে ফেলা হয়েছে (`{branch}`)

**Invariant (#2907): issue claim ছাড়া কোনো এজেন্ট branch তৈরি করতে পারবে না।**

- **Actor:** `{actor}`
- **কারণ:** {reason}
- **সময়:** {ts} UTC

### সঠিক পথ (২ ধাপ)
```bash
# ১) আগে claim — atomic, ফাইল-ঘোষণাসহ:
scripts/ci/atomic_claim.sh {issue_num} <agent-name> --skip-assign --files "<ফাইল-তালিকা>"
# ২) তারপর branch — নামে issue-number-সহ (coder-1-{issue_num}-<slug> প্যাটার্ন):
git checkout -b <lane>-<slot>-{issue_num}-<slug>
```

Claim Gate (#2644) PR-এ একই চেক করে — এখন থেকে branch-জন্মেই ধরা পড়বে। 🙏
"""

VIOLATION_COMMENT_KEPT = """## 🌿 Branch Creation Guard — violation: branch রেখে দেওয়া হয়েছে (`{branch}`)

**Invariant (#2907): issue claim ছাড়া কোনো এজেন্ট branch তৈরি করতে পারবে না।**

- **Actor:** `{actor}`
- **কারণ:** {reason}
- **সময়:** {ts} UTC
- **কেন রাখা হলো:** এই branch থেকে open PR আছে — ব্যবস্থা **PR-gate-এর হাতে**
  (Claim/Scope/Template Gate-এর BLOCK + self-heal কমেন্টই পথ দেখাবে)।

### সঠিক পথ (২ ধাপ)
```bash
# ১) আগে claim — atomic, ফাইল-ঘোষণাসহ:
scripts/ci/atomic_claim.sh {issue_num} <agent-name> --skip-assign --files "<ফাইল-তালিকা>"
# ২) তারপর branch — নামে issue-number-সহ (coder-1-{issue_num}-<slug> প্যাটার্ন):
git checkout -b <lane>-<slot>-{issue_num}-<slug>
```

Claim Gate (#2644) PR-এ একই চেক করে — এখন থেকে branch-জন্মেই ধরা পড়বে। 🙏
"""


def enforce(
    branch: str,
    actor: str,
    verdict: str,
    reason: str,
    issue_num,
    policy: dict,
    api=None,
    repo: str = "",
) -> list:
    """Violation-অ্যাকশন: branch-delete-সিদ্ধান্ত → issue-কমেন্ট (সৎ, প্রকৃত অ্যাকশন অনুযায়ী)।

    # বাংলা মন্তব্য (#2928): আগে কমেন্ট আগে যেত ("মুছে ফেলা হয়েছে" হার্ডকোড),
    # তারপর delete-সিদ্ধান্ত — open-PR থাকলে মিথ্যা কমেন্ট থেকে যেত।
    # এখন সিদ্ধান্ত আগে, কমেন্ট পরে — টেমপ্লেট-পছন্দ প্রকৃত ফলাফল অনুযায়ী।
    Return নেওয়া action-তালিকা।
    """
    api = api or gh_api
    actions: list = []
    if verdict != "VIOLATION":
        return actions

    branch_deleted = False
    if policy.get("delete_violating_branch", True):
        skip = False
        if policy.get("skip_delete_if_open_pr", True):
            try:
                owner = repo.split("/")[0]
                prs = api(f"repos/{repo}/pulls?head={owner}:{branch}&state=open")
                if prs:
                    skip = True
                    actions.append(
                        f"delete skipped — open PR from '{branch}' (PR-gate দায়ী)"
                    )
            except Exception:
                skip = True  # অনিশ্চিত হলে delete করা নিরাপদ নয়
                actions.append("delete skipped — open-PR check failed (conservative)")
        if not skip:
            try:
                api(f"repos/{repo}/git/refs/heads/{branch}", method="DELETE")
                branch_deleted = True
                actions.append(f"branch '{branch}' deleted")
            except Exception as exc:  # noqa: BLE001
                actions.append(f"branch delete FAILED ({exc})")
    # বাংলা মন্তব্য: policy-তে delete বন্ধ থাকলে branch_deleted=False-ই থাকে →
    # কমেন্ট-টেমপ্লেট সৎভাবে "রেখে দেওয়া হয়েছে" প্রতিবেদন করবে।

    if issue_num and policy.get("comment_on_issue", True):
        import datetime

        template = VIOLATION_COMMENT_DELETED if branch_deleted else VIOLATION_COMMENT_KEPT
        body = template.format(
            branch=branch,
            actor=actor,
            reason=reason,
            issue_num=issue_num,
            ts=datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        )
        try:
            api(
                f"repos/{repo}/issues/{issue_num}/comments",
                method="POST",
                payload={"body": body},
            )
            actions.append(f"commented on #{issue_num}")
        except Exception as exc:  # noqa: BLE001
            actions.append(f"comment on #{issue_num} FAILED ({exc})")

    return actions


def main() -> int:
    ref_type = (os.environ.get("GUARD_REF_TYPE") or "branch").strip().lower()
    if ref_type == "tag":
        print("[SKIP] tag creation — branch guard applies to branches only")
        return 0
    branch = (
        os.environ.get("GUARD_BRANCH") or os.environ.get("GITHUB_REF") or ""
    ).strip()
    branch = branch.removeprefix("refs/heads/")
    actor = (
        os.environ.get("GUARD_ACTOR") or os.environ.get("GITHUB_ACTOR") or ""
    ).strip()
    repo = (
        os.environ.get("GITHUB_REPOSITORY") or os.environ.get("GUARD_REPO") or ""
    ).strip()
    if not branch or not repo:
        print("[SKIP] missing GUARD_BRANCH/GITHUB_REPOSITORY context")
        return 0

    policy = load_branch_policy()
    verdict, reason, issue_num = check_branch(branch, actor, policy, repo=repo)
    actions = enforce(branch, actor, verdict, reason, issue_num, policy, repo=repo)

    line = f"Branch Creation Guard: {verdict} — branch='{branch}' actor='{actor}' :: {reason}"
    print(line)
    for a in actions:
        print(f"  ↳ action: {a}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"### 🌿 Branch Creation Guard\n\n- {line}\n")
            for a in actions:
                fh.write(f"- {a}\n")
    # VIOLATION → exit 1 (Actions-এ লাল দৃশ্যমানতা); SKIP/ALLOW → 0
    return 1 if verdict == "VIOLATION" else 0


if __name__ == "__main__":
    sys.exit(main())
