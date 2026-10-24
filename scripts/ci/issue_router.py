#!/usr/bin/env python3
"""SupremeAI Issue Router — auto-label + auto-prioritize issues.

বাংলা মন্তব্য: নতুন issue create হলে এই script trigger হবে।
issue body থেকে keywords মিলিয়ে auto-label করে:
- area:backend/frontend/ci/architecture/infrastructure
- type:bug/architecture/dead-code/duplication/security/etc
- priority: P0/P1/P2/P3 (title keywords থেকে)
- handoff:agent (সব agent-এর জন্য universal)

Usage:
  python scripts/ci/issue_router.py --issue 1234
  python scripts/ci/issue_router.py --issue 1234 --dry-run
"""
import argparse
import json
import os
import subprocess
import sys

# Keyword → label mapping
AREA_KEYWORDS = {
    "area:backend": ["backend", "python", ".py", "import", "backend/", "api/", "core/", "fastapi", "pytest"],
    "area:frontend": ["frontend", ".tsx", ".ts", "react", "vite", "typescript", "frontend/"],
    "area:ci": [".github/", "workflow", "ci", "github actions", "gate", "pipeline"],
    "area:architecture": ["architecture", "design", "abstraction", "kernel", "circle", "consolidat"],
    "area:infrastructure": ["docker", "render", "supabase", "upstash", "cloudflare", "infrastructure"],
}

TYPE_KEYWORDS = {
    "bug": ["bug", "broken", "crash", "error", "fail", "500", "404", "traceback"],
    "type:dead-code": ["dead", "orphan", "unused", "zero importer", "0 importers"],
    "type:duplication": ["duplicate", "redundant", "competing", "fragmented"],
    "type:security": ["security", "vulnerability", "secret", "credential", "injection", "auth"],
    "type:architecture": ["architecture", "refactor", "consolidate", "merge", "unify"],
    "type:reliability": ["reliability", "regression", "test", "coverage", "stability"],
}

PRIORITY_KEYWORDS = {
    "P0-critical": ["critical", "production down", "main red", "security breach", "data loss"],
    "P1-high": ["bug", "broken", "fail", "crash", "high", "important"],
    "P2-medium": ["cleanup", "refactor", "improve", "medium"],
    "P3-low": ["docs", "documentation", "minor", "nice to have", "low"],
}


def fetch_issue(issue_num: int) -> dict:
    repo = os.environ.get("GH_REPO", "")
    token = os.environ.get("GH_TOKEN", "")
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/issues/{issue_num}"],
        capture_output=True, text=True, timeout=30
    )
    return json.loads(result.stdout) if result.stdout else {}


def classify(text: str, keyword_map: dict) -> list[str]:
    """Match text against keyword map and return matching labels."""
    text_lower = text.lower()
    labels = []
    for label, keywords in keyword_map.items():
        if any(kw in text_lower for kw in keywords):
            labels.append(label)
    return labels


def route_issue(issue: dict, dry_run: bool = False) -> list[str]:
    """Auto-label an issue based on its title + body."""
    title = issue.get("title", "")
    body = issue.get("body", "")
    combined = f"{title} {body}"

    labels_to_add = []

    # Area detection
    area_labels = classify(combined, AREA_KEYWORDS)
    labels_to_add.extend(area_labels)

    # Type detection
    type_labels = classify(combined, TYPE_KEYWORDS)
    labels_to_add.extend(type_labels)

    # Priority detection (only if no priority label exists)
    existing_labels = [l["name"] for l in issue.get("labels", [])]
    has_priority = any(l.startswith("P") for l in existing_labels)
    if not has_priority:
        prio_labels = classify(combined, PRIORITY_KEYWORDS)
        if prio_labels:
            labels_to_add.append(prio_labels[0])  # first match
        else:
            labels_to_add.append("P3-low")  # default

    # Universal handoff
    if not any(l.startswith("handoff:") for l in existing_labels):
        labels_to_add.append("handoff:coder")

    # Deduplicate
    labels_to_add = list(set(labels_to_add))

    if dry_run:
        print(f"[DRY RUN] Would add: {labels_to_add}")
    else:
        repo = os.environ.get("GH_REPO", "")
        for label in labels_to_add:
            if label not in existing_labels:
                subprocess.run(
                    ["gh", "issue", "edit", str(issue["number"]),
                     "--add-label", label],
                    capture_output=True, timeout=10
                )
        print(f"✅ Issue #{issue['number']}: added {len(labels_to_add)} labels: {labels_to_add}")

    return labels_to_add


def ensure_sequence(issue: dict, labels_applied: list[str]) -> None:
    """Router hook (#3218 AC-1): a newly grouped issue must receive its
    sequence automatically — no agent/admin supplies --seq.

    The router only decides WHEN (issue open/edit event reached routing);
    the queue manager owns the HOW (deterministic allocation + downstream
    shifts), so there is exactly one queue engine (U4/P2 — no fork).
    Fail-soft: allocation failure is reported but does not fail routing —
    the scheduled reconcile sweep is the safety net.
    """
    existing = [l["name"] for l in issue.get("labels", [])]
    all_labels = set(existing) | set(labels_applied)
    has_group = any(l.startswith("group:") for l in all_labels)
    has_seq = any(l.startswith("seq:") for l in all_labels)
    if not has_group or has_seq:
        return

    qm = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "issue_queue_manager.py")
    result = subprocess.run(
        [sys.executable, qm, "allocate", "--issue", str(issue["number"])],
        capture_output=True, text=True, timeout=120
    )
    out = (result.stdout or "").strip()
    if out:
        print(out)
    if result.returncode != 0:
        err = (result.stderr or "").strip()
        print(f"⚠️ Auto-sequence allocation failed for #{issue['number']} "
              f"(scheduled reconcile will cover it): {err}")


def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI Issue Router")
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    issue = fetch_issue(args.issue)
    if not issue:
        print(f"❌ Could not fetch issue #{args.issue}")
        return 1

    labels_applied = route_issue(issue, args.dry_run)
    if not args.dry_run:
        ensure_sequence(issue, labels_applied)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
