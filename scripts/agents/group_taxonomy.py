#!/usr/bin/env python3
"""Canonical Group Taxonomy + Group-First Issue Discovery (#3088)।
=============================================================
# বাংলা মন্তব্য (#3088 §2): প্রতিটি কাজ-ইস্যুর **একটি primary group** বাধ্যতামূলক।
Domain-ভিত্তিক semantic ownership — queue-এর ordering/ownership এই primary group
দিয়েই নির্ধারিত হবে; `area:*` লেবেল থাকবে secondary হিসেবে।

৮টি canonical primary group (#3088 spec):
    governance | security | pipeline | architecture | reliability |
    product | intelligence | infrastructure

Group invariants (#3088 §2):
  - প্রতিটি ইস্যুর একটি primary group বাধ্যতামূলক
  - নতুন issue create-র আগে agent **প্রথমে একই group-এর active issues** search করবে
    (group-first lookup — এই মডিউলের `group_first_lookup`)
  - Rollout কৌশল (spec §9.11): observe-only → high-confidence blocking → full
    enforcement। তাই `validate_primary_group` আপাতত **advisory** — legacy group
    (step-3, pipeline-failures, autonomy-audit...) backward-compatible থাকবে;
    hard-enforcement follow-up slice-এ (guard-wiring)।

Usage (CLI — subcommand-ভিত্তিক):
    python scripts/agents/group_taxonomy.py list
    python scripts/agents/group_taxonomy.py validate governance
    python scripts/agents/group_taxonomy.py lookup pipeline --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

ROOT_DIR = Path(__file__).resolve().parents[2]

# ── Canonical primary group taxonomy (#3088 §2) ──────────────────────────────
# বাংলা মন্তব্য: spec-এ নাম uppercase; লেবেল-জগত লোয়ারকেস — canonical label =
# `group:<lowercase>`। normalize_group() দুই রূপই গ্রহণ করে।
PRIMARY_GROUPS: tuple[str, ...] = (
    "governance",      # agent rules, permissions, admin approval, task contracts, policy
    "security",        # auth/RBAC, secrets, tenant isolation, sandbox gates, breaker findings
    "pipeline",        # GitHub Actions, CI/CD, PR gates, merge orchestration, issue router
    "architecture",    # স্ট্রাকচারাল/ফাউন্ডেশন রিফ্যাক্টর, ADR
    "reliability",     # লাইভনেস, watchdog, resilience, graceful degradation
    "product",         # ইউজার-মুখী ফিচার, UX, ডকুমেন্টেশন-ডেলিভারেবল
    "intelligence",    # LLM/প্ল্যানিং/মেমোরি/learning-loop ক্যাপাবিলিটি
    "infrastructure",  # ডিপ্লয়, secrets-infra, CDN, এক্সটার্নাল সার্ভিস ইন্টিগ্রেশন
)

# ── Master Federation Group Taxonomy Registry (#180) ─────────────────────────
# ৪টি প্রধান ক্যাটাগরিতে মোট ২৭টি ক্যানোনিকাল ফেডারেশন গ্রুপ:
FEDERATION_REPO_GROUPS: dict[str, str] = {
    "agents": "Supremeai-bd/supremeai-agents",
    "browser": "Supremeai-bd/supremeai-browser",
    "command": "Supremeai-bd/supremeai-command",
    "skills": "Supremeai-bd/supremeai-skills",
    "vscode": "Supremeai-bd/supremeai-vscode",
    "api": "Supremeai-bd/supremeai-api",
    "studio": "Supremeai-bd/supremeai-studio",
    "core": "Supremeai-bd/supremeai-core",
    "security": "Supremeai-bd/supremeai-security",
    "infra": "Supremeai-bd/supremeai-infra",
    "memory": "Supremeai-bd/supremeai-memory",
    "gateway": "Supremeai-bd/supremeai-open",
}

AI_INTELLIGENCE_GROUPS: tuple[str, ...] = (
    "prompts",
    "evals",
    "llm-routing",
    "datasets",
)

SYSTEM_RESILIENCE_GROUPS: tuple[str, ...] = (
    "reliability",
    "perf",
    "cost",
    "telemetry",
    "quality",
)

OPERATIONS_GOVERNANCE_GROUPS: tuple[str, ...] = (
    "governance",
    "bridge",
    "release",
    "docs",
    "billing",
    "triage",
)

# All 27 unique Master Federation Groups
MASTER_FEDERATION_GROUPS: tuple[str, ...] = tuple(sorted(set(
    list(FEDERATION_REPO_GROUPS.keys())
    + list(AI_INTELLIGENCE_GROUPS)
    + list(SYSTEM_RESILIENCE_GROUPS)
    + list(OPERATIONS_GOVERNANCE_GROUPS)
)))

GROUP_LABEL_PREFIX = "group:"
DEFAULT_REPO = "SaifulHaqueNiloy/supremeai"

# Legacy/operational group লেবেল — canonical ৮-টার বাইরে কিন্তু প্রথাগতভাবে চালু
# (pipeline-failures register, autonomy-audit পরিবার, step-N গ্রুপ...)।
# validate-র ফলাফলে এগুলো "legacy" হিসেবে রিপোর্ট হবে — blocked নয় (observe-only)।
KNOWN_LEGACY_GROUPS: tuple[str, ...] = (
    "pipeline-failures",
    "autonomy-audit",
    "platform-hygiene",
    "foundation-closeout",
    "pipeline-governance",
    "backlog",
    "ci-hotfix",
)


@dataclass
class GroupValidation:
    """#3088 §2 / #180 — primary-group validation-ফলাফল (observe-only rollout)।"""

    group: str
    is_canonical: bool = False
    is_legacy: bool = False
    known: bool = False
    message: str = ""
    target_repo: str | None = None
    category: str = "unknown"

    @property
    def advisory_only(self) -> bool:
        # বাংলা মন্তব্য: slice-1 সব ফলাফল advisory — hard-block follow-up slice।
        return True


