#!/usr/bin/env python3
"""Merge Gate (Sequential Landing Controller) — Pipeline 2 of the 3-Pipeline Law.

বাংলা সারসংক্ষেপ (Merge Gate Convergence):
    Pipeline Constitution:
      RULE 1  PR Gate (pr.yml)        = প্রমাণ করে change-টা ঠিক আছে
      RULE 2  MERGE GATE (এই ইঞ্জিন)  = সিদ্ধান্ত নেয় প্রমাণিত change-টা land করতে পারে কি না
      RULE 3  Main Pipeline           = প্রমাণ করে land হওয়া সিস্টেম ঠিক আছে
    এই ইঞ্জিন কোনো টেস্ট rerun করে না — শুধু লাইভ evidence consume করে।

Fail-closed চুক্তি (Rule 10):
    Skipped ≠ passed · Missing evidence ≠ healthy · Unknown ≠ green।
    প্রতিটি evidence-fetch ব্যর্থতা = HOLD — কখনোই merge নয়।

Evidence (সব লাইভ — কোনো assumption নয়):
    a. PR state       : open + ready (draft নয়) + queue:hold নেই
    b. Required checks: branch-protection থেকে লাইভ তালিকা (fallback:
       DEFAULT_REQUIRED_CHECKS); head SHA-র check-runs-এ SUCCESS/SKIPPED/NEUTRAL
       ছাড়া কিছু = ব্লক; নিজের check-run না-পাওয়া নিজেই ব্লক (fail-closed)
    c. Evaluator      : fresh `ai_pr_evaluator.py --pr N --json` (read-only,
       main-ref verdict-integrity) রায় == AUTO_MERGE; অনুপস্থিত/ব্যর্থ = HOLD
    d. Freshness      : merge-base(FETCH_HEAD, origin/main) == origin/main HEAD —
       freshness_gate.py (#2935)-এর হুবহু ক্রাইটেরিয়ন; exempt-actor parity
    e. Predecessor    : group:X + seq:N হলে seq:N-1-এর merged-PR query =
       authoritative proof — open → HOLD · closed-unmerged → HOLD ·
       evidence-নেই → HOLD ("not open ⇒ merged" assumption নিষিদ্ধ)
    f. Mergeability   : mergeStateStatus == 'clean' (execution-মুহূর্তে)

Execution (RULE 6 — single landing path):
    gh pr merge <N> --squash --delete-branch
    Admin bypass (--admin) কখনোই ব্যবহৃত হয় না — এই repo-র main protection-এ
    enforce_admins=false, তাই --admin মানেই সব required-check bypass।
    tests/test_merge_gate.py-এর meta-test এটা source-level-এ enforce করে।

Usage:
    python scripts/ci/merge_gate.py --pr 123 --plan
    python scripts/ci/merge_gate.py --pr 123 --execute
    python scripts/ci/merge_gate.py --scan --plan
    python scripts/ci/merge_gate.py --scan --execute --limit 1
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")
MAIN_REF = os.environ.get("MERGE_GATE_MAIN_REF", "origin/main")

# branch-protection API না-পেলে fallback — 2026-10 লাইভ-প্রোবে যাচাইকৃত তালিকা।
DEFAULT_REQUIRED_CHECKS: tuple[str, ...] = (
    "Branch Naming Guard",
    "🚦 Unified PR Gate (Security, Scope & Policy Orchestrator)",
)

# evaluator/freshness_gate-এর OK-conclusion parity।
OK_CONCLUSIONS = {"SUCCESS", "SKIPPED", "NEUTRAL"}

# freshness_gate.py DEFAULT_POLICY.exempt_actors-এর parity (rules.yml-override
# পড়ার চেষ্টা করে, না-পেলে এটাই)।
DEFAULT_EXEMPT_ACTORS = {
    "dependabot[bot]",
    "app/dependabot",
    "renovate[bot]",
    "github-actions[bot]",
}

PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


# ── Transport (injectable — tests fake করে; সব বাহ্যিক I/O এক চোক-পয়েন্টে) ──

class Gateway:
    """সব বাহ্যিক I/O-র একক চোক-পয়েন্ট: gh CLI · git · python subprocess।"""

    def __init__(
        self,
        gh_fn: Any = None,
        git_fn: Any = None,
        run_fn: Any = None,
    ) -> None:
        self._gh_fn = gh_fn
        self._git_fn = git_fn
        self._run_fn = run_fn

    @staticmethod
    def _gh_command(*args: str) -> list[str]:
        """gh argv builder — injectable-path থেকেও এই চুক্তি টেস্টযোগ্য থাকে।"""
        cmd = ["gh", *args]
        if args[0] != "api":
            cmd += ["--repo", REPO]
        return cmd

    # #103 root-cause (#4291/#4292 চুক্তির merge-gate পা): ব্যক্তিগত fine-grained PAT
    # (SELF_HEAL_PAT) private repo-তে checks:read নেই → check-runs API 403 →
    # প্রতিটি রায় fail-closed HOLD → কোনো PR নিজে-নিজে land করতে পারে না (fleet-
    # deadlock)। চুক্তি: শুধু token-scope-শ্রেণির ত্রুটিতে (HTTP 403 "not accessible")
    # একবার GH_FALLBACK_TOKEN (= workflow-এর নিজস্ব github.token, স্যাংশনড পারমিশন)
    # দিয়ে retry — অন্যান্য ত্রুটি (404/422/নেটওয়ার্ক) সৎভাবে ব্যর্থ হয়
    # (fail-closed অপরিবর্তিত, কোনো ভুয়া প্রমাণ নয়)।
    _TOKEN_SCOPE_MARKERS = ("not accessible", "http 403")

    def gh(self, *args: str) -> str:
        """gh CLI — nonzero exit বা exec-ব্যর্থতায় exception (fail-closed)।

        # বাংলা মন্তব্য: `gh api` এ `--repo` flag নেই (endpoint-এ owner/repo থাকে) —
        # শুধু api-বহির্ভূত সাবকমান্ডে (pr view/list/merge) --repo যোগ হয়।
        # লাইভ-ল্যান্ডিং প্রথম চেষ্টায় ধরা পড়া বাগ: api-কলে --repo দিলে
        "unknown flag: --repo" → evidence-fetch-fail → প্রতিটি রায় HOLD।
        """
        if self._gh_fn is not None:
            return self._gh_fn(*args)
        err = ""
        try:
            res = subprocess.run(
                self._gh_command(*args),
                capture_output=True, text=True, timeout=60, check=False,
            )
            if res.returncode == 0:
                return res.stdout.strip()
            err = res.stderr or ""
        except Exception as exc:  # noqa: BLE001 — timeout/exec: fallback সিদ্ধান্তে যায়
            err = str(exc)
        fb = (os.environ.get("GH_FALLBACK_TOKEN") or "").strip()
        cur = (os.environ.get("GH_TOKEN") or "").strip()
        if (
            not fb or fb == cur
            or not any(m in err.lower() for m in self._TOKEN_SCOPE_MARKERS)
        ):
            raise RuntimeError(f"gh {' '.join(args[:2])}… failed: {err[:200]}")
        # বাংলা মন্তব্য: fallback retry-তে gh-র জন্য GH_TOKEN env-ওভাররাইড —
        # প্রক্সি-প্রসেসে মূল env দূষিত হয় না (শুধু এই subprocess-এ)।
        res2 = subprocess.run(
            self._gh_command(*args),
            capture_output=True, text=True, timeout=60, check=False,
            env={**os.environ, "GH_TOKEN": fb},
        )
        if res2.returncode != 0:
            raise RuntimeError(
                f"gh {' '.join(args[:2])}… failed (primary+fallback): {res2.stderr[:200]}"
            )
        return res2.stdout.strip()

    def git(self, *args: str) -> str:
        if self._git_fn is not None:
            return self._git_fn(*args)
        res = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=120, check=False,
        )
        if res.returncode != 0:
            raise RuntimeError(f"git {' '.join(args[:2])}… failed: {res.stderr[:200]}")
        return res.stdout.strip()

    def run(self, cmd: list[str]) -> str:
        if self._run_fn is not None:
            return self._run_fn(cmd)
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, check=False,
        )
        if res.returncode != 0:
            raise RuntimeError(f"{cmd[0]} … failed (rc={res.returncode}): {res.stderr[:200]}")
        return res.stdout.strip()


# ── Label parsing ────────────────────────────────────────────────────────────

def _label_names(labels: Any) -> list[str]:
    names: list[str] = []
    for lab in labels or []:
        if isinstance(lab, dict):
            names.append(str(lab.get("name", "")))
        else:
            names.append(str(lab))
    return [n for n in names if n]


def extract_priority(labels: Any) -> str:
    """Hyphen-aware: 'P1-high' → 'P1' (merge_queue_manager-এর ভাঙা
    `name in PRIORITY_RANK` extraction-এর সংশোধন — rules.yml priority_regex
    'P[0-3]-(critical|high|medium|low)' প্রমাণ করে hyphenated লেবেলই বাস্তব)।"""
    for name in _label_names(labels):
        m = re.match(r"^(P[0-3])", name)
        if m:
            return m.group(1)
    return "P3"


def extract_group(labels: Any) -> str:
    for name in _label_names(labels):
        if name.startswith("group:"):
            return name[6:]
    return ""


def extract_seq(labels: Any) -> int:
    for name in _label_names(labels):
        m = re.match(r"^seq:(\d+)$", name)
        if m:
            return int(m.group(1))
    return 0


def extract_priority_rank(labels: Any) -> int:
    return PRIORITY_RANK.get(extract_priority(labels), 3)


# ── Evidence collectors (প্রতিটিটা fail-closed) ───────────────────────────────

def fetch_required_checks(gw: Gateway) -> tuple[list[str], str]:
    """branch-protection থেকে লাইভ required-context তালিকা; ব্যর্থ হলে
    যাচাইকৃত fallback — source-সহ রিটার্ন (decision-log-এ গিয়ে পড়বে)।"""
    try:
        data = json.loads(gw.gh("api", f"repos/{REPO}/branches/main/protection"))
        contexts = (data.get("required_status_checks") or {}).get("contexts") or []
        if contexts:
            return [str(c) for c in contexts], "branch-protection"
    except Exception:  # noqa: BLE001 — fallback-ই fail-closed কাভার করে
        pass
    return list(DEFAULT_REQUIRED_CHECKS), "default-fallback"


def required_checks_verdict(
    gw: Gateway, head_sha: str, required: list[str]
) -> tuple[list[str], list[str]]:
    """রিটার্ন: (missing-or-red check-নামের তালিকা, evidence-failure কারণসমূহ)।"""
    blocked: list[str] = []
    failures: list[str] = []
    runs: list[dict[str, Any]] | None = None
    try:
        raw = gw.gh("api", f"repos/{REPO}/commits/{head_sha}/check-runs?per_page=100")
        runs = json.loads(raw).get("check_runs", [])
    except Exception as exc:  # noqa: BLE001
        return [], [f"evidence-fetch-failed: check-runs API ({exc})"]

    for name in required:
        mine = [r for r in (runs or []) if r.get("name") == name]
        if not mine:
            blocked.append(name)
            continue
        mine.sort(key=lambda r: r.get("id", 0))
        concl = str(mine[-1].get("conclusion") or "").upper()
        if concl not in OK_CONCLUSIONS:
            blocked.append(f"{name} ({concl or 'PENDING'})")
    return blocked, failures


def evaluator_verdict(gw: Gateway, pr_number: int) -> tuple[str, list[str]]:
    """Fresh read-only রায় (কোনো --apply নেই — লেখা Merge Gate-এর কাজ নয়)।"""
    script = Path("scripts/ci/ai_pr_evaluator.py")
    if not script.exists():
        return "", ["evidence-missing: scripts/ci/ai_pr_evaluator.py not on main checkout"]
    try:
        raw = gw.run([sys.executable, str(script), "--pr", str(pr_number), "--json"])
        return str(json.loads(raw).get("verdict", "")), []
    except Exception as exc:  # noqa: BLE001
        return "", [f"evidence-fetch-failed: evaluator ({exc})"]


def freshness_verdict(
    gw: Gateway,
    pr_number: int,
    author: str,
    main_ref: str = MAIN_REF,
) -> tuple[bool, list[str]]:
    """#2935-এর হুবহু ক্রাইটেরিয়ন, git-plumbing-এ: merge-base(PR-head, main)
    == main-HEAD হলে synced। exempt-actor parity freshness_gate-এর সাথে।"""
    if author in exempt_actors():
        return True, []
    try:
        gw.git("fetch", "-q", "origin", f"pull/{pr_number}/head")
        merge_base = gw.git("merge-base", "FETCH_HEAD", main_ref)
        main_head = gw.git("rev-parse", main_ref)
    except Exception as exc:  # noqa: BLE001
        return False, [f"evidence-fetch-failed: freshness git ({exc})"]
    if merge_base != main_head:
        return False, [
            f"freshness: PR-head main-এর পেছনে (merge-base {str(merge_base)[:12]} "
            f"≠ main {str(main_head)[:12]}) — self-heal: fetch → merge main → push"
        ]
    return True, []


def exempt_actors() -> set[str]:
    try:
        import yaml  # noqa: PLC0415 — lazy

        data = yaml.safe_load(
            Path(".github/constitution/rules.yml").read_text(encoding="utf-8")
        )
        override = (data or {}).get("freshness_policy") or {}
        if override.get("exempt_actors"):
            return {str(a) for a in override["exempt_actors"]}
    except Exception:  # noqa: BLE001
        pass
    return set(DEFAULT_EXEMPT_ACTORS)


def predecessor_verdict(gw: Gateway, group: str, seq: int) -> tuple[bool, list[str]]:
    """Authoritative predecessor proof — 'open না হলে merged ধরে নেওয়া' নিষিদ্ধ।"""
    if not group or seq <= 1:
        return True, []
    target = seq - 1
    try:
        raw = gw.gh(
            "pr", "list", "--state", "all", "--base", "main", "--limit", "200",
            "--json", "number,state,labels",
        )
        prs = json.loads(raw or "[]")
    except Exception as exc:  # noqa: BLE001
        return False, [f"evidence-fetch-failed: predecessor PR query ({exc})"]

    def has_label(p: dict[str, Any], wanted: str) -> bool:
        return wanted in _label_names(p.get("labels"))

    pred = [
        p for p in prs
        if has_label(p, f"group:{group}") and has_label(p, f"seq:{target}")
    ]
    if not pred:
        return False, [
            f"evidence-missing: group:{group} seq:{target}-এর কোনো PR-ই পাওয়া যায়নি "
            "(unknown ≠ green — assumption নিষিদ্ধ)"
        ]
    pred.sort(key=lambda p: int(p.get("number", 0)))
    p = pred[-1]
    state = str(p.get("state", "")).lower()
    if state == "merged":
        return True, []
    if state == "open":
        return False, [f"predecessor PR #{p.get('number')} (seq:{target}) এখনো open"]
    return False, [
        f"predecessor PR #{p.get('number')} state={state} (closed-unmerged) — rebuild দরকার"
    ]


# ── Decision core ────────────────────────────────────────────────────────────

def pr_view(gw: Gateway, pr_number: int) -> dict[str, Any]:
    raw = gw.gh(
        "pr", "view", str(pr_number), "--json",
        "number,title,state,isDraft,headRefName,headRefOid,mergeStateStatus,"
        "labels,author,createdAt",
    )
    return json.loads(raw)


def decide(gw: Gateway, pr_number: int) -> dict[str, Any]:
    """এক PR-এর পূর্ণ evidence-রায় — MERGE বা HOLD(reasons-সহ)। fail-closed।"""
    try:
        pr = pr_view(gw, pr_number)
    except Exception as exc:  # noqa: BLE001
        return {"pr": pr_number, "verdict": "HOLD",
                "reasons": [f"evidence-fetch-failed: pr view ({exc})"]}

    labels = pr.get("labels")
    reasons: list[str] = []
    state = str(pr.get("state", "")).lower()
    if state != "open":
        reasons.append(f"PR state={state}")
    if pr.get("isDraft"):
        reasons.append("PR draft")
    if "queue:hold" in _label_names(labels):
        reasons.append("queue:hold")
    if reasons:
        return {"pr": pr_number, "title": pr.get("title", ""), "verdict": "HOLD",
                "priority": extract_priority(labels), "reasons": reasons}

    head_sha = str(pr.get("headRefOid") or "")
    if not head_sha:
        return {"pr": pr_number, "title": pr.get("title", ""), "verdict": "HOLD",
                "priority": extract_priority(labels),
                "reasons": ["evidence-missing: head SHA"]}

    # b. required checks (লাইভ protection তালিকা; fetch-ব্যর্থতা নিজেই fail-closed)
    required, src = fetch_required_checks(gw)
    blocked, failures = required_checks_verdict(gw, head_sha, required)
    reasons.extend(failures)
    if blocked:
        reasons.append(f"required checks not green: {', '.join(blocked)} [source={src}]")

    # c. evaluator verdict (fresh, read-only)
    verdict, failures = evaluator_verdict(gw, pr_number)
    reasons.extend(failures)
    if verdict and verdict != "AUTO_MERGE":
        reasons.append(f"evaluator verdict={verdict} (≠ AUTO_MERGE)")

    # d. freshness (exempt-actor parity)
    author = str(((pr.get("author") or {}) or {}).get("login") or "")
    fresh_ok, failures = freshness_verdict(gw, pr_number, author)
    reasons.extend(failures)

    # e. predecessor proof
    pred_ok, failures = predecessor_verdict(
        gw, extract_group(labels), extract_seq(labels)
    )
    reasons.extend(failures)

    # f. GitHub mergeability — execution-মুহূর্তের authoritative শেষ-মোড়ক
    mss = str(pr.get("mergeStateStatus") or "").upper()
    if mss != "CLEAN":
        reasons.append(f"mergeStateStatus={mss or 'UNKNOWN'} (≠ CLEAN)")

    v = "MERGE" if not reasons else "HOLD"
    return {
        "pr": pr_number,
        "title": pr.get("title", ""),
        "priority": extract_priority(labels),
        "group": extract_group(labels),
        "seq": extract_seq(labels),
        "head_sha": head_sha[:12],
        "verdict": v,
        "required_checks_source": src,
        "freshness_ok": fresh_ok,
        "predecessor_ok": pred_ok,
        "reasons": reasons,
    }


def plan_queue(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Priority-sequential সাজ়: P0 আগে → group-বিহীন আগে → group → seq → পুরনো।"""
    return sorted(
        items,
        key=lambda x: (
            extract_priority_rank(x.get("labels")),
            0 if not extract_group(x.get("labels")) else 1,
            extract_group(x.get("labels")),
            extract_seq(x.get("labels")),
            str(x.get("createdAt") or ""),
        ),
    )


