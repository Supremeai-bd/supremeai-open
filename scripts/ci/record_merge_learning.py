#!/usr/bin/env python3
"""Merge-Learning Recorder (issue #1929, founder directive).

Gathers the learning report for a merged PR and POSTs it to the backend
/api/merge-learning/webhook:

  - why the merge was allowed as an improvement  (Unified PR Gate verdict)
  - what it did                                  (title/body/files/±counts)
  - the mistake trail                            (held/queue:hold/conflict timeline)
  - lane, linked issues, merge metadata

Idempotent: the backend upserts on pr_number — re-running updates, never duplicates.

Usage:
  GH_TOKEN=... python scripts/ci/record_merge_learning.py --pr 1923 [--dry-run]

Env:
  GH_TOKEN                    GitHub token (read access)
  MERGE_LEARNING_WEBHOOK_URL  Backend endpoint (default: $BACKEND_URL/api/merge-learning/webhook)
  CI_WEBHOOK_SECRET           Shared secret header value
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

GITHUB_API = "https://api.github.com"

LANE_PATTERN = re.compile(
    r"^(planner|coder|pr-helper|ci|browser|platform|super)-\d+$"
)
HELD_LABELS = {"queue:hold", "hold:merge-conflict", "queue:failed", "pr-helper:blocked"}
ISSUE_REF = re.compile(r"(?:closes|fixes|resolves)\s+#(\d+)", re.IGNORECASE)


def gh_api(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{GITHUB_API}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def detect_lane(branch: str) -> str | None:
    m = LANE_PATTERN.match(branch)
    return m.group(1) if m else None


def extract_gate_verdict(comments: list[dict]) -> tuple[str | None, str | None, str | None]:
    """Return (status, risk_class, rationale) from the LAST Unified PR Gate comment."""
    verdict_status = risk_class = None
    rationale_lines: list[str] = []
    for c in comments:  # chronological; last one wins
        body = c.get("body", "")
        if "Unified PR Gate" not in body:
            continue
        for line in body.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and cells[0].replace("**", "").strip() == "Status":
                verdict_status = cells[1].replace("*", "").replace("`", "").strip()
            if len(cells) >= 2 and cells[0].replace("**", "").strip() == "Risk class":
                risk_class = cells[1].replace("*", "").replace("`", "").strip()
        rationale_lines = []
        for line in body.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and cells[0].replace("**", "").strip() in (
                "Protected scope touched", "Self-modification detected",
                "Preservation guard", "Guardian-Lite findings", "Guardian-Deep findings",
            ):
                rationale_lines.append(f"{cells[0].replace('**','')}: {cells[1].replace('**','').replace('`','')}")
    rationale = "; ".join(rationale_lines)[:2000] if rationale_lines else None
    return verdict_status, risk_class, rationale


def extract_held_history(timeline: list[dict]) -> list[dict]:
    events = []
    for ev in timeline:
        if ev.get("event") == "labeled" and ev.get("label", {}).get("name") in HELD_LABELS:
            events.append({
                "label": ev["label"]["name"],
                "at": ev.get("created_at"),
                "by": (ev.get("actor") or {}).get("login"),
            })
        elif ev.get("event") == "unlabeled" and ev.get("label", {}).get("name") in HELD_LABELS:
            events.append({
                "label_removed": ev["label"]["name"],
                "at": ev.get("created_at"),
                "by": (ev.get("actor") or {}).get("login"),
            })
    return events


def build_payload(pr: dict, token: str) -> dict:
    comments = gh_api(f"/repos/{pr['base']['repo']['full_name']}/issues/{pr['number']}/comments?per_page=100", token)
    try:
        timeline = gh_api(f"/repos/{pr['base']['repo']['full_name']}/issues/{pr['number']}/timeline?per_page=100", token)
    except Exception:
        timeline = []  # timeline needs preview accept header on older GHES; tolerate
    verdict_status, risk_class, rationale = extract_gate_verdict(comments)

    files = gh_api(f"/repos/{pr['base']['repo']['full_name']}/pulls/{pr['number']}/files?per_page=100", token)
    file_names = [f["filename"] for f in files]
    additions = sum(f.get("additions", 0) for f in files)
    deletions = sum(f.get("deletions", 0) for f in files)

    linked = sorted({int(m) for m in ISSUE_REF.findall(pr.get("body") or "")})
    what_it_did = (pr.get("body") or pr["title"]).strip()[:4000]

    return {
        "pr_number": pr["number"],
        "title": pr["title"],
        "author": pr["user"]["login"],
        "merged_by": (pr.get("merged_by") or {}).get("login"),
        "lane": detect_lane(pr["head"]["ref"]),
        "branch": pr["head"]["ref"],
        "merge_sha": pr.get("merge_commit_sha"),
        "merged_at": int(__import__("datetime").datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00")).timestamp()),
        "risk_class": risk_class,
        "gate_status": verdict_status,
        "why_allowed": rationale,
        "what_it_did": what_it_did,
        "held_history": extract_held_history(timeline),
        "linked_issues": linked,
        "files": file_names,
        "additions": additions,
        "deletions": deletions,
        "lessons_ref": None,
    }


def post_payload(payload: dict, dry_run: bool, attempts: int = 3, backoff_seconds: int = 60) -> None:
    url = os.environ.get("MERGE_LEARNING_WEBHOOK_URL") or (
        (os.environ.get("BACKEND_URL") or "").rstrip("/") + "/api/merge-learning/webhook"
    )
    secret = os.environ.get("CI_WEBHOOK_SECRET", "")
    if dry_run:
        print("[dry-run] would POST to", url)
        print(json.dumps(payload, indent=2)[:3000])
        return
    if not url or not secret:
        print("error: MERGE_LEARNING_WEBHOOK_URL/BACKEND_URL and CI_WEBHOOK_SECRET must be set", file=sys.stderr)
        sys.exit(1)
    body = json.dumps(payload).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "X-CI-Webhook-Secret": secret},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                print(f"✅ merge-learning recorded: {resp.read().decode('utf-8')}")
                return
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            last_err = exc
            # বাংলা মন্তব্য: ব্যাকএন্ড রিডিপ্লয় উইন্ডোতে রুট/টেবিল এখনো না থাকলে রিট্রাই (issue #1944)
            if attempt < attempts:
                print(f"⚠️ attempt {attempt}/{attempts} failed ({exc}); retrying in {backoff_seconds}s...", file=sys.stderr)
                time.sleep(backoff_seconds)
    print(f"error: merge-learning recording failed after {attempts} attempts: {last_err}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr", type=int, required=True, help="merged PR number to record")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("GH_TOKEN")
    if not token:
        print("error: GH_TOKEN required", file=sys.stderr)
        sys.exit(1)

    pr = gh_api(f"/repos/{os.environ.get('GH_REPO', 'SaifulHaqueNiloy/supremeai')}/pulls/{args.pr}", token)
    if not pr.get("merged_at"):
        # Open (not-yet-merged) PR is a legitimate state for the workflow_dispatch
        # backfill/recovery arm: a bot or human may dispatch against a PR's head
        # sha before it merges. "Nothing to learn from yet" is informational, NOT
        # a failure — exit 0 so the run stays green and the dispatch can be retried
        # after the PR merges. The pull_request(closed+merged) event path still
        # only fires after a real merge, so no learning is silently skipped.
        print(f"PR #{args.pr} is not merged yet — nothing to record; exiting 0 (retry after merge).", file=sys.stderr)
        sys.exit(0)

    payload = build_payload(pr, token)
    post_payload(payload, args.dry_run)


if __name__ == "__main__":
    main()