def normalize_group(name: str) -> str:
    """`GOVERNANCE`/`Governance` → `governance` (case-insensitive canonicalization)।"""
    return (name or "").strip().lower().removeprefix(GROUP_LABEL_PREFIX).strip()


def resolve_group_repository(group: str) -> str | None:
    """Returns the targeted federation repository for a given group, or None if cross-cutting."""
    g = normalize_group(group)
    return FEDERATION_REPO_GROUPS.get(g)


def group_category(group: str) -> str:
    """Returns the functional category for a given group."""
    g = normalize_group(group)
    if g in FEDERATION_REPO_GROUPS:
        return "repository-direct"
    if g in AI_INTELLIGENCE_GROUPS:
        return "ai-intelligence"
    if g in SYSTEM_RESILIENCE_GROUPS:
        return "system-resilience"
    if g in OPERATIONS_GOVERNANCE_GROUPS:
        return "operations-governance"
    return "unknown"


def validate_primary_group(name: str) -> GroupValidation:
    """Primary group canonical/legacy/unknown শ্রেণীবিভাগ (observe-only)।

    # বাংলা মন্তব্য (#3088 §9.11 / #180): enforcement ধাপে যাওয়ার আগ পর্যন্ত unknown
    group = advisory warning, creation আটকাবে না — বর্তমান চালু ফ্লো (step-N
    group ইত্যাদি) ভাঙা নিষিদ্ধ (Engineering constraint: existing preserved)।
    """
    g = normalize_group(name)
    if not g:
        return GroupValidation(group=g, message="primary group খালি — spec অনুযায়ী বাধ্যতামূলক (advisory এখন)")
    if g in MASTER_FEDERATION_GROUPS or g in PRIMARY_GROUPS:
        repo = resolve_group_repository(g)
        cat = group_category(g)
        repo_note = f" -> target repo: {repo}" if repo else ""
        return GroupValidation(
            group=g,
            is_canonical=True,
            known=True,
            target_repo=repo,
            category=cat,
            message=f"canonical primary group: {g} [{cat}]{repo_note}"
        )
    if g in KNOWN_LEGACY_GROUPS or g.startswith("step-"):
        return GroupValidation(group=g, is_legacy=True, known=True, message=f"legacy/operational group: {g} (advisory)")
    return GroupValidation(group=g, known=False, message=f"unknown group: {g} — canonical মাস্টার তালিকার একটি বিবেচনা করুন (advisory)")


def primary_group_of_labels(labels: list[str] | None) -> str | None:
    """লেবেল-তালিকা থেকে প্রথম primary `group:<name>` বের করে (normalized)।

    # বাংলা মন্তব্য: একাধিক group লেবেল থাকলে lexicographically প্রথমটা নেই —
    deterministic। (Spec: "প্রতিটি issue-এর একটি primary group" — একাধিক থাকা
    নিজেই একটি anomaly, follow-up guard রিপোর্ট করবে।)
    """
    groups = sorted(
        normalize_group(lbl)
        for lbl in (labels or [])
        if str(lbl).startswith(GROUP_LABEL_PREFIX)
    )
    return groups[0] if groups else None


