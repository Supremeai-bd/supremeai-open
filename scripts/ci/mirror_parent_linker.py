#!/usr/bin/env python3
"""Mirror-claim issue → parent has-pr linker (#2894).

সমস্যা (issue #2894): planner/agent যখন কোনো parent issue-র জন্য আলাদা
mirror/claim issue তৈরি করে (যেমন #2756 for #2718), parent-এ কোনো গার্ড
লেবেল যায় না — ফলে অন্য agent parent-কে unclaimed ভেবে duplicate PR
খোলে (প্রমাণ: #2718 → #2756 → parallel PR #2783)।

মিরর-মার্কার (প্রমাণ-কেস থেকে derived — conservative):
  title/body-তে `root-cause #N` বা `root-cause fix for #N`
  জেনেরিক `Refs/Fixes/Closes #N` ইচ্ছাকৃতভাবে বাদ (dependency-ref
  false-positive: #2925-এর `Refs #2919` হলো নির্ভরতা, mirror নয়);
  group-predecessor (`পূর্ববর্তী ইস্যু: #N`)-ও নয়।

সুযোগ (spec-অনুযায়ী দুই স্তর):
  ১. creation-time linking — create_group_issue.py নতুন issue তৈরির পরে
     এটি কল করে (parent পাওয়া গেলে has-pr + বাংলা নোটিশ)।
  ২. claim-time scan — atomic_claim.sh parent claim-এর আগে --scan-parent
     চালায়; open mirror থাকলে has-pr backfill + claim abort। ফলে
     planner-created mirror (external flow) থাকলেও coder-side race বন্ধ।

I/O চুক্তি: সব gh-কল একটি injectable runner-এর ভেতর দিয়ে যায় — টেস্টে
fake runner, রানটাইমে subprocess (gh CLI; CI/operator env-এ উপলব্ধ)।
Idempotent: has-pr আগেই থাকলে বা marker-কমেন্ট থাকলে দ্বিতীয়বার কিছু করে না।
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

DEFAULT_REPO = "SaifulHaqueNiloy/supremeai"
MARKER = "🪪 Mirror claim issue"

# বাংলা মন্তব্য: conservative mirror-মার্কার — শুধু planner-এর প্রতিষ্ঠিত
# root-cause টেমপ্লেট; জেনেরিক রেফারেন্স থেকে false-positive এড়াতে।
MIRROR_REF_RE = re.compile(r"root-cause\s+(?:fix\s+)?(?:for\s+)?#(\d+)", re.IGNORECASE)


def _default_runner(cmd: list[str], **kw):
    # বাংলা মন্তব্য: রানটাইম runner — subprocess.run-এর চেয়ে বেশি কিছু নয়;
    # টেস্টে এটি fake runner দিয়ে প্রতিস্থাপিত হয় (I/O মুক্ত চুক্তি-টেস্ট)।
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def extract_parent_ref(title: str, body: str) -> int | None:
    """title → body ক্রমে প্রথম root-cause mirror-রেফারেন্সের parent নম্বর।"""
    for text in (title or "", body or ""):
        match = MIRROR_REF_RE.search(text)
        if match:
            return int(match.group(1))
    return None


def _gh_labels(parent_issue: int, repo: str, runner) -> list[str]:
    # বাংলা মন্তব্য: --jq নয় — raw JSON নিয়ে python-এ পার্স (fake-runner চুক্তি
    # সরল থাকে এবং jq-নির্ভরতা/escaping-পিটফল এড়ানো যায়)।
    proc = runner(["gh", "api", f"repos/{repo}/issues/{parent_issue}"])
    try:
        data = json.loads(proc.stdout or "{}")
        return [lbl.get("name", "") for lbl in (data.get("labels") or []) if isinstance(lbl, dict)]
    except Exception:
        return []


def _gh_comments(parent_issue: int, repo: str, runner) -> list[dict]:
    proc = runner(["gh", "api", f"repos/{repo}/issues/{parent_issue}/comments"])
    try:
        data = json.loads(proc.stdout or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []


def link_mirror_to_parent(
    mirror_issue: int,
    parent_issue: int,
    agent_name: str,
    *,
    runner=None,
    repo: str = DEFAULT_REPO,
) -> dict:
    """Parent issue-তে has-pr লেবেল + নোটিশ কমেন্ট (idempotent)।

    রিটার্ন: {"label_added": bool, "comment_posted": bool}
    """
    runner = runner or _default_runner
    label_added = False
    comment_posted = False

    labels = _gh_labels(parent_issue, repo, runner)
    if "has-pr" not in labels:
        runner(["gh", "issue", "edit", str(parent_issue), "--repo", repo, "--add-label", "has-pr"])
        label_added = True

    # বাংলা মন্তব্য: marker + mirror নম্বর দিয়ে কমেন্ট-ডুপ শনাক্ত — পুনঃরান-নিরাপদ।
    marker_token = f"{MARKER} #{mirror_issue} "
    comments = _gh_comments(parent_issue, repo, runner)
    already = any(marker_token in (c.get("body") or "") for c in comments)
    if not already:
        body = (
            f"{MARKER} #{mirror_issue} created by {agent_name} — parent guarded (duplicate-PR race prevention #2894)।\n\n"
            f"এই parent-এর কাজ একটি mirror/claim issue হিসেবে ট্র্যাকড — parent সরাসরি claim/PR করার আগে "
            f"mirror issue-র অবস্থা দেখে নিন। (has-pr লেবেল স্বয়ংক্রিয়ভাবে যোগ করা হয়েছে।)"
        )
        runner(
            [
                "gh", "issue", "comment", str(parent_issue),
                "--repo", repo,
                "--body", body,
            ]
        )
        comment_posted = True

    return {"label_added": label_added, "comment_posted": comment_posted}


def find_open_mirror_issues(parent_issue: int, *, runner=None, repo: str = DEFAULT_REPO) -> list[int]:
    """Parent-এর জন্য খোলা mirror issue-গুলোর তালিকা (python-সাইড রি-ফিল্টার সহ)।

    gh search আলগা হতে পারে — তাই প্রার্থীদের ওপর আবার একই conservative
    regex চালানো হয়; self (parent নিজে) বাদ।
    """
    runner = runner or _default_runner
    proc = runner(
        [
            "gh", "issue", "list", "--repo", repo,
            "--state", "open",
            "--search", f'"root-cause #{parent_issue}"',
            "--json", "number,title,body",
        ]
    )
    try:
        issues = json.loads(proc.stdout or "[]")
    except Exception:
        return []

    mirrors: list[int] = []
    for item in issues if isinstance(issues, list) else []:
        try:
            number = int(item.get("number"))
        except (TypeError, ValueError):
            continue
        if number == int(parent_issue):
            continue
        if extract_parent_ref(item.get("title") or "", item.get("body") or "") == int(parent_issue):
            mirrors.append(number)
    return sorted(mirrors)


def maybe_link_created_mirror(
    *,
    url: str,
    title: str,
    body: str,
    agent_name: str,
    runner=None,
    repo: str = DEFAULT_REPO,
) -> int | None:
    """create_group_issue.py-এর post-create hook।

    নতুন issue-র title/body-তে mirror-মার্কার থাকলে parent-কে link করে এবং
    parent নম্বর ফেরত দেয়; না থাকলে None (কোনো gh-কল ছাড়াই)। URL থেকে
    mirror-নম্বর পার্স করা হয়।
    """
    parent = extract_parent_ref(title, body)
    if parent is None:
        return None
    match = re.search(r"/issues/(\d+)", url or "")
    if not match:
        return None
    mirror_number = int(match.group(1))
    link_mirror_to_parent(mirror_number, parent, agent_name, runner=runner, repo=repo)
    return parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mirror-claim issue → parent has-pr linker (#2894)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--scan-parent", type=int, help="parent issue N-এর খোলা mirror স্ক্যান (JSON)")
    mode.add_argument("--mirror", type=int, help="mirror issue N → parent link")
    parser.add_argument("--parent", type=int, default=None, help="parent issue (omit: --mirror-এর title/body থেকে extract)")
    parser.add_argument("--agent", default="unknown-agent", help="agent name (comment-এ ব্যবহৃত)")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    args = parser.parse_args(argv)

    if args.scan_parent is not None:
        mirrors = find_open_mirror_issues(args.scan_parent, repo=args.repo)
        print(json.dumps({"mirrors": mirrors}))
        return 0

    parent = args.parent
    if parent is None:
        proc = _default_runner(["gh", "issue", "view", str(args.mirror), "--repo", args.repo, "--json", "title,body"])
        try:
            data = json.loads(proc.stdout or "{}")
        except Exception:
            data = {}
        parent = extract_parent_ref(data.get("title") or "", data.get("body") or "")
    if parent is None:
        print("no mirror parent reference found (root-cause #N pattern absent)", file=sys.stderr)
        return 1
    report = link_mirror_to_parent(args.mirror, parent, args.agent, repo=args.repo)
    print(json.dumps({"parent": parent, **report}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
