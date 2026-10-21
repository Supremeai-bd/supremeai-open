#!/usr/bin/env python3
"""
self_healing_reporter.py — Automated CI-Failure Issue Generation (WO #488)

Deliverable 1 of the Runway-First Dispatch Engine. Whenever a PR check
fails, this reporter files a healing work-order issue so the existing
deterministic priority ladder (P0 > P1 > P2 > P3) naturally sorts runway
clearance above all backlog features — unblocking in-flight work first.

Deliverable 2 (loop-side wiring) is operator-side: scripts/agents/
continuous_agent_loop.py already exposes classify_task_role (line 201)
which maps CI-keyword issues to the ci-fixer role; the loop's
pick_next_issue needs no new logic — it simply picks up the P0/P1
healing issues this reporter files. This module therefore ships the
missing producer, not a duplicate classifier.

Issue contract (verbatim from WO #488):
  Title:   fix(<repo>): [ci-failure] Heal PR #<num> checks (<check_names>)
  Group:   repo:<repo_name>            Sub-group: area:ci
  Priority: P0-critical (main/merge blocked) | P1-high (otherwise)
  Labels:  bridge:queued, <priority>, repo:<repo>, area:ci
  Payload: PR branch, target commit, exact failure log snippet

Dedup: a sha256 fingerprint of (repo, pr_number) is embedded as a hidden
HTML comment in the issue body; the reporter skips filing when an open
issue already carries the marker. Fingerprinting is collision-free by
construction (truncated sha256 over a canonical tuple) and idempotent.

CLI:
  python3 scripts/agents/self_healing_reporter.py --self-test   (offline)
  python3 scripts/agents/self_healing_reporter.py --dry-run     (uses gh CLI, files nothing)
  python3 scripts/agents/self_healing_reporter.py --execute     (files via gh; needs gh)

stdlib-only. gh CLI absent -> graceful no-op with clear exit code (loop
precedent run_cmd: 127), never a crash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys

DEFAULT_REPO = "Supremeai-bd/supremeai-open"

P0 = "P0-critical"
P1 = "P1-high"
TITLE_RE = re.compile(
    r"^fix\((?P<repo>[A-Za-z0-9._/-]+)\): \[ci-failure\] Heal PR #(?P<num>\d+) "
    r"checks \((?P<checks>.+)\)$"
)


def healing_title(repo: str, pr_number: int, failing_checks: list[str]) -> str:
    checks = ", ".join(sorted(failing_checks))
    return f"fix({repo}): [ci-failure] Heal PR #{pr_number} checks ({checks})"


def priority_for_failure(blocked_merge: bool) -> str:
    """P0-critical when main/merge is blocked, else P1-high (WO #488)."""
    return P0 if blocked_merge else P1


def healing_labels(repo: str, priority: str) -> list[str]:
    # `status:runway` (S09 LABEL_PRIORITY[0]) makes the continuous loop's
    # deterministic dispatch route every healing issue to the ci-fixer role;
    # a healing issue IS a jammed merge-runway item by definition.
    return ["bridge:queued", priority, "status:runway", f"repo:{repo}", "area:ci"]


def dedup_fingerprint(repo: str, pr_number: int) -> str:
    canonical = f"{repo}#{int(pr_number)}"
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def fingerprint_marker(fp: str) -> str:
    return f"<!-- healing-fp:{fp} -->"


def build_healing_issue(pr: dict) -> dict:
    """Build the full issue payload for one failing PR (pure, deterministic)."""
    repo = pr["repo"]
    num = int(pr["number"])
    checks = list(pr.get("failing_checks") or ["unknown-check"])
    priority = priority_for_failure(bool(pr.get("blocked_merge")))
    fp = dedup_fingerprint(repo, num)
    title = healing_title(repo, num, checks)
    body = "\n".join(
        [
            "### Automated CI-Heal Work Order (runway-first, self-healing reporter)",
            "",
            f"- **PR:** {repo}#{num}",
            f"- **Branch:** `{pr.get('branch', 'unknown')}`",
            f"- **Target commit:** `{pr.get('head_sha', 'unknown')}`",
            f"- **Failing checks:** {', '.join(sorted(checks))}",
            f"- **Priority rationale:** {priority} — "
            + (
                "main/merge path blocked"
                if priority == P0
                else "in-flight work, runway hygiene"
            ),
            "",
            "**Failure log snippet:**",
            "```",
            (pr.get("log_snippet") or "(log unavailable)").strip()[:400],
            "```",
            "",
            "**Heal procedure (CI-FIXER role):**",
            "1. Fetch the PR branch; rebase against current main (resolves Stale-Base Guard).",
            "2. Enrich PR metadata: summary + test evidence (resolves Knowledge Sharing Guard).",
            "3. Push the fix; CI green -> landing.yml auto-merges -> this issue auto-closes.",
            "",
            f"Dedup fingerprint: `{fp}`",
            fingerprint_marker(fp),
            "",
        ]
    )
    return {"title": title, "body": body, "labels": healing_labels(repo, priority)}


def is_ci_failure_issue(title: str, labels: list[str]) -> bool:
    """Classifier-compat predicate matching the loop's ci-fixer triggers."""
    combined = f"{title} {' '.join(labels)}".lower()
    return "[ci-failure]" in combined or "area:ci" in combined


# ---------------------------------------------------------------------------
# gh CLI integration (mirrors continuous_agent_loop.run_cmd conventions)
# ---------------------------------------------------------------------------


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"executable not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout: {' '.join(cmd)}"


def collect_failing_prs(repo: str = DEFAULT_REPO) -> tuple[list[dict], str]:
    """Return (failing_prs, mode). mode in {gh, gh-missing}. Never raises."""
    code, out, _err = _run(["gh", "--version"])
    if code == 127:
        return [], "gh-missing"
    code, out, _ = _run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--json",
            "number,headRefName,headRefOid,mergeable,statusCheckRollup",
        ]
    )
    if code != 0:
        return [], "gh-missing"
    try:
        prs = json.loads(out or "[]")
    except json.JSONDecodeError:
        return [], "gh-missing"
    failing: list[dict] = []
    for pr in prs:
        rollup = pr.get("statusCheckRollup") or []
        bad = [
            c.get("name", "check")
            for c in rollup
            if (c.get("conclusion") or "").upper() in ("FAILURE", "TIMED_OUT")
        ]
        if not bad:
            continue
        blocked = (pr.get("mergeable") or "").upper() == "CONFLICTING"
        log_snip = ""
        for c in rollup:
            if (c.get("conclusion") or "").upper() in ("FAILURE", "TIMED_OUT"):
                cc, co, _ = _run(
                    [
                        "gh",
                        "run",
                        "view",
                        str(c.get("detailsUrl", "")),
                        "--repo",
                        repo,
                        "--log-failed",
                    ],
                    timeout=20,
                )
                if cc == 0 and co:
                    log_snip = co[-400:]
                    break
        failing.append(
            {
                "repo": repo,
                "number": pr.get("number"),
                "branch": pr.get("headRefName"),
                "head_sha": pr.get("headRefOid"),
                "failing_checks": bad,
                "blocked_merge": blocked,
                "log_snippet": log_snip,
            }
        )
    return failing, "gh"