def execute_merge(gw: Gateway, pr_number: int) -> tuple[bool, str]:
    """RULE 6 landing — squash, branch-delete, NO admin bypass।"""
    try:
        gw.gh("pr", "merge", str(pr_number), "--squash", "--delete-branch")
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:300]


# ── CLI ──────────────────────────────────────────────────────────────────────

def cmd_pr(gw: Gateway, pr_number: int, execute: bool) -> dict[str, Any]:
    d = decide(gw, pr_number)
    if execute and d["verdict"] == "MERGE":
        ok, err = execute_merge(gw, pr_number)
        d["executed"] = ok
        if err:
            d["execute_error"] = err
    return d


def cmd_scan(gw: Gateway, execute: bool, limit: int, evaluate_top: int = 5) -> list[dict[str, Any]]:
    try:
        raw = gw.gh(
            "pr", "list", "--state", "open", "--limit", "100", "--json",
            "number,title,labels,createdAt,isDraft",
        )
        prs = json.loads(raw or "[]")
    except Exception as exc:  # noqa: BLE001 — fail-closed: স্ক্যান-ব্যর্থতা = কোনো merge নয়
        return [{"pr": None, "verdict": "HOLD",
                 "reasons": [f"evidence-fetch-failed: pr list ({exc})"]}]
    prs = [p for p in prs if not p.get("isDraft")]
    ordered = plan_queue(prs)
    results: list[dict[str, Any]] = []
    for item in ordered[:max(evaluate_top, limit)]:
        d = decide(gw, int(item["number"]))
        results.append(d)
        if execute and d["verdict"] == "MERGE":
            ok, err = execute_merge(gw, int(item["number"]))
            d["executed"] = ok
            if err:
                d["execute_error"] = err
            break  # single-flight: এক run-এ এক landing
    return results


