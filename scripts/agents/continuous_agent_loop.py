#!/usr/bin/env python3
"""SupremeAI — Minimal Autonomous Agent Loop (Unified Rules & Roles Dispatcher).

CONTRACT_VERSION = "agent-loop-contract/1"

Traffic-police logic:
1. Always display the 5 Universal Invariant Pillars (Common Rules).
2. If unclaimed issues exist -> Unlimited Solvers allowed: prompt agent with solver mandate & auto-dispatch.
3. If no open issues exist -> Reset/zero cadence timers so scheduled roles can run immediately.
4. Scheduled roles -> Exactly 1 agent at a time per role (active lock / immediate state advance).
5. Problematic/stuck issues -> Agents autonomously decide and handle them.
6. Single-dispatch clean execution: external runner/scheduler drives loop cadence.
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, threading, time, urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "agent-loop-contract/1"
UPSTREAM_REPO = "Supremeai-bd/supremeai-open"
REPO_ROOT = Path(__file__).resolve().parents[2]
CADENCE_FILE = REPO_ROOT / "scripts" / "agents" / "agent_cadence.json"
STATE_FILE = REPO_ROOT / "scripts" / "agents" / "agent_cadence_state.json"
ISSUE_LEASE_FILE = REPO_ROOT / "scripts" / "agents" / "dispatched_issues_state.json"
# #57 SSOT: the lease length is owned by scripts/agents/claim_thresholds.py.
# That module was landed to end the release<->re-claim flip-flop war, but the
# loop kept its own hardcoded copy — the exact dual-SSOT drift #57 documents.
# Support both direct repo-root imports (scripts.agents.claim_thresholds) and
# same-dir execution (claim_thresholds).
try:
    from scripts.agents.claim_thresholds import ORPHAN_RELEASE_MINUTES  # noqa: E402
except ImportError:
    from claim_thresholds import ORPHAN_RELEASE_MINUTES  # noqa: E402

ISSUE_LEASE_SECONDS = ORPHAN_RELEASE_MINUTES * 60.0  # 30-minute autonomous lease (Rule 9 parity without GitHub claim friction)

RULE_FRESHNESS_FILES = (
    "AGENTS.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
)
# বাংলা: AGENT_RULES.md আর নেই — PR #1526 নিজেই ফাইলটি মুছে দিয়েছে (Single Door
# SSOT এখন AGENTS.md)। তালিকায় মুছে-যাওয়া ফাইল রাখলে step_2_rules()
# fresh main-এ সবসময় exit 1 দেয় (missing_local + rev-parse দুই জায়গাতেই fail) —
# নিজের মুছে-ফেলা ফাইলকে পূর্বশর্ত করে রাখা লুপের আত্ম-পরাজয়।

OFFLINE_ENV_VARS = (
    "SUPREMEAI_OFFLINE",
    "AGENT_LOOP_OFFLINE",
    "CI_OFFLINE",
)

# বাংলা: board-exclusion এখন একটাই SSOT। আগে pick_next_issue()-এ এক সেট
# (state:seq-hold, mirror:private আছে, anchor-hub/admin-only নেই) আর main()-এ
# অন্য সেট (anchor-hub, admin-only আছে, state:seq-hold/mirror:private নেই)
# ছিল — একই ধারণার দুই SSOT drift করে এক পথে claimable, অন্য পথে নয়।
# বাংলা: bridge-plane স্টেট লেবেল — tower নিজেই WO-তে in-flight/terminal মার্কার
# স্ট্যাম্প করে: pr-opened/queued/in-gates = PR পথে চলছে; rejected/idempotent-noop =
# terminal (rescue plane scripts/ci/rejected_wo_rescue.py rejected-comment আলাদাভাবে
# triage করে — এই সেট তাকে স্পর্শ করে না)। verdict-plane blackout (#2100) চলাকালে
# landed WO-ও bridge:queued-ই থাকে (verdict history খালি) — এই ৫টা লেবেল ছাড়া
# pick_next_issue landed/in-flight কাজকে পুনঃদাবিযোগ্য ভাবত; live প্রমাণ 2026-10-28:
# খোলা বোর্ডের ২৭টা non-excluded সারির ২০টাই bridge:queued মিরর (landed #2071/#2056
# সহ), ফলে drained board-এ সত্যিকারের নতুন কাজের (#2103) আগে ভুলভাবে বেছে নেওয়া হত।
EXCLUDED_LABELS = frozenset({
    "status:claimed",
    "status:in-progress",
    "state:seq-hold",
    "blocked-by-upstream",
    "mirror:private",
    "anchor-hub",
    "admin-only",
    "bridge:pr-opened",
    "bridge:queued",
    "bridge:in-gates",
    "bridge:rejected",
    "bridge:idempotent-noop",
})

DEFAULT_GROUP = "core"
VALID_TASK_TYPES = frozenset({"FEAT", "FIX", "DOCS", "STYLE", "REFACTOR", "TEST", "CHORE", "PERF", "OPS", "AUDIT", "SCOUT", "IMPLEMENT"})
VALID_PRIORITIES = frozenset({"P0", "P1", "P2", "P3", "P4"})
VALID_ADMIN_GATE_STATUSES = frozenset({"NOT_REQUIRED", "PENDING", "APPROVED", "REJECTED"})
VALID_GROUPS = frozenset({"core", "gateway", "studio", "vscode", "browser", "docs", "infra", "marketplace", "federation"})

def build_task_contract(
    task_id: str,
    issue: str | int | None = None,
    task_type: str = "IMPLEMENT",
    group: str = DEFAULT_GROUP,
    priority: str = "P2",
    objective: str = "",
    touching_files: list[str] | None = None,
    forbidden_paths: list[str] | None = None,
    dependencies: list[str] | None = None,
    predecessor: str | int | None = None,
    admin_gate_required: bool = False,
    admin_gate_status: str = "NOT_REQUIRED",
    role_policy: str = "contributor",
    required_evidence: list[str] | None = None,
    verification: list[str] | None = None,
    acceptance: list[str] | None = None,
    stop_conditions: list[str] | None = None,
    output_format: str = "structured",
) -> dict[str, Any]:
    task_type_upper = task_type.upper()
    if task_type_upper not in VALID_TASK_TYPES:
        raise ValueError(f"Invalid task_type: '{task_type}'")
    priority_upper = priority.upper()
    if priority_upper not in VALID_PRIORITIES:
        raise ValueError(f"Invalid priority: '{priority}'")
    gate_status_upper = admin_gate_status.upper()
    if gate_status_upper not in VALID_ADMIN_GATE_STATUSES:
        raise ValueError(f"Invalid admin_gate_status: '{admin_gate_status}'")
    if group not in VALID_GROUPS:
        raise ValueError(f"Invalid group: '{group}'")
    # বাংলা: আগের সংস্করণ touching_files/forbidden_paths/admin_gate_status-সহ ১২টি
    # প্যারামিটার ভ্যালিডেট করেও নীরবে ফেলে দিত — চুক্তি নিজের স্কিমাটিই মিথ্যা বলত
    # (admin_gate গভর্নেন্স-ডেটা হারিয়ে যেত)। এখন ভ্যালিডেট-করা প্রতিটি ফিল্ড
    # এমিট হয় (AGENT_LOOP_SPEC.md §2 envelope sections-এর সাথে সামঞ্জস্য)।
    # CI শুধু version==1 ও invalid task_type ValueError দাবি করে — দুটোই অক্ষত।
    return {
        "task_contract": {
            "version": 1,
            "task_id": str(task_id),
            "issue": issue,
            "task_type": task_type_upper,
            "group": group,
            "priority": priority_upper,
            "objective": objective,
            "touching_files": list(touching_files or []),
            "forbidden_paths": list(forbidden_paths or []),
            "dependencies": list(dependencies or []),
            "predecessor": predecessor,
            "admin_gate": {
                "required": bool(admin_gate_required),
                "status": gate_status_upper,
            },
            "role_policy": role_policy,
            "required_evidence": list(required_evidence or []),
            "verification": list(verification or []),
            "acceptance": list(acceptance or []),
            "stop_conditions": list(stop_conditions or []),
            "output_format": output_format,
        }
    }

def label_names(item: dict[str, Any]) -> list[str]:
    labels = item.get("labels")
    if not isinstance(labels, list):
        return []
    return [str(l.get("name", "")).lower() for l in labels if isinstance(l, dict)]

def has_open_p0_blocker(issues: list[dict[str, Any]]) -> bool:
    """Check if there is any open, actionable P0-critical architectural issue.

    বাংলা: P0 Drainage Invariant (Rule 5) কেবল অ্যাকশনেবল P0-তে প্রযোজ্য।
    blocked-by-upstream লেবেলযুক্ত P0 এই লেনের কেউই দাবি করতে পারে না
    (pick_next_issue()-এর EXCLUDED_LABELS-এও আছে) — এমন চিরকাল-খোলা P0
    has_open_p0_blocker()-ও ধরে রাখলে cadence রোল অনির্দিষ্টকালের জন্য
    অবরুদ্ধ হয় (starvation): কেউ সমাধান করতে পারবে না, আবার অন্য সব রুটিন
    কাজও বন্ধ থাকবে। তাই এই লেনে-অ্যাকশনেবল-নয় এমন P0 ব্লকার-গণনা থেকে বাদ;
    status:claimed P0 আগের মতোই ব্লক করবে (অন্য রানার সক্রিয়ভাবে কাজ করছে —
    নিয়ম ৫-এর উদ্দিষ্ট আচরণ)।
    """
    unactionable_in_lane = frozenset({"blocked-by-upstream", "admin-only", "mirror:private"})
    # বাংলা: admin-only / mirror:private P0-ও একই starvation শ্রেণি —
    # pick_next_issue()-এর EXCLUDED_LABELS এই দুই লেবেলযুক্ত সারি কখনোই pick করে
    # না, অর্থাৎ এই লেনের কোনো এজেন্ট সেগুলো চিরকালের জন্য কাজ করতে পারবে না;
    # অথচ ব্লকার-গণনা সেগুলোকে গুনলে cadence রোল চিরকাল থেমে থাকে — একই SSOT-এর
    # দুই ভোক্তায় দুই আচরণ, ঠিক এই ফাইলের board-exclusion কমেন্টে নথিভুক্ত
    # dual-SSOT drift-শ্রেণি। তাই ব্লকার-গণনাও একই লেন-অ্যাকশনেবিলিটি SSOT মানে।
    # বৈপরীত্যে status:claimed সাময়িক (claim TTL শেষে পুনঃদাবিযোগ্য), লেন-সীমা
    # লেবেলগুলো স্থায়ী — তাই claimed P0 আগের মতোই ব্লক করবে (নিয়ম ৫-এর অন্তর্গত)।
    for item in issues:
        if not isinstance(item, dict):
            continue
        names = label_names(item)
        if unactionable_in_lane & set(names):
            continue
        if any(name == "p0" or name.startswith("p0-") or name.startswith("p0 ") for name in names):
            return True
    return False

# #2794 fix (1) — live-claim pre-verify depth: only the top-N sorted candidates
# are probed against the feedback plane. Bounded so the dispatch hot path stays
# O(N) tower reads (<=5 small bridge_read_feedback calls, each degrade-safe);
# beyond-window rows are NOT dispatched blind — an exhausted window returns
# None with an honest note instead (see pick_next_issue).
FEEDBACK_PREVERIFY_TOPN = 5

# #3050: stale-incident demotion. A CI-failure incident row whose referenced run
# is superseded by this many green main runs of the SAME workflow (with zero
# newer red runs) is mechanically skipped by the picker — U3's manual
# "verify on live main" duty becomes a pick-time filter. Live anatomy that
# motivates the constant (a43 dossier #3048, item 18 cost model): the #3019
# incident consumed 4 dispatches and a claim-release lap while every agent
# re-derived the same staleness by hand; the treadmill kept re-serving the row
# because the falsified premise lived above the pick line. Fail-open: any
# probe failure (rate limit, timeout, parse, renamed workflow) serves the row
# unchanged — the filter can only REMOVE a dispatch, never block one.
STALE_INCIDENT_GREEN_RUNS = 5
STALE_INCIDENT_PROBE_TIMEOUT_S = 10.0
STALE_INCIDENT_RUNS_WINDOW = 60  # per_page for the runs fetch (newest-first)

_INCIDENT_RUN_RE = re.compile(r"Run\s*#(\d+)", re.IGNORECASE)
_INCIDENT_FAIL_MARKER = " failed on main"


def _incident_stale_note(
    item: dict[str, Any],
    fetch_runs: Callable[[int], list[dict[str, Any]]] | None = None,
    min_green: int | None = None,
) -> str | None:
    """#3050 — demotion note for a superseded CI-failure incident, else None.

    Recognizes the mirror's incident-title shape
    "...[<state>] <workflow> failed on main (Run #<id>)"; resolves the run's
    workflow name and run_number via the runs surface, then checks whether
    min_green (default STALE_INCIDENT_GREEN_RUNS) SUCCESS runs of the same
    workflow on main exist strictly newer than it with zero newer FAILURES
    (cancelled/timed-out runs are inconclusive and ignored — storm concurrency
    pruning must not read as red). Returns None for anything unjudgeable
    (non-incident titles, scrolled-off runs, renamed workflows, fetch errors):
    fail-open by construction, the row is served exactly as before.
    """
    n_green = STALE_INCIDENT_GREEN_RUNS if min_green is None else min_green
    title = str(item.get("title", ""))
    if _INCIDENT_FAIL_MARKER not in title:
        return None
    run_match = _INCIDENT_RUN_RE.search(title)
    if not run_match:
        return None
    try:
        incident_run_id = int(run_match.group(1))
    except ValueError:
        return None
    head = title.split(_INCIDENT_FAIL_MARKER)[0]
    if "] " not in head:
        return None
    workflow = head.rsplit("] ", 1)[1].strip()
    if not workflow:
        return None

    if fetch_runs is None:
        def fetch_runs(per_page: int) -> list[dict[str, Any]]:
            url = (
                f"https://api.github.com/repos/{UPSTREAM_REPO}/actions/runs"
                f"?branch=main&per_page={per_page}"
            )
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "supremeai-agent-loop-stale-incident-probe",
                },
            )
            with urllib.request.urlopen(req, timeout=STALE_INCIDENT_PROBE_TIMEOUT_S) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return list(payload.get("workflow_runs") or [])

    try:
        runs = fetch_runs(STALE_INCIDENT_RUNS_WINDOW)
    except Exception:  # noqa: BLE001 — fail-open: a dark runs surface serves the row
        return None

    incident = next(
        (r for r in runs if r.get("id") == incident_run_id),
        None,
    )
    if incident is None:
        return None  # scrolled off the window — cannot judge, serve unchanged
    incident_num = incident.get("run_number")
    incident_name = str(incident.get("name") or "")
    if not isinstance(incident_num, int):
        return None

    def _same_workflow(r: dict[str, Any]) -> bool:
        name = str(r.get("name") or "")
        return bool(name) and (name == workflow or name == incident_name or name in workflow or workflow in name or name in incident_name)

    newer = [
        r
        for r in runs
        if isinstance(r.get("run_number"), int)
        and r["run_number"] > incident_num
        and _same_workflow(r)
    ]
    concluded = [
        r for r in newer if r.get("conclusion") in ("success", "failure")
    ]
    if not concluded:
        return None
    greens = sum(1 for r in concluded if r.get("conclusion") == "success")
    has_red = any(r.get("conclusion") == "failure" for r in concluded)
    newest_first = concluded[0].get("conclusion") == "success"
    if greens >= n_green and not has_red and newest_first:
        return (
            f"incident-stale (U3 demotion, #3050): run #{incident_run_id} "
            f"superseded by {greens} green main runs of '{workflow}' with zero "
            "newer reds"
        )
    return None


def _probe_incident_stale(item: dict[str, Any]) -> str | None:
    """Live-plane wrapper handed to pick_next_issue as incident_probe.

    Never raises (the pick path's never-raise contract); returns the demotion
    note or None. Hermetic callers inject fetch_runs into _incident_stale_note
    directly instead.
    """
    try:
        return _incident_stale_note(item)
    except Exception:  # noqa: BLE001
        return None


# Stale-sentry demotion (#3050 demotion family, board-local extension):
# the platform sentry series is a rolling sentinel — every pass supersedes the
# previous one, yet all 20 open passes sit on the board as claimable rows
# (labels [] / status:unclaimed / platform-guardian+sentry), so the
# age-first priority sort serves the OLDEST fossil (live 2026-10-30 09:25Z:
# #2237 — a 2-day-old pass — was dispatched as the top pick while the live
# sentinel #3111, carrying that cycle's first-hand TELEGRAM-PRIMARY DOWN
# finding, sorted last). The falsified premise is the same class as #3050's:
# "you are looking at the freshest evidence" — false for every superseded
# pass. Unlike the CI-incident probe this judgment needs ZERO network: the
# family comparison is board-local (max issue number among open rows sharing
# the family shape; issue numbers are monotonic with filing order, which makes
# them a robustness-proof ordering token — no timestamp parsing). Two title
# spellings coexist in the series ("guard(platform): sentry pass …" and
# "guard(platform): provider sentry pass …"); the family test is prefix +
# marker so both join. Bridge mirror rows ("🌉 Bridge Work Order — … sentry
# pass …") do NOT start with the prefix and never join. Fail-open: any
# malformed row (missing title, non-numeric number) serves unchanged — the
# filter can only REMOVE a dispatch, never block one.
SENTRY_FAMILY_PREFIX = "guard(platform):"
SENTRY_FAMILY_MARKER = "sentry pass"


def _sentry_pass_newest_open(issues: list[dict[str, Any]]) -> int | None:
    """Newest (max issue number) open platform sentry pass on the board.

    Board-local, never-raise: comparison runs over the full open-row list
    (not just claimable candidates) so a claimed/bot-labeled newest sibling
    still supersedes the older fossils — the sentinel duty follows the
    newest OPEN pass regardless of its claim state.
    """
    newest: int | None = None
    try:
        for row in issues:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").casefold()
            if not title.startswith(SENTRY_FAMILY_PREFIX) or SENTRY_FAMILY_MARKER not in title:
                continue
            try:
                num = int(row.get("number", 0))
            except (TypeError, ValueError):
                continue
            if newest is None or num > newest:
                newest = num
    except Exception:  # noqa: BLE001 — fail-open
        return newest
    return newest


def _sentry_superseded_note(item: dict[str, Any], newest: int | None) -> str | None:
    """Demotion note when item is an OLDER member of the sentry-pass family.

    None for non-family rows, malformed rows, and the newest member itself
    (its premise — freshest sentinel evidence — is intact). Never raises.
    """
    try:
        if newest is None:
            return None
        title = str(item.get("title") or "").casefold()
        if not title.startswith(SENTRY_FAMILY_PREFIX) or SENTRY_FAMILY_MARKER not in title:
            return None
        num = int(item.get("number", 0))
    except Exception:  # noqa: BLE001 — fail-open
        return None
    if num < newest:
        return (
            "superseded platform sentry pass (stale-sentry demotion, #3050 family): "
            f"newest open sibling #{newest} carries the sentinel duty"
        )
    return None


# Case-file item 15 (§6ak, docs/reports/CI_4617_U4_DUPLICATE_GUARD_LANDING_DISCONNECT_2026-10-28.md)
# — premise-delivered demotion ("landing-receipt cross-scan candidate picking").
# The picker reads a row's body to extract a TASK but never checks whether the
# body's PROMISE is already kept. Live anatomy (GLM Agent 27, Job 486827,
# 2026-10-30): the loop dispatched #2395 minutes after its landing receipt hit
# main (merged #3158, squash subject "…live-verified by receipt #2395…"), and
# the board's #2597/#2792 rows were served while their receipts/landing
# vehicles existed plane-adjacent (merged #3162 "…for #2597…"; WO #3169) —
# each serve is a duplicate-minting invitation (U4's founding class), caught
# pre-claim only because each lane re-scanned by hand and walked away. Two
# bounded scans, both fail-open (the filter can only REMOVE a dispatch, never
# block one — the #3050-family contract):
#   A. promised-artifact existence (item 15's literal mechanism): backticked
#      repo paths inside the reach of a promise marker ("lands in-repo as",
#      "dossier at", "full dossier in", "companion PR") are tested against the
#      current tree; EVERY promised artifact existing ⇒ demote (any missing
#      path keeps the row — the promise may be partially unmet).
#   B. merged-landing citation (the a39 narrative's own receipt shape —
#      "landed … as the companion PR whose squash subject refs the row
#      back"): one cached /pulls?state=closed fetch per pick run; a MERGED PR
#      whose title/body cites the row in delivery form (closes/fixes/resolves/
#      for/receipt #N) ⇒ demote with the citing PR named. Closed-unmerged and
#      in-gates vehicles never demote — their work may still land or be
#      retried; only a merged receipt is a definitive landing signal.
PROMISE_MARKER_RE = re.compile(
    r"lands?\s+in[-\s]?repo\s+as|dossier\s+at|full\s+dossier\s+in|companion\s+pr",
    re.IGNORECASE,
)
# বাংলা: শুধুমাত্র ব্যাকটিকে ঘেরা রিপো-আপেক্ষিক পথ — কমপক্ষে একটি "/" থাকতে হবে,
# "/" বা ".." দিয়ে শুরু/এসকেপ করা পথ বাদ (tree-escape প্রতিরোধ)।
PROMISED_PATH_RE = re.compile(r"`(\w[\w.-]*(?:/[\w.-]+)+)`")
# item 15 R2 (GLM Agent 23, 2026-10-30) — bridge WO receipt shape. The tower
# mints every submit receipt with the SAME structured headers (### Task ID /
# ### Patch Branch / ### Scope Paths / ### Test Evidence); "Scope Paths" is a
# markdown list of repo-relative paths, NOT prose promise markers, so the
# marker-only scanner never saw the receipt class's own deliverable list.
# Receipt-shape gate: the scope scan only fires when the body carries the
# receipt's own headers (### Task ID / ### Patch Branch) — a fresh admin WO
# that merely lists files to CREATE must never demote off this scan alone.
RECEIPT_SHAPE_RE = re.compile(
    r"^#{1,6}\s*(?:task\s*id|patch\s*branch)\s*$", re.IGNORECASE | re.MULTILINE,
)
SCOPE_HEADING_RE = re.compile(
    r"^#{1,6}\s*scope\s*paths\s*:?[ \t]*$", re.IGNORECASE | re.MULTILINE,
)
SCOPE_ITEM_RE = re.compile(r"^[-*][ \t]+`?([^\s`]+)`?[ \t]*$")
# bridge:receipt — the tower labels a WO receipt issue at mint time. A receipt
# row is BY CONSTRUCTION a record of already-submitted work (its own body says
# "Bridge Work Order … Target Repo … Test Evidence"); a coder-IMPLEMENT solver
# dispatch on it can only mint a duplicate. Label-plane truth, zero network.
RECEIPT_LABEL = "bridge:receipt"
MERGED_LANDING_WINDOW = 80  # /pulls?state=closed newest-updated window (one fetch per pick run)
PREMISE_PROBE_TIMEOUT_S = 10.0

# বাংলা: প্রক্রিয়া-স্তরের একক ফেচ — প্রতি pick রানে সর্বোচ্চ একবার REST কল
# (rate-limit নিয়ন্ত্রণ); ব্যর্থতাও ক্যাশ হয় (খালি তালিকা) যাতে একই রানের
# পরবর্তী প্রার্থীরা বারবার নেটওয়ার্কে না যায়। ব্যর্থ ফেচ = কোনো demotion নয়
# (fail-open দিক: ফিল্টার শুধু dispatch সরায়, কখনো ব্লক করে না)।
_LANDING_FETCH_DONE = False
_LANDING_ROWS: list[dict[str, Any]] = []
# item 15 R2 (GLM Agent 23): a failed fetch used to be indistinguishable from
# a healthy empty scan — the fail-open dispatch was SILENT, so a rate-limited
# run re-dispatched premise-delivered rows as fresh work with no trace (live
# 2026-10-30: same sandbox, run 1 demoted #2360 via the citation scan, run 3
# re-picked it after the anonymous 60 req/h quota burned out; #3351's landed
# artifact rode the same dark run). The failure is now a first-class state
# surfaced at the pick log and on the task envelope's board_note.
_LANDING_FETCH_FAILED = False


def landing_crossscan_advisory() -> str | None:
    """Honest dark-scan advisory, or None when the scan never failed.

    বাংলা: fail-open dispatch থাকবে (never-raise চুক্তি অটুট), কিন্তু আর নীরব নয় —
    ফেচ-ব্যর্থতা হলে রিসিভিং এজেন্ট envelope-এই দেখবে যে premise স্ক্যান অন্ধকার
    ছিল, দাবি করার আগে নিজে যাচাই করতে হবে। Hermetic callers (injected
    fetch_merged) এই গ্লোবাল স্পর্শ করে না — তাদের জন্য সবসময় None।
    """
    if not _LANDING_FETCH_FAILED:
        return None
    return (
        "landing cross-scan DARK this run (anonymous /pulls fetch failed — "
        "rate-limit/timeout/parse): merged-citation premise scan was not "
        "performed; re-verify the row's premise on live main before claiming"
    )


def _fetch_merged_landing_prs(per_page: int) -> list[dict[str, Any]]:
    global _LANDING_FETCH_DONE, _LANDING_ROWS
    if _LANDING_FETCH_DONE:
        return _LANDING_ROWS
    _LANDING_FETCH_DONE = True
    url = (
        f"https://api.github.com/repos/{UPSTREAM_REPO}/pulls"
        f"?state=closed&sort=updated&direction=desc&per_page={per_page}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "supremeai-agent-loop-landing-receipt-probe",
        },
    )
    global _LANDING_FETCH_FAILED  # single-writer run-scoped cache
    try:
        with urllib.request.urlopen(req, timeout=PREMISE_PROBE_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:  # fail-open, but NOT silent (item 15 R2)
        _LANDING_FETCH_FAILED = True
        _LANDING_ROWS = []
        return _LANDING_ROWS
    _LANDING_ROWS = list(payload if isinstance(payload, list) else [])
    return _LANDING_ROWS


def _promised_artifact_paths(body: str) -> list[str]:
    """Backticked repo-relative paths inside the reach of a promise marker.

    বাংলা: item 15-এর শাব্দিক মেকানিজম — প্রতিশ্রুতি-মার্কারের বাক্যসীমার ভেতরে
    থাকা ব্যাকটিক-পথগুলোই "promised artifact"। মার্কার-পরের উইন্ডো প্রথম
    বাক্য-সমাপ্তিতে কাটা হয় যাতে অসংশ্লিষ্ট গদ্যের পথ ঢুকে না যায়। কখনোই
    raise করে না (বিকৃত body = খালি তালিকা)।
    """
    try:
        paths: list[str] = []
        seen: set[str] = set()
        text = str(body or "")
        for marker in PROMISE_MARKER_RE.finditer(text):
            reach = text[marker.end(): marker.end() + 200]
            # বাংলা: বাক্য-সীমা = নিউলাইন, অথবা [.!?]-এর পরে স্পেস/স্ট্রিং-শেষ —
            # ফাইলনেমের ভেতরের ডট (docs/x.md) বাক্য-সমাপ্তি নয়, সেটি রক্ষা করতেই
            # lookahead।
            stop = re.search(r"\n|[.!?](?=\s|$)", reach)
            if stop:
                reach = reach[: stop.start()]
            for pm in PROMISED_PATH_RE.finditer(reach):
                path = pm.group(1)
                parts = path.split("/")
                if path.startswith("/") or ".." in parts:
                    continue
                if path not in seen:
                    seen.add(path)
                    paths.append(path)
        return paths
    except Exception:  # noqa: BLE001 — fail-open
        return []


def _receipt_scope_paths(body: str) -> list[str]:
    """Repo-relative paths from a bridge WO receipt's structured Scope Paths block.

    বাংলা (item 15 R2): tower-মিন্টেড রিসিটের ডেলিভারেবল তালিকা গদ্য-মার্কারে নয়,
    `### Scope Paths` হেডিং-এর নিচের লিস্টে থাকে। রিসিট-শেপ গেট (### Task ID /
    ### Patch Branch হেডার) ছাড়া এই স্ক্যান চলে না — ফাইল-তালিকা আছে এমন সাধারণ
    নতুন কাজের body কখনো শুধু এই স্ক্যানে ডিমোট হবে না। কখনোই raise করে না।
    """
    try:
        text = str(body or "")
        if not RECEIPT_SHAPE_RE.search(text):
            return []
        paths: list[str] = []
        seen: set[str] = set()
        for heading in SCOPE_HEADING_RE.finditer(text):
            window = text[heading.end(): heading.end() + 800]
            for line in window.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    break  # next receipt section — scope block ended
                item = SCOPE_ITEM_RE.match(stripped)
                if not item:
                    break  # prose resumed — scope block ended
                path = item.group(1)
                parts = path.split("/")
                if "/" not in path or path.startswith("/") or ".." in parts:
                    continue
                if path not in seen:
                    seen.add(path)
                    paths.append(path)
        return paths
    except Exception:  # fail-open
        return []


def _premise_delivered_note(
    item: dict[str, Any],
    tree_root: Path | None = None,
    fetch_merged: Callable[[int], list[dict[str, Any]]] | None = None,
) -> str | None:
    """Item 15 — demotion note when a row's premise is already delivered, else None.

    বাংলা: স্ক্যানগুলো সবই সৎ-নোটবহন: (A) body-র প্রতিশ্রুত আর্টিফ্যাক্ট বর্তমান
    গাছে আছে কি না; (A2, R2) bridge:receipt লেবেল = সাবমিট-হয়ে-যাওয়া কাজের
    রেকর্ড — coder ডিসপ্যাচ শুধু ডুপ্লিকেট মিন্ট করে; (A3, R2) রিসিট-শেপ body-র
    `### Scope Paths` ব্লকের সব পথ বর্তমান গাছে থাকলে কাজটি ল্যান্ডেড বা ইতিমধ্যে
    সাবমিটেড; (B) মার্জড PR কি ডেলিভারি-ফর্মে রো-নম্বর উদ্ধৃত করছে। যেকোনো
    প্রোব-ব্যর্থতা (rate limit, timeout, parse) রো অপরিবর্তিত সার্ভ করে — ফিল্টার
    শুধু একটি dispatch সরাতে পারে, কখনো ব্লক করে না। হারমেটিক কলার
    tree_root/fetch_merged ইনজেক্ট করে (zero network)।
    """
    try:
        # A2 (R2): label-plane receipt truth — zero network, zero heuristics.
        raw_labels = item.get("labels") or []
        label_names = {
            str(l.get("name", "")).lower() if isinstance(l, dict) else str(l).lower()
            for l in raw_labels if isinstance(l, (dict, str))
        }
        if RECEIPT_LABEL in label_names:
            return (
                "premise-delivered (bridge:receipt label, item 15/§6ak R2): this row is a "
                "work-order receipt for already-submitted work, not solver-actionable "
                "IMPLEMENT surface — a fresh dispatch would mint a duplicate"
            )
        promised = _promised_artifact_paths(str(item.get("body") or ""))
        if promised:
            root = tree_root if tree_root is not None else REPO_ROOT
            missing = [p for p in promised if not (root / p).exists()]
            if not missing:
                return (
                    "premise-delivered (landing-receipt cross-scan, item 15/§6ak): promised "
                    f"in-repo artifact(s) already exist on main: {', '.join(promised)} — "
                    "the row's own deliverable is landed; claiming would mint a duplicate landing"
                )
        # A3 (R2): receipt-shape scope-block existence — zero network.
        scope = _receipt_scope_paths(str(item.get("body") or ""))
        if scope:
            root = tree_root if tree_root is not None else REPO_ROOT
            missing = [p for p in scope if not (root / p).exists()]
            if not missing:
                return (
                    "premise-delivered (receipt scope cross-scan, item 15/§6ak R2): receipt's "
                    f"scope artifact(s) all exist on main: {', '.join(scope)} — the work order "
                    "is landed or already submitted; a fresh solver dispatch would mint a duplicate"
                )
        if fetch_merged is None:
            fetch_merged = _fetch_merged_landing_prs
        rows = fetch_merged(MERGED_LANDING_WINDOW)
        num = int(item.get("number"))
    except Exception:  # noqa: BLE001 — fail-open: a dark plane serves the row
        return None
    cite = re.compile(rf"(?:closes|fixes|resolves|for|receipt)\s+#{num}\b", re.IGNORECASE)
    try:
        for pr in rows:
            if not isinstance(pr, dict) or not pr.get("merged_at"):
                continue
            hay = f"{pr.get('title') or ''}\n{pr.get('body') or ''}"
            m = cite.search(hay)
            if not m:
                continue
            title = str(pr.get("title") or "").strip()[:80]
            return (
                "premise-delivered (landing-receipt cross-scan, item 15/§6ak): merged PR "
                f"#{pr.get('number')} already cites this row ('{m.group(0)}' in \"{title}\") — "
                "the landing receipt is on main; re-verify the residual need before claiming"
            )
    except Exception:  # noqa: BLE001 — fail-open
        return None
    return None


def _probe_premise_delivered(item: dict[str, Any]) -> str | None:
    """Live-plane wrapper handed to pick_next_issue as premise_probe.

    Never raises (the pick path's never-raise contract); returns the demotion
    note or None. Hermetic callers inject tree_root/fetch_merged into
    _premise_delivered_note directly instead.
    """
    try:
        return _premise_delivered_note(item)
    except Exception:  # noqa: BLE001
        return None


def _feedback_claim_active(issue_number: int | str, timeout_s: float = 6.0) -> tuple[bool, str]:
    """#2794 fix (1) — live-plane claim pre-verify for the dispatch pick.

    বাংলা: কিউ-লেবেল লাইভ tower claim-কে ৩০-মিনিট claim TTL পর্যন্ত পিছিয়ে থাকে
    (#2100/#2111 arc; #2794-এর লাইভ প্রমাণ 2026-10-29: ১ ঘণ্টায় ৩টি live-claimed
    রো dispatch হয়েছে — #1776/#2597/#2738) — ফলে label-only pick অন্য এজেন্টের
    মালিকানাধীন রো পুনঃ-এমিট করে এবং এজেন্টের পুরো সাইকেল atomic-claim rejection-
    এ পোড়ে যায়। এই প্রোব bridge_read_feedback-এর latestClaim জিজ্ঞেস করে জানায়
    সক্রিয় (মেয়াদ-অপ্রাপ্ত) claim আছে কি না — claim-lag অর্ধেক-চার্ন স্ট্রাকচারালি
    বন্ধ করতে (#2794 proposed fix (1); item (2)-র lane:admin convention আলাদা,
    owner-blessing অপেক্ষায়)।

    Transport mirrors _tower_queue_floor's never-raise contract: lazy sibling
    import, daemon probe thread + hard join, and every failure mode degrades to
    (False, honest-note) — a dark feedback plane must NOT silently change pick
    behavior (label-only dispatch proceeds; the STALE-CLAIM advisory prose stays
    as the agent-side second layer — U3 two-layer pattern preserved). Small
    payloads ride the sibling client's call_tool (the urllib transport split in
    _tower_board_rows is only needed for the giant queue payload).

    Returns (claim_active, note): True ⇒ row owned right now (note carries
    agent/at/ttl/remaining); False ⇒ no active claim OR plane dark (note says
    which — callers log it honestly). Decision logic is exercised with injected
    probes by tests/test_pick_feedback_preverify.py (zero network).
    """
    outcome: dict[str, Any] = {}

    def _probe() -> None:
        try:
            sys.path.insert(0, str(REPO_ROOT / "scripts" / "agents"))
            import mcp_tower_client as _mtc  # noqa: E402  (lazy sibling import)

            client = _mtc.McpTowerClient()
            client.connect()
            # Live-registry name (underscore form) — the dotted bridge.read_feedback
            # is dead since #2454-r3; same pin the STALE-CLAIM advisory text follows (#2775).
            fb = client.call_tool("bridge_read_feedback", {"number": int(issue_number)})
            # call_tool returns the raw MCP envelope ({"content": [{"text": ...}]});
            # the feedback dict rides as JSON inside content[0].text — tolerate both
            # envelope and already-parsed shapes (same extraction as _tower_queue_floor).
            if isinstance(fb, dict) and isinstance(fb.get("content"), list) and fb["content"]:
                first = fb["content"][0]
                txt = first.get("text") if isinstance(first, dict) else None
                if isinstance(txt, str):
                    try:
                        fb = json.loads(txt)
                    except Exception:
                        fb = None
            if isinstance(fb, dict):
                outcome["fb"] = fb
            else:
                outcome["error"] = "feedback payload not parseable"
        except Exception as exc:  # noqa: BLE001 — probe must never raise
            outcome["error"] = f"{type(exc).__name__}: {exc}"

    try:
        t = threading.Thread(target=_probe, daemon=True)
        t.start()
        t.join(timeout=timeout_s)
    except Exception as exc:  # noqa: BLE001 — floor must never raise
        return False, f"feedback probe error ({type(exc).__name__})"
    if t.is_alive():
        return False, f"feedback probe timed out after {timeout_s:.0f}s"
    if "error" in outcome:
        return False, f"feedback plane dark ({outcome['error']})"

    fb = outcome.get("fb")
    claim = fb.get("latestClaim") if isinstance(fb, dict) else None
    if not isinstance(claim, dict) or not claim:
        return False, "no active claim on the feedback plane"

    agent = str(claim.get("agent") or "unknown-agent")
    at_raw = claim.get("at")
    ttl_raw = claim.get("ttlMinutes")
    if not isinstance(at_raw, str) or not isinstance(ttl_raw, (int, float)):
        return False, (
            f"latestClaim present but unparseable (at={at_raw!r}, ttl={ttl_raw!r})"
        )

    import datetime as _dt  # local import — the shared import lines are #2796-conflict surfaces

    try:
        claimed_at = _dt.datetime.fromisoformat(str(at_raw).replace("Z", "+00:00"))
    except ValueError:
        return False, f"latestClaim timestamp unparseable ({at_raw!r})"

    age_s = max(0.0, time.time() - claimed_at.timestamp())  # clock skew ⇒ just-claimed
    ttl_s = float(ttl_raw) * 60.0
    if age_s < ttl_s:
        remaining_m = (ttl_s - age_s) / 60.0
        return True, (
            f"live claim by {agent} at {at_raw} (ttl {ttl_raw:g}m, {remaining_m:.0f}m remaining)"
        )
    return False, (
        f"latestClaim by {agent} expired ({age_s / 60.0:.0f}m age > {ttl_raw:g}m ttl)"
    )

def pick_next_issue(
    exclude: set[str] | list[str] | None = None,
    issues: list[dict[str, Any]] | None = None,
    claim_probe: Callable[[int | str], tuple[bool, str]] | None = None,
    log_fn: Callable[[str, str], None] | None = None,
    incident_probe: Callable[[dict[str, Any]], str | None] | None = None,
    premise_probe: Callable[[dict[str, Any]], str | None] | None = None,
) -> str | None:
    # বাংলা: log_fn=None → call-time-এ log-এ ফলব্যাক। ডিফল্ট-প্যারামিটারে সরাসরি log
    # লিখলে def-time evaluation-এ NameError হত — log() এই ফাইলে pick_next_issue-
    # এর পরে সংজ্ঞাত (forward reference def-time-এ মেলে না)।
    """বাংলা: priority-অনুসারে পরবর্তী claimable issue বাছাই (P0 আগে, তারপর নম্বর)।

    আগের সংস্করণে এই ফাংশনটিই একমাত্র priority-sorter ছিল কিন্তু main() কখনো ডাকতই না
    (dead code) — ফলে লুপ P0 আগে দেবে এই প্রতিশ্রুতি কোডে কখনো কার্যকর হয়নি। এখন
    main() pre-fetched board এখানে পাঠায় (issues=...) — এক সাইকেলে দুবার gh query হয় না।

    #2794 fix (1): claim_probe দিলে top-FEEDBACK_PREVERIFY_TOPN প্রার্থী bridge_read_feedback
    দিয়ে live-claim যাচাই হয় — সক্রিয় claim-পত রো একই রানে স্কিপ হয়ে পরের প্রার্থীতে
    এগোয় (এজেন্টকে পুরো লুপ পুনঃরান করতে বলা হয় না); প্রোব-ডার্ক হলে label-only
    আচরণ (আচরণ অপরিবর্তিত, সৎ নোট); উইন্ডো শেষ হলে সৎ None — জানা-মালিকানাধীন রো
    এক র‍্যাঙ্ক নিচে দিয়ে অন্ধ dispatch নয়। claim_probe=None মানে pure mode —
    label-only pick, আগের চুক্তি অক্ষত (হারমেটিক টেস্ট এভাবেই ডাকে)।
    """
    if issues is None:
        code, out, _ = run_cmd([
            "gh", "issue", "list",
            "--repo", UPSTREAM_REPO,
            "--state", "open",
            "--limit", "200",
            "--json", "number,title,labels",
        ])
        issues = []
        if code == 0 and out.strip():
            try:
                issues = json.loads(out)
            except Exception:
                pass
    if not issues:
        return None
    log_fn = log_fn or log

    lease_store = load_issue_lease_store()
    now_ts = time.time()

    def is_claimable(item: dict[str, Any]) -> bool:
        names = label_names(item)
        if EXCLUDED_LABELS & set(names):
            return False
        # বাংলা: ৩০ মিনিটের স্বয়ংক্রিয় লিজ ট্র্যাকিং — অন্য এজেন্ট যদি ৩০ মিনিটের মধ্যে কাজ শেষ না
        # করে থাকে, তবে এটি নিজে থেকেই রিলিজ হয়ে রি-ক্লেইমযোগ্য হয়ে যাবে।
        # #2903 fix: state truth on the fallback plane — the gh-present path
        # pre-filters `gh issue list --state open`, but tower-board fallback rows
        # carry `state` verbatim, so a closed row with stale unclaimed labels
        # dispatched as claimable (live 2026-10-29: #2225 picked while closed at
        # 9f32c01 — the #2211/#2225 false-closure family, contained only by the
        # #2886 template scoping; #2794 fix (2)-adjacent mechanical filter, not
        # the owner-pending convention space). Rows without a `state` key (the
        # gh-present contract: number,title,labels) default open — that path's
        # behavior is unchanged.
        state = item.get("state")
        if state is not None and str(state).lower() != "open":
            return False
        num_str = str(item.get("number", ""))
        leased_at = lease_store.get(num_str)
        if leased_at is not None and (now_ts - leased_at) < ISSUE_LEASE_SECONDS:
            return False
        return True

    PRIORITY_MAP = (("p0", 0), ("p1", 1), ("p2", 2), ("p3", 3))

    def priority_key(item: dict[str, Any]) -> tuple[int, int]:
        names = label_names(item)
        tier = 4
        for marker, rank in PRIORITY_MAP:
            if any(name == marker or name.startswith(marker + "-") or name.startswith(marker + " ") for name in names):
                tier = rank
                break
        return (tier, int(item.get("number", 0)))

    candidates = [i for i in issues if isinstance(i, dict) and is_claimable(i)]
    if exclude:
        excluded_set = {str(e) for e in exclude}
        candidates = [i for i in candidates if str(i.get("number")) not in excluded_set]
    # Stale-sentry demotion (#3050 family, board-local): superseded platform
    # sentry passes are filtered from the candidates BEFORE the priority sort,
    # so the live sentinel (newest open pass) and real work surface within the
    # top-FEEDBACK_PREVERIFY_TOPN pre-verify window instead of the window
    # exhausting on fossils (live 2026-10-30: 20 open sentry passes; top-5 by
    # age were ALL fossils, #2237 dispatched while #3111 sorted last).
    # Gated on live mode (claim_probe wired) — pure mode keeps the pre-change
    # label-only contract byte-identical for hermetic callers, exactly the
    # boundary the #2794/#3050 probes ride. Malformed rows fail open and are
    # served unchanged.
    if claim_probe is not None:
        newest_sentry = _sentry_pass_newest_open(issues or [])
        if newest_sentry is not None:
            survivors: list[dict[str, Any]] = []
            demoted = 0
            for cand in candidates:
                if _sentry_superseded_note(cand, newest_sentry) is not None:
                    demoted += 1
                    continue
                survivors.append(cand)
            if demoted:
                log_fn(
                    "!",
                    f"stale-sentry demotion: {demoted} superseded platform sentry pass row(s) "
                    f"filtered from the pick — newest open sibling #{newest_sentry} carries the sentinel duty",
                )
            candidates = survivors
    sorted_issues = sorted(candidates, key=priority_key)
    if claim_probe is None:
        # Pure mode — label-only pick, exactly the pre-#2794 contract (hermetic
        # tests and opt-out callers ride this path; zero network, zero behavior change).
        if sorted_issues:
            return str(sorted_issues[0].get("number"))
        return None

    # #2794 fix (1) — live-plane pre-verify before ACTION: queue labels lag live
    # claims by up to the 30-min claim TTL, so the label-only pick re-emits rows
    # another agent already owns (live 2026-10-29: #1776/#2597/#2738 dispatched
    # while live-claimed). An active claim skips the row IN THE SAME RUN; a dark
    # probe degrades to label-only (behavior unchanged, honest note); an exhausted
    # window returns None instead of dispatching a known-owned row one rank lower.
    for item in sorted_issues[:FEEDBACK_PREVERIFY_TOPN]:
        num = str(item.get("number", ""))
        try:
            active, note = claim_probe(item.get("number"))
        except Exception as exc:  # noqa: BLE001 — a broken probe must not break the pick
            active, note = False, f"probe raised {type(exc).__name__}"
        if active:
            log_fn("!", f"pick pre-verify: #{num} skipped — {note}; advancing to next candidate (#2794 fix (1))")
            continue
        if incident_probe is not None:
            # #3050 — stale-incident demotion: a superseded CI-failure incident
            # is skipped IN THE SAME RUN (advance to the next candidate), the
            # same skip-and-advance shape as the live-claim filter above.
            # Fail-open: probe errors serve the row (never-raise contract).
            try:
                stale_note = incident_probe(item)
            except Exception as exc:  # noqa: BLE001
                stale_note = None
                log_fn("!", f"pick pre-verify: #{num} incident probe raised {type(exc).__name__} — serving row unchanged")
            if stale_note:
                log_fn("!", f"pick pre-verify: #{num} skipped — {stale_note}; advancing to next candidate (#3050 U3 demotion)")
                continue
        if premise_probe is not None:
            # item 15 (§6ak) — premise-delivered demotion: a row whose own
            # promised in-repo artifact already exists on main, or whose
            # merged landing receipt already cites the row, is skipped IN THE
            # SAME RUN (advance to the next candidate), the same
            # skip-and-advance shape as the live-claim and incident filters.
            # Fail-open: probe errors serve the row (never-raise contract);
            # the filter can only REMOVE a dispatch, never block one.
            try:
                delivered_note = premise_probe(item)
            except Exception as exc:  # noqa: BLE001
                delivered_note = None
                log_fn("!", f"pick pre-verify: #{num} premise probe raised {type(exc).__name__} — serving row unchanged")
            if delivered_note:
                log_fn("!", f"pick pre-verify: #{num} skipped — {delivered_note}; advancing to next candidate (item 15 premise-delivered demotion)")
                continue
            # item 15 R2 — dark-scan honesty: a served row whose citation scan
            # never ran (anonymous fetch failed) must not LOOK verified. The
            # advisory is log-only here; the envelope path threads it into
            # board_note so the receiving agent sees it in the JSON itself.
            dark = landing_crossscan_advisory()
            if dark:
                log_fn("!", f"pick pre-verify: #{num} {dark}")
        if note and not note.startswith("no active claim"):
            log_fn("!", f"pick pre-verify: #{num} {note} — proceeding on labels (live advisory to the agent stays in force)")
        return num
    if sorted_issues:
        log_fn(
            "!",
            f"pick pre-verify: top {min(FEEDBACK_PREVERIFY_TOPN, len(sorted_issues))} candidates live-claimed — "
            "no clean pick this run (rerun later or dispatch explicitly via --issue N); "
            "dispatching a known-owned row would burn the cycle on atomic-claim rejection",
        )
    return None


def action_instruction(picked: str | int) -> str:
    """#2738 evidence lane — boundary-honest ACTION template for the solver pick.

    The pre-#2738 template unconditionally granted every pick an on-merge
    auto-close: a PR-description "Closes #N" line whose merge closes the issue,
    printed for EVERY pick regardless of where the remedy lives. An agent that
    followed it against a row whose remedy lives outside the open repo auto-closed
    the issue on merge with zero recovery — the documented false-closure family:
    #2211 was
    closed "completed" while 2 of 3 named services were still broken (the residual
    became #2225); #2225 was then closed under materially identical conditions and
    is now challenged by #2738 (27th hourly tower proof: render-primary +
    render-worker lastDeployStatus=update_failed, updatedAt frozen since
    2026-10-24T08:32:4xZ, latestVerdict null); #2608's zero-verdict false close is
    flagged by #2615. GitHub auto-close fires on the Closes line regardless of
    whether the remedy actually landed, so the printed instruction must scope the
    auto-close grant to remedies that are fully inside this open repo, and route
    out-of-envelope remedies to evidence-only submission with the closure decision
    left to the verdict plane/admin.

    Scope note: this is TEMPLATE honesty only. It deliberately does NOT implement
    the lane-classification convention proposed by #2794 item (2) (lane:admin
    labels + pick exclusion) — that item is owner-pending ("needs the convention
    blessed first" per the filer). The pick surface, label semantics, and dispatch
    flow are unchanged; only the instruction text stops granting blanket auto-close
    authority. audit:finding rows must stay dispatchable — #2794 itself carried
    that label and was legitimately fixed in-repo (#2815). The U3 two-layer pattern
    is preserved: the STALE-CLAIM/boundary prose guards remain the agent-side
    second layer.
    """
    return (
        f"ACTION: Highest-priority unclaimed issue = #{picked}. Solve root cause and submit PR. "
        f"Include 'Closes #{picked}' in the PR description ONLY when the remedy is fully inside "
        "this open repo — the merge then closes the issue truthfully. If the remedy lives outside "
        "the agent envelope (tower policy/HITL approval, service redeploys, satellite repos, "
        "protected paths such as .github/ or docs/master_docs/) or the row is report-only evidence "
        "(audit:finding challenge/note), submit evidence via the bridge and do NOT auto-close: "
        "leave the closure decision to the verdict plane/admin — a Closes line on an un-remedied "
        "issue is a false closure (#2211/#2225 family; #2738 challenge; #2608 flagged by #2615)."
    )


DEFAULT_CADENCE_HOURS: dict[str, int] = {
    "ecosystem-scout": 12,
    "auditor": 12,
    "human-eye": 24,
    "rules-breaker": 24,
    "platform-guardian": 24,
}

DEFAULT_MERGED_ROLES: dict[str, str] = {
    "federation-auditor": "auditor",
    "task-auditor": "auditor",
    "ci-fixer": "solver",
    "coder": "solver",
}

ROLE_RULES: dict[str, str] = {
    "solver": "Unlimited concurrent solvers allowed. Solve root cause, verify boundary, and submit PR.",
    "auditor": "6 repo codebase-এ যা যা সমস্যা আছে তা পুঙ্খানুপুঙ্খ অডিট ও সমাধান বের করা।",
    "ecosystem-scout": "সারা বিশ্বের যেকোনো জায়গা থেকে SupremeAI-এর জন্য সবচেয়ে লাভজনক ও উপকারী হবে এমন জিনিস ও ইনোভেশন খুঁজে আনা। শুধুমাত্র লাইভ প্রমাণসহ কংক্রিট, বাস্তবায়নযোগ্য ফাইন্ডিং ফাইল করা যাবে; অনুমাননির্ভর/হাইপ টিকেট কঠোরভাবে নিষিদ্ধ; কোড এডিট নয়।",
    "human-eye": "আমাদের কাস্টমার যেন সর্বোত্তম ও শ্রেষ্ঠ এক্সপেরিয়েন্স পায় তার জন্য প্রয়োজনীয় সমস্ত UI/UX ও পারফরম্যান্স নিশ্চিত করা।",
    "rules-breaker": "আমাদের সম্পূর্ণ সিস্টেমের সিকিউরিটি, টেকনিক্যাল ডেট এবং লজিক্যাল গ্যাপের সমস্ত দুর্বলতা খুঁজে বের করে রিপোর্ট করা।",
    "platform-guardian": "প্রজেক্টের সাথে যুক্ত অন্যান্য সমস্ত থার্ড-পার্টি প্ল্যাটফর্ম ও সার্ভিসের সার্বক্ষণিক তদারকি ও নজরদারি নিশ্চিত করা।",
}

COMMON_RULES = """=== UNIVERSAL INVARIANTS (ALL ROLES MUST FOLLOW) ===
1. Dual-Rebase: Rebase origin/main at work-start AND pre-push (0 behind).
2. Boundary: Zero satellite code in repo root (src/*, service/*, packages/*).
3. Superior Replacement: Discard broken legacy code/tests; never hack new code to appease past errors.
4. Verification: No direct push to protected branches; all PRs require local proof.
5. P0 Drainage & Anti-Stampede: Architectural P0 blockers supersede all routine audits/scout tickets; idempotency check mandatory."""

def log(icon: str, msg: str) -> None:
    try:
        print(f"{icon} {msg}")
    except UnicodeEncodeError:
        print(f"[*] {msg}")

def _stderr_log(icon: str, msg: str) -> None:
    """SPEC §4b stdout-purity logger for envelope-mode pick advisories.

    বাংলা: --task-envelope মোডের stdout চুক্তি হলো শুধুই envelope JSON (SPEC §4b —
    "stdout শুধুই envelope JSON থাকে যাতে pipe/parse নিরাপদ থাকে")। কিন্তু
    pick_next_issue()-এর ভেতরের log() লাইনগুলো stdout-এই ছাপাত — লাইভ প্রমাণ
    2026-10-29 ও 2026-10-30 (sha 35c6302): top-5 প্রার্থীতে live claim থাকলে
    envelope JSON-এর আগে "! pick pre-verify: #N ..." লাইন এমিট হত, ফলে
    json.loads(stdout) ভেঙে যেত — pipe-করে envelope খাওয়া প্রতিটি external
    automation ঠিক এই কেসেই আটকায়। এই লগার একই মেসেজ stderr-এ পাঠায় —
    ডিসপ্যাচ-পথ (stdout-মার্কার গণনা) অস্পৃষ্ট থাকে, কারণ সেখানে default log_fn=log
    থাকে (pick_next_issue-এর নতুন log_fn প্যারামিটার, default = আগের আচরণ)।
    """
    try:
        print(f"{icon} {msg}", file=sys.stderr)
    except UnicodeEncodeError:
        print(f"[*] {msg}", file=sys.stderr)

def _tower_queue_floor(timeout_s: float = 12.0) -> str:
    """R61/#2318 option B — honesty floor for the gh-absent skip line.

    On the documented external-agent runtime (no gh CLI) the skip line used to
    say only "issue board unavailable", which reads as an EMPTY board while the
    Tower queue is in fact reachable zero-credential — and the P0-drainage gate
    (Universal Invariant 5) is dark there BY CONSTRUCTION (AGENT_LOOP_SPEC
    scans the same gh-derived items). This best-effort probe appends the live
    queue depth so the skip line stops lying by omission (the R61 body's live
    quantification: 93 open rows incl. a P1 invisible to this runtime).

    Never raises, never hangs: lazy sibling import (same sys.path pattern as
    tests/test_tower_url_resolution.py), daemon probe thread + hard join, and
    every failure mode degrades to the plain P0-dark note. Runs ONLY on the
    gh-absent path, so gh-present runtimes (CI) are untouched."""
    outcome: dict[str, str] = {}

    def _probe() -> None:
        try:
            sys.path.insert(0, str(REPO_ROOT / "scripts" / "agents"))
            import mcp_tower_client as _mtc  # noqa: E402  (lazy sibling import)

            client = _mtc.McpTowerClient()
            client.connect()
            # 2026-10-29: the tower renamed bridge_work_queue -> bridge.work_queue
            # (#2454 r3 deploy; old name absent from the live registry) — use the
            # dotted name or the P0-drainage probe stays dark (#2457).
            q = client.call_tool("bridge.work_queue", {})
            # call_tool returns the raw MCP envelope ({"content":[{"text": ...}]});
            # the queue dict rides as JSON inside content[0].text (same extraction
            # the client's own CLI does). Tolerate both envelope and parsed shapes.
            if isinstance(q, dict) and isinstance(q.get("content"), list) and q["content"]:
                first = q["content"][0]
                txt = first.get("text") if isinstance(first, dict) else None
                if isinstance(txt, str):
                    try:
                        q = json.loads(txt)
                    except Exception:
                        q = None
            total = q.get("totalOpen") if isinstance(q, dict) else None
            if isinstance(total, int):
                outcome["note"] = (
                    f"tower board reachable: {total} open work orders — "
                    "P0-drainage gate (Invariant 5) is dark on this gh-less runtime"
                )
            else:
                outcome["note"] = (
                    "tower board probe returned no totalOpen — "
                    "P0-drainage gate (Invariant 5) is dark on this gh-less runtime"
                )
        except Exception as exc:  # noqa: BLE001 — floor must never raise
            outcome["note"] = (
                f"tower board probe failed ({type(exc).__name__}) — "
                "P0-drainage gate (Invariant 5) is dark on this gh-less runtime"
            )

    try:
        t = threading.Thread(target=_probe, daemon=True)
        t.start()
        t.join(timeout=timeout_s)
    except Exception as exc:  # noqa: BLE001 — floor must never raise
        return f"tower board probe error ({type(exc).__name__}) — P0-drainage gate (Invariant 5) is dark on this gh-less runtime"
    if t.is_alive():
        return "tower board probe timed out — P0-drainage gate (Invariant 5) is dark on this gh-less runtime"
    return outcome.get("note", "P0-drainage gate (Invariant 5) is dark on this gh-less runtime")

def _tower_board_rows(timeout_s: float = 20.0) -> tuple[list[dict[str, Any]], str]:
    """R78/J484751 — gh-absent tower board fallback (revives the dispatch path).

    বাংলা: gh CLI নেই এমন ডকুমেন্টেড external-agent runtime-এ ডিসপ্যাচ পথের
    বোর্ড-কোয়েরি সবসময় ব্যর্থ হয় — ফলে solver dispatch ও P0-drainage গেট (Invariant
    ৫) দুটোই অন্ধকার থাকে, অথচ tower queue zero-credential থেকেই reachable (live
    প্রমাণ 2026-10-30: bridge.work_queue, totalOpen=115)। R61 floor-প্রোব শুধু একটা
    সত্য-নোট যোগ করত — বোর্ড-ডেটা নিজে ফেরত দিত না; ফলে লুপ যেখানে
    আসলেই চলে সেখানে solver-পথ মৃত ছিল এবং P0-অবস্থা যাচাই অসম্ভব ছিল। এই fallback
    সেই একই lazy sibling import প্যাটার্ন (daemon thread + hard join, কখনো raise/
    hang নয় — প্রতিটি ব্যর্থতা সৎ নোটে নামে) দিয়ে bridge.work_queue-র সারিগুলোকে
    gh-shaped বোর্ড আইটেমে ম্যাপ করে; একই পেলোড এখন দুই ভোক্তা পায় (floor-নোট +
    বোর্ড-ডেটা)। gh-present runtime-এ এই ফাংশন ডাকা হয় না (CI অস্পৃষ্ট)।

    Shape contract: workOrders[].labels স্ট্রিং-তালিকা, কিন্তু label_names() dict-শেপ
    আশা করে — তাই {"name": l} এ মোড়া হয় (EXCLUDED_LABELS/P0-গেট/priority-scan
    তিনটিই এভাবে কাজ করে); body অনুপস্থিত রাখা হয় — envelope hydrate-পথ (title/body
    অনুপস্থিতিতে gh issue view + সৎ board_note) এটাকেই সামলায়। ফেরত: (rows, note) —
    rows খালি মানে fallback-ব্যর্থতা, note-এ সৎ কারণ।

    Transport note (live 2026-10-30): পুরো বোর্ডের (limit=200) tools/call রেসপন্স
    একটাই ~১৩৪ KB-র SSE data-লাইন; সিবলিং ক্লায়েন্টের call_tool পথ requests-
    এর iter_lines(decode_unicode=True) ব্যবহার করে, যা chunk-boundary-তে বড়
    single-line পেলোড মাঝপথে ভেঙে দেয় (fragment 63,624 chars — id-match ব্যর্থ,
    McpTowerTimeoutError)। তাই এই প্রোব urllib-এ (stdlib) raw streamable POST
    করে এবং পুরো body থেকে bytes-স্তরে data-line এক্সট্র্যাক্ট করে — যেকোনো সাইজে
    নিরাপদ (প্রমাণিত: একই পেলোড json.loads 134,253 bytes-এ পাস)। সিবলিং ক্লায়েন্ট
    থেকে শুধু MCP_SERVER_URL রেজোলিউশন ধার নেওয়া হয় (env/mcp.json/default —
    operator-এর mcp.json চুক্তি অক্ষত); heartbeat/status-এর মতো ছোট পেলোডে
    ক্লায়েন্টের call_tool অক্ষত।
    """
    outcome: dict[str, Any] = {}

    def _probe() -> None:
        try:
            sys.path.insert(0, str(REPO_ROOT / "scripts" / "agents"))
            import mcp_tower_client as _mtc  # noqa: E402  (lazy sibling import)

            base = _mtc.MCP_SERVER_URL.rstrip("/")
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }

            def _post(payload: dict[str, Any], sid: str | None, timeout: int = 30) -> tuple[str, str]:
                hdrs = dict(headers)
                if sid:
                    hdrs["mcp-session-id"] = sid
                req = urllib.request.Request(
                    f"{base}/mcp", data=json.dumps(payload).encode(), headers=hdrs, method="POST"
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.headers.get("mcp-session-id") or sid or "", resp.read().decode("utf-8", errors="replace")

            # 1) initialize (handshake) 2) initialized notification 3) tools/call
            init_id = "cal-board-fallback-1"
            sid, _ = _post({
                "jsonrpc": "2.0", "id": init_id, "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "supremeai-agent-loop", "version": "1.0"},
                },
            }, None)
            # বাংলা: initialize-থেকে mcp-session-id ধরে রাখা বাধ্যতামূলক — tower
            # notification/call-এ header ছাড়া 4xx দেয় (live 2026-10-30, HTTPError);
            # কিছু ডিপ্লয়মেন্ট session-id ছাড়াই চলে, তাই sid=None হলেও এগোনো নিরাপদ।
            _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid, timeout=15)
            call_id = "cal-board-fallback-2"
            _, body = _post({
                "jsonrpc": "2.0", "id": call_id, "method": "tools/call",
                "params": {"name": "bridge.work_queue", "arguments": {"limit": 200}},
            }, sid, timeout=45)

            # বাংলা: body হয় SSE (data: লাইন) নয়তো সরাসরি JSON — দুই শেপই সমর্থিত।
            # limit=200-এর মতো বড় single-line পেলোড splitlines/iter_lines-এ ভাঙে,
            # তাই regex পুরো body-র উপর চলে (mcp_call.py-এর প্রমাণিত প্যাটার্ন)।
            envelopes: list[dict[str, Any]] = []
            for m in re.finditer(r"^data: (.*)$", body, re.MULTILINE):
                try:
                    envelopes.append(json.loads(m.group(1)))
                except json.JSONDecodeError:
                    pass
            if not envelopes:
                try:
                    envelopes.append(json.loads(body))
                except json.JSONDecodeError:
                    pass
            result: Any = None
            for env in envelopes:
                if isinstance(env, dict) and env.get("id") == call_id and "error" not in env:
                    result = env.get("result")
                    break
            text = ""
            if isinstance(result, dict) and isinstance(result.get("content"), list) and result["content"]:
                first = result["content"][0]
                txt = first.get("text") if isinstance(first, dict) else None
                if isinstance(txt, str):
                    text = txt
            q: Any = None
            if text:
                try:
                    q = json.loads(text)
                except json.JSONDecodeError:
                    q = None
            rows = q.get("workOrders") if isinstance(q, dict) else None
            if not isinstance(rows, list):
                outcome["error"] = "tower queue payload carried no workOrders list"
                return
            board: list[dict[str, Any]] = []
            for row in rows:
                if not isinstance(row, dict) or row.get("number") is None:
                    continue
                raw_labels = row.get("labels")
                labels: list[Any] = []
                if isinstance(raw_labels, list):
                    labels = [{"name": str(l)} for l in raw_labels]
                board.append(
                    {
                        "number": row.get("number"),
                        "title": row.get("title"),
                        "state": row.get("state") or "open",
                        "labels": labels,
                    }
                )
            outcome["rows"] = board
            detail = ""
            if isinstance(q, dict) and isinstance(q.get("totalOpen"), int):
                detail += f" (totalOpen={q['totalOpen']}"
                if q.get("windowTruncated"):
                    detail += ", window truncated"
                detail += ")"
            elif isinstance(q, dict) and q.get("windowTruncated"):
                detail = " (window truncated)"
            outcome["note"] = f"tower board fallback: {len(board)} rows{detail}"
        except Exception as exc:  # noqa: BLE001 — fallback must never raise
            outcome["error"] = f"tower board fallback failed ({type(exc).__name__})"

    try:
        t = threading.Thread(target=_probe, daemon=True)
        t.start()
        t.join(timeout=timeout_s)
    except Exception as exc:  # noqa: BLE001 — fallback must never raise
        return [], f"tower board fallback error ({type(exc).__name__})"
    if t.is_alive():
        return [], "tower board fallback timed out"
    if outcome.get("error"):
        return [], str(outcome["error"])
    return outcome.get("rows", []), str(outcome.get("note", "tower board fallback returned no rows"))

def _tower_issue_hydrate(number: int | str, timeout_s: float = 75.0) -> dict[str, Any] | None:
    """Per-issue tower hydration fallback — the mirror of _tower_board_rows (R78).

    বাংলা: R78 বোর্ড-fallback বোর্ড জীবিত রাখে (number/title/labels), কিন্তু
    envelope-মোডের hydrate-পথ body-র জন্য কেবল gh issue view-এর উপর দাঁড়িয়ে ছিল।
    gh-absent রানটাইমে ফল দুটো: auto-pick এনভেলপে problem_statement.body="" (এজেন্ট
    acceptance-criteria ছাড়া অন্ধকারে কাজ করে — SPEC §2 body-গ্যারান্টি ভাঙে), আর
    --issue N পথ সম্পূর্ণ ad-hoc এনভেলপে পতিত হয় (issue=null) — অথচ বোর্ড তখন
    tower-fallback-এ জেগে থাকে (asymmetry: বোর্ড revive আছে, hydrate নেই)। এই
    fallback একই lazy-sibling/never-raise প্যাটার্নে tower-এর live tool
    bridge.work_order দিয়ে per-issue title/body/labels/state hydrate করে।
    Transport: R78-এর urllib প্রোবই বাহক — live 2026-10-30 প্রমাণ: সিবলিং ক্লায়েন্টের
    call_tool RESPONSE_WAIT=15s-এ bridge.work_order-এর tower-side GitHub-fetch
    (>15s, Render cold tier) McpTowerTimeoutError দেয়, আর iter_lines বড়
    single-line পেলোড chunk-boundary-তে ভাঙে; urllib raw-body data-line
    এক্সট্র্যাকশন যেকোনো সাইজে/দেরিতে নিরাপদ (R78-এ ১৩৪KB-তে প্রমাণিত)। সততা:
    sanitization tower-side (bridge.work_order-এর নিজস্ব চুক্তি) — এনভেলপে
    বোর্ড-নোট সেটাই বলে।
    ফেরত: gh-shaped dict (number/title/labels/state/body) বা None — কখনো raise নয়,
    ব্যর্থতায় কলার-সাইটের আগের সৎ note অক্ষত থাকে।
    """
    outcome: dict[str, Any] = {}

    def _probe() -> None:
        try:
            sys.path.insert(0, str(REPO_ROOT / "scripts" / "agents"))
            import mcp_tower_client as _mtc  # noqa: E402  (lazy sibling import)

            base = _mtc.MCP_SERVER_URL.rstrip("/")
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }

            def _post(payload: dict[str, Any], sid: str | None, timeout: int = 30) -> tuple[str, str]:
                hdrs = dict(headers)
                if sid:
                    hdrs["mcp-session-id"] = sid
                req = urllib.request.Request(
                    f"{base}/mcp", data=json.dumps(payload).encode(), headers=hdrs, method="POST"
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.headers.get("mcp-session-id") or sid or "", resp.read().decode("utf-8", errors="replace")

            sid, _ = _post({
                "jsonrpc": "2.0", "id": "cal-hydrate-1", "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "supremeai-agent-loop", "version": "1.0"},
                },
            }, None)
            _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid, timeout=15)
            call_id = "cal-hydrate-2"
            _, body = _post({
                "jsonrpc": "2.0", "id": call_id, "method": "tools/call",
                "params": {"name": "bridge.work_order", "arguments": {"number": int(number)}},
            }, sid, timeout=60)

            # বাংলা: body হয় SSE (data: লাইন) নয়তো সরাসরি JSON — দুই শেপই সমর্থিত;
            # regex পুরো body-র উপর চলে (splitlines/iter_lines বড় single-line-এ ভাঙে)।
            envelopes: list[dict[str, Any]] = []
            for m in re.finditer(r"^data: (.*)$", body, re.MULTILINE):
                try:
                    envelopes.append(json.loads(m.group(1)))
                except json.JSONDecodeError:
                    pass
            if not envelopes:
                try:
                    envelopes.append(json.loads(body))
                except json.JSONDecodeError:
                    pass
            result: Any = None
            for env in envelopes:
                if isinstance(env, dict) and env.get("id") == call_id and "error" not in env:
                    result = env.get("result")
                    break
            text = ""
            if isinstance(result, dict) and isinstance(result.get("content"), list) and result["content"]:
                first = result["content"][0]
                if isinstance(first, dict):
                    text = first.get("text") or ""
            if not text:
                outcome["error"] = "tower work-order payload carried no text"
                return
            wo = json.loads(text)
            if not isinstance(wo, dict) or wo.get("number") is None:
                outcome["error"] = "tower work-order payload carried no number"
                return
            raw_labels = wo.get("labels")
            labels: list[Any] = []
            if isinstance(raw_labels, list):
                labels = [{"name": str(l)} for l in raw_labels]
            outcome["issue"] = {
                "number": wo.get("number"),
                "title": wo.get("title"),
                "state": wo.get("state") or "open",
                "labels": labels,
                "body": wo.get("body") or "",
            }
        except Exception as exc:  # noqa: BLE001 — hydration must never raise
            outcome["error"] = f"tower issue hydration failed ({type(exc).__name__})"

    try:
        t = threading.Thread(target=_probe, daemon=True)
        t.start()
        t.join(timeout=timeout_s)
    except Exception:  # noqa: BLE001 — hydration must never raise
        return None
    if t.is_alive():
        return None
    return outcome.get("issue")

def run_cmd(
    cmd: list[str], cwd: Path | None = None, check: bool = False, timeout: int = 300
) -> tuple[int, str, str]:
    target_cwd = cwd or REPO_ROOT
    try:
        p = subprocess.run(
            cmd,
            cwd=target_cwd,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        stdout = p.stdout.decode("utf-8", errors="replace").strip()
        stderr = p.stderr.decode("utf-8", errors="replace").strip()
        if check and p.returncode != 0:
            raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(cmd)}\n{stderr}")
        return p.returncode, stdout, stderr
    except FileNotFoundError as exc:
        err = f"Binary not found: '{cmd[0] if cmd else 'unknown'}'"
        if check:
            raise RuntimeError(err) from exc
        return 127, "", err
    except subprocess.TimeoutExpired:
        err = f"Command timed out after {timeout}s: {' '.join(cmd)}"
        if check:
            raise RuntimeError(err)
        return 124, "", err
    except Exception as exc:
        err = f"Execution error for {' '.join(cmd)}: {exc}"
        if check:
            raise RuntimeError(err) from exc
        return 1, "", err

def hooks_path_advisory() -> str | None:
    """R63/#2343 option B — start-of-run local-enforcement probe (agent-plane lane).

    বাংলা: রিপো যে `.githooks/` স্যুট (Board-Freshness pre-push গেট, #4177) শিপ করে
    সেটি git-এর ডিফল্টে কখনো সক্রিয় হয় না — সক্রিয় হতে প্রতি-ক্লোনে
    `git config core.hooksPath .githooks` দরকার (git-এর নিজস্ব anti-malware
    নীতি; Documentation/githooks.adoc), আর রিপোর কোনো পৃষ্ঠই সেই কনফিগ-লাইন
    বুটস্ট্র্যাপ করে না (R63 স্ক্যান: hooksPath/githooks শূন্য হিট)। ফলে
    Universal Invariant 1 (Dual-Rebase "0 behind pre-push")-এর স্থানীয়-স্তর
    প্রয়োগ প্রতিটি স্ট্যান্ডার্ড ক্লোনে অন্ধকার — #2322-শ্রেণির stale-base
    clobber ঠেকানোর প্রথম স্তরটাই ডিফল্টে বন্ধ। এই প্রোব সত্যিকারের worktree-তে
    unset hooksPath দেখলে ঠিক এক লাইনের সত্য-সতর্কতা stderr-এ দেয় (লুপের বিদ্যমান
    advisory-নোট শৈলী: --loop/--auto-pr নোটের মতোই; stdout-চুক্তি অস্পৃষ্ট —
    envelope-মোডের SPEC §4b stdout-purity ও dispatch stdout মার্কার-গণনা দুটোই
    অক্ষত)। git-কনফিগ মিউটেশন করে না (option D প্রত্যাখ্যাত — অপারেটর-সম্মতি);
    worktree না হলে নীরব; নেটওয়ার্ক-মুক্ত তাই offline-এও সৎ।

    Returns:
        str | None: stderr-এ মুদ্রণযোগ্য এক-লাইন advisory, বা None (সক্রিয়/প্রযোজ্য নয়)।
    """
    rc, out, _ = run_cmd(["git", "config", "--get", "core.hooksPath"], timeout=10)
    if rc == 0 and out.strip():
        return None  # বাংলা: হুক-পাথ সক্রিয় — কিছু বলার নেই।
    # বাংলা: git-রিপোজিটরি নয় এমন ডিরেক্টরিতে মিথ্যা সতর্কতা নয় — নীরব।
    rc_repo, _, _ = run_cmd(["git", "rev-parse", "--is-inside-work-tree"], timeout=10)
    if rc_repo != 0:
        return None
    return (
        "hooks-path probe: core.hooksPath is unset in this worktree — the shipped "
        ".githooks/ enforcement suite (Board-Freshness pre-push gate, #4177) stays dark "
        "by git default ($GIT_DIR/hooks). One-line activation: "
        "git config core.hooksPath .githooks"
    )

def diff_rule_freshness(
    local_shas: dict[str, str | None], remote_shas: dict[str, str | None]
) -> list[str]:
    diverged: list[str] = []
    # Preserve order of RULE_FRESHNESS_FILES first, then any extra keys
    ordered_keys: list[str] = [k for k in RULE_FRESHNESS_FILES if k in local_shas or k in remote_shas]
    for k in sorted(set(local_shas) | set(remote_shas)):
        if k not in ordered_keys:
            ordered_keys.append(k)
    for key in ordered_keys:
        loc = local_shas.get(key)
        rem = remote_shas.get(key)
        if loc != rem:
            diverged.append(key)
    return diverged

def mandatory_invariant_checklist() -> list[dict[str, Any]]:
    return [
        {"id": "zero-admin-budget", "rule": "Work budget <= 0.01%"},
        {"id": "claim-gate", "rule": "Atomic claim before branch (status:claimed)"},
        {"id": "reflection-evidence", "rule": "## Reflection Evidence with - **why:** and - **alternatives_rejected:**"},
        {"id": "p7-cohesive-sizing", "rule": "Cohesive domain slice <= 30 files / <= 200 KB diff"},
        {"id": "boundary-guard", "rule": "Satellite code strictly in domain mirrors"},
        {"id": "stale-base-guard", "rule": "Rebase origin/main at work-start AND pre-push (0 behind)"},
    ]

def _offline_requested(flag: bool) -> bool:
    if flag:
        return True
    return any(
        os.environ.get(var, "").strip().lower() in ("1", "true", "yes", "on")
        for var in OFFLINE_ENV_VARS
    )

def _print_rule_version_and_checklist() -> None:
    """R78/J484751 — rule-1 contract surface (was a silent `pass` stub).

    বাংলা: traffic-police নিয়ম ১ বলে "Always display the 5 Universal Invariant
    Pillars (Common Rules)" — অথচ এই ফাংশনটি ছিল `pass` স্টাব; step_2_rules()
    (freshness গেট) একে ডাকত কিন্তু কিছুই দৃশ্যমান হত না — চুক্তির অর্ধেক নীরব।
    সাথে mandatory_invariant_checklist() নির্মিত ও টেস্ট-পিন্ড হয়েও (test_02/03/04)
    কোনো রানটাইম ভোক্তা ছিল না — dead surface। এখন গেট-যাচাইকৃত রানে ৫টি পিলার
    (COMMON_RULES) + চুক্তি-ভার্সন + fail-closed guard চেকলিস্ট stderr-এ দৃশ্যমান হয়।
    stderr-ই চ্যানেল: --verify-only-র stdout চুক্তি পিন্ড (tier-এভিডেন্স + final
    CONTRACT_VERSION marker exactly-once, test_23/26) — সেখানে নতুন stdout লাইন
    parity-grep ভাঙত; dispatch-পথে COMMON_RULES আগের মতোই stdout-এ যায় (এই স্টাব
    dispatch-পথে ডাকা হয় না — test_27 AST-পিন)। advisory সারফেস — প্রিন্ট-ব্যর্থতা
    কখনো গেট ফেল করাবে না।
    """
    try:
        print(COMMON_RULES, file=sys.stderr)
        print(f"RULE SURFACE: {CONTRACT_VERSION} — fail-closed invariant checklist:", file=sys.stderr)
        for entry in mandatory_invariant_checklist():
            print(f"  - {entry['id']}: {entry['rule']}", file=sys.stderr)
    except Exception:  # noqa: BLE001 — advisory surface must never break the gate
        pass

def step_2_rules(offline: bool = False, auto_sync: bool = True) -> bool:
    """Step 2: Constitution freshness gate + governing-rules loading (#567)."""
    repo_root = REPO_ROOT
    missing_local = [p for p in RULE_FRESHNESS_FILES if not (repo_root / p).exists()]

    if _offline_requested(offline):
        # বাংলা: অফলাইনে সেলফ-হিল অসম্ভব — আচরণ অপরিবর্তিত (missing মানে fail)।
        if missing_local:
            log("❌", f"[Rules] offline and missing local freshness files: {missing_local}")
            return False
        _print_rule_version_and_checklist()
        return True

    code, _, err = run_cmd(["git", "fetch", "origin", "main"], cwd=repo_root)
    if code != 0:
        return False

    local_shas: dict[str, str | None] = {}
    remote_shas: dict[str, str | None] = {}
    for path in RULE_FRESHNESS_FILES:
        r_code, r_out, _ = run_cmd(
            ["git", "rev-parse", "--verify", "--quiet", f"origin/main:{path}"], cwd=repo_root
        )
        if r_code != 0:
            # বাংলা: ফাইলটি origin/main-এ আর নেই (deleted/renamed upstream)।
            # মুছে-ফেলা ফাইলকে পূর্বশর্ত করে রাখা লুপের আত্ম-পরাজয় — AGENT_RULES.md
            # ঠিক এভাবেই #1526-এ লুপটা মেরেছিল (rev-parse fail মানে exit 1 চিরকাল)।
            # তাই এই রানে গেট থেকে বাদ; fail-closed নয়, honest-skip।
            log("!", f"[Rules] {path} no longer exists on origin/main — deleted upstream; skipping this run.")
            continue
        remote_shas[path] = r_out.strip() or None
        h_code, h_out, h_err = run_cmd(["git", "hash-object", "--", path], cwd=repo_root)
        if h_code != 0:
            # বাংলা: স্থানীয় কপি নেই কিন্তু origin/main-এ আছে —
            # fetch ইমেধেই ব্যর্থ ঘোষণা নিজের সেলফ-হিল-প্রণালীকে প্রতারাধ করত।
            # এখন diverged-sync ব্রাঞ্চের মেকানিসম দিয়ে পুনরুদ্ধার করে hash করা হয়।
            c_code, _, _ = run_cmd(
                ["git", "checkout", "origin/main", "--", path], cwd=repo_root
            )
            if c_code != 0:
                log("❌", f"[Rules] {path} missing locally and self-heal from origin/main failed.")
                return False
            h_code, h_out, h_err = run_cmd(["git", "hash-object", "--", path], cwd=repo_root)
            if h_code != 0:
                return False
        local_shas[path] = h_out.strip() or None

    diverged = diff_rule_freshness(local_shas, remote_shas)

    if diverged and auto_sync:
        for path in diverged:
            c_code, _, _ = run_cmd(
                ["git", "checkout", "origin/main", "--", path], cwd=repo_root
            )
            if c_code != 0:
                return False
    elif diverged:
        # বাংলা: report-only মোডে (auto_sync=False) ড্রিফট নীরবে গিলে ফেলা যায় না —
        # চুক্তি: "drift is reported, the result stays True, and the tree is NEVER
        # mutated" (tests/test_constitution_freshness.py মডিউল-ডকস্ট্রিং, #567
        # Tier-1)। আগে diverged তালিকা কোথাও ছাপা হত না — report-only মোডের
        # "reported" প্রতিশ্রুতি অন্ধ ছিল (test_21 শুধু no-mutation pin করত,
        # রিপোর্ট লাইন কখনো assert করত না কারণ লাইনটাই ছিল না)। stdout লাইন
        # #1551/#67 চুক্তি-নিরাপদ: --verify-only-এর শেষ stdout লাইন (মার্কার) ও
        # marker-count অপরিবর্তিত; টিয়ার-এভিডেন্সের সাথে ড্রিফট-রিপোর্টও artifact-এ থাকবে।
        log(
            "!",
            "[Rules] constitution drift (report-only, not synced): " + ", ".join(diverged),
        )

    _print_rule_version_and_checklist()
    return True

def pre_push_rebase_guard() -> tuple[bool, int, str]:
    """#514 Pre-Push Rebase Invariant (Anti-Stale-Base Mandate). Fail-closed."""
    fetch_code, _, fetch_err = run_cmd(["git", "fetch", "origin", "main"])
    if fetch_code != 0:
        return False, 0, f"fetch of origin main failed: {fetch_err or 'unknown'}"
    rc, out, err = run_cmd(["git", "rev-list", "--count", "HEAD..origin/main"])
    if rc != 0:
        return False, 0, f"behind-count failed: {err or 'unknown'}"
    try:
        behind = int((out or "0").strip() or "0")
    except ValueError:
        return False, 0, f"unparseable behind-count: {out!r}"
    if behind <= 0:
        return True, 0, "fresh"
    rc, _, err = run_cmd(["git", "rebase", "origin/main"])
    if rc != 0:
        run_cmd(["git", "rebase", "--abort"])
        return False, behind, f"rebase failed; aborted: {err or ''}"
    return True, behind, f"stale ({behind} behind); rebased onto origin/main"

def pre_work_rebase_guard() -> tuple[bool, int, str]:
    """Start-of-Work Rebase Mandate (#161, #514)."""
    return pre_push_rebase_guard()

# বাংলা: পুরনো step-পাইপলাইনের মৃত ক্লাস্টার (step_4_branch, step_6_verify,
# push_branch_to_fork, step_7_record, run_cycle) বাদ দেওয়া হলো। step_6_verify ও
# push_branch_to_fork কোনো কাজ না করেই True ফেরাত — ভুয়া সাফল্য (U2)।
# step_7_record সেই দুই মিথ্যার উপর দাঁড়িয়ে ছিল; step_4_branch শাখা না
# বানিয়েও "main" নাম ফেরাত; run_cycle-এর একমাত্র কাজ ছিল step_2_rules ডাকা —
# কোনোটিই main()-এর dispatch/envelope পথ থেকে ডাকা হত না (zero importers,
# code-search যাচাইকৃত; SPEC/CONTRIBUTING-এও কোনো রেফারেন্স নেই)। ব্রাঞ্চ/
# পুশ/রেকর্ডের আসল মালিক ব্রিজ পাইপলাইন — minimal লুপ নিজে git অপারেশন
# চালায় না। সৎ pre-push/pre-work rebase গার্ড (#161, #514) অক্ষত রাখা হলো —
# এরা সত্যিকারের কাজ করে; ভবিষ্যতে বাস্তব কনজিউমার এলে সরাসরি wire করা যাবে।

def classify_task_role(
    title: str = "", labels: Iterable[str] = (), body: str = ""
) -> str:
    present = frozenset(labels)
    if "status:runway" in present:
        return "ci-fixer"
    if "gate:pre-landing" in present:
        return "task-auditor"
    if "status:claimed" in present:
        return "coder"
    return "coder"

SPECIALIST_ROLES = frozenset({"solver", "coder", "ci-fixer", "auditor", "task-auditor"})

ENVELOPE_FORBIDDEN_PATHS = [".env*", "secrets/**", "credentials/**", "vault/**"]

PRIORITY_TIER_LABELS = ("P0", "P1", "P2", "P3", "P4")

def _detect_priority(labels: Iterable[str]) -> str:
    names = [str(l).lower() for l in labels]
    for marker, tier in (("p0", 0), ("p1", 1), ("p2", 2), ("p3", 3)):
        if any(name == marker or name.startswith(marker + "-") or name.startswith(marker + " ") for name in names):
            return PRIORITY_TIER_LABELS[tier]
    return "P4"

def _detect_group(labels: Iterable[str]) -> str:
    for name in sorted({str(l).lower() for l in labels}):
        if name in VALID_GROUPS:
            return name
    return DEFAULT_GROUP

def build_task_envelope(
    issue: dict[str, Any] | None,
    group: str = "",
    role_override: str = "",
    board_note: str = "",
) -> dict[str, Any]:
    """বাংলা: AGENT_LOOP_SPEC.md §2-র canonical task-envelope-v1 এমিট করে।

    আগে --task-envelope শুধু একটা স্টাব ছাপত {"task_contract": {"version": 1,
    "task_type": "IMPLEMENT"}} — task_id/issue/role/scope/admin_gate কিছুই ছিল না;
    ডাউনস্ট্রিম এজেন্ট envelope পেয়েও কাজ করতে পারত না। এখন বোর্ড-থেকে-পাওয়া
    issue payload (বা --issue N, বা --allow-adhoc) থেকে সৎ, deterministic
    envelope তৈরি হয়: role classify_task_role() থেকে, group fail-closed রেজিস্ট্রি
    থেকে, priority label-থেকে। body ফিল্ড hydrate-পথে (gh issue view
    --json …,body) অন্তর্ভুক্ত — SPEC §2 problem_statement.body-র স্কিমা-মান;
    hydrate ব্যর্থ/অনুপস্থিত হলে মিথ্যা খালি string নয়, কী-ই বাদ (সৎ absence)।
    """
    labels: list[str] = []
    title = ""
    issue_number: str | None = None
    state = "open"
    body = ""
    if isinstance(issue, dict):
        issue_number = str(issue.get("number")) if issue.get("number") is not None else None
        title = str(issue.get("title", "") or "")
        state = str(issue.get("state", "open") or "open")
        body = str(issue.get("body", "") or "")
        raw_labels = issue.get("labels")
        if isinstance(raw_labels, list):
            labels = [
                str(l.get("name", "")).lower() if isinstance(l, dict) else str(l).lower()
                for l in raw_labels
            ]

    resolved_group = group or _detect_group(labels)
    classified = classify_task_role(title=title, labels=labels)
    role = classified
    if role_override:
        if role_override in SPECIALIST_ROLES or role_override in ROLE_RULES:
            role = role_override
        else:
            # বাংলা: অজানা role-এ নীরব গ্রহণ নয় — সৎ warning ও classified fallback।
            log("!", f"[Envelope] unknown --role '{role_override}'; falling back to classified role '{classified}'")
            role = classified

    role_description = ROLE_RULES.get(
        role,
        ROLE_RULES["solver"] if role in ("coder", "solver") else "Execute role objectives strictly.",
    )

    specialist_prompt = "\n".join(
        [
            COMMON_RULES,
            "",
            f"ROLE: {role}",
            f"MANDATE: {role_description}",
            "PR BLUEPRINT: PR must carry 'Closes #<issue_number>' in PR description to automatically close the resolved issue on merge.",
            "CONTINUOUS DISPATCH: After completing this task, rerun continuous agent loop again.",
            "STALE-INCIDENT GUARD (U3): before claiming a CI-failure incident, verify on live main that the referenced run still fails; resolved incidents are skipped with evidence, never re-solved. The picker also auto-demotes mechanically (#3050): an incident whose referenced run is superseded by >=5 green main runs of the same workflow (zero newer reds) is skipped at pick time — for explicit --issue N dispatches this manual check remains the backstop.",
            # বাংলা: কিউ-স্তরের claim লেবেল tower-এর লাইভ claim-কে পিছিয়ে থাকে (live
            # 2026-10-28: ৩ সারি >=১৯ মিনিট ধরে status:unclaimed দেখিয়েছে যদিও claim
            # স্ট্যাম্প হয়ে গিয়েছিল — #2111, #2123, #2102; স্থায়ী প্রোব
            # scripts/queue_consistency_probe.py R2)। ভুল লেবেল-ডেটা লুপের কোডে ঠিক হয়
            # না (b3dfbbe ব্রিজ-স্টেট বাদ দেয়, ভুল ডেটা নয়) — তাই সৎ প্রতিকার:
            # এজেন্টকে claim-এর আগে feedback-plane যাচাইয়ের নির্দেশ।
            "STALE-CLAIM GUARD: board claim labels can lag live tower claims (2026-10-28: 3 rows dispatched as unclaimed were claimed >=19min earlier; #2111, #2123, #2102). Label 'unclaimed' is advisory: re-verify claimability via the feedback plane (bridge_read_feedback latestClaim) immediately before work_claim; on atomic-claim rejection move to the next candidate - never retry the same row.",
        ]
    )

    envelope: dict[str, Any] = {
        "envelope_version": 1,
        "output_format": "task-envelope-v1",
        "task_id": f"task-{issue_number}" if issue_number else "task-adhoc",
        "issue": issue_number,
        "task_type": "IMPLEMENT",
        "group": resolved_group,
        "priority": _detect_priority(labels),
        "objective": title or ("Ad-hoc task — objective supplied by the calling agent." if not issue_number else ""),
        "role": role,
        "role_policy": "contributor",
        "role_description": role_description,
        "scope": {
            "touching_files": [],
            "forbidden_paths": list(ENVELOPE_FORBIDDEN_PATHS),
        },
        "acceptance": [],
        "verification": [],
        "required_evidence": ["Reflection Evidence (why + alternatives_rejected)"],
        "stop_conditions": [],
        "admin_gate": {"required": False, "status": "NOT_REQUIRED"},
        "specialist_prompt": specialist_prompt,
        "submission": {
            "pathway": "bridge_submit_patch | pull_request",
            "reference": "AGENTS.md §2.1 Pathway 1 + §8 (bridge_submit_patch)",
            "base_branch": "main",
            "pr_title_prefix": "fix(open):",
            "issue_reference_required": True,
            "branch_convention": "^(feat|fix|docs|chore|test|refactor|perf|bridge|group|contributor|hotfix|release|agent)/<slug>",
        },
    }
    if issue_number is not None:
        # বাংলা: আগে `if labels:` ছিল — লেবেলহীন issue-র গোটা problem_statement
        # হারিয়ে যেত; SPEC §2-তে এটি issue-ভিত্তিক, label-ভিত্তিক নয়।
        problem_statement: dict[str, Any] = {
            "id": issue_number,
            "title": title,
            "labels": labels,
            "state": state,
        }
        if body:
            problem_statement["body"] = body
        envelope["problem_statement"] = problem_statement
    if board_note:
        envelope["board_note"] = board_note
    return {"task_envelope": envelope}

def load_cadence_config(path: Path | None = None) -> dict[str, Any]:
    target = path or CADENCE_FILE
    try:
        if not target.exists():
            return {
                "cadences_hours": dict(DEFAULT_CADENCE_HOURS),
                "merged_roles": dict(DEFAULT_MERGED_ROLES),
            }
        with target.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        cadences = data.get("cadences_hours") or {}
        merged = data.get("merged_roles") or {}
        cleaned = {str(k): int(v) for k, v in cadences.items() if str(v).isdigit() and int(v) > 0}
        return {
            "cadences_hours": cleaned or dict(DEFAULT_CADENCE_HOURS),
            "merged_roles": merged or dict(DEFAULT_MERGED_ROLES),
        }
    except Exception:
        return {
            "cadences_hours": dict(DEFAULT_CADENCE_HOURS),
            "merged_roles": dict(DEFAULT_MERGED_ROLES),
        }

def canonical_role(role: str, config: dict[str, Any] | None = None) -> str:
    cfg = config or load_cadence_config()
    merged = cfg.get("merged_roles", DEFAULT_MERGED_ROLES)
    return merged.get(role, role)

def load_last_run_store(path: Path | None = None) -> dict[str, float]:
    target = path or STATE_FILE
    try:
        if not target.exists():
            return {}
        with target.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {str(k): float(v) for k, v in data.items() if str(v).replace(".", "", 1).isdigit()}
    except Exception:
        return {}

def save_last_run_store(store: dict[str, float], path: Path | None = None) -> bool:
    target = path or STATE_FILE
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(store, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False

def load_issue_lease_store(path: Path | None = None) -> dict[str, float]:
    """বাংলা: ডিসপ্যাচ করা ইস্যুগুলোর টাইমস্ট্যাম্প লোড করে (৩০ মিনিটের স্বয়ংক্রিয় লিজ ট্র্যাকিং)"""
    target = path or ISSUE_LEASE_FILE
    try:
        if not target.exists():
            return {}
        with target.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {str(k): float(v) for k, v in data.items() if str(v).replace(".", "", 1).isdigit()}
    except Exception:
        return {}

def mark_issue_leased(issue_number: str | int, now: float | None = None, path: Path | None = None) -> bool:
    """বাংলা: ইস্যু ডিসপ্যাচ হওয়ার সাথে সাথে টাইমস্ট্যাম্প রেকর্ড করে অন্য এজেন্টের কনফ্লিক্ট আটকায়"""
    target = path or ISSUE_LEASE_FILE
    now_ts = now if now is not None else time.time()
    store = load_issue_lease_store(target)
    # বাংলা: লেখার সময় মেয়াদোত্তীর্ণ entry প্রুন হয় — ফাইলে সর্বোচ্চ ৩০-মিনিট উইন্ডোর
    # তরুণ লিজ + এই মুহূর্তে লেখা entry থাকে। claimability-চেক উইন্ডোর বাইরের entry
    # যেকোনো অবস্থাতেই উপেক্ষা করে, তাই প্রুনিং আচরণ-নিরপেক্ষ — শুধু ফাইল সীমাবদ্ধ থাকে।
    store = {k: v for k, v in store.items() if (now_ts - v) < ISSUE_LEASE_SECONDS}
    store[str(issue_number)] = now_ts
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(store, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False

def role_is_due(
    role: str,
    last_run_ts: float | None,
    now_ts: float,
    config: dict[str, Any] | None = None,
) -> bool:
    cfg = config or load_cadence_config()
    cadences = cfg.get("cadences_hours", DEFAULT_CADENCE_HOURS)
    canon = canonical_role(role, cfg)
    hours = cadences.get(canon) or cadences.get(role)
    if not hours or hours <= 0:
        return False
    if last_run_ts is None:
        return True
    return ((now_ts - float(last_run_ts)) / 3600.0) >= hours

def due_roles(
    last_runs: dict[str, float] | None,
    now_ts: float | None = None,
    config: dict[str, Any] | None = None,
) -> list[str]:
    cfg = config or load_cadence_config()
    store = last_runs or {}
    now = now_ts if now_ts is not None else time.time()
    # বাংলা: state কী-ও অবশ্যই canonical হতে হবে। mark_role_run() একটি
    # merged-source role-এর টাইমস্ট্যাম্প canonical কী-তে লেখে (যেমন
    # task-auditor → auditor), তাই read-ও সেই একই কী থেকে হতে হবে —
    # নইলে canonical API নিজের mark নিজেই দেখে না এবং role প্রতি সাইকেলে
    # আবার due হয়ে যায় (state-key drift, ট্রাফিক-পুলিশ নিয়ম ৪ ভাঙে)।
    # ডিফল্ট কনফিগে canonical_role() identity — আচরণ বাইট-অপরিবর্তিত।
    return [r for r in cfg.get("cadences_hours", DEFAULT_CADENCE_HOURS) if role_is_due(r, store.get(canonical_role(r, cfg)), now, cfg)]

def mark_role_run(
    role: str,
    store: dict[str, float],
    now_ts: float | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, float]:
    cfg = config or load_cadence_config()
    canon = canonical_role(role, cfg)
    store[canon] = now_ts if now_ts is not None else time.time()
    return store

def run_verify() -> list[dict[str, Any]]:
    """Honest 8-tier verification (U2 truth — no fabricated PASS).

    বাংলা: প্রতিটি টিয়ার এখন সত্যিই চেক হয় (সস্তা, dependency-মুক্ত সেলফ-চেক);
    ব্যর্থ বা exception হলে passed=False। আগের সংস্করণ ৮টি টিয়ারই শর্তহীনভাবে
    PASS ছাপাত — যাচাই-ভয়াবহতা (false assurance) U2 লঙ্ঘন; পুরনো ১২৫০-লাইন
    লুপে এই ত্রুটি PR #1498 ঠিক করেছিল, #1526 রিরাইটে আবার ফিরে এসেছিল।

    চুক্তি: টিয়ার এমিশন অবশ্যই লিটারাল {"tier": N, ...} ডিক্ট হতে হবে —
    Loop-Contract Parity Guard (#118) এই লিটারাল প্যাটার্ন grep করে docs/
    AGENT_LOOP_SPEC.md §4-এর "tiers 1–8" SSOT-এর সাথে মেলায় (fail-closed)।
    তাই ফাংশন-কল দিয়ে ভ্যারিয়েবল-জাত dict বানানো যাবে না; honesty ও
    লিটারাল-এমিশন দুটোই একসাথে রাখতে হবে।
    """

    def _run(fn: Any) -> bool:
        try:
            return bool(fn())
        except Exception:
            return False

    def _json_ok() -> bool:
        # বাংলা: থাকা ফাইলগুলো অবশ্যই বৈধ JSON হতে হবে; অনুপস্থিত হলে বাধা নেই।
        for p in (CADENCE_FILE, STATE_FILE):
            if p.exists():
                json.loads(p.read_text(encoding="utf-8"))
        return True

    def _yaml_ok() -> bool:
        wf = REPO_ROOT / ".github" / "workflows"
        if not wf.is_dir():
            return False
        files = [p for p in wf.iterdir() if p.suffix in (".yml", ".yaml")]
        return bool(files) and all(p.stat().st_size > 0 for p in files)

    def _binary_ok() -> bool:
        agents_dir = REPO_ROOT / "scripts" / "agents"
        for p in agents_dir.glob("*.py"):
            blob = p.read_bytes()
            if b"\x00" in blob or b"\x7fELF" in blob:
                return False
        return True

    evidence: list[dict[str, Any]] = [
        {
            "tier": 1,
            "name": "syntax_py_compile",
            "passed": _run(
                lambda: compile(
                    Path(__file__).read_text(encoding="utf-8"),
                    "continuous_agent_loop.py",
                    "exec",
                )
                is not None,
            ),
        },
        {"tier": 2, "name": "json_validity", "passed": _run(_json_ok)},
        {"tier": 3, "name": "yaml_validity", "passed": _run(_yaml_ok)},
        {"tier": 4, "name": "binary_guard", "passed": _run(_binary_ok)},
        {
            "tier": 5,
            "name": "contract_guard",
            "passed": _run(lambda: CONTRACT_VERSION == "agent-loop-contract/1"),
        },
        {
            "tier": 6,
            "name": "group_registry_guard",
            "passed": _run(
                lambda: isinstance(VALID_GROUPS, frozenset) and "core" in VALID_GROUPS
            ),
        },
        {
            "tier": 7,
            "name": "envelope_determinism",
            "passed": _run(
                lambda: build_task_contract("verify-probe")
                == build_task_contract("verify-probe")
            ),
        },
        {
            "tier": 8,
            "name": "machine_path_isolation",
            "passed": _run(
                lambda: Path(__file__).resolve().parents[2] == REPO_ROOT
                and (REPO_ROOT / "scripts" / "agents").is_dir()
            ),
        },
    ]

    for ev in evidence:
        print(f"[{ev['tier']}/8] {ev['name']}: {'PASS' if ev['passed'] else 'FAIL'}")
    print(f"CONTRACT_VERSION={CONTRACT_VERSION}")
    return evidence

def run_dispatch_cycle(args: argparse.Namespace) -> int:
    """One dispatch cycle: board query → solver/envelope dispatch or cadence role.

    বাংলা: একক সাইকেলের পরিষ্কার ডিসপ্যাচ এক্সিকিউশন। বাহ্যিক শিডিউলার বা রানার
    দ্বারা সাইকেল পরিচালিত হয়।
    """
    # বাংলা: R63/#2343 option B — start-of-run স্থানীয়-প্রয়োগ প্রোব। ডিসপ্যাচ-পথের
    # একেবারে শুরুতে একবার; সতর্কতাটি সবসময় stderr-এ (envelope-মোডের stdout-purity
    # ও dispatch stdout মার্কার-গণনা অস্পৃষ্ট)। --verify-only পথ এখানে পৌঁছায় না
    # (main()-এ আগেই রিটার্ন করে) — তাই বুট-স্মোকের stderr-চুক্তিও বাইট-অপরিবর্তিত।
    advisory = hooks_path_advisory()
    if advisory:
        print(advisory, file=sys.stderr)
    cmd = [
        "gh", "issue", "list",
        "--repo", UPSTREAM_REPO,
        "--json", "number,labels",
        "--state", "open",
        # R78/J484751: 100 → 200 — pick_next_issue()-র নিজস্ব gh-কোয়েরির সাথে উইন্ডো
        # SSOT-প্যারিটি; লাইভ বোর্ডে ১১৫+ খোলা সারি থাকায় ১০০-র জানালা নীরবে
        # প্রাপ্য-তালিকা কেটে দিত (P1/P2 সারি পুরো দেখার আগেই উইন্ডো শেষ)।
        "--limit", "200",
    ]
    # বাংলা: main() এখানে run_cmd() বাইপাস করে সরাসরি subprocess.run() ডাকছিল —
    # gh CLI অনুপস্থিত মেশিনে FileNotFoundError ছুঁড়ে পুরো লুপ crash করত
    # (স্ট্যাকট্রেস সহ)। এখন সৎভাবে জানায় বোর্ড জিজ্ঞেস করা যায়নি, solver
    # dispatch বাদ দিয়ে cadence পাথ চলতে থাকে — নীরব মিথ্যা "clean" নয়।
    # --repo UPSTREAM_REPO: দুই কপির বোর্ড SSOT এখন pick_next_issue()-এর সাথে
    # একই — আগে cwd-র remote-নির্ভর query ছিল, private mirror থেকে চালালে ভুল
    # বোর্ড পড়ত। gh non-zero exit এখন "empty board" নয়, সৎ board_unavailable।
    board_unavailable = False
    board_error = ""
    raw: list[dict[str, Any]] = []
    if _offline_requested(getattr(args, "offline", False)):
        # বাংলা: --offline আগে শুধু parse হতো, main-path একে উপেক্ষা করত —
        # অফলাইন মেশিনেও লুপ নেটওয়ার্কে gh কল করত ও timeout খেত। এখন সৎভাবে
        # বোর্ড-কোয়েরি বাদ (step_2_rules()-এর offline আচরণের সাথে একরূপ)।
        board_unavailable = True
        board_error = "offline mode (--offline/OFFLINE env): board query honestly skipped"
    else:
        try:
            p = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, errors="replace")
            if p.returncode != 0:
                board_unavailable = True
                board_error = (p.stderr or "").strip() or f"gh exit code {p.returncode}"
            elif p.stdout.strip():
                try:
                    parsed = json.loads(p.stdout)
                    raw = parsed if isinstance(parsed, list) else []
                except Exception:
                    board_unavailable = True
                    board_error = "unparseable gh issue list output"
        except FileNotFoundError:
            board_unavailable = True
            board_error = "gh CLI not found on PATH"

        # বাংলা: R78/J484751 — gh ব্যর্থ/অনুপস্থিত হলে tower-বোর্ড fallback। বোর্ড
        # তখন খালি নয়, অদৃশ্য ছিল; tower queue zero-credential reachable হওয়ায়
        # solver dispatch ও P0-গেট দুটোই প্রাণ ফিরে পায় (বিস্তারিত
        # _tower_board_rows()-এর ডকস্ট্রিং-এ)। --offline পথ এই else-ব্রাঞ্চে আসেই না
        # (offline মানে নেটওয়ার্ক নেই — fallback সেখানে অবাঞ্ছিত)। fallback সফল হলে
        # board_unavailable=False; দুই প্লেনই অন্ধকার হলে আগের সৎ skip-লাইন ও
        # gh-absent honesty floor (test-pinned) অপরিবর্তিত থাকে।
        if board_unavailable and not raw:
            fb_rows, fb_note = _tower_board_rows()
            if fb_rows:
                raw = fb_rows
                board_unavailable = False
                board_error = f"gh board query failed ({board_error}); revived via {fb_note}"
                # বাংলা: fallback-নোট stderr-এ — dispatch-stdout মার্কার-গণনা ও
                # envelope-মোডের stdout-purity অস্পৃষ্ট (hooks_path_advisory-এর
                # একই চ্যানেল-শৃঙ্খলা)।
                print(
                    f"! board query revived: {board_error}",
                    file=sys.stderr,
                )

    envelope_mode = args.task_envelope or args.emit_prompt or args.emit_contract

    if envelope_mode:
        # বাংলা: SPEC §4b — envelope মোডে banner (COMMON_RULES) stderr-এ যায়,
        # stdout শুধুই envelope JSON থাকে যাতে pipe/parse নিরাপদ থাকে।
        print(COMMON_RULES, file=sys.stderr)
        print("=" * 52, file=sys.stderr)
        if args.emit_prompt or args.emit_contract:
            print(
                "DEPRECATED: --emit-prompt/--emit-contract are shims for --task-envelope "
                "(AGENT_LOOP_SPEC §4); removal is gated on private-mirror parity — do not remove in a drive-by change.",
                file=sys.stderr,
            )

        target_issue: dict[str, Any] | None = None
        note = ""
        if args.issue:
            # বাংলা: --issue N → নির্দিষ্ট issue-র সৎ এনভেলপ; gh ব্যর্থ হলে
            # crash নয়, সৎ board_note সহ envelope (নীরব স্টাব নয়)।
            if board_unavailable:
                note = f"issue board unavailable ({board_error}); envelope emitted without problem_statement"
            else:
                v_cmd = [
                    "gh", "issue", "view", str(args.issue),
                    "--repo", UPSTREAM_REPO,
                    "--json", "number,title,labels,state,body",
                ]
                try:
                    vp = subprocess.run(v_cmd, cwd=REPO_ROOT, capture_output=True, text=True, errors="replace")
                    if vp.returncode != 0:
                        note = f"gh issue view {args.issue} failed: {(vp.stderr or '').strip() or vp.returncode}"
                    else:
                        target_issue = json.loads(vp.stdout)
                except FileNotFoundError:
                    note = "gh CLI not found on PATH"
                except Exception as exc:
                    note = f"gh issue view error: {exc}"
                if target_issue is None and note:
                    # বাংলা: R78 board-fallback-এর আয়না — gh অনুপস্থিত/ব্যর্থ হলে
                    # tower bridge.work_order দিয়ে per-issue hydrate। এর আগে --issue N
                    # পথ gh-absent মেশিনে সম্পূর্ণ ad-hoc এনভেলপে পতিত হত (task-adhoc,
                    # issue=null) — বোর্ড tower-fallback-এ জীবিত থাকলেও। hydrate সফল
                    # হলে সত্যিকারের issue-বাউন্ড এনভেলপ যায় ও lease mark কাজ করে;
                    # ব্যর্থ হলে আগের সৎ note অক্ষত থাকে (নীরব স্টাব নয়)।
                    hydrated = _tower_issue_hydrate(args.issue)
                    if hydrated is not None:
                        target_issue = hydrated
                        note = (f"gh issue view unavailable; hydrated via tower work-order "
                                f"fallback (issue {args.issue})")
        elif board_unavailable:
            note = f"issue board unavailable ({board_error}); envelope emitted without problem_statement"
        else:
            # বাংলা: SPEC §4b stdout-purity — envelope-মোডে pick-প্রি-ভেরিফাই অ্যাডভাইজরি
            # stderr-এ যায় (log_fn=_stderr_log), stdout শুধুই envelope JSON; ডিসপ্যাচ-পথে
            # (নিচের সাইট) default log_fn=log অপরিবর্তিত — stdout-মার্কার গণনা অক্ষত।
            picked = pick_next_issue(issues=raw, claim_probe=_feedback_claim_active, log_fn=_stderr_log, incident_probe=_probe_incident_stale, premise_probe=_probe_premise_delivered)
            if picked:
                target_issue = next((i for i in raw if str(i.get("number")) == picked), None)
                # বাংলা: board query-র list payload-এ title থাকে না (gh issue list
                # --json number,labels) — auto-pick পথে target_issue শুধু number+labels
                # বহন করত, ফলে এমিটেড envelope-এ objective="" যেত এবং এজেন্ট
                # envelope পেয়েও কাজটা কী তা বুঝতে পারত না (SPEC §2 objective ফাঁকা)।
                # --issue পথের মতোই নির্বাচিত issue-র title/state/body hydrate করা হয়;
                # body ছাড়া এজেন্ট acceptance criteria না-জেনে অন্ধকারে কাজ করত
                # (SPEC §2 problem_statement.body স্কিমার অংশই)। hydrate ব্যর্থ হলে
                # সৎ board_note — নীরব খালি objective নয়।
                # বাংলা: hydrate-ট্রিগার শুধু title-অনুপস্থিতিতে সীমাবদ্ধ রাখলে
                # ভবিষ্যতে board payload-এ title যোগ হলে (যেমন --json
                # number,title,labels) body-হীন envelope নীরবে বেরিয়ে যেত —
                # SPEC §2-এর body-গ্যারান্টি ট্রিগার-শেপ-কাপলিং ভেঙে পড়ত
                # (U4 fallback false-positive-এর একই শেপ-কাপলিং ক্লাস)। তাই
                # title বা body — যেকোনো একটা অনুপস্থিত হলেই hydrate: আজকের
                # payload-এ (number,labels) আচরণ অপরিবর্তিত, ভবিষ্যতের যেকোনো
                # board-query শেপে title+body নিশ্চিত।
                if target_issue is not None and (
                    target_issue.get("title") is None or target_issue.get("body") is None
                ):
                    h_cmd = [
                        "gh", "issue", "view", str(picked),
                        "--repo", UPSTREAM_REPO,
                        "--json", "number,title,labels,state,body",
                    ]
                    try:
                        hp = subprocess.run(h_cmd, cwd=REPO_ROOT, capture_output=True, text=True, errors="replace")  # nosec B603 — list-argv repo-pinned verifier command, same class as the 3 baseline-absorbed sites (#2081 audit)
                        if hp.returncode == 0 and hp.stdout.strip():
                            target_issue = json.loads(hp.stdout)
                        else:
                            note = f"gh issue view {picked} failed: {(hp.stderr or '').strip() or hp.returncode}; envelope emitted without title/body"
                    except FileNotFoundError:
                        note = "gh CLI not found on PATH; envelope emitted without title/body"
                    except Exception as exc:
                        note = f"gh issue view error: {exc}; envelope emitted without title/body"
                    # বাংলা: SPEC §2 body-গ্যারান্টি — auto-pick পথে hydrate-ট্রিগার
                    # (title/body অনুপস্থিতি) gh ব্যর্থ হলে এতদিন শুধু খালি body-র
                    # এনভেলপ রেখে দিত; tower work-order fallback সেটাই পূরণ করে
                    # (একই চুক্তি: note সৎ, objective খালি নয়)।
                    if target_issue is not None and (
                        target_issue.get("title") is None or target_issue.get("body") is None
                    ):
                        hydrated = _tower_issue_hydrate(picked)
                        if hydrated is not None:
                            target_issue = hydrated
                            note = (f"gh issue view unavailable; hydrated via tower "
                                    f"work-order fallback (issue {picked})")
            elif not args.allow_adhoc:
                print(
                    "No claimable issue on the board. Pass --allow-adhoc to emit an ad-hoc envelope.",
                    file=sys.stderr,
                )
                return 1

        # বাংলা: envelope-পথেও lease mark হবে — mark_issue_leased() আগে শুধু
        # dispatch-পথে ছিল; কিন্তু --task-envelope auto-pick এবং --issue N — এই দুই
        # পথেও issue এজেন্টকে অর্পণই হয়, lease ছাড়া একই মেশিনে ৩০ মিনিটের মধ্যে
        # পুনঃরান করলে pick_next_issue একই issue আবার বেছে নিত (lease-ফিচার যে
        # ডুপ্লিকেট-ডিসপ্যাচ আটকায় তা SPEC-ক্যাননিকাল envelope মোডেই ঘটত)।
        # শুধু সত্যিকারের resolved target-এ mark — board-unavailable/ad-hoc এনভেলপে নয়।
        if target_issue is not None and target_issue.get("number") is not None:
            mark_issue_leased(target_issue["number"])
        # item 15 R2 — dark-scan honesty on the envelope: when the anonymous
        # merged-citation fetch failed this run, the envelope carries an
        # explicit board_note instead of silently serving an unverified premise.
        dark_note = landing_crossscan_advisory()
        if dark_note:
            note = f"{note}; {dark_note}" if note else dark_note
            _stderr_log("!", f"envelope premise advisory: {dark_note}")
        envelope = build_task_envelope(
            target_issue,
            group=args.group,
            role_override=args.role,
            board_note=note,
        )
        print(json.dumps(envelope, indent=2))
        return 0

    print(COMMON_RULES)
    print("=" * 52)

    if args.auto_pr:
        # বাংলা: pipeline.yml workflow_dispatch --auto-pr পাঠায় (#89)। minimal
        # লুপ নিজে PR খোলে না — সৎ stderr নোট, stdout অপরিবর্তিত।
        print(
            "--auto-pr: pipeline-parity flag — the minimal loop opens no PR itself; "
            "auto_bridge_pr_opener.py owns PR opening in the workflow.",
            file=sys.stderr,
        )
    if board_unavailable:
        log("!", f"issue board unavailable ({board_error}) — skipping solver dispatch. Cadence roles still evaluated.")
        if board_error == "gh CLI not found on PATH":
            # R61/#2318 option B honesty floor — on a gh-less runtime the board
            # is not empty, it is UNSEEN: report the dark P0 gate + live tower
            # queue depth instead of implying an empty board. Best-effort,
            # never raises/hangs (see _tower_queue_floor).
            log("!", _tower_queue_floor())
    else:
        picked = pick_next_issue(issues=raw, claim_probe=_feedback_claim_active, incident_probe=_probe_incident_stale, premise_probe=_probe_premise_delivered)
        if picked:
            # বাংলা: classify_task_role() এখন dispatch-এ তার সত্যিকারের কাজ পায় —
            # status:runway → ci-fixer, gate:pre-landing → task-auditor হলেও
            # dispatch টেক্সটে শুধু সৎ classification-নোট যোগ হয়; solver-এর
            # claim-first mandate অপরিবর্তিত (#1530-র zero-dispatch-change শৃঙ্খলা)।
            picked_issue = next((i for i in raw if str(i.get("number")) == picked), None)
            picked_labels = []
            if isinstance(picked_issue, dict) and isinstance(picked_issue.get("labels"), list):
                picked_labels = [
                    str(l.get("name", "")).lower() for l in picked_issue["labels"] if isinstance(l, dict)
                ]
            classified = classify_task_role(labels=picked_labels)
            dispatch_role = args.role or "solver"
            if args.role and args.role not in SPECIALIST_ROLES and args.role not in ROLE_RULES:
                log("!", f"unknown --role '{args.role}'; dispatching as solver")
                dispatch_role = "solver"
            mandate = ROLE_RULES.get(
                dispatch_role,
                ROLE_RULES["solver"] if dispatch_role in ("coder", "solver") else "Execute role objectives strictly.",
            )
            concurrency = "Unlimited concurrency allowed" if dispatch_role in ("solver", "coder") else "Single-runner role lock"
            suffix = f" (classified specialist: {classified})" if classified not in ("coder", "solver") and dispatch_role in ("solver", "coder") else ""
            mark_issue_leased(picked)
            print(f"ASSIGNED ROLE: {dispatch_role}{suffix} ({concurrency})\nROLE MANDATE: {mandate}")
            print(action_instruction(picked))
            print("CONTINUOUS DISPATCH: After completing this task, rerun continuous agent loop again.")
            print("STALE-INCIDENT GUARD (U3 Live Validity): before claiming a CI-failure incident, verify on live main that the referenced run still fails; resolved incidents are skipped with evidence, never re-solved. The picker auto-demotes superseded incidents at pick time (#3050); this manual check remains the backstop for explicit --issue N dispatches.")
            # বাংলা: STALE-CLAIM GUARD — envelope-এর specialist_prompt-এর সাথে সমান্তরাল
            # (U3-র দুই-স্তর প্যাটার্ন)। কিউ-লেবেল লাইভ claim-কে পিছিয়ে থাকায়
            # status:unclaimed পরামর্শ মাত্র, সত্য নয়; work_claim-এর আগে
            # bridge_read_feedback দিয়ে latestClaim যাচাই বাধ্যতামূলক, আর
            # atomic-claim rejection হলে একই সারি রিট্রাই নয় — পরের প্রার্থী।
            print("STALE-CLAIM GUARD: board claim labels can lag live tower claims (2026-10-28: 3 rows dispatched as unclaimed were claimed >=19min earlier; #2111, #2123, #2102). Label 'unclaimed' is advisory: re-verify claimability via the feedback plane (bridge_read_feedback latestClaim) immediately before work_claim; on atomic-claim rejection move to the next candidate - never retry the same row.")
            return 0

    cfg = load_cadence_config()
    cadence = cfg.get("cadences_hours", {})
    state = load_last_run_store()
    now = time.time()

    # বাংলা: docstring-এর traffic-police নিয়ম ৩ ("If no open issues exist ->
    # Reset/zero cadence timers so scheduled roles can run immediately") আগে
    # কোডে কখনো বাস্তবায়িত হয়নি — স্থায়ীভাবে ব্যস্ত বোর্ডে শিডিউল-রোলগুলো
    # চিরকালে অপেক্ষা করত। বোর্ড সত্যিই খালি (query সফল, raw শূন্য) হলে এখন
    # টাইমার রিসেট হয় এবং এই সাইকেলেই প্রথম cadence রোল তাৎক্ষণিক চলে।
    if not board_unavailable and not raw and state:
        state = {}
        save_last_run_store(state)
        log("*", "board is clean — cadence timers reset (docstring rule 3); scheduled roles may run immediately.")

    # বাংলা: cadence due-check এখন এক SSOT-এ — canonical API (due_roles →
    # role_is_due → mark_role_run)। আগের inline হিসাব state[role] কাঁচা কী-তে
    # পড়ত-লিখত এবং merged_roles উপেক্ষা করত; ফলে canonical mark অদৃশ্য হয়ে
    # একই লজিক্যাল role বারবার ডিসপ্যাচ হত (live main 3a2dabf-এ প্রমাণিত:
    # mark_role_run('task-auditor') → store['auditor'], inline loop
    # store['task-auditor'] খোঁজে — ১০ ঘণ্টা পরেও পুনঃ-ডিসপ্যাচ; ট্রাফিক-পুলিশ
    # নিয়ম ৪ ভাঙে)। due_roles() cadences_hours-এর ক্রমেই ফেরে, তাই প্রথম due
    # role আগের মতোই প্রথমটি — ডিসপ্যাচ টেক্সট ও ক্রম বাইট-অপরিবর্তিত;
    # ডিফল্ট কনফিগে canonical_role() identity, তাই আচরণে কোনো পরিবর্তন নেই।
    # immediate state-advance (নিয়ম ৪) অক্ষত: mark → save → print → return।
    # বাংলা: P0 Drainage Invariant (Rule 5) — যদি বোর্ডে কোনো P0-critical
    # ইস্যু সক্রিয় থাকে (এমনকি অন্য রানার যদি অস্থায়ী লিজ নিয়েও থাকে), তবুও
    # কোনো রুটিন অডিট/স্কাউট রোল রান হবে না যাতে ব্যাকলগ আটকে রেখে অগুরুত্বপূর্ণ
    # কাজ না হয়। P0 সমাধান না হওয়া পর্যন্ত ক্যাডেন্স স্থগিত থাকবে।
    if not board_unavailable and has_open_p0_blocker(raw):
        log("!", "P0 Drainage Invariant: Active P0-critical blocker detected on board. Holding cadence roles until P0 issues are resolved.")
        print("ACTION: System is draining P0-critical architectural backlog. Routine cadence roles held.")
        return 0

    for role in due_roles(state, now, cfg):
        mark_role_run(role, state, now, cfg)
        save_last_run_store(state)
        mandate = ROLE_RULES.get(role, "Execute role objectives strictly.")
        print(f"ASSIGNED ROLE: {role} (Single-runner role lock)\nROLE MANDATE: {mandate}")
        print("CONTINUOUS DISPATCH: After completing this task, rerun continuous agent loop again.")
        return 0

    print("ACTION: System is clean and up to date.")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI Minimal Continuous Loop")
    parser.add_argument("--verify-only", action="store_true", help="Run 8-tier verification only")
    parser.add_argument("--task-envelope", action="store_true", help="Emit the canonical task-envelope-v1 JSON (SPEC §2)")
    parser.add_argument("--emit-prompt", action="store_true", help="Deprecated shim for --task-envelope")
    parser.add_argument("--emit-contract", action="store_true", help="Deprecated shim for --task-envelope")
    parser.add_argument("--group", type=str, default="", help="Group override (fail-closed against VALID_GROUPS, exit 2)")
    parser.add_argument("--loop", action="store_true", help="Shared flag (SPEC §4b): single dispatch cycle per invocation (scheduler is the outer loop)")
    parser.add_argument("--offline", action="store_true", help="Run offline (board query honestly skipped)")
    parser.add_argument("--pick-next", action="store_true", help="Shared flag (SPEC §4b): pick highest-priority claimable issue (default dispatch behavior)")
    parser.add_argument("--issue", type=str, default="", help="Target a specific issue number for the task envelope")
    parser.add_argument("--role", type=str, default="", help="Role override (validated against ROLE_RULES + specialist classes, honest fallback)")
    parser.add_argument("--max-tasks", dest="max_tasks", type=int, default=1, help="Max tasks per dispatch cycle (minimal loop honors 1; >1 gets an honest stderr note)")
    parser.add_argument("--allow-adhoc", dest="allow_adhoc", action="store_true", help="Emit an ad-hoc envelope when no claimable issue exists")
    parser.add_argument("--auto-pr", action="store_true", help="Accepted for pipeline parity (#89); the minimal loop itself opens no PR")
    args, _ = parser.parse_known_args()

    if args.group and args.group not in VALID_GROUPS:
        log("❌", f"--group '{args.group}' is not in the VALID_GROUPS registry {sorted(VALID_GROUPS)} (SPEC §3 fail-closed)")
        return 2

    if args.verify_only:
        # বাংলা: #567-এর Tier-1 fresh-গেট step_2_rules() সম্পূর্ণ নির্মিত ও
        # ২৬-অফলাইন-টেস্টে যাচাইকৃত, অথচ #1551-এর dead-cluster removal-এর পর
        # একে কোনো কলার ডাকে না (git grep প্রমাণিত) — freshনেস যাচাই নীরবে শূন্য:
        # ড্রিফটেড AGENTS.md-সহ --verify-only নিঁখোচ পাস করে (live main-এ প্রমাণিত)।
        # tests/test_constitution_freshness.py-র মডিউল-ডকস্ট্রিং এই আচরণটাকেই চুক্তি
        # হিসেবে বর্ণনা করে: "report-only mode (--verify-only boot smoke): drift is
        # reported, the result stays True, and the tree is NEVER mutated"। এই
        # বুট-স্মোক সেই চুক্তি ফেরত বসায় — report-only: auto_sync=False (গাছ
        # কখনো মিউটেট হয় না — governance PR-এর constitution পরিবর্তন অক্ষত),
        # ফলাফল stderr-এ সৎ রিপোর্ট; exit-code ও stdout টিয়ার-এভিডেন্স
        # অপরিবর্তিত (--verify-only-র fail-closed চুক্তি #1551 অক্ষত; মার্কার
        # exactly-once অক্ষত; §4b-1 cross-repo check 2>/dev/null pipe করে)।
        # ডিসপ্যাচ-পথের fresh-গেটিং owner-level সিদ্ধান্ত (#1551 TaskCycleWiring
        # docstring) — এখানে স্পর্শ করা হয়নি।
        try:
            if _offline_requested(getattr(args, "offline", False)):
                print(
                    "[Rules] offline: constitution-freshness boot smoke honestly skipped",
                    file=sys.stderr,
                )
            elif step_2_rules(auto_sync=False):
                print(
                    "[Rules] constitution freshness gate: PASS (report-only boot smoke; "
                    "drift, if any, is reported on stdout above)",
                    file=sys.stderr,
                )
            else:
                print(
                    "[Rules] constitution freshness gate: UNVERIFIED (report-only boot "
                    "smoke, non-blocking by contract)",
                    file=sys.stderr,
                )
        except Exception as exc:  # বাংলা: বুট-স্মোক কখনো --verify-only ফেল করাবে না
            print(
                f"[Rules] boot smoke error (report-only, non-blocking): {exc}",
                file=sys.stderr,
            )
        evidence = run_verify()
        failed = [ev for ev in evidence if not ev.get("passed")]
        if failed:
            print(
                "verification FAILED: "
                + ", ".join(f"tier {ev['tier']} ({ev['name']})" for ev in failed),
                file=sys.stderr,
            )
            return 1
        return 0

    if args.loop:
        # বাংলা: এই স্ক্রিপ্ট একটি পরিষ্কার একক-ডিসপ্যাচ সাইকেল চালায়। বাইরের শিডিউলার/রানারই
        # পুনরাবৃত্তি নিয়ন্ত্রণ করে; ইন-প্রসেস অসীম লুপ প্রক্রিয়ার অপব্যবহার বন্ধ রাখা হয়েছে।
        print("--loop: runs ONE dispatch cycle per invocation; the scheduler/orchestrator is the outer loop.", file=sys.stderr)

    if args.max_tasks is not None and args.max_tasks <= 0:
        print("--max-tasks <= 0: dispatch suppressed by caller.", file=sys.stderr)
        return 0
    if args.max_tasks is not None and args.max_tasks > 1:
        print(
            "--max-tasks > 1: this loop dispatches exactly ONE task per cycle "
            "(the scheduler/orchestrator is the outer loop); honoring 1.",
            file=sys.stderr,
        )

    return run_dispatch_cycle(args)

if __name__ == "__main__":
    sys.exit(main())
