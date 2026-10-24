#!/usr/bin/env python3
"""Automatic Priority Escalation Engine (#2573).

When higher-priority queues empty, promotes oldest/high-value issues from
the next lower tier so the queue never starves.

Triggers:
- Post-merge/close hook
- Scheduled CI job
- Manual: python scripts/ci/auto_escalate_priority.py

Rules:
1. Count open issues per priority tier (P0, P1, P2, P3).
2. If P0 count == 0, promote up to N oldest P1 issues to P0-critical.
3. If P0 count < MIN_P0_THRESHOLD, backfill from P1.
4. Repeat for P1 <- P2, P2 <- P3.
5. Never demote already-higher-priority issues.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

REPO = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")
PRIORITY_ORDER = ["P0-critical", "P1-high", "P2-medium", "P3-low"]
MIN_P0_THRESHOLD = 1
MIN_P1_THRESHOLD = 2
PROMOTE_BATCH = 3


def run(cmd: list[str], **kwargs):
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **kwargs,
    )


def get_open_issues():
    res = run(["gh", "issue", "list", "--repo", REPO, "--state", "open", "--limit", "300", "--json", "number,title,labels,createdAt"])
    if res.returncode == 0 and res.stdout.strip():
        try:
            return json.loads(res.stdout)
        except json.JSONDecodeError:
            pass
    return []


def parse_priority(labels):
    for label in labels:
        if label in ("P0-critical", "P1-high", "P2-medium", "P3-low"):
            return label
    return None


def count_by_priority(issues):
    counts = defaultdict(int)
    for issue in issues:
        prio = parse_priority(issue.get("labels", []))
        if prio:
            counts[prio] += 1
    return counts


def promote_issues(issues, target_priority, batch_size):
    candidates = []
    for issue in issues:
        prio = parse_priority(issue.get("labels", []))
        if prio and PRIORITY_ORDER.index(prio) == PRIORITY_ORDER.index(target_priority) + 1:
            candidates.append(issue)
    candidates.sort(key=lambda x: x.get("createdAt", ""))
    return candidates[:batch_size]


def escalate():
    issues = get_open_issues()
    counts = count_by_priority(issues)
    report = []
    
    for tier in PRIORITY_ORDER[:-1]:
        current_count = counts.get(tier, 0)
        threshold = MIN_P0_THRESHOLD if tier == "P0-critical" else (MIN_P1_THRESHOLD if tier == "P1-high" else 0)
        
        if current_count == 0 or (threshold and current_count < threshold):
            needed = max(0, threshold - current_count) if threshold else (1 if current_count == 0 else 0)
            if needed > 0:
                to_promote = promote_issues(issues, tier, min(needed, PROMOTE_BATCH))
                for issue in to_promote:
                    num = issue["number"]
                    old_prio = parse_priority(issue.get("labels", []))
                    run([
                        "gh", "issue", "edit", str(num),
                        "--remove-label", old_prio,
                        "--add-label", tier
                    ])
                    report.append({
                        "issue": num,
                        "from": old_prio,
                        "to": tier
                    })
    return report


def main():
    parser = argparse.ArgumentParser(description="Automatic Priority Escalation Engine (#2573)")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()
    
    report = escalate()
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        if not report:
            print("✅ No priority escalation needed.")
        else:
            print(f"🔄 Escalated {len(report)} issues:")
            for item in report:
                print(f"   #{item['issue']}: {item['from']} -> {item['to']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
