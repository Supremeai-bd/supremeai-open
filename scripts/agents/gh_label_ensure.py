#!/usr/bin/env python3
"""Shared GitHub label-ensure helper (#3278) — issue-filing funnel revival.

বাংলা মন্যব্য (#3278 root-cause): `gh issue create --label X` তখনই পুরো create
ব্যর্থ করে যখন লেবেল X রিপোতে নেই (GitHub API-তে conditional-create নেই)।
লাইভ ঘটনা: rules_breaker-এর ৩৩ security-finding নীরবে হারাল
(`could not add label: 'vulnerability' not found`); create_issue.py-ও
`--severity high` → label `high` (repo-তে নেই) তে মৃত — fallback-ও একই ভাঙা
লেবেল ব্যবহার করত।

চুক্তি:
  ensure_labels(["a", "b"]) → প্রতিটি লেবেল existence-check + অনুপস্থিত হলে
  সৃষ্টি (idempotent, race-tolerant) → issue-create-এর জন্য প্রস্তুত তালিকা
  return। একটি `gh label list` কলে সব existence যাচাই (per-process cache)।

ডিজাইন-সিদ্ধান্ত (founder-নীতি "keep everything dynamic"):
  - কোনো হার্ডকোড লেবেল-তালিকা নেই — নতুন caller ভবিষ্যতে যে-কোনো লেবেল
    চাইলে স্বয়ংক্রিয়ভাবে তৈরি হবে; রিপো-র লেবেল-শব্দভান্ডার ব্যবহা-নির্ভর।
  - Infrastructure-failure (gh missing/token invalid) হলে LabelEnsureError
    raise — নীরব ডিগ্রেড নয় (যে-বাগ ফিক্স করছি সেটাই নীরবতা ছিল)।
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from functools import lru_cache

DEFAULT_REPO = "SaifulHaqueNiloy/supremeai"


class LabelEnsureError(RuntimeError):
    """Label existence যাচাই/সৃষ্টি অবকাঠামোগতভাবে ব্যর্থ — নীরব ডিগ্রেড নিষেধ।"""


@lru_cache(maxsize=4)
def _existing_labels(repo: str) -> frozenset[str]:
    """রিপোর বর্তমান লেবেল-সেট (per-process cache; এক স্ক্যানে একবারই নেটওয়ার্ক)।"""
    cmd = ["gh", "label", "list", "--limit", "300", "--json", "name"]
    if repo:
        cmd.extend(["--repo", repo])
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LabelEnsureError(f"gh label list failed: {exc}") from exc
    if res.returncode != 0:
        raise LabelEnsureError(
            f"gh label list failed (exit {res.returncode}): {(res.stderr or '')[:200]}"
        )
    try:
        return frozenset(
            item["name"] for item in json.loads(res.stdout or "[]") if item.get("name")
        )
    except (json.JSONDecodeError, AttributeError) as exc:
        raise LabelEnsureError(f"gh label list output parse failed: {exc}") from exc


def _create_label(label: str, repo: str) -> bool:
    """অনুপস্থিত লেবেল সৃষ্টি। Race-tolerant: সমান্তরাল creator-এ ইতিমধ্যে
    তৈরি হয়ে গেলে ("already exists") সেটা সাফল্যই ধরা হয়।
    Return: True = এই কলে তৈরি হলো বা ইতিমধ্যে আছে।"""
    cmd = ["gh", "label", "create", label]
    if repo:
        cmd.extend(["--repo", repo])
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LabelEnsureError(f"gh label create '{label}' failed: {exc}") from exc
    if res.returncode == 0:
        return True
    stderr = (res.stderr or "").lower()
    if "already exists" in stderr:
        return True  # race-lost কিন্তু লক্ষ্য পূর্ণ — লেবেল এখন আছে
    raise LabelEnsureError(
        f"gh label create '{label}' failed (exit {res.returncode}): {(res.stderr or '')[:200]}"
    )


def ensure_labels(labels: list[str], repo: str = DEFAULT_REPO) -> list[str]:
    """প্রতিটি লেবেল নিশ্চিত করো (থাকলে রাখো, না থাকলে সৃষ্টি) → প্রস্তুত তালিকা।

    - খালি/সাদা-স্পেস লেবেল চুপচাপ বাদ (gh CLI সেগুলোতে ব্যর্থ হয়)।
    - সব লেবেল ইতিমধ্যে থাকলে কোনো লেখা-কল হয় না (শুধু একটি list-কল)।
    - LabelEnsureError = infrastructure-failure — caller স্পষ্টভাবে সামলাবে।
    """
    cleaned: list[str] = []
    for lbl in labels:
        text = (lbl or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    if not cleaned:
        return []
    existing = _existing_labels(repo)
    for lbl in cleaned:
        if lbl not in existing:
            _create_label(lbl, repo)
    return cleaned


def main(argv: list[str] | None = None) -> int:
    """CLI: python gh_label_ensure.py LABEL [LABEL...] [--repo OWNER/REPO]"""
    parser = argparse.ArgumentParser(description="Ensure GitHub labels exist (create missing)")
    parser.add_argument("labels", nargs="+", help="labels to ensure")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="target repository")
    parser.add_argument(
        "--quiet", action="store_true",
        help="print only the ensured labels (machine-readable, space-separated)",
    )
    args = parser.parse_args(argv)
    try:
        ensured = ensure_labels(args.labels, repo=args.repo)
    except LabelEnsureError as exc:
        print(f"❌ [gh_label_ensure] {exc}", file=sys.stderr)
        return 1
    if args.quiet:
        print(" ".join(ensured))
    else:
        for lbl in ensured:
            print(f"✅ label ensured: {lbl}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
