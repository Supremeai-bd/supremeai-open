#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dependabot_classify.py — Dependency-bump semver classification
================================================================
বাংলা: এই script একটি PR-কে dependabot dependency-bump কিনা চিনে এবং
bump-এর semver class (major/minor/patch) নির্ণয় করে। Merge policy-র
single source of truth:

    patch / minor  →  auto-merge eligible (CI সবুজ হলে Helper auto-merge করে)
    major / unknown →  human review mandatory (auto-merge NEVER)

Fail-closed নীতি: version পার্স করা না গেলে বা dependabot title format
মেলে না কিন্তু author dependabot হলে → bump_class=unknown →
major-এর মতোই treat হয় (কখনোই fail-open নয়)।

Usage:
    python3 dependabot_classify.py --title "chore(deps): bump X from 1.0.0 to 1.1.0" \
        --author "dependabot[bot]" --output-json out.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# dependabot PR titles: "chore(deps): bump X from A to B" / "chore(deps-dev): bump ..."
# scope may be "deps", "deps-dev", "actions" etc.; pip bumps append " in <dir>"
BUMP_RE = re.compile(
    r"^chore\(deps(?:-dev)?\): bump\s+(?P<pkg>.+?)\s+from\s+"
    r"(?P<frm>\S+)\s+to\s+(?P<to>\S+)"
    r"(?:\s+in\s+.+)?$"
)

DEPENDABOT_AUTHORS = {"dependabot[bot]", "dependabot-preview[bot]"}


def semver_class(frm: str, to: str) -> str:
    """Semver transition class: major / minor / patch / unknown.

    Numeric dotted comparison (len = max of the two). Non-numeric segments
    (e.g. '0.1.0b1') fail-closed to 'unknown'.
    """
    def segs(v: str):
        return v.lstrip("v").split(".")

    try:
        a, b = segs(frm), segs(to)
        n = max(len(a), len(b))
        a += ["0"] * (n - len(a))
        b += ["0"] * (n - len(b))
        ai = [int(x) for x in a]
        bi = [int(x) for x in b]
    except (ValueError, AttributeError):
        return "unknown"

    if ai[0] != bi[0]:
        return "major"
    if len(ai) > 1 and ai[1] != bi[1]:
        return "minor"
    if ai != bi:
        return "patch"
    return "unknown"


def classify(title: str, author: str) -> dict:
    is_dependabot = (author or "").strip() in DEPENDABOT_AUTHORS
    pkg = frm = to = ""
    bump_class = "none"

    if is_dependabot:
        m = BUMP_RE.match((title or "").strip())
        if m:
            pkg = m.group("pkg")
            frm = m.group("frm")
            to = m.group("to")
            bump_class = semver_class(frm, to)
        else:
            # dependabot author but unexpected title format → fail-closed
            bump_class = "unknown"

    return {
        "is_dependabot": is_dependabot,
        "bump_class": bump_class,
        "package": pkg,
        "from_version": frm,
        "to_version": to,
        # auto_merge_eligible: deterministic policy single source of truth
        "auto_merge_eligible": is_dependabot and bump_class in ("patch", "minor"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Classify dependabot dependency bumps")
    ap.add_argument("--title", required=True, help="PR title")
    ap.add_argument("--author", required=True, help="PR author login")
    ap.add_argument("--output-json", default=None, help="write JSON here (also stdout)")
    args = ap.parse_args()

    result = classify(args.title, args.author)
    text = json.dumps(result, indent=2)
    print(text)
    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            f.write(text)
    # classification itself never fails the caller — callers branch on the JSON
    return 0


if __name__ == "__main__":
    sys.exit(main())