def _print_human(results: list[dict[str, Any]]) -> None:
    print(f"{'PR':>6}  {'Pri':<3}  {'Verdict':<7}  Reasons / Evidence")
    print("-" * 100)
    for d in results:
        rs = "; ".join(d.get("reasons") or []) or "all evidence green"
        print(f"#{d.get('pr') or '?':>5}  {d.get('priority', '-'):<3}  "
              f"{d.get('verdict', '?'):<7}  {rs[:90]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge Gate — Sequential Landing Controller")
    parser.add_argument("--pr", type=int, help="নির্দিষ্ট PR-এর রায়")
    parser.add_argument("--scan", action="store_true", help="পুরো open-PR কিউ priority-অনুসারে")
    parser.add_argument("--execute", action="store_true", help="MERGE রায় হলে সত্যিই merge (না দিলে শুধু রায়)")
    parser.add_argument("--limit", type=int, default=1, help="scan-execute-এ সর্বোচ্চ landing")
    args = parser.parse_args(argv)

    if not args.pr and not args.scan:
        parser.error("--pr অথবা --scan দিতে হবে")

    gw = Gateway()
    if args.pr:
        results = [cmd_pr(gw, args.pr, args.execute)]
    else:
        results = cmd_scan(gw, args.execute, args.limit)

    _print_human(results)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    # HOLD একটা সুস্থ রায় (failure নয়) — exit 0; workflow-red হবে শুধু engine-crash-এ।
    return 0


if __name__ == "__main__":
    sys.exit(main())
