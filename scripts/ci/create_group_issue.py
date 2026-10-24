#!/usr/bin/env python3
"""
SupremeAI Group Sequence Issue Creator
======================================
Enforces standardized group-sequenced issue creation with:
1. Group & Sequence labeling (group:step-X, seq:Y).
2. Group Staging & Batch Merge Train mandate (queue:hold staging until full group complete).
3. Declared touching files & atomic blast radius.
4. 3-Tier Verification contract (Reflection -> Boot Smoke -> Pytest).
5. Mandatory Bengali / Banglish rule for code comments (# বাংলা মন্তব্য:), PR descriptions, and discussions.

Usage:
    python scripts/ci/create_group_issue.py \\
        --group step-3 \\
        --seq 1 \\
        --type refactor \\
        --scope ai \\
        --title "consolidate 18 LLM routing layers into single LiteLLM/OpenRouter gateway" \\
        --predecessor 2277 \\
        --touching-files "backend/core/ai_router.py,backend/api/routes/llm.py" \\
        --test-cmd "pytest backend/tests/test_ai_router.py -v" \\
        --description "Consolidates redundant provider wrappers into canonical LiteLLM gateway."
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# #3088: canonical group-first + fingerprint dedup — ইস্যু-জন্মের আগেই জাল।
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "agents"))
from group_taxonomy import group_first_lookup, validate_primary_group  # noqa: E402
from issue_fingerprint import duplicate_guard, prepend_marker  # noqa: E402

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPO = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")

BODY_TEMPLATE = """## {formatted_title}

> 🇧🇩 **টিম নোটিশ:** আমাদের সম্পূর্ণ টেক টিম বাংলাদেশি — তাই কোডের ভেতরের সমস্ত কমেন্ট (`# বাংলা মন্তব্য:`), PR বিবরণ ও ডিসকাশন বাংলায়/বাংলিশে হতে হবে।

---

### 🔒 ১. Group Staging & Batch Merge Train Notice (কঠোর নিয়ম)
- **গ্রুপ পরিচিতি:** `group:{group}` · **সিকোয়েন্স:** `seq:{seq}` {predecessor_line}
- **স্ট্রেজিং নিয়ম (Staging Rule):** এই issue-র বিপরীতে তৈরি হওয়া PR কখনোই একাকী বা বিচ্ছিন্নভাবে `main`-এ মার্জ হবে না।
- **Queue Hold Mandate:** PR খোলার সাথে সাথেই `gh pr edit <PR#> --add-label 'queue:hold'` দিতে হবে।
- **Batch Landing Invariant:** সম্পূর্ণ গ্রুপের (`seq:1` থেকে শেষ `seq:N`) প্রতিটি issue-র PR তৈরি, টেস্ট গ্রিন এবং গ্রুপ ক্লোজআউট অডিট (`Capability Harvest & Zero Loss Audit`) সম্পন্ন হওয়ার পর কেবল **Merge Train** চালু হয়ে পুরো গ্রুপ একসাথে `main`-এ মার্জ হবে।

---

### 🎯 ২. Mission & Problem Statement
{description}

---

### 📁 ৩. Declared Touching Files (Atomic Blast Radius)
> **নিয়ম:** ১ Issue = ১ Branch = ১ PR (সর্বোচ্চ ১–২ ফাইল)। ক্লেইম করা স্কোপের বাইরে ড্রাইভ-বাই রিফ্যাক্টরিং নিষিদ্ধ।
```text
Touching files: {touching_files}
```

---

### 🧪 ৪. 3-Tier Verification Contract
PR খোলার পূর্বে নিচের ৩টি স্তর সফলভাবে সম্পন্ন হতে হবে:
1. **Reflection Check (Grep):**
   `git grep -n "{search_symbol}"` (অপ্রয়োজনীয় রেফারেন্স বা ডেড কোড পরীক্ষা)
2. **Boot Smoke Test:**
   `python -c "import backend.main; print('Boot smoke passed')"`
3. **Pytest Suite:**
   `{test_cmd}`

---

