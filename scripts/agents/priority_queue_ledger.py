#!/usr/bin/env python3
"""Priority Queue Ledger — the DYNAMIC auto-ranked claim order.
================================================================
Implements the founder directive (2026-09-27):

    "dynamic kora jay kina... jemon 1st close howar por 2nd auto
     1st hoa jabe"  — when #1 closes, #2 automatically becomes #1.

How the dynamic behavior works
------------------------------
* `.github/workflows/priority-queue.yml` fires on EVERY issue event
  (opened / closed / reopened / labeled / unlabeled) plus a 6-hourly
  drift sweep and manual dispatch.
* This script then re-computes the full claim queue from live labels
  (ladder priority DESC → oldest first, missing label = P3 — exactly
  `docs/agents/ISSUE_PRIORITY_POLICY.md` and `next_claimable.sh`).
* The ranked queue is written to ONE ledger issue (find-by-marker,
  create-if-missing). Body edit = the live queue; no comment spam.
* When the overall #1 CHANGES because the previous #1 was closed or
  claimed, a single notification comment is posted on the NEW #1
  ("you are now the head of the queue") and on the ledger.
  → Close #1 today, #2 is publicly #1 seconds later. Automatic.

Usage
-----
    python scripts/agents/priority_queue_ledger.py            # live run
    python scripts/agents/priority_queue_ledger.py --dry-run  # print only
    python scripts/agents/priority_queue_ledger.py --limit 10 # top-N rows

    GH_TOKEN must be set (or an authenticated gh CLI available).

Companions
----------
* `docs/agents/ISSUE_PRIORITY_POLICY.md`  — the policy this enforces
* `scripts/agents/next_claimable.sh`      — per-lane CLI view
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- constants ---------------------------------------------------------------

LEDGER_TITLE = "🎯 [PRIORITY-QUEUE-LEDGER] Auto-ranked claim order — live queue"
LEDGER_BODY_MARKER = "<!-- SUPREMEAI_PRIORITY_QUEUE_LEDGER v1 -->"
TOP1_MARKER_RE = re.compile(r"<!-- TOP1:OVERALL:(\d+) -->")
# NOTE: quote ONLY the phrase — the in:title qualifier must stay OUTSIDE the
# quotes, otherwise gh searches for the literal string including the qualifier
# and the find-or-create loop creates duplicate ledgers (found the hard way).
LEDGER_SEARCH = '"PRIORITY-QUEUE-LEDGER" in:title'

RANK: Dict[str, int] = {"P0-critical": 0, "P1-high": 1, "P2-medium": 2, "P3-low": 3}
RANK_DEFAULT = "P3-low"

# lanes rendered in a fixed order first (policy lanes), then any other
# handoff:<lane> labels discovered dynamically
KNOWN_LANES = ["coder", "ci", "pr-helper", "platform", "planner", "browser", "super"]


# --- gh helpers --------------------------------------------------------------


def gh_bin() -> str:
    for candidate in (os.environ.get("GH_BIN"), "gh", os.path.expanduser("~/bin/gh")):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    found = subprocess.run(["which", "gh"], capture_output=True, text=True).stdout.strip()
    if found:
        return found
    print("error: gh CLI not found (install github cli or set GH_BIN)", file=sys.stderr)
    sys.exit(1)


GH = gh_bin()


def gh_run(args: List[str], check: bool = True) -> str:
    env = dict(os.environ)
    env.setdefault("GH_REPO", "SaifulHaqueNiloy/supremeai")
    res = subprocess.run([GH] + args, capture_output=True, text=True, env=env, timeout=120)
    if check and res.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout


# --- queue computation -------------------------------------------------------


def priority_of(labels: List[Dict[str, Any]]) -> str:
    names = [l["name"] for l in labels]
    present = [n for n in names if n in RANK]
    return min(present, key=lambda n: RANK[n]) if present else RANK_DEFAULT


def fetch_unclaimed() -> List[Dict[str, Any]]:
    """The claimable universe: open issues NOT actively worked and not ledgers.

    `status:planned` AND `status:unclaimed` both mean "awaiting a claim"
    (auditor-filed work carries planned; auto-filed blockers carry unclaimed).
    Only `status:in-progress` (claimed/being worked) and `type:ledger`
    (maintenance dashboards like this one) are excluded.
    """
    out = gh_run([
        "issue", "list", "--state", "open", "--limit", "400",
        "--json", "number,title,labels,createdAt",
    ])
    issues = json.loads(out or "[]")
    result = []
    for i in issues:
        names = [l["name"] for l in i["labels"]]
        if "status:in-progress" in names or "type:ledger" in names:
            continue
        # the ledger itself is never part of the queue
        if "PRIORITY-QUEUE-LEDGER" in i.get("title", ""):
            continue
        result.append(i)
    return result


def lane_of(labels: List[Dict[str, Any]]) -> str:
    for l in labels:
        if l["name"].startswith("handoff:"):
            return l["name"].split(":", 1)[1]
    return "generic"


def build_queue(issues: List[Dict[str, Any]]) -> List[Tuple[int, str, Dict[str, Any]]]:
    """(rank, createdAt, issue) — priority DESC, then FIFO within a priority."""
    queue = [(RANK[priority_of(i["labels"])], i["createdAt"], i) for i in issues]
    queue.sort(key=lambda row: (row[0], row[1]))
    return queue


# --- rendering ---------------------------------------------------------------


def render_row(issue: Dict[str, Any], rank: int) -> str:
    p = priority_of(issue["labels"])
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(issue["createdAt"].replace("Z", "+00:00"))).days
    return f"| #{issue['number']} | `{p}` | {age}d | {issue['title'][:90]} |"


def render_body(queue: List[Tuple[int, str, Dict[str, Any]]], limit: int, trigger: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    counts = {p: 0 for p in RANK}
    for rank, _, issue in queue:
        counts[priority_of(issue["labels"])] += 1

    lines: List[str] = [
        LEDGER_BODY_MARKER,
        f"# {LEDGER_TITLE.split('] ', 1)[-1]}",
        "",
        "> **Auto-maintained.** `.github/workflows/priority-queue.yml` re-ranks this queue on every issue",
        "> event — when the #1 issue closes, #2 automatically becomes #1 (founder directive 2026-09-27).",
        "> Claim order: **priority ladder DESC** (`P0-critical → P1-high → P2-medium → P3-low`,",
        "> no label = P3) then **oldest first** — [`ISSUE_PRIORITY_POLICY.md`](../../docs/agents/ISSUE_PRIORITY_POLICY.md).",
        "",
        f"**Last update:** {now} · **trigger:** `{trigger}` · **unclaimed total:** {len(queue)} "
        f"(P0: {counts['P0-critical']} · P1: {counts['P1-high']} · P2: {counts['P2-medium']} · P3: {counts['P3-low']})",
        "",
        "## 🥇 Overall — claim from the top",
        "",
        "| Issue | Priority | Age | Title |",
        "|---|---|---|---|",
    ]
    for rank, _, issue in queue[:limit]:
        lines.append(render_row(issue, rank))
    if not queue:
        lines.append("| — | — | — | _No unclaimed issues — lanes, verify with the auditor before idling (GOLDEN_RULES 1)._ |")

    # per-lane sections
    lanes: Dict[str, List[Dict[str, Any]]] = {}
    for _, _, issue in queue:
        lanes.setdefault(lane_of(issue["labels"]), []).append(issue)
    ordered_lanes = [l for l in KNOWN_LANES if l in lanes] + sorted(
        l for l in lanes if l not in KNOWN_LANES and l != "generic"
    )
    if "generic" in lanes:
        ordered_lanes.append("generic")

    lines += ["", "## Per-lane top (handoff:<lane> → explicit; generic → any lane may claim)", ""]
    for lane in ordered_lanes:
        lane_queue = build_queue(lanes[lane])
        lines += [f"### `{lane}` — {len(lanes[lane])} unclaimed", "",
                  "| Issue | Priority | Age | Title |", "|---|---|---|---|"]
        for rank, _, issue in lane_queue[:5]:
            lines.append(render_row(issue, rank))
        lines.append("")

    lines += [
        "---",
        "_Lanes: run `./scripts/agents/next_claimable.sh <lane>` for the full list + ready-to-paste claim command._",
        "_Auditor stewardship: priority changes need a reason comment on the issue (policy §3)._",
        "",
    ]
    if queue:
        lines.append(f"<!-- TOP1:OVERALL:{queue[0][2]['number']} -->")
    else:
        lines.append("<!-- TOP1:OVERALL:0 -->")
    return "\n".join(lines)


# --- ledger issue management --------------------------------------------------


def find_ledger() -> Optional[int]:
    out = gh_run([
        "issue", "list", "--state", "open", "--search", LEDGER_SEARCH,
        "--json", "number,title",
    ], check=False)
    try:
        matches = [
            int(issue["number"]) for issue in json.loads(out or "[]")
            if "PRIORITY-QUEUE-LEDGER" in issue.get("title", "")
        ]
        if matches:
            # deterministic: the OLDEST ledger is canonical (a stray duplicate
            # from an indexing-lag race must never hijack the ledger identity)
            return min(matches)
    except json.JSONDecodeError:
        pass
    return None


def create_ledger(body: str) -> int:
    out = gh_run([
        "issue", "create", "--title", LEDGER_TITLE, "--body", body,
        "--label", "type:ledger",
    ], check=False)
    m = re.search(r"/issues/(\d+)", out)
    if not m:
        raise RuntimeError(f"could not parse ledger issue number from: {out}")
    return int(m.group(1))


def ledger_body(num: int) -> str:
    out = gh_run(["issue", "view", str(num), "--json", "body"])
    return json.loads(out)["body"] or ""


def issue_state(num: int) -> str:
    out = gh_run(["issue", "view", str(num), "--json", "state"], check=False)
    try:
        return json.loads(out)["state"]
    except Exception:
        return "unknown"


# --- main ---------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Priority Queue Ledger (dynamic claim order)")
    ap.add_argument("--limit", type=int, default=10, help="overall top-N rows (default 10)")
    ap.add_argument("--dry-run", action="store_true", help="print the body, write nothing")
    args = ap.parse_args()

    trigger = os.environ.get("LEDGER_TRIGGER", "manual")
    issues = fetch_unclaimed()
    queue = build_queue(issues)

    if not queue:
        print("No unclaimed issues — ledger will render an empty (healthy) queue.")

    body = render_body(queue, args.limit, trigger)
    top1 = int(queue[0][2]["number"]) if queue else 0
    top1_title = queue[0][2]["title"] if queue else ""
    top1_prio = priority_of(queue[0][2]["labels"]) if queue else "-"

    if args.dry_run:
        print(body)
        print(f"\n[dry-run] top1=#{top1} — nothing written.")
        return 0

    num = find_ledger()
    created = False
    prev_body: str = ""
    if num is None:
        num = create_ledger(body)
        created = True
        print(f"ledger created: #{num}")
    else:
        # IMPORTANT: read the PREVIOUS body BEFORE overwriting it — the old
        # TOP1 marker is what the promotion logic compares against.
        prev_body = ledger_body(num)
        gh_run(["issue", "edit", str(num), "--body", body])
        print(f"ledger updated: #{num}")

    # --- dynamic promotion notification (the founder's ask) --------------------
    # Comment ONLY when the head changed because the previous head left the
    # queue (closed or claimed) — not on mere re-ranks (no ping-pong spam).
    if not created and top1:
        prev_match = TOP1_MARKER_RE.search(prev_body)
        if prev_match:
            prev_top1 = int(prev_match.group(1))
            if prev_top1 != top1:
                # gh returns UPPERCASE states ("CLOSED"/"OPEN") — compare
                # case-insensitively or the promotion never fires.
                prev_state = issue_state(prev_top1).lower()
                if prev_state == "closed":
                    note = (
                        f"🔄 **Queue re-ranked — new #1: #{top1}** (`{top1_prio}`) — {top1_title[:100]}\n"
                        f"Previous #1 #{prev_top1} **closed** → সর্বোচ্চ প্রায়োরিটির unclaimed issue এখন "
                        f"**#{top1}** — lanes, এটি থেকে claim করো (`next_claimable.sh <lane>`)."
                    )
                    gh_run(["issue", "comment", str(num), "--body", note])
                    gh_run(["issue", "comment", str(top1), "--body", (
                        f"🥇 **Head of the queue** — previous #1 #{prev_top1} বন্ধ হওয়ায় এই issue এখন "
                        f"সর্বোচ্চ প্রায়োরিটির unclaimed issue ({top1_prio})। "
                        f"Live queue: [Priority Queue Ledger #{num}](../issues/{num})।"
                    )])
                    print(f"promotion comment posted: #{top1} is the new #1 (prev #{prev_top1} closed)")
                else:
                    print(f"head changed #{prev_top1}→#{top1} but prev still open — no promotion comment")

    print(f"done: {len(issues)} unclaimed issues ranked; ledger #{num}; top1=#{top1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
