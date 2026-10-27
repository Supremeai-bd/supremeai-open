#!/usr/bin/env python3
"""Issue Revalidator — machine-readable live-issue gate (#3215).

নীতি (#3215 live-validation doctrine): "No live validation = no implementation."
একটি open issue কেবল তার অস্তিত্বের কারণে valid নয়। যেকোনো agent claim-এর
আগে এই gate চালাবে — রায় machine-readable state হিসেবে আসবে:

    LIVE        প্রমাণ এখনও বৈধ, কাজ এখনও দরকার → claim চলতে পারে
    STALE       প্রমাণ পুরনো — গভীর re-check স্বীকার (acknowledge) করলেই চলবে
    OBSOLETE    merged PR/ভিন্ন পরিবর্তন সমস্যাটা ইতিমধ্যে সমাধান করেছে
    DUPLICATE   একই fingerprint-বাহক আরেকটি active issue আছে
    BLOCKED     label/dependency/admin-gate দাবি আটকে দিচ্ছে
    REVALIDATE  পর্যাপ্ত প্রমাণ নেই বা check ব্যর্থ — fail-closed (U2: UNKNOWN≠LIVE)

Ground-truth mapping (#3215 §Ground-truth checks → machine enforcement):
  1. current main state          → STALE age check + acknowledge-স্বীকার
  2. recent commits/merged PRs   → merged cross-reference scan (OBSOLETE)
  3. relevant files/behavior     → agent deep re-check (STALE acknowledgment বাধ্য করে)
  4. related group/priority/seq  → group labels + issue_queue_manager.verify-claim
                                   (claim path-এ আগে থেকেই চলে — এখানে ফের-নয়)
  5. open PRs / existing fixes   → atomic_claim.sh has-pr/mirror guards (আগেই আছে)
  6. duplicate fingerprint       → issue_fingerprint.find_active_duplicate (reuse, U4)
  7. architecture intent         → STALE acknowledgment + OBSOLETE merged-ref
  8. evidence/acceptance         → empty body → REVALIDATE
  9. Admin Decision state        → gate:admin-approval label → BLOCKED

Exit codes: 0 = claim চলতে পারে (LIVE, বা STALE+acknowledged);
            1 = claim নিষিদ্ধ (বাকি সব state); 2 = usage error।

Usage:
    python scripts/agents/issue_revalidator.py --issue 3215 [--json]
    python scripts/agents/issue_revalidator.py --issue 3215 --acknowledge-stale
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.agents.issue_fingerprint import (  # noqa: E402
    extract_fingerprint,
    find_active_duplicate,
    find_recently_closed_duplicate,
)

REPO = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")

# Machine-readable states (#3215 §Revalidation states)
LIVE = "LIVE"
STALE = "STALE"
OBSOLETE = "OBSOLETE"
DUPLICATE = "DUPLICATE"
BLOCKED = "BLOCKED"
REVALIDATE = "REVALIDATE"

# বাংলা মন্তব্য: label → রায়ের ম্যাপ — প্রতিটি blocked-label আলাদা reason বহন করে।
BLOCKING_LABELS = {
    "status:in-progress": "already claimed — another agent owns this work",
    "status:claimed": "already claimed — another agent owns this work",
    "status:in-review": "work already in review — wait for its PR outcome",
    "blocked": "explicitly blocked",
    "state:blocked-by-upstream": "blocked by upstream dependency",
    "queue:hold": "queue hold active",
    "gate:admin-approval": "admin gate required — not claimable until approved",
}
OBSOLETE_LABEL = "status:complete"
LEDGER_LABEL = "type:ledger"  # #2928: perpetual dashboard — implementation checks N/A

STALE_DAYS_DEFAULT = 45  # env ISSUE_REVALIDATE_STALE_DAYS দিয়ে বদলানো যায়


@dataclass
class RevalidationVerdict:
    """গেটের চূড়ান্ত রায় — state + কারণ + কোন checks চলল তার প্রমাণ (U2)।"""

    state: str
    reasons: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    acknowledged_stale: bool = False

    @property
    def proceed(self) -> bool:
        if self.state == LIVE:
            return True
        return self.state == STALE and self.acknowledged_stale


def revalidate(ctx: dict) -> RevalidationVerdict:
    """Pure state machine — সব ground-truth ডেটা ctx-এ আসে (test-যোগ্য)।

    ctx keys:
      issue: {number, title, body, labels, createdAt, updatedAt}
      merged_refs: [{number, title}]  — merged PRs referencing this issue
      active_dup: {number, title} | None
      closed_dup: {number, closed_at} | None
      check_errors: [str]
    """
    issue = ctx["issue"]
    labels = [l["name"] for l in issue.get("labels", [])]
    number = issue["number"]
    reasons: list[str] = []
    evidence: dict = {
        "issue": number,
        "labels_checked": True,
        "merged_ref_checked": "merged_refs" in ctx,
        "fingerprint_checked": ("active_dup" in ctx) or ("closed_dup" in ctx),
        "age_checked": bool(issue.get("updatedAt")),
        "check_errors": list(ctx.get("check_errors", [])),
    }

    # ধাপ ০: type:ledger ড্যাশবোর্ড — চিরসবুজ সত্তা (#2928), implementation
    # যাচাই প্রযোজ্য নয়; দাবি-অযোগ্যতা claim স্তরে পৃথকভাবে নিয়ন্ত্রিত।
    if LEDGER_LABEL in labels:
        return RevalidationVerdict(
            state=LIVE,
            reasons=["perpetual dashboard issue — implementation revalidation N/A (#2928)"],
            evidence=evidence,
        )

    # ধাপ ১: BLOCKED labels (প্রথমে — claim-অযোগ্যতার সবচেয়ে সুস্পষ্ট প্রমাণ)।
    for lbl in labels:
        if lbl in BLOCKING_LABELS:
            reasons.append(f"label '{lbl}': {BLOCKING_LABELS[lbl]}")
    if reasons:
        return RevalidationVerdict(state=BLOCKED, reasons=reasons, evidence=evidence)

    # ধাপ ২: OBSOLETE — merged PR ইতিমধ্যে এই issue-কে reference করেছে।
    merged_refs = ctx.get("merged_refs") or []
    if merged_refs:
        ref_list = ", ".join(f"#{r['number']}" for r in merged_refs[:5])
        return RevalidationVerdict(
            state=OBSOLETE,
            reasons=[f"merged PR(s) already reference this issue: {ref_list} — verify whether the problem is already solved on main"],
            evidence={**evidence, "merged_refs": merged_refs[:5]},
        )

    if OBSOLETE_LABEL in labels:
        return RevalidationVerdict(
            state=OBSOLETE,
            reasons=["labeled status:complete while still open — confirm whether the problem was already solved"],
            evidence=evidence,
        )

    # ধাপ ৩: DUPLICATE — একই fingerprint-বাহক অন্য open issue।
    active_dup = ctx.get("active_dup")
    if active_dup and active_dup.get("number") != number:
        return RevalidationVerdict(
            state=DUPLICATE,
            reasons=[f"open issue #{active_dup['number']} carries the same fingerprint — link to it instead of claiming this copy"],
            evidence={**evidence, "duplicate_of": active_dup["number"]},
        )

    # ধাপ ৪: OBSOLETE — একই fingerprint-এর সাম্প্রতিক-বন্ধ issue (window-এ ভিতরে
    # বন্ধ = সমস্যা সমাধান/ইচ্ছাকৃত-বন্ধ; এটি বেঁচে থাকা কপি)।
    closed_dup = ctx.get("closed_dup")
    if closed_dup:
        return RevalidationVerdict(
            state=OBSOLETE,
            reasons=[f"same-fingerprint issue #{closed_dup['number']} was closed recently ({closed_dup.get('closed_at')}) — this copy is already covered"],
            evidence={**evidence, "closed_duplicate_of": closed_dup["number"]},
        )

    # ধাপ ৫: REVALIDATE — check ব্যর্থ বা পর্যাপ্ত প্রমাণ নেই (fail-closed, U2)।
    errors = list(ctx.get("check_errors", []))
    if errors:
        return RevalidationVerdict(
            state=REVALIDATE,
            reasons=[f"check failed: {e}" for e in errors],
            evidence=evidence,
        )
    if not (issue.get("body") or "").strip():
        return RevalidationVerdict(
            state=REVALIDATE,
            reasons=["issue body is empty — insufficient evidence to classify (fix the issue text first)"],
            evidence=evidence,
        )

    # ধাপ ৬: STALE — বয়স-প্রমাণ (§5: বয়স কখনো priority নয়; STALE মানে
    # "গভীর re-check ছাড়া দাবি নয়", স্বীকার করলে চলে — fleet অনাহারে নয়)।
    stale_days = int(os.environ.get("ISSUE_REVALIDATE_STALE_DAYS", str(STALE_DAYS_DEFAULT)))
    updated_raw = issue.get("updatedAt")
    if updated_raw:
        try:
            updated = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - updated).days
            evidence["last_updated_days_ago"] = age_days
            if age_days > stale_days:
                return RevalidationVerdict(
                    state=STALE,
                    reasons=[f"no issue activity for {age_days} days (threshold {stale_days}) — deep re-check against current main required before claiming"],
                    evidence=evidence,
                )
        except ValueError:
            return RevalidationVerdict(
                state=REVALIDATE,
                reasons=[f"unparsable updatedAt '{updated_raw}' — cannot verify freshness"],
                evidence=evidence,
            )

    # ধাপ ৭: সব check পাস → LIVE।
    reasons.append("open, unclaimed, unblocked; no merged reference, duplicate, or staleness signal")
    return RevalidationVerdict(state=LIVE, reasons=reasons, evidence=evidence)


# ── Ground-truth assembly (CLI) ────────────────────────────────────────────


def _gh(*args: str, timeout: int = 30) -> str:
    res = subprocess.run(
        ["gh", *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip()[:200] or f"gh exit {res.returncode}")
    return res.stdout


def build_context(issue_number: int) -> tuple[dict, list[str]]:
    """gh থেকে ground-truth জড়ো করে ctx বানায়; ব্যর্থ check REVALIDATE-এ যায়।"""
    errors: list[str] = []
    issue: dict = {}
    try:
        issue = json.loads(_gh(
            "issue", "view", str(issue_number), "--repo", REPO,
            "--json", "number,title,body,labels,createdAt,updatedAt,state",
        ))
    except (subprocess.SubprocessError, RuntimeError, ValueError) as exc:
        errors.append(f"issue fetch: {exc}")
        issue = {"number": issue_number, "title": "", "body": "", "labels": [],
                 "createdAt": "", "updatedAt": ""}

    merged_refs: list[dict] = []
    try:
        raw = _gh("pr", "list", "--repo", REPO, "--state", "merged",
                  "--search", f"\"#{issue_number}\" in:title,body",
                  "--limit", "10", "--json", "number,title,mergedAt")
        merged_refs = [p for p in json.loads(raw or "[]")
                       if f"#{issue_number}" in (p.get("title") or "")]
    except (subprocess.SubprocessError, RuntimeError, ValueError) as exc:
        errors.append(f"merged-PR scan: {exc}")

    active_dup = closed_dup = None
    body = issue.get("body") or ""
    fp = extract_fingerprint(body)
    if fp:
        try:
            active_dup = find_active_duplicate(fp)
        except Exception as exc:  # noqa: BLE001 — fail-closed-এ যাবে, crash নয়
            errors.append(f"duplicate scan: {exc}")
        try:
            closed_dup = find_recently_closed_duplicate(fp)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"closed-duplicate scan: {exc}")

    return {
        "issue": issue,
        "merged_refs": merged_refs,
        "active_dup": active_dup,
        "closed_dup": closed_dup,
        "check_errors": errors,
    }, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live-issue revalidation gate (#3215)")
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--acknowledge-stale", action="store_true",
                        help="STALE-এর জন্য গভীর re-check সম্পন্ন হয়েছে — স্বীকার করে এগোও")
    args = parser.parse_args(argv)

    ctx, errors = build_context(args.issue)
    verdict = revalidate(ctx)
    if args.acknowledge_stale and verdict.state == STALE:
        verdict.acknowledged_stale = True

    payload = {
        "issue": args.issue,
        "state": verdict.state,
        "proceed": verdict.proceed,
        "reasons": verdict.reasons,
        "evidence": verdict.evidence,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        icon = {"LIVE": "✅", "STALE": "⏳", "OBSOLETE": "🪦", "DUPLICATE": "🧬",
                "BLOCKED": "🚫", "REVALIDATE": "🛑"}.get(verdict.state, "❔")
        print(f"{icon} Revalidation #{args.issue}: {verdict.state} "
              f"({'proceed' if verdict.proceed else 'do-not-claim'})")
        for r in verdict.reasons:
            print(f"   - {r}")

    return 0 if verdict.proceed else 1


if __name__ == "__main__":
    raise SystemExit(main())