### 📋 ৫. Compliance & Checklist
- [ ] `./scripts/ci/atomic_claim.sh <issue#> <slot>` দিয়ে ক্লেইম করা হয়েছে
- [ ] 'Touching files: {touching_files}' কমেন্টে ঘোষণা করা হয়েছে
- [ ] সমস্ত নতুন বা পরিবর্তিত লজিকের সাথে `# বাংলা মন্তব্য:` যুক্ত আছে
- [ ] PR ডেসক্রিপশনে Test Evidence সংযুক্ত আছে
- [ ] PR খোলার সাথে সাথে `queue:hold` এবং parent issue-তে `has-pr` লেবেল যোগ করা হয়েছে
- [ ] সম্পূর্ণ গ্রুপ শেষ না হওয়া পর্যন্ত এটি মার্জ ট্রেনের অপেক্ষায় থাকবে

---
*Created per SupremeAI Constitution (`AGENTS.md` v2 & Group Batch Staging Protocol).*
"""


def build_issue_payload(args: argparse.Namespace) -> tuple[str, str, list[str]]:
    formatted_title = f"{args.type}({args.scope}): [Step-{args.group.replace('step-', '')}.{args.seq}] {args.title}"
    predecessor_line = f"· **পূর্ববর্তী ইস্যু:** #{args.predecessor}" if args.predecessor else ""
    search_symbol = args.touching_files.split(",")[0].split("/")[-1].replace(".py", "").replace(".ts", "")

    body = BODY_TEMPLATE.format(
        formatted_title=formatted_title,
        group=args.group,
        seq=args.seq,
        predecessor_line=predecessor_line,
        description=args.description.strip(),
        touching_files=args.touching_files.strip(),
        search_symbol=search_symbol,
        test_cmd=args.test_cmd.strip(),
    )

    labels = [
        f"group:{args.group}",
        f"seq:{args.seq}",
        args.priority,
        f"handoff:{args.lane}",
    ]
    if args.seq == 1:
        labels.append("status:unclaimed")
    else:
        labels.extend(["status:unclaimed", "blocked"])

    if args.extra_labels:
        for lbl in args.extra_labels.split(","):
            lbl_clean = lbl.strip()
            if lbl_clean and lbl_clean not in labels:
                labels.append(lbl_clean)

    return formatted_title, body, labels


def create_issue(title: str, body: str, labels: list[str], dry_run: bool = False, repo: str = DEFAULT_REPO) -> str:
    cmd = [
        "gh", "issue", "create",
        "--repo", repo,
        "--title", title,
        "--body", body,
        "--label", ",".join(labels),
    ]

    if dry_run:
        print("\n[DRY RUN] Executing command:")
        print(" ".join(cmd[:4]) + f" --title '{title}' --label '{','.join(labels)}'")
        print("\n--- ISSUE BODY PREVIEW ---\n")
        print(body)
        print("--------------------------\n")
        return "dry-run-url"

    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        print(f"❌ Error creating issue: {res.stderr}", file=sys.stderr)
        sys.exit(res.returncode)

    return res.stdout.strip()


def pre_create_guard(args: argparse.Namespace, title: str) -> tuple[str, str]:
    """#3088 §3 — group-first lookup + fingerprint duplicate-guard।

    # বাংলা মন্তব্য (#3088): ইস্যু খোলার আগে নিয়মক্রম —
      ১. একই group-এর active ইস্যু রিপোর্ট (context)
      ২. fingerprint dedup: active duplicate থাকলে **block** (escape: --allow-duplicate)
      ৩. closed-window duplicate থাকলে **block** (#2983-প্যাটার্ন)
    সফল পথে fingerprint-মার্কার-যুক্ত body ফেরত দেয়।
    """
    validation = validate_primary_group(args.group)
    print(f"🏷️  Group validation: {validation.message}")

    if not args.allow_duplicate:
        lookup = group_first_lookup(args.group)
        if lookup.lookup_ok and lookup.active_count:
            states = lookup.issues_by_state()
            print(f"👥 group:{args.group} active: {lookup.active_count} "
                  f"(in-progress: {len(states['in_progress'])}, has-pr: {len(states['has_pr'])}, "
                  f"claimable: {len(states['claimable'])})")

        verdict = duplicate_guard(
            primary_group=args.group,
            problem=args.title,
            affected_scope=args.touching_files,
            root_cause_class=args.root_cause,
        )
        if verdict.blocked:
            print(f"⛔ [GUARD-DUPLICATE] {verdict.reason}")
            print(f"   fingerprint: {verdict.fingerprint}")
            print("   → বিদ্যমান ইস্যু link/update করুন; নতুন creation নিষিদ্ধ।")
            print("   → (সচেতন ব্যতিক্রম হলে --allow-duplicate, কারণসহ কমেন্টে লিখুন)")
            sys.exit(3)
        print(f"✅ [GUARD-DUPLICATE] {verdict.reason} (fp={verdict.fingerprint})")
        return verdict.fingerprint, args.description.strip()
    print("⚠️  --allow-duplicate: dedup-জাল সচেতনভাবে বাইপাস — কারণ ইস্যুতে লিখুন।")
    return "", args.description.strip()


def link_parent_if_mirror(url: str, title: str, body: str) -> None:
    """#2894: নতুন issue-টি যদি mirror-claim (root-cause #N প্যাটার্ন) হয়,
    parent issue-তে has-pr + নোটিশ কমেন্ট যোগ করা হয় — duplicate-PR race
    প্রতিরোধ। Best-effort: কোনো ব্যর্থতা creation-কে ব্যর্থ করবে না।"""
    try:
        from mirror_parent_linker import maybe_link_created_mirror

        parent = maybe_link_created_mirror(
            url=url, title=title, body=body, agent_name="create_group_issue",
        )
        if parent is not None:
            print(f"🪪 Mirror detected — parent #{parent} guarded with has-pr (#2894).")
    except Exception as error:  # বাংলা মন্তব্য: linking ঐচ্ছিক — ব্যর্থতায় সতর্ক করে এগিয়ে যাওয়া
        print(f"⚠️ mirror parent-linking skipped: {error}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Create a standardized SupremeAI Group Sequence Issue.")
    parser.add_argument("--group", required=True, help="Group name, e.g. step-2, step-3")
    parser.add_argument("--seq", type=int, required=True, help="Sequence number within group, e.g. 1, 2, 3")
    parser.add_argument("--type", default="refactor", choices=["refactor", "chore", "feat", "fix", "audit"], help="Type prefix")
    parser.add_argument("--scope", required=True, help="Scope name, e.g. mesh, ai, memory, cleanup")
    parser.add_argument("--title", required=True, help="Issue title summary")
    parser.add_argument("--predecessor", type=int, default=None, help="Predecessor issue number (if any)")
    parser.add_argument("--touching-files", required=True, help="Comma-separated declared touching files")
    parser.add_argument("--test-cmd", default="pytest -v", help="Pytest verification command")
    parser.add_argument("--description", required=True, help="Problem & mission description")
    parser.add_argument("--priority", default="P2-medium", choices=["P0-critical", "P1-high", "P2-medium", "P3-low"], help="Issue priority")
    parser.add_argument("--lane", default="coder", choices=["coder", "planner", "ci", "platform"], help="Lane for handoff")
    parser.add_argument("--extra-labels", default="", help="Comma-separated additional labels")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub target repo")
    parser.add_argument("--dry-run", action="store_true", help="Print issue preview without creating on GitHub")
    # ── #3088: group-first + fingerprint dedup ──
    parser.add_argument(
        "--root-cause", default="unspecified",
        choices=["concurrency", "logic", "wiring", "contract", "stale-state",
                 "hardcoding", "security", "reliability", "unspecified"],
        help="Root-cause class — fingerprint-উপাদান (#3088 §3)",
    )
    parser.add_argument(
        "--allow-duplicate", action="store_true",
        help="Active/closed fingerprint-duplicate থাকলেও create (সচেতন ব্যতিক্রম, কারণ লিখুন)",
    )

    args = parser.parse_args()

    # #3088 §3: খোলার আগেই group-first + duplicate-guard — ভুল জন্মানোর আগে থামা।
    fp, _ = pre_create_guard(args, args.title)

    title, body, labels = build_issue_payload(args)
    if fp:
        # বাংলা মন্তব্য: fingerprint-মার্কার বডির প্রথম লাইনে (#2983-চুক্তি) —
        # ভবিষ্যতের যেকোনো creator এই মার্কার দেখে duplicate ধরবে।
        body = prepend_marker(body, fp)
    url = create_issue(title, body, labels, dry_run=args.dry_run, repo=args.repo)
    print(f"✅ Issue successfully generated: {url}")
    if not args.dry_run:
        # বাংলা মন্তব্য: mirror-claim issue হলে parent guard (#2894) — non-fatal।
        link_parent_if_mirror(url, title, body)


if __name__ == "__main__":
    main()