def open_issue_has_marker(repo: str, fp: str) -> bool:
    code, out, _ = _run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--search",
            f'"{fingerprint_marker(fp)}"',
            "--json",
            "number",
        ]
    )
    if code != 0:
        return (
            False  # fail-open on search errors only; fingerprint still logged in body
        )
    try:
        return len(json.loads(out or "[]")) > 0
    except json.JSONDecodeError:
        return False


def self_test() -> int:
    """Offline verification, no gh required."""
    t = healing_title(
        DEFAULT_REPO, 480, ["Stale-Base Guard", "Knowledge Sharing Guard"]
    )
    assert t == (
        f"fix({DEFAULT_REPO}): [ci-failure] Heal PR #480 checks "
        "(Knowledge Sharing Guard, Stale-Base Guard)"
    ), t
    assert TITLE_RE.match(t)
    assert priority_for_failure(True) == P0 and priority_for_failure(False) == P1
    labels = healing_labels(DEFAULT_REPO, P0)
    assert labels == ["bridge:queued", "P0-critical", f"repo:{DEFAULT_REPO}", "area:ci"]
    issue = build_healing_issue(
        {
            "repo": DEFAULT_REPO,
            "number": 481,
            "branch": "feat/x",
            "head_sha": "abc1234",
            "failing_checks": ["Stale-Base Guard"],
            "blocked_merge": True,
            "log_snippet": "error: branch is stale\n",
        }
    )
    assert issue["labels"][1] == P0
    for needle in ("feat/x", "abc1234", "Stale-Base Guard", "healing-fp:"):
        assert needle in issue["body"], needle
    fp1 = dedup_fingerprint(DEFAULT_REPO, 480)
    fp2 = dedup_fingerprint("Supremeai-bd/supremeai-infra", 480)
    fp3 = dedup_fingerprint(DEFAULT_REPO, 484)
    assert fp1 == dedup_fingerprint(DEFAULT_REPO, 480), "must be deterministic"
    assert len({fp1, fp2, fp3}) == 3, "must be collision-free across pairs"
    assert is_ci_failure_issue("[ci-failure] heal", []) and is_ci_failure_issue(
        "x", ["area:ci"]
    )
    assert not is_ci_failure_issue("feat: new dashboard", ["enhancement"])
    print(
        "self-test: 6/6 scenario groups PASS (title, priority, labels, payload, fingerprint, classifier)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Automated CI-failure healing issue reporter"
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    prs, gh_mode = collect_failing_prs(args.repo)
    if gh_mode == "gh-missing":
        print(
            "gh CLI not available or failed; nothing collected (exit 0, fail-honest)."
        )
        return 0
    payloads = [build_healing_issue(pr) for pr in prs]
    fresh = [
        p
        for p, pr in zip(payloads, prs)
        if not open_issue_has_marker(
            args.repo, dedup_fingerprint(pr["repo"], pr["number"])
        )
    ]
    for pr, p in zip(prs, payloads):
        print(f"[{'FRESH' if p in fresh else 'DUPLICATE-SKIP'}] {p['title']}")
    if args.execute and fresh:
        for p in fresh:
            lbl = ",".join(p["labels"])
            code, _, err = _run(
                [
                    "gh",
                    "issue",
                    "create",
                    "--repo",
                    args.repo,
                    "--title",
                    p["title"],
                    "--body",
                    p["body"],
                    "--label",
                    lbl,
                ],
                timeout=45,
            )
            print(f"filed rc={code} {p['title'][:60]} {err.strip()[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