# ── Group-first issue discovery (#3088 §3) ───────────────────────────────────

@dataclass
class GroupLookupReport:
    """একই group-এর active কাজের context — creation-সিদ্ধান্তের প্রথম ইনপুট।"""

    group: str
    active_issues: list[dict] = field(default_factory=list)
    lookup_ok: bool = False
    error: str = ""

    @property
    def active_count(self) -> int:
        return len(self.active_issues)

    def issues_by_state(self) -> dict[str, list[int]]:
        # বাংলা মন্তব্য: queue-health-এর সারসংক্ষেপ — কয়টা claimable, কয়টা চলমান।
        states: dict[str, list[int]] = {"in_progress": [], "has_pr": [], "claimable": [], "other": []}
        for iss in self.active_issues:
            # বাংলা মন্তব্য: gh --json labels = [{"name": ...}] — name-ফিল্ড বের করে নিই।
            names = {str(lbl.get("name", "")) if isinstance(lbl, dict) else str(lbl)
                     for lbl in iss.get("labels", [])}
            num = iss.get("number")
            if "status:in-progress" in names:
                states["in_progress"].append(num)
            elif "has-pr" in names:
                states["has_pr"].append(num)
            elif "type:ledger" in names or "template:violating" in names:
                states["other"].append(num)
            else:
                states["claimable"].append(num)
        return states


def _run_gh(args: list[str], repo_dir: Path = ROOT_DIR) -> str:
    res = subprocess.run(
        args, cwd=str(repo_dir), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip()[:200] or f"gh exit {res.returncode}")
    return res.stdout


def group_first_lookup(
    group: str,
    repo_dir: Path = ROOT_DIR,
    limit: int = 60,
) -> GroupLookupReport:
    """একই group-এর সব active (open) ইস্যু — #3088 §3 lookup-order-এর ধাপ ১।

    # বাংলা মন্তব্য: নতুন ইস্যু খোলার আগে agent এই রিপোর্ট দেখবে —
    existing work থাকলে link/update, না থাকলে তবেই create। API/নেটওয়ার্ক
    ব্যর্থ হলে lookup_ok=False (caller সিদ্ধান্ত নেবে — fail-open প্রথা
    মেনে চলমান কাজ আটকাবেনা, শুধু সতর্ক করবে)।
    """
    g = normalize_group(group)
    report = GroupLookupReport(group=g)
    try:
        out = _run_gh([
            "gh", "issue", "list", "--repo", DEFAULT_REPO, "--state", "open",
            "--label", f"{GROUP_LABEL_PREFIX}{g}", "--limit", str(limit),
            "--json", "number,title,labels,updatedAt",
        ], repo_dir=repo_dir)
        report.active_issues = json.loads(out or "[]")
        report.lookup_ok = True
    except (subprocess.SubprocessError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        report.error = f"lookup failed: {exc}"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonical group taxonomy utilities (#3088)")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list", help="৮টি canonical primary group তালিকা")
    v = sub.add_parser("validate", help="group-নাম canonical/legacy/unknown শ্রেণীবিভাগ")
    v.add_argument("name")
    lk = sub.add_parser("lookup", help="group-first: একই group-এর active ইস্যু")
    lk.add_argument("name")
    lk.add_argument("--json", action="store_true", help="JSON আউটপুট")

    args = parser.parse_args()
    if args.cmd == "list":
        for g in PRIMARY_GROUPS:
            print(f"group:{g}")
        return 0
    if args.cmd == "validate":
        print(json.dumps(validate_primary_group(args.name).__dict__, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "lookup":
        report = group_first_lookup(args.name)
        if args.json:
            payload = {
                "group": report.group, "lookup_ok": report.lookup_ok,
                "active_count": report.active_count, "error": report.error,
                "states": report.issues_by_state(),
                "issues": [{"number": i.get("number"), "title": i.get("title")} for i in report.active_issues],
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            if not report.lookup_ok:
                print(f"⚠️  {report.error}")
                return 1
            print(f"👥 group:{report.group} — {report.active_count} active issue(s)")
            for state, nums in report.issues_by_state().items():
                if nums:
                    print(f"   {state}: {', '.join(f'#{n}' for n in nums)}")
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
