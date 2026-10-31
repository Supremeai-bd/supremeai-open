#!/usr/bin/env python3
"""bridge_landing_watchdog.py — bridge work-order landing watchdog (#1964 gap).

The measured failure class (#1964, 2026-10-28): run 4532 failed main preflight
on index drift and main was force-pushed back, EVICTING the R42 deliverable
(d9d9385/7f8d8df, unfetchable by SHA) while its work order #1953 stayed
`bridge:queued` with an empty verdict — a landing can now silently vanish
between "bridge accepted the patch" and "CI Guardian lands it", and nothing
reconciles the two planes. This is the watchdog mirror the triage asked for.

Reconciliation model (three planes, one join key):
  - board plane   : open WOs labeled `bridge:queued` (Tower bridge.work_queue —
                    renamed from bridge_work_queue 2026-10-29, #2454 r3 deploy
                    / #2457 migration; zero-credential; limit ladder
                    200->50->default crosses the queue-fidelity deploy window
                    #2115/#2123) — each title carries the lane slug
  - rejected plane: open `bridge:rejected` issues enumerated straight from
                    the GitHub API (zero-credential, S05 query SSOT; #2158) —
                    the queue omits rejected WOs (#1972), so landing truth
                    must be checked where Tower hides them
                    `(bridge-YYYYMMDD-<slug>)`. Open WOs labeled
                    `bridge:rejected` are ALSO read, but solely to detect
                    FALSE_REJECTION (below) — a rejection is presumed
                    legitimate unless main history proves otherwise.
  - history plane : landed commit subjects on origin/main (squash-merge
                    convention embeds the same slug and the PR number).
  - flight plane  : open PR titles (Tower github.list_prs — dotted form since
                    the 2026-10-29 github-family rename wave, #2486) — same
                    slug token.
  - verdict plane : Tower bridge_read_feedback per WO number — the feedback-
                    plane reader this file's own scope note called for. Used
                    ONLY to enrich MERGED_ON_MAIN rows (tower_verdict /
                    tower_unstamped): a history-proven landing whose Tower
                    stamp is missing is bookkeeping blackout, visible here.
                    Live 2026-10-28 condition that motivated it: 13/13 merged
                    WOs carried latestVerdict=null while every slug was
                    provably in main history. Best-effort, fail-open, never
                    strict — a transient Tower condition must not red a gate
                    (same doctrine as the report-only default).

Verdict per open bridge:queued WO (any-slug match wins):
  MERGED_ON_MAIN   slug found in main history — WO should close; flagged as
                   bookkeeping lag when it ages past the threshold. Since
                   #2516 the join is FULL-BOARD: an open row with any other
                   label whose slug IS in history reports too (tagged
                   plane=outside-queued) — a landing is a self-fulfilled WO
                   regardless of label. Rows whose `updatedAt == createdAt`
                   additionally carry the never-touched
                   close-on-merge flap fingerprint (#2401/#2430 class: the
                   closure worker never even touched the row — the reconciler's
                   exact worklist), while touched rows stay untagged and rows
                   missing timestamps stay honestly untagged (unknown).
  OPEN_PR          slug found in an open PR title — in flight, healthy.
  IN_GATES         no match anywhere, WO younger than the threshold — normal
                   CI-Guardian latency, not a signal.
  LANDING_AT_RISK  no match anywhere, WO older than the threshold — the
                   deliverable is neither landed nor in flight: evicted,
                   rejected-without-verdict, or stuck. This is the class
                   #1953 sat in with zero signal.
  SATELLITE_TARGET the WO body names a satellite Target Repo (#1916:
                   Supremeai-bd/supremeai-browser) — its landing lands in the
                   satellite and can NEVER appear in this repo's history or
                   PR planes, so age-based risk flagging would be a structural
                   false positive. Informational (never strict-flagged); the
                   satellite landing remains outside this guard's observation.
  NO_SLUG          title carries no bridge slug — outside this guard's model
                   (reported informationally, never strict-flagged).
  FALSE_REJECTION  WO is labeled `bridge:rejected` yet its slug IS found in
                   main history — the rejection is provably wrong. Live case
                   #1972 (2026-10-28): rejected "branch not found" at
                   05:50:43Z AFTER the deliverable had landed at 05:00:16Z
                   (3273abe); the post-merge branch cleanup raced the verdict
                   evaluator, which checks branch existence but never merge
                   state. Demands relabel/audit; strict-flagged.
                   Rejected WOs with NO landing stay unreported (a rejection
                   is usually correct — e.g. guard failures, v2-routing),
                   keeping the strict surface minimal. Honest scope limit:
                   the board plane IS the queue payload, and Tower currently
                   omits some rejected WOs from it entirely (live: #1972 was
                   absent from bridge.work_queue) — since 2026-10-28 (#2158)
                   the rejected plane enumerates those rows directly from
                   GitHub, closing the invisible-rejected half of this note
                   (the merged-row half closed with the feedback-plane
                   reader); the classification logic is proven hermetically
                   and on the real #1972/#2158 data fed directly
                   (integration runs, 2026-10-28). The queued half of the
                   omission class is covered too (#2190): the queue-
                   integrity plane enumerates open `bridge:queued` rows
                   from the same label plane and diffs BOTH directions
                   against the listing Tower serves (missing-from-listing,
                   phantom-in-listing) — disclosure-only, since queued rows
                   can be mid-transition and joining them could resurrect
                   work another plane owns. Live motivation (2026-10-28,
                   #2173): a landed-and-merged WO stayed `bridge:queued`
                   yet absent from an untruncated 16-18-row listing while
                   bridge.work_order confirmed it — the integrity line is
                   the only place such a row surfaces.

Modes:
  --self-test   hermetic verdict-matrix proof (fixture WOs/history/flight;
                miss=0, false-positive=0). No network. (roster mode)
  --strict      exit 1 when any FALSE_REJECTION, LANDING_AT_RISK, or
                MERGED_ON_MAIN lagging past the threshold exists; report-only
                default exits 0 with the table so a transient Tower condition
                never reds a gate.
Exit codes: 0 = report OK, 1 = strict findings, 2 = board/history unreachable
            (honest skip — never reported as pass).

Zero credentials for Tower/GitHub planes. The history plane reads local git
log and, on a SHALLOW checkout (the agent-loop caller's depth-1 default,
r13/cycle-18 Job 486770), performs ONE bounded `git fetch --deepen` that
enriches only the local object store — no ref update, no Tower/repo write.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess  # nosec B404 — live-mode IO wrappers shell out to git via list-argv only (#2081 audit)
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    from tower_name_tolerance import call_across_names, epoch_spellings  # flat: scripts/ci on sys.path
except ImportError:  # pragma: no cover — package-style load (tests, CI runner)
    from scripts.ci.tower_name_tolerance import call_across_names, epoch_spellings

REPO_ROOT = Path(__file__).resolve().parents[2]
TOWER = "https://supremeai-mcp-tower.onrender.com/mcp"

# Landing-latency threshold: past this age with neither a landing nor an open
# PR, the WO's deliverable is at risk (#1964 class). Hours.
DEFAULT_AT_RISK_HOURS = 2.0
# Depth of main history scanned for landing subjects (squash-merges embed the
# slug; a fresh WO's landing, if any, is always inside this window).
LOG_DEPTH = 400

SLUG_RE = re.compile(r"\(bridge-\d{8}-[a-z0-9][a-z0-9-]*\)")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
# The repo whose history/PR planes this guard reconciles against. A WO whose
# body names ANY other Target Repo lands in that satellite (#1916 class).
OPEN_REPO = "Supremeai-bd/supremeai-open"
TARGET_REPO_RE = re.compile(r"^###\s+Target Repo\s*\n\s*(\S+)", re.MULTILINE)
# Cap on per-WO body fetches during refinement (only at-risk candidates are
# fetched; the common board has zero, so the steady-state cost is nil).
MAX_SATELLITE_PROBES = 5
# Cap on per-WO feedback fetches during verdict-plane enrichment (only
# MERGED_ON_MAIN rows are probed — the rows Tower should have stamped; a
# healthy board probes zero, the 2026-10-28 blackout board probed 13).
MAX_FEEDBACK_PROBES = 24

_id = [100]


def _rpc(method, params=None, session_id=None, notify=False, attempts=4):
    """Minimal zero-credential MCP client (same protocol as the bridge lane)."""
    payload = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    if not notify:
        _id[0] += 1
        payload["id"] = _id[0]
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               # Streamable HTTP (spec rev >= 2025-06-18): every post-initialize request
               # must carry the negotiated version; a missing header makes the server
               # assume 2025-03-26, voiding the 2025-11-25 floor (#2568, radar R70).
               # Mirrors PROTOCOL_VERSION_STREAMABLE in scripts/agents/mcp_tower_client.py.
               "MCP-Protocol-Version": "2025-11-25"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(TOWER, data=json.dumps(payload).encode(),
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:  # nosec B310 — tower URL is a pinned https module constant; audited #2081
                sid = resp.headers.get("Mcp-Session-Id")
                body = resp.read().decode("utf-8", errors="replace")
                ctype = resp.headers.get("Content-Type") or ""
                break
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(10 * (attempt + 1))
    else:
        raise last  # noqa: TRY201 - caller maps to the honest-skip exit
    if "text/event-stream" in ctype:
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip()), sid
                except Exception:  # noqa: BLE001  # nosec B112 — SSE lines are individually skippable by design; continue IS the contract (#2081 audit)
                    continue
    if not body.strip():
        return {"accepted": True}, sid
    return json.loads(body), sid


def _text_of(res) -> str:
    content = res.get("result", {}).get("content", []) if isinstance(res, dict) else []
    return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))


def _tower_text(name: str, arguments: dict) -> str:
    _, sid = _rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                 "clientInfo": {"name": "bridge-landing-watchdog", "version": "1.0"}})
    _rpc("notifications/initialized", {}, session_id=sid, notify=True)

    # বাংলা: নাম-ঢেউ সহনশীল কল (Zero-Recurrence U6 shared cure)। ঢেউ-৩ (live
    # 2026-10-31) dotted বানানগুলি আবার মৃত — এই ফানেল পিন-করা এক-বানানে অন্ধ
    # হয়ে গিয়েছিল (board/history প্লেন SKIP: "MCP error -32602 ... not found"
    # text-ই json.loads ভাঙত — live GLM Agent 11, cycle-15)। যুগ-লেজার ক্রমে
    # চেষ্টা (tower_name_tolerance.epoch_spellings) — মৃত-নামের সাড়া JSON-RPC
    # error নয়, isError content-text; প্রেডিকেট এখন result.content আকৃতিও চেনে।
    # একই সেশন দুই বানানে পুনঃব্যবহৃত — initialize দ্বিতীয়বার হয় না।
    def _call_by_spelling(spelling: str):
        res, _ = _rpc("tools/call", {"name": spelling, "arguments": arguments},
                      session_id=sid)
        return res

    res = call_across_names(_call_by_spelling, epoch_spellings(name))
    return _text_of(res)


# ── queue fetch: limit ladder across the fidelity deploy window (#2115/#2123) ──

QUEUE_LIMIT_LADDER: tuple = (200, 50, None)


def _fetch_work_orders(fetch_text=_tower_text) -> tuple:
    """Fetch open work orders across the queue-fidelity deploy window.

    r2 (#2115/#2123) makes bridge.work_queue paginate (short-page-stop,
    number-dedupe merge) and raises its limit cap 50 -> 200, but the
    DEPLOYED tower can keep running the pre-r2 single-page handler while
    the redeploy lags — and a single-page window is a creation-rank
    window: rows drop as traffic flows (#2115: 98 open issues read as
    20-35 rows; the default window observed at ~20 rows). Ladder: ask for
    200 first (an r2 tower answers with full pagination); only an
    argument-validation rejection (non-JSON error text, or an isError
    envelope) falls through to 50 (the pre-r2 cap), then to the tower
    default — exact pre-ladder behavior as the last rung. Transport
    failures propagate so main() keeps its fail-close SKIP. A rung that
    answers is served as-is (never retried). Returns (workOrders,
    serving_limit); serving_limit is None for the tower-default rung.
    """
    last_err: Exception = RuntimeError("queue ladder exhausted")
    for limit in QUEUE_LIMIT_LADDER:
        arguments = {} if limit is None else {"limit": limit}
        try:
            payload = json.loads(fetch_text("bridge.work_queue", arguments))
        except json.JSONDecodeError as err:  # error-envelope text, not JSON
            last_err = err
            continue
        if not isinstance(payload, dict) or payload.get("isError"):
            last_err = TypeError(f"queue rung {limit} answered a non-payload")
            continue
        return (payload.get("workOrders", []) or [], limit)
    raise last_err


# ── rejected plane: GitHub-side enumeration of rows the queue omits (#2158) ──

REJECTED_LABEL = "bridge:rejected"
QUEUED_LABEL = "bridge:queued"


def _load_reference_module():
    """SSOT import of the S05 queue-query reference (R51 pattern: semantics
    owned upstream, no private copy)."""
    path = REPO_ROOT / "scripts" / "tower" / "work_queue_query_reference.py"
    spec = importlib.util.spec_from_file_location("work_queue_query_reference", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_REF = _load_reference_module()


def _github_get_json(url: str, timeout: int = 20):
    """Zero-credential GET (browser UA, per the freshness-probe convention)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "bridge-landing-watchdog/1.0 (zero-credential board audit)",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — URL from the S05 SSOT reference (fixed repo, https)
        return json.loads(resp.read().decode("utf-8"))


def _fetch_label_rows(label: str, fetch_json=_github_get_json,
                      max_pages: int | None = None) -> list[dict]:
    """Enumerate open issues carrying `label` straight from GitHub.

    The S05 r2 contract (build_queue_query SSOT) forbids single-page
    fetches — pages until a short page or the MAX_PAGES cap, number-dedupe
    merged. Rows come back in normalize_queue shape. Shared core for the
    rejected plane (bridge:rejected) and the queue-integrity cross-check
    (bridge:queued, #2190).
    """
    pages = max(1, max_pages if max_pages is not None else _REF.QUEUE_MAX_PAGES)
    rows: list[dict] = []
    seen: set = set()
    for page in range(1, pages + 1):
        q = _REF.build_queue_query(label, page=page)
        payload = fetch_json(q["url"])
        if not isinstance(payload, list):
            raise TypeError(
                f"github page {page}: expected a list, got {type(payload).__name__}")
        for wo in _REF.normalize_queue(payload, q["applied_label"])["workOrders"]:
            n = wo.get("number")
            if n in seen:
                continue
            seen.add(n)
            rows.append(wo)
        if len(payload) < _REF.QUEUE_PAGE_SIZE:  # short page = enumeration end
            break
    return rows


def _fetch_rejected_rows(fetch_json=_github_get_json,
                         max_pages: int | None = None) -> list[dict]:
    """Enumerate open `bridge:rejected` issues straight from GitHub.

    The queue omits rejected WOs (#1972 was absent from bridge.work_queue;
    live #2158: landed #2020/#2056 stamped rejected and queue-invisible).
    Rows are ready for run_verdicts' existing rejected-row branch (zero new
    verdict classes)."""
    return _fetch_label_rows(REJECTED_LABEL, fetch_json=fetch_json,
                             max_pages=max_pages)


def _fetch_rejected_rows_tower(fetch_text=_tower_text) -> list[dict]:
    """Tower-plane enumeration of open `bridge:rejected` via the
    label-filtered bridge.work_queue query — the disclosed fallback when the
    unauthenticated GitHub budget is exhausted (per-IP, shared egress).

    #2251 un-self-defeated the tower-side label filter: queueFromIssues had
    applied the universal !isRejectedOrLanded board filter to EVERY path
    including label-filtered ones (live pre-fix: confirmed open+rejected
    #2020/#2056 enumerated 0 rows; live post-fix 2026-10-29, zero-credential
    vantage: 20 rows). Rows carry number/title/labels/createdAt in the same
    normalize shape as the github plane (no body — run_verdicts needs none
    and refine_satellites fetches bodies itself).

    Limit ladder (#2292 evidence, #2286 class): the no-limit call fetched
    only the tower default page — 20 rows against a 52-row rejected plane
    (R58 sweep, 2026-10-29), silently truncating the FALSE_REJECTION
    worklist. Walks the SAME QUEUE_LIMIT_LADDER as the queue plane, label
    preserved per rung: an r2 tower answers 200; a lagging pre-r2 deploy
    descends to 50, then the tower default (exact pre-ladder behavior as
    the last rung). Transport rejections (non-JSON error text, isError
    envelope) descend; a payload that ANSWERS with the wrong shape stays
    fail-loud — a contract violation is never read as an empty truth."""
    last_err: Exception = RuntimeError("rejected-plane tower ladder exhausted")
    for limit in QUEUE_LIMIT_LADDER:
        arguments = {"label": REJECTED_LABEL} if limit is None else {
            "label": REJECTED_LABEL, "limit": limit}
        try:
            payload = json.loads(fetch_text("bridge.work_queue", arguments))
        except json.JSONDecodeError as err:  # error-envelope text, not JSON
            last_err = err
            continue
        if not isinstance(payload, dict) or payload.get("isError"):
            last_err = TypeError(f"rejected rung {limit} answered a non-payload")
            continue
        if not isinstance(payload.get("workOrders"), list):
            raise TypeError("bridge.work_queue: expected {workOrders: [...]}, got "
                            f"{type(payload).__name__}")
        return payload["workOrders"]
    raise last_err


def _load_rejected_plane(fetch_rows=_fetch_rejected_rows,
                         tower_rows=_fetch_rejected_rows_tower) -> tuple:
    """Dual-transport rejected plane, per-plane fail-open: a down plane
    degrades THIS plane only (honest note), never the queue plane, never a
    fake empty truth. GitHub direct stays primary (independent transport of
    the same S05 build_queue_query contract); the tower label-filtered
    queue is the fallback for the per-IP unauthenticated GitHub budget —
    shared by everything egressing the same address (live 2026-10-29:
    github 403 from this egress while the tower plane served 20 rows).
    The 403 cause is disclosed verbatim whether the fallback covers it or
    both planes fail — rate-limited is transient (resets hourly), unlike a
    genuine outage."""
    try:
        return fetch_rows(), "ok"
    except urllib.error.HTTPError as err:
        gh_note = ("HTTP 403 — unauthenticated GitHub API rate limit for "
                   "this egress IP (shared egress may exhaust it "
                   "continuously); budget resets hourly" if err.code == 403
                   else f"HTTP {err.code}")
    except Exception as err:  # noqa: BLE001 — one plane down is a disclosed skip
        gh_note = err.__class__.__name__
    try:
        return tower_rows(), f"tower-plane fallback (github: {gh_note})"
    except Exception as err:  # noqa: BLE001 — both planes down: dual-cause note
        return [], (f"unreachable (github {gh_note}; "
                    f"tower {err.__class__.__name__})")


def _join_rejected_plane(work_orders: list[dict], rejected_rows: list[dict]) -> tuple:
    """Queue rows win on number collision (the queue stays the board SSOT
    for queued work); only queue-omitted rejected rows join the payload."""
    queued = {w.get("number") for w in work_orders}
    merged = [r for r in rejected_rows if r.get("number") not in queued]
    return work_orders + merged, len(merged)


def _check_queue_integrity(listing_numbers: set, label_numbers: set) -> tuple:
    """Both directions of label-plane vs listing divergence (#2190).

    missing = open `bridge:queued` on GitHub yet absent from the tower
    listing — queued work the board cannot see (live: #2173 landed on main
    while listed nowhere). phantom = listed by the tower yet absent from
    the GitHub label plane — the listing source diverged. Disclosure-only
    by design: unlike rejected rows (terminal, queue-omitted BY DESIGN), a
    queued row can be mid-transition (claim-label lag is structural per
    the #2182 plane watch), so these rows do NOT join the verdict payload
    — the line discloses exact numbers; bridge.work_order resolves each.
    """
    missing = sorted(label_numbers - listing_numbers)
    phantom = sorted(listing_numbers - label_numbers)
    return missing, phantom


def _load_queue_integrity(listing_numbers: set,
                          fetch_rows=_fetch_label_rows) -> tuple:
    """Fail-open like the rejected plane: an unreachable GitHub label plane
    degrades this disclosure only, never the queue plane, with the same
    cause-level 403 note (per-IP unauthenticated budget, shared egress)."""
    try:
        rows = fetch_rows(QUEUED_LABEL)
    except urllib.error.HTTPError as err:
        if err.code == 403:
            return None, ("unreachable (HTTP 403 — unauthenticated GitHub API "
                          "rate limit for this egress IP (shared egress may "
                          "exhaust it continuously); budget resets hourly)")
        return None, f"unreachable (HTTP {err.code})"
    except Exception as err:  # noqa: BLE001 — one plane down is a disclosed skip
        return None, f"unreachable ({err.__class__.__name__})"
    missing, phantom = _check_queue_integrity(
        set(listing_numbers), {r.get("number") for r in rows})
    return (len(rows), missing, phantom), "ok"


# ── pure verdict core (hermetically testable) ────────────────────────────────

def extract_slugs(title: str) -> list[str]:
    """Full bridge-slug tokens in a WO title, in order of appearance."""
    return SLUG_RE.findall(title or "")


def _age_hours(created_at: str, now_epoch: float) -> float | None:
    if not created_at or not TS_RE.match(created_at):
        return None
    try:
        created = time.mktime(time.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
    except ValueError:
        return None
    return max(0.0, (now_epoch - created) / 3600.0)


def parse_target_repo(body: str | None) -> str | None:
    """Extract the WO body's `### Target Repo` value (standard WO template).

    Returns the repo slug (e.g. 'Supremeai-bd/supremeai-browser') or None when
    the section is absent/unparseable — None means 'no satellite evidence',
    which keeps the WO on the default open-repo model (fail-closed).
    """
    if not body:
        return None
    m = TARGET_REPO_RE.search(body)
    return m.group(1).strip() if m else None


def classify(wo: dict, main_subjects: list[str], open_pr_titles: list[str],
             now_epoch: float, at_risk_hours: float = DEFAULT_AT_RISK_HOURS,
             target_repo: str | None = None) -> dict:
    """Verdict one open bridge:queued WO against the history + flight planes.

    Any slug match wins (a WO with several lane slugs is landed if ANY of them
    landed). Slug matching is full-token: `bridge-20261028-foo` must NOT match
    a history subject carrying `bridge-20261028-foobar` (prefix collisions are
    real — e.g. the -r2 rescue lanes).

    `target_repo` (from the WO body via parse_target_repo) short-circuits the
    age-based risk flag: a satellite-targeted WO can never match the open-repo
    planes by design, so an old unmatched satellite WO is SATELLITE_TARGET
    (informational), not LANDING_AT_RISK (#1916 live false positive).
    """
    num = wo.get("number")
    title = wo.get("title") or ""
    slugs = extract_slugs(title)
    age = _age_hours(wo.get("createdAt") or "", now_epoch)
    base = {"number": num, "slug": slugs[0] if slugs else None, "age_hours": age}

    if not slugs:
        return {**base, "verdict": "NO_SLUG", "evidence": "no (bridge-YYYYMMDD-slug) token in title"}

    merged = [s for s in slugs if any(s in subj for subj in main_subjects)]
    if merged:
        v = {**base, "verdict": "MERGED_ON_MAIN", "evidence": f"slug {merged[0]} in main history"}
        ca, ua = wo.get("createdAt") or "", wo.get("updatedAt") or ""
        if ca and ua and ca == ua:
            # never-touched close-on-merge flap fingerprint (#2401/#2430):
            # the closure worker never touched the row post-creation — the
            # reconciler's exact worklist. Touched rows and rows with missing
            # timestamps stay untagged (touched-lag vs honest unknown).
            v["never_touched"] = True
            v["evidence"] += " — never-touched since creation (close-on-merge flap fingerprint, #2401/#2430)"
        return v

    inflight = [s for s in slugs if any(s in t for t in open_pr_titles)]
    if inflight:
        return {**base, "verdict": "OPEN_PR", "evidence": f"slug {inflight[0]} in an open PR title"}

    if target_repo and target_repo != OPEN_REPO:
        return {**base, "verdict": "SATELLITE_TARGET",
                "evidence": f"targets satellite {target_repo} — lands outside the open-repo "
                            f"history/PR planes (never matchable by design; satellite landing "
                            f"not observable here)"}

    if age is None:
        return {**base, "verdict": "IN_GATES", "evidence": "no match yet; unparseable createdAt (honest no-signal)"}
    if age >= at_risk_hours:
        return {**base, "verdict": "LANDING_AT_RISK",
                "evidence": f"no landing and no open PR after {age:.1f}h (threshold {at_risk_hours:g}h) — evicted/rejected/stuck?"}
    return {**base, "verdict": "IN_GATES",
            "evidence": f"no match yet; age {age:.1f}h < threshold {at_risk_hours:g}h"}


def run_verdicts(work_orders: list[dict], main_subjects: list[str],
                 open_pr_titles: list[str], now_epoch: float,
                 at_risk_hours: float = DEFAULT_AT_RISK_HOURS) -> list[dict]:
    """Classify every open bridge:queued WO (labels SSOT), plus bridge:rejected
    WOs solely to surface FALSE_REJECTION (rejected-but-landed, the #1972
    class). Rejected WOs with no landing stay out of the report: a rejection
    is presumed legitimate unless main history contradicts it, so widening the
    strict surface costs zero new false positives.

    Full-board drainage join (#2516 remedy item 2): open rows carrying any
    OTHER label are ALSO joined against main history. A landing makes a row a
    self-fulfilled work order regardless of its label, so it must surface in
    the same cycle instead of accumulating invisibly between manual
    matrix-scoped sweeps (live: the 34-row #2516 cohort — 14 pre-crash
    stragglers included — while the label-plane figure said 14). Outside-
    queued rows enter the report ONLY on a history-proven landing, tagged
    `label_plane: outside-queued`; non-landed non-queued rows stay silent —
    they may be plain tracker issues, and age-based risk flags for them would
    be a brand-new false-positive surface (mirrors the rejected-plane
    doctrine). Verdict classes themselves are untouched."""
    out = []
    for wo in work_orders:
        labels = wo.get("labels") or []
        if isinstance(labels, str):
            labels = [labels]
        if "bridge:queued" in labels:
            out.append(classify(wo, main_subjects, open_pr_titles, now_epoch, at_risk_hours))
        elif "bridge:rejected" in labels:
            v = classify(wo, main_subjects, open_pr_titles, now_epoch, at_risk_hours)
            if v["verdict"] == "MERGED_ON_MAIN":
                out.append({**v, "verdict": "FALSE_REJECTION",
                            "evidence": f"labeled bridge:rejected yet {v['evidence']} — "
                                        f"rejection contradicted by main history "
                                        f"(#1972 class: post-merge branch cleanup raced "
                                        f"the verdict evaluator)"})
            # rejected + IN_GATES/OPEN_PR/LANDING_AT_RISK/NO_SLUG: out of scope —
            # no provable contradiction, silence is the honest default.
        else:
            # বাংলা: #2516 ফুল-বোর্ড জয়েন — যেকোনো খোলা রো-র deliverable main-এ
            # প্রমাণিত হলে সেটা self-fulfilled WO, লেবেল যা-ই হোক। আগে এই ব্রাঞ্চ
            # নীরবে বাদ দিত — সারিরা ম্যানুয়াল ম্যাট্রিক্স-সুইপের ফাঁকে অদৃশ্যভাবে
            # জমা হত (#2516: ১৪ pre-crash straggler সহ ৩৪-সারির কোহোর্ট, অথচ
            # label-plane ফিগার ১৪ বলছিল)। মূল কারণ ঠিক: লেবেল-ফিল্টার ছিল
            # রিপোর্ট-সারফেস সংকুচিত করত, git-join-কে নয়। শুধু প্রমাণিত
            # ল্যান্ডিং-ই রিপোর্টে আসে; non-landed non-queued রো নীরব (শূন্য
            # নতুন false positive — rejected-plane মতবাদের প্রতিফলন)।
            v = classify(wo, main_subjects, open_pr_titles, now_epoch, at_risk_hours)
            if v["verdict"] == "MERGED_ON_MAIN":
                out.append({**v, "label_plane": "outside-queued"})
    return out


# ── IO wrappers (live mode) ──────────────────────────────────────────────────

def _git_log_subjects(depth: int, git_bin: str) -> list[str]:
    out = subprocess.run(  # nosec B603 — list-argv, no shell, pinned git read-only command (#2081 audit)
        [git_bin, "-C", str(REPO_ROOT), "log", "--format=%s", "-n", str(depth), "origin/main"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"git log failed: {out.stderr.strip()[:120]}")
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def _clone_is_shallow() -> bool:
    """actions/checkout's depth-1 default (fetch-depth unset) writes .git/shallow."""
    return (REPO_ROOT / ".git" / "shallow").exists()


def _deepen_main(depth: int, git_bin: str) -> bool:
    """One bounded enrichment past the shallow boundary (local store only —
    no ref update, no Tower/repo mutation; anonymous works on the public
    origin, checkout-persisted credentials elsewhere)."""
    try:
        out = subprocess.run(  # nosec B603 — list-argv, no shell, read-only fetch
            [git_bin, "-C", str(REPO_ROOT), "fetch", f"--deepen={depth}", "origin", "main"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
        )
        return out.returncode == 0
    except Exception:  # noqa: BLE001 — offline/permission failures degrade, never crash
        return False


def _gh_close(num: int | str, comment: str) -> subprocess.CompletedProcess:
    """One gh close attempt (live-mode IO; token comes from the caller's env)."""
    return subprocess.run(  # nosec B603 — list-argv, no shell, pinned gh close
        ["gh", "issue", "close", str(num), "--comment", comment],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )


def _close_result(num: int | str, comment: str, closer=_gh_close) -> str:
    """One HONEST line per apply-leg close attempt.

    The pre-fix leg printed its success line without reading gh's exit
code, so a failing close (403, rate limit, token-less runner) was
logged as success — a false witness in the exact janitor log the
ghost-attribution reads back (CI tolerates a failing janitor step, so
that per-item line is the only surviving evidence).
    """
    try:
        proc = closer(num, comment)
    except Exception as err:  # noqa: BLE001 — gh missing/exec failure degrades, never crashes
        return f"  [WARN] Failed to close #{num}: {err}"
    rc = getattr(proc, "returncode", None)
    if rc == 0:
        return f"  [OK] Auto-closed #{num}"
    out = f"{getattr(proc, 'stderr', '') or ''}{getattr(proc, 'stdout', '') or ''}".strip().splitlines()
    detail = out[-1][:160] if out else "gh produced no output"
    return f"  [FAIL] #{num} not closed (gh exit {rc}): {detail}"


def _main_subjects(depth: int = LOG_DEPTH,
                   log_reader=_git_log_subjects,
                   shallow_probe=_clone_is_shallow,
                   deepener=_deepen_main) -> list[str]:
    """Landing subjects on origin/main, shallow-self-healing (r13/cycle-18).

    Live-proof of the blindness this heals (cycle-18, Job 486770): the only
    wired caller — the agent-loop janitor step, #3341 — checks out depth-1
    while this census joins the last LOG_DEPTH subjects; the join saw ONE
    subject, every landed slug was invisible, and the daily sweep closed
    NOTHING even when it fired (board census 19/19 MERGED_ON_MAIN right
    after the 06:00Z fire, all never-touched). The root fix lives in the
    TOOL, not the caller, so every wired caller — daily janitor, future
    sync-job step, local run — sees the full join window. Self-heal is one
    bounded deepen; failure degrades LOUDLY (::warning:: GHA annotation,
    check_commit_sizing.py idiom) — a truncated census is never silently
    trusted again.
    """
    git_bin = shutil.which("git") or "git"  # B607: resolve to absolute path when available
    subjects = log_reader(depth, git_bin)
    if len(subjects) >= depth or not shallow_probe():
        return subjects  # full window, or genuinely short history — nothing to heal
    if deepener(depth, git_bin):
        healed = log_reader(depth, git_bin)
        if len(healed) > len(subjects):
            print(f"::warning::landing-watchdog census self-healed a shallow "
                  f"checkout: {len(subjects)} -> {len(healed)} of {depth} "
                  f"subjects visible")
            return healed
        print(f"::warning::landing-watchdog census ran on a shallow checkout: "
              f"{len(subjects)}/{depth} subjects visible and deepen fetched "
              f"no new commits — MERGED_ON_MAIN detection may under-report")
        return subjects
    print(f"::warning::landing-watchdog census ran on a shallow checkout: "
          f"{len(subjects)}/{depth} subjects visible and git fetch --deepen "
          f"failed (offline/credentials) — MERGED_ON_MAIN detection may "
          f"under-report")
    return subjects


def _open_pr_titles(fetch_text=_tower_text) -> list[str]:
    # Flight plane pins the OPEN repo and the schema-conformant limit knob.
    # Two stacked silent defects found live (cycle 23/24, Job 478338): (1) a
    # repo-less call resolved github-primary's account url = the CORE
    # satellite (Supremeai-bd/supremeai), so open-repo bridge PRs were never
    # in the listing at all; (2) the tool schema has no per_page — it was
    # silently ignored and limit fell back to its default 5 (five newest
    # rows only). Neither defect raises; classification just degraded to the
    # age ladder (LANDING_AT_RISK false positives for WOs whose PR was
    # genuinely in flight). Third silent mode (cycle 36, #2486): the
    # github-family dotted-wave rename turned the legacy wire name into a
    # -32602 error whose text flowed into the classifier as pseudo-titles
    # (OPEN_PR=0 while PRs were open) — migrated to the dotted name.
    txt = fetch_text("github.list_prs", {"state": "open", "repo": OPEN_REPO, "limit": 50})
    titles = []
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith(("#", "\"#", "{\"number\"")):
            titles.append(line)
    # fall back to whole text — the slug token match is substring-based anyway
    return titles or ([txt] if txt else [])


def _fetch_wo_body(number: int) -> str | None:
    """Fetch one WO's full body (read-only tower round-trip) for refinement."""
    try:
        return json.loads(_tower_text("bridge.work_order", {"number": number})).get("body")
    except Exception:  # noqa: BLE001 - refinement is best-effort, fail-closed
        return None


def refine_satellites(verdicts: list[dict], fetch_body=_fetch_wo_body,
                      max_probes: int = MAX_SATELLITE_PROBES) -> list[dict]:
    """Re-classify LANDING_AT_RISK verdicts whose WO body targets a satellite.

    The queue payload carries no body, so this fetches bodies ONLY for the
    at-risk candidates (steady-state cost: zero round-trips on a healthy
    board). Fail-closed: any fetch/parse failure keeps the risk flag — no
    evidence of satellite targeting never downgrades a LANDING_AT_RISK.
    """
    out = list(verdicts)
    probed = 0
    for i, v in enumerate(out):
        if v["verdict"] != "LANDING_AT_RISK" or probed >= max_probes:
            continue
        probed += 1
        try:
            repo = parse_target_repo(fetch_body(v["number"]))
        except Exception:  # noqa: BLE001 - defense in depth: a raising injectable
            repo = None     # fetcher must never turn a risk flag into a crash
        if repo and repo != OPEN_REPO:
            out[i] = classify(
                {"number": v["number"], "title": (v.get("slug") or "") and f"x ({v['slug']})",
                 "createdAt": None}, [], [], time.time(), target_repo=repo)
            # preserve the measured age for the report line
            out[i]["age_hours"] = v.get("age_hours")
    return out


def _fetch_wo_feedback(number: int) -> dict | None:
    """Fetch one WO's Tower verdict-plane record (read-only round-trip)."""
    try:
        return json.loads(_tower_text("bridge_read_feedback", {"number": number}))
    except Exception:  # noqa: BLE001 - enrichment is best-effort, never fatal
        return None


def _verdict_string(latest) -> str | None:
    """Extract a non-blank verdict token from the plane's evolving shapes.

    The stamp plane migrated live within hours (2026-10-28, cbb9ab2 plane
    watch): latestVerdict went from null to plain strings to OBJECTS
    carrying EMPTY verdict strings. A blank stamp is a blackout, not a
    stamp: '' / whitespace / {'verdict': ''} must read unstamped, and a
    real {'verdict': 'X'} must surface its token (never a dict repr)."""
    val = latest.get("verdict") if isinstance(latest, dict) else latest
    if isinstance(val, str):
        val = val.strip()
    return str(val) if val else None


def enrich_tower_verdicts(verdicts: list[dict], fetch_feedback=_fetch_wo_feedback,
                          max_probes: int = MAX_FEEDBACK_PROBES) -> list[dict]:
    """Cross-check MERGED_ON_MAIN rows against Tower's own verdict plane.

    The history plane proves a landing; only Tower's verdict plane can say
    whether the bookkeeping stamped it. Sets `tower_verdict` ('none' when
    latestVerdict is null/absent, else its string value) and `tower_unstamped`
    (True = history-proven landing with no Tower stamp; False = stamped;
    None = unreadable, honest unknown) on each probed MERGED_ON_MAIN row.

    Fail-open by contract: enrichment is best-effort and NEVER changes a
    verdict class or the strict surface — a transient Tower condition must
    not red a gate. Non-merged rows cost zero probes (healthy-board steady
    state: zero round-trips, mirroring refine_satellites). Shape evolution
    (null -> string -> blank-stamp object) is handled by _verdict_string.
    """
    out = list(verdicts)
    probed = 0
    for i, v in enumerate(out):
        if v["verdict"] != "MERGED_ON_MAIN" or probed >= max_probes:
            continue
        probed += 1
        fb = None
        try:
            fb = fetch_feedback(v["number"])
        except Exception:  # noqa: BLE001 - defense in depth vs raising injectables
            fb = None
        if not isinstance(fb, dict):
            out[i] = {**v, "tower_verdict": "unreadable", "tower_unstamped": None}
            continue
        verdict_str = _verdict_string(fb.get("latestVerdict"))
        if verdict_str:
            out[i] = {**v, "tower_verdict": verdict_str, "tower_unstamped": False}
        else:
            out[i] = {**v, "tower_verdict": "none", "tower_unstamped": True}
    return out


def self_test() -> list[tuple[str, bool, str]]:
    """Hermetic verdict-matrix proof: every class reachable, no false flags."""
    cases: list[tuple[str, bool, str]] = []
    now = 1793160000.0  # fixed epoch (2026-10-28T04:00:00Z) — fixtures derived from it
    fresh = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 20 * 60))   # 20 min old
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 4 * 3600))    # 4 h old
    slug_a = "(bridge-20261028-alpha-lane)"
    slug_r2 = "(bridge-20261028-alpha-lane-r2)"

    # 1. landed: slug present in main history
    v = classify({"number": 1, "title": f"x {slug_a} y", "createdAt": fresh},
                 [f"feat: something (bridge-20261028-alpha-lane) (#1900)"], [], now)
    cases.append(("landed slug -> MERGED_ON_MAIN", v["verdict"] == "MERGED_ON_MAIN", json.dumps(v)[:160]))

    # 2. in flight: slug in an open PR title
    v = classify({"number": 2, "title": f"x {slug_a} y", "createdAt": fresh},
                 [], [f"PR title (bridge-20261028-alpha-lane) (#1901)"], now)
    cases.append(("in-flight slug -> OPEN_PR", v["verdict"] == "OPEN_PR", json.dumps(v)[:160]))

    # 3. young unmatched -> IN_GATES (normal CI-Guardian latency)
    v = classify({"number": 3, "title": f"x {slug_a} y", "createdAt": fresh}, [], [], now)
    cases.append(("young unmatched -> IN_GATES", v["verdict"] == "IN_GATES", json.dumps(v)[:160]))

    # 4. old unmatched -> LANDING_AT_RISK (the #1964 class)
    v = classify({"number": 4, "title": f"x {slug_a} y", "createdAt": old}, [], [], now)
    cases.append(("old unmatched -> LANDING_AT_RISK", v["verdict"] == "LANDING_AT_RISK", json.dumps(v)[:160]))

    # 5. no slug -> NO_SLUG, never strict-flagged
    v = classify({"number": 5, "title": "operator handoff, no lane slug", "createdAt": old}, [], [], now)
    cases.append(("slugless title -> NO_SLUG", v["verdict"] == "NO_SLUG", json.dumps(v)[:160]))

    # 6. prefix collision: -r2 slug must not match the base lane's landing
    v = classify({"number": 6, "title": f"x {slug_r2} y", "createdAt": old},
                 [f"feat: base lane (bridge-20261028-alpha-lane) (#1902)"], [], now)
    cases.append(("prefix collision rejected (-r2 vs base)",
                  v["verdict"] == "LANDING_AT_RISK", json.dumps(v)[:160]))

    # 7. r2 lane landed under its own slug -> matched
    v = classify({"number": 7, "title": f"x {slug_r2} y", "createdAt": fresh},
                 [f"feat: rescue (bridge-20261028-alpha-lane-r2) (#1903)"], [], now)
    cases.append(("-r2 slug matches its own landing", v["verdict"] == "MERGED_ON_MAIN", json.dumps(v)[:160]))

    # 8. any-slug-wins: multi-slug WO counts as landed if ONE slug landed
    v = classify({"number": 8, "title": f"a {slug_a} b {slug_r2} c", "createdAt": old},
                 [f"feat: base (bridge-20261028-alpha-lane) (#1904)"], [], now)
    cases.append(("multi-slug any-match -> MERGED_ON_MAIN", v["verdict"] == "MERGED_ON_MAIN", json.dumps(v)[:160]))

    # 9. unparseable createdAt -> honest IN_GATES (never a risk flag on bad data)
    v = classify({"number": 9, "title": f"x {slug_a} y", "createdAt": "not-a-timestamp"}, [], [], now)
    cases.append(("bad timestamp -> IN_GATES (honest no-signal)", v["verdict"] == "IN_GATES", json.dumps(v)[:160]))

    # 10. label filter: non-queued UNLANDED WOs stay unreported (list OR string
    # label form). Landed non-queued rows DO report since the #2516 full-board
    # join (case 17b) — an unlanded tracker issue is not this guard's subject.
    vs = run_verdicts(
        [{"number": 10, "title": f"x {slug_a}", "createdAt": old, "labels": ["bridge:queued"]},
         {"number": 11, "title": f"x {slug_a}", "createdAt": old, "labels": ["P2-medium"]},
         {"number": 12, "title": f"x {slug_a}", "createdAt": old, "labels": "bridge:queued"}],
        [], [], now)
    nums = sorted(v["number"] for v in vs)
    cases.append(("label filter keeps bridge:queued only (str-or-list)",
                  nums == [10, 12], json.dumps(vs)[:200]))

    # 11. threshold boundary: age exactly at threshold flags (>=)
    edge = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 2.0 * 3600))
    v = classify({"number": 13, "title": f"x {slug_a} y", "createdAt": edge}, [], [], now, at_risk_hours=2.0)
    cases.append(("age == threshold -> LANDING_AT_RISK (>=)", v["verdict"] == "LANDING_AT_RISK", json.dumps(v)[:160]))

    # 12. run_verdicts miss/fp proof on a mixed fixture board (the young WO
    # carries a distinct slug so the shared history can't match it).
    slug_g = "(bridge-20261028-gamma-lane)"
    vs = run_verdicts(
        [{"number": 14, "title": f"landed {slug_a}", "createdAt": old, "labels": ["bridge:queued"]},
         {"number": 15, "title": f"stuck {slug_r2}", "createdAt": old, "labels": ["bridge:queued"]},
         {"number": 16, "title": f"young {slug_g}", "createdAt": fresh, "labels": ["bridge:queued"]}],
        [f"feat: landed (bridge-20261028-alpha-lane) (#1905)"], [], now)
    by_num = {v["number"]: v["verdict"] for v in vs}
    ok = (by_num == {14: "MERGED_ON_MAIN", 15: "LANDING_AT_RISK", 16: "IN_GATES"})
    cases.append(("mixed fixture board classifies exactly", ok, json.dumps(by_num)[:200]))

    # 13. satellite refinement (the #1916 live false positive): an old
    # unmatched WO whose body targets a satellite is SATELLITE_TARGET,
    # never LANDING_AT_RISK.
    sat_body = "### Task ID\nbridge-20261028-browser-webbotauth-probe\n\n### Target Repo\nSupremeai-bd/supremeai-browser\n"
    cases.append(("parse_target_repo extracts satellite",
                  parse_target_repo(sat_body) == "Supremeai-bd/supremeai-browser",
                  repr(parse_target_repo(sat_body))))
    cases.append(("parse_target_repo open repo", parse_target_repo(
        "### Target Repo\nSupremeai-bd/supremeai-open\n") == OPEN_REPO, ""))
    cases.append(("parse_target_repo absent -> None (fail-closed default)",
                  parse_target_repo("no section here") is None, ""))
    v = classify({"number": 17, "title": f"sat {slug_a} y", "createdAt": old},
                 [], [], now, target_repo="Supremeai-bd/supremeai-browser")
    cases.append(("old unmatched satellite WO -> SATELLITE_TARGET (not risk)",
                  v["verdict"] == "SATELLITE_TARGET", json.dumps(v)[:160]))
    v = classify({"number": 18, "title": f"sat {slug_a} y", "createdAt": fresh},
                 [], [], now, target_repo="Supremeai-bd/supremeai-browser")
    cases.append(("young satellite WO -> SATELLITE_TARGET (age-independent)",
                  v["verdict"] == "SATELLITE_TARGET", json.dumps(v)[:160]))
    v = classify({"number": 19, "title": f"sat landed {slug_a}", "createdAt": old},
                 [f"feat: sat (bridge-20261028-alpha-lane) (#1906)"], [], now,
                 target_repo="Supremeai-bd/supremeai-browser")
    cases.append(("matched slug still wins over satellite hint",
                  v["verdict"] == "MERGED_ON_MAIN", json.dumps(v)[:160]))
    v = classify({"number": 20, "title": f"open {slug_a} y", "createdAt": old},
                 [], [], now, target_repo=OPEN_REPO)
    cases.append(("open-repo target keeps LANDING_AT_RISK",
                  v["verdict"] == "LANDING_AT_RISK", json.dumps(v)[:160]))

    # 13b. never-touched flap fingerprint (#2401/#2430): MERGED_ON_MAIN rows
    # whose updatedAt == createdAt carry the close-on-merge flap signature;
    # touched rows and rows missing timestamps stay untagged (honest unknown);
    # the tag propagates to FALSE_REJECTION rows (same classify path).
    merged_hist = [f"feat: landed (bridge-20261028-alpha-lane) (#1905)"]
    v = classify({"number": 31, "title": f"x {slug_a}", "createdAt": old, "updatedAt": old},
                 merged_hist, [], now)
    cases.append(("never-touched merged row carries flap fingerprint",
                  v["verdict"] == "MERGED_ON_MAIN" and v.get("never_touched") is True
                  and "flap fingerprint" in v["evidence"], json.dumps(v)[:200]))
    v = classify({"number": 32, "title": f"x {slug_a}", "createdAt": old, "updatedAt": fresh},
                 merged_hist, [], now)
    cases.append(("touched merged row carries no fingerprint",
                  v["verdict"] == "MERGED_ON_MAIN" and "never_touched" not in v,
                  json.dumps(v)[:160]))
    v = classify({"number": 33, "title": f"x {slug_a}", "createdAt": old},
                 merged_hist, [], now)
    cases.append(("missing updatedAt -> no fingerprint (honest unknown)",
                  v["verdict"] == "MERGED_ON_MAIN" and "never_touched" not in v, ""))
    vs = run_verdicts([{"number": 34, "title": f"rej {slug_a}", "createdAt": old,
                        "updatedAt": old, "labels": ["bridge:rejected"]}],
                      merged_hist, [], now)
    cases.append(("never-touched propagates to FALSE_REJECTION rows",
                  len(vs) == 1 and vs[0]["verdict"] == "FALSE_REJECTION"
                  and vs[0].get("never_touched") is True, json.dumps(vs)[:200]))

    # 14. refine_satellites: at-risk + satellite body -> downgraded; at-risk +
    # open/absent body -> kept; fetch failure -> kept (fail-closed).
    def _fetch_sat(number):
        return sat_body

    def _fetch_open(number):
        return "### Target Repo\nSupremeai-bd/supremeai-open\n"

    def _fetch_boom(number):
        raise RuntimeError("tower down")

    base_risk = {"number": 21, "verdict": "LANDING_AT_RISK", "slug": "(bridge-20261028-sat-lane)",
                 "age_hours": 3.0}
    vs = refine_satellites([dict(base_risk)], fetch_body=_fetch_sat)
    cases.append(("refine downgrades satellite-targeted at-risk WO",
                  vs[0]["verdict"] == "SATELLITE_TARGET" and vs[0]["age_hours"] == 3.0,
                  json.dumps(vs[0])[:200]))
    vs = refine_satellites([dict(base_risk)], fetch_body=_fetch_open)
    cases.append(("refine keeps open-repo at-risk WO",
                  vs[0]["verdict"] == "LANDING_AT_RISK", json.dumps(vs[0])[:160]))
    vs = refine_satellites([dict(base_risk)], fetch_body=_fetch_boom)
    cases.append(("refine is fail-closed on fetch failure (risk kept)",
                  vs[0]["verdict"] == "LANDING_AT_RISK", json.dumps(vs[0])[:160]))

    # 15. FALSE_REJECTION (the live #1972 class): a WO labeled bridge:rejected
    # whose slug IS in main history — the rejection is provably wrong.
    vs = run_verdicts(
        [{"number": 22, "title": f"recert {slug_a}", "createdAt": old,
          "labels": ["bridge:rejected"]}],
        [f"feat: landed (bridge-20261028-alpha-lane) (#1907)"], [], now)
    ok = (len(vs) == 1 and vs[0]["verdict"] == "FALSE_REJECTION"
          and "1972" in vs[0]["evidence"])
    cases.append(("rejected-but-landed -> FALSE_REJECTION (#1972 class)", ok, json.dumps(vs)[:220]))

    # 16. rejected WITHOUT landing stays unreported (rejection presumed
    # legitimate — zero new false positives on the strict surface).
    vs = run_verdicts(
        [{"number": 23, "title": f"truly rejected {slug_a}", "createdAt": old,
          "labels": ["bridge:rejected"]}],
        [], [], now)
    cases.append(("rejected without landing stays unreported", vs == [], json.dumps(vs)[:120]))

    # 17. mixed queued/rejected board: both classified, no interference.
    vs = run_verdicts(
        [{"number": 24, "title": f"queued landed {slug_a}", "createdAt": old,
          "labels": ["bridge:queued"]},
         {"number": 25, "title": f"rejected landed {slug_a}", "createdAt": old,
          "labels": ["bridge:rejected"]}],
        [f"feat: landed (bridge-20261028-alpha-lane) (#1908)"], [], now)
    by_num = {v["number"]: v["verdict"] for v in vs}
    cases.append(("mixed queued/rejected board classifies exactly",
                  by_num == {24: "MERGED_ON_MAIN", 25: "FALSE_REJECTION"}, json.dumps(by_num)[:200]))

    # 17b. full-board drainage join (#2516 remedy item 2): an open row with a
    # non-bridge label whose deliverable IS on main surfaces as MERGED_ON_MAIN
    # tagged label_plane=outside-queued — previously such rows accumulated
    # invisibly between manual matrix-scoped sweeps (live: 14 pre-crash
    # stragglers stranded while every sweep was matrix-scoped). The flap
    # fingerprint works there too; a non-landed non-queued row stays
    # unreported (zero new false positives on the strict surface).
    hist_17b = [f"feat: landed (bridge-20261028-alpha-lane) (#1908)"]
    vs = run_verdicts(
        [{"number": 35, "title": f"landed {slug_a}", "createdAt": old,
          "updatedAt": old, "labels": ["report-only", "ops"]},
         {"number": 36, "title": f"stuck {slug_r2}", "createdAt": old,
          "labels": ["status:claimed"]},
         {"number": 37, "title": f"queued landed {slug_a}", "createdAt": old,
          "labels": ["bridge:queued"]}],
        hist_17b, [], now)
    by_num = {v["number"]: v["verdict"] for v in vs}
    row35 = next((v for v in vs if v["number"] == 35), {})
    cases.append(("outside-queued landed row joins the census (#2516)",
                  by_num == {35: "MERGED_ON_MAIN", 37: "MERGED_ON_MAIN"}
                  and row35.get("label_plane") == "outside-queued"
                  and row35.get("never_touched") is True,
                  json.dumps(vs)[:220]))
    vs = run_verdicts(
        [{"number": 38, "title": f"stuck {slug_r2}", "createdAt": old,
          "labels": ["status:claimed"]}],
        hist_17b, [], now)
    cases.append(("outside-queued non-landed row stays unreported (zero fp)",
                  vs == [], json.dumps(vs)[:120]))

    # 18. feedback-plane enrichment (the guard's own documented future work;
    # live 2026-10-28 blackout class): merged rows get tower_verdict /
    # tower_unstamped; non-merged rows untouched and unprobed; fetch failure
    # -> honest unknown (None), never False; a Tower stamp -> False.
    merged_v = {"number": 26, "verdict": "MERGED_ON_MAIN", "slug": slug_a, "age_hours": 0.5}
    risk_v = {"number": 27, "verdict": "LANDING_AT_RISK", "slug": slug_r2, "age_hours": 3.0}

    def _fb_none(number):
        return {"issueNumber": number, "state": "open", "labels": ["bridge:queued"],
                "latestVerdict": None, "verdictHistory": [], "commentCount": 0}

    def _fb_stamped(number):
        return {"issueNumber": number, "state": "open", "labels": ["bridge:queued"],
                "latestVerdict": "MERGED_ON_MAIN", "verdictHistory": ["MERGED_ON_MAIN"],
                "commentCount": 1}

    def _fb_boom(number):
        raise RuntimeError("tower down")

    vs = enrich_tower_verdicts([dict(merged_v), dict(risk_v)], fetch_feedback=_fb_none)
    ok = (vs[0]["tower_unstamped"] is True and vs[0]["tower_verdict"] == "none"
          and "tower_verdict" not in vs[1])
    cases.append(("merged + null Tower verdict -> tower_unstamped (blackout visible)",
                  ok, json.dumps(vs)[:220]))
    vs = enrich_tower_verdicts([dict(merged_v)], fetch_feedback=_fb_stamped)
    cases.append(("merged + Tower stamp -> tower_unstamped False",
                  vs[0]["tower_unstamped"] is False and vs[0]["tower_verdict"] == "MERGED_ON_MAIN",
                  json.dumps(vs[0])[:160]))
    vs = enrich_tower_verdicts([dict(merged_v)], fetch_feedback=_fb_boom)
    cases.append(("feedback fetch failure -> honest unknown (never False)",
                  vs[0]["tower_unstamped"] is None and vs[0]["tower_verdict"] == "unreadable",
                  json.dumps(vs[0])[:160]))
    probed: list[int] = []

    def _fb_spy(number):
        probed.append(number)
        return _fb_none(number)

    enrich_tower_verdicts([dict(risk_v)], fetch_feedback=_fb_spy)
    cases.append(("non-merged rows cost zero feedback probes", probed == [], str(probed)))

    # queue limit ladder (deploy-window consumer, #2115/#2123)
    def _r2(name, arguments):
        assert arguments.get("limit") == 200, arguments
        return json.dumps({"workOrders": [{"number": 1}]})

    def _prer2(name, arguments):
        if arguments.get("limit") == 200:
            return "MCP error -32602: Too big: expected number to be <=50"
        assert arguments.get("limit") == 50, arguments
        return json.dumps({"workOrders": [{"number": 1}, {"number": 2}]})

    def _dead(name, arguments):
        raise ConnectionError("unreachable")

    rows, rung = _fetch_work_orders(fetch_text=_r2)
    cases.append(("ladder r2 serves rung 200",
                  rows == [{"number": 1}] and rung == 200, f"rung={rung}"))
    rows, rung = _fetch_work_orders(fetch_text=_prer2)
    cases.append(("ladder pre-r2 falls 200->50",
                  len(rows) == 2 and rung == 50, f"rung={rung}"))
    try:
        _fetch_work_orders(fetch_text=_dead)
        cases.append(("ladder transport failure fail-close", False, "no raise"))
    except ConnectionError:
        cases.append(("ladder transport failure fail-close", True, ""))
    except Exception as e:  # noqa: BLE001 — wrong failure class is a FAIL
        cases.append(("ladder transport failure fail-close", False, type(e).__name__))

    # flight plane arguments lock (wrong-repo + ignored per_page, both silent)
    sent = {}

    def _cap(name, arguments):
        sent["name"], sent["args"] = name, arguments
        return json.dumps([{"number": 2220, "title": "feat: x (bridge-20261029-y)"}])

    titles = _open_pr_titles(fetch_text=_cap)
    cases.append(("flight plane pins open repo + schema limit (no per_page)",
                  sent.get("name") == "github.list_prs"
                  and sent.get("args", {}).get("repo") == OPEN_REPO
                  and sent.get("args", {}).get("limit") == 50
                  and "per_page" not in sent.get("args", {})
                  and bool(titles), json.dumps(sent.get("args", {}))[:120]))

    # rejected plane (GitHub-side enumeration, #2158)
    page1 = [{"number": 1000 + i, "title": f"w{i}", "state": "open",
              "labels": ["bridge:rejected"]} for i in range(100)]
    page2 = [{"number": 5, "title": "a (bridge-20261028-x)", "state": "open",
              "labels": [{"name": "bridge:rejected"}]},
             {"number": 5, "title": "dup", "state": "open",
              "labels": ["bridge:rejected"]}]

    def _fake_fetch(url):
        assert "labels=bridge%3Arejected" in url, url
        return {1: page1, 2: page2}[int(url.rsplit("page=", 1)[1].split("&")[0])]

    rows = _fetch_rejected_rows(fetch_json=_fake_fetch)
    cases.append(("rejected plane paginates + dedupes + normalizes",
                  len(rows) == 101 and rows[-1]["number"] == 5
                  and rows[-1]["labels"] == ["bridge:rejected"],
                  f"rows={len(rows)}"))
    try:
        _fetch_rejected_rows(fetch_json=lambda u: {"error": "nope"})
        cases.append(("rejected plane non-list fails loud", False, "no raise"))
    except TypeError:
        cases.append(("rejected plane non-list fails loud", True, ""))

    def _boom():
        raise RuntimeError("down")

    gone, note = _load_rejected_plane(fetch_rows=_boom, tower_rows=_boom)
    cases.append(("rejected plane per-plane fail-open (both down, dual cause)",
                  gone == [] and "unreachable" in note
                  and "github RuntimeError" in note and "tower RuntimeError" in note,
                  f"note={note}"))

    def _ratelimited():
        raise urllib.error.HTTPError("https://api.github.com/x", 403,
                                     "rate limit exceeded", None, None)

    gone, note = _load_rejected_plane(fetch_rows=_ratelimited,
                                      tower_rows=lambda: [{"number": 2056}])
    cases.append(("rejected plane 403 falls back to tower, cause disclosed",
                  gone == [{"number": 2056}] and "rate limit" in note
                  and "resets hourly" in note and "tower-plane fallback" in note,
                  f"note={note}"))

    tower_rows = _fetch_rejected_rows_tower(fetch_text=lambda n, a: json.dumps(
        {"count": 1, "workOrders": [{"number": 2056, "title": "x",
                                     "labels": ["bridge:rejected"]}]}))
    cases.append(("tower rejected plane parses workOrders",
                  len(tower_rows) == 1 and tower_rows[0]["number"] == 2056,
                  f"rows={len(tower_rows)}"))
    try:
        _fetch_rejected_rows_tower(fetch_text=lambda n, a: '{"repo": "x"}')
        cases.append(("tower rejected plane missing workOrders fails loud",
                      False, "no raise"))
    except TypeError:
        cases.append(("tower rejected plane missing workOrders fails loud",
                      True, ""))
    sent_args: list = []
    _fetch_rejected_rows_tower(fetch_text=lambda n, a: (sent_args.append(dict(a)) or
        json.dumps({"count": 1, "workOrders": [{"number": 2056, "title": "x",
                                                "labels": ["bridge:rejected"]}]})))
    cases.append(("rejected tower ladder asks label+limit 200 first",
                  sent_args and sent_args[0].get("label") == REJECTED_LABEL
                  and sent_args[0].get("limit") == 200,
                  f"args={sent_args[:1]}"))
    rung_calls: list = []

    def _pre_r2(n, a):
        rung_calls.append(dict(a))
        if len(rung_calls) == 1:
            return "MCP error -32602: limit 200 above pre-r2 cap"
        return json.dumps({"count": 1, "workOrders": [{"number": 2056}]})

    descended = _fetch_rejected_rows_tower(fetch_text=_pre_r2)
    cases.append(("rejected tower ladder descends to 50, label preserved",
                  descended == [{"number": 2056}] and len(rung_calls) == 2
                  and rung_calls[1].get("label") == REJECTED_LABEL
                  and rung_calls[1].get("limit") == 50,
                  f"calls={rung_calls}"))
    joined, joined_n = _join_rejected_plane([{"number": 5, "title": "q"}], rows)
    cases.append(("rejected plane queue rows win on collision",
                  joined_n == 100 and joined[0]["title"] == "q"
                  and all(r["number"] != 5 for r in joined[1:]), f"n={joined_n}"))
    # verdict-shape hardening (cbb9ab2: blank-stamp objects are blackout)
    def _fb(n, latest):
        return {"issueNumber": n, "latestVerdict": latest, "verdictHistory": []}

    vs = enrich_tower_verdicts(
        [{"number": 60, "verdict": "MERGED_ON_MAIN"}],
        fetch_feedback=lambda n: _fb(n, {"verdict": "", "at": "x"}))
    cases.append(("enrich blank-stamp object reads unstamped",
                  vs[0]["tower_unstamped"] is True
                  and vs[0]["tower_verdict"] == "none", str(vs[0])))
    vs = enrich_tower_verdicts(
        [{"number": 61, "verdict": "MERGED_ON_MAIN"}],
        fetch_feedback=lambda n: _fb(n, {"verdict": "MERGED_ON_MAIN", "at": "x"}))
    cases.append(("enrich stamped object surfaces its token",
                  vs[0]["tower_unstamped"] is False
                  and vs[0]["tower_verdict"] == "MERGED_ON_MAIN", str(vs[0])))
    # queue-integrity plane (#2190): label-plane vs listing divergence
    missing, phantom = _check_queue_integrity({5}, {5, 9, 11})
    cases.append(("integrity missing direction",
                  missing == [9, 11] and phantom == [],
                  f"m={missing} p={phantom}"))
    missing, phantom = _check_queue_integrity({5, 7}, {5})
    cases.append(("integrity phantom direction",
                  missing == [] and phantom == [7],
                  f"m={missing} p={phantom}"))
    qpage = [{"number": 9, "title": "queued", "state": "open",
              "labels": ["bridge:queued"]}]

    def _fake_queued(url):
        assert "labels=bridge%3Aqueued" in url, url
        return qpage  # short page -> single-page enumeration

    qrows = _fetch_label_rows(QUEUED_LABEL, fetch_json=_fake_queued)
    cases.append(("label core parameterizes the queued label",
                  len(qrows) == 1 and qrows[0]["number"] == 9,
                  f"n={len(qrows)}"))
    (q_n, q_missing, q_phantom), q_note = _load_queue_integrity(
        {5, 9}, fetch_rows=lambda label: qpage)
    cases.append(("integrity ok-path diffs both directions",
                  q_note == "ok" and q_n == 1 and q_missing == []
                  and q_phantom == [5], f"m={q_missing} p={q_phantom}"))

    def _q_ratelimited(label):
        raise urllib.error.HTTPError("https://api.github.com/x", 403,
                                     "rate limit exceeded", None, None)

    qi, q_note = _load_queue_integrity({5}, fetch_rows=_q_ratelimited)
    cases.append(("integrity 403 discloses cause, unchecked never empty",
                  qi is None and "rate limit" in q_note
                  and "resets hourly" in q_note, f"note={q_note}"))

    def _q_down(label):
        raise ConnectionError("nope")

    qi, q_note = _load_queue_integrity({5}, fetch_rows=_q_down)
    cases.append(("integrity per-plane fail-open",
                  qi is None and "unreachable" in q_note, f"note={q_note}"))

    # r13/cycle-18 (Job 486770): shallow-checkout census self-heal. The only
    # wired caller checks out depth-1; the census must heal (one bounded
    # deepen) or degrade loudly — never silently join a truncated window.
    class _FakeShallowRepo:
        def __init__(self, deepen_works, heals_wider):
            self.calls: list[str] = []
            self.deepen_works = deepen_works
            self.heals_wider = heals_wider
            self._deepened = False

        def log(self, depth, git_bin):
            self.calls.append(f"log:{depth}")
            if self._deepened and self.heals_wider:
                return [f"subj-{i}" for i in range(min(depth, 400))]
            return ["subj-0"]

        def probe(self):
            self.calls.append("probe")
            return True

        def deepen(self, depth, git_bin):
            self.calls.append(f"deepen:{depth}")
            self._deepened = self.deepen_works
            return self.deepen_works

    repo = _FakeShallowRepo(deepen_works=True, heals_wider=True)
    got = _main_subjects(400, log_reader=repo.log, shallow_probe=repo.probe,
                         deepener=repo.deepen)
    cases.append(("shallow census self-heals to the full join window",
                  len(got) == 400 and any(c.startswith("deepen") for c in repo.calls),
                  f"visible={len(got)} calls={repo.calls}"))

    repo2 = _FakeShallowRepo(deepen_works=False, heals_wider=False)
    got2 = _main_subjects(400, log_reader=repo2.log, shallow_probe=repo2.probe,
                          deepener=repo2.deepen)
    cases.append(("shallow census degrades to truncated view, never crashes",
                  got2 == ["subj-0"] and repo2.calls == ["log:400", "probe", "deepen:400"],
                  f"got={got2} calls={repo2.calls}"))

    class _FakeDeepRepo:
        def __init__(self):
            self.calls: list[str] = []

        def log(self, depth, git_bin):
            self.calls.append(f"log:{depth}")
            return [f"subj-{i}" for i in range(min(depth, 400))]

        def probe(self):
            self.calls.append("probe")
            return True

        def deepen(self, depth, git_bin):
            self.calls.append("deepen:MUST-NOT-RUN")
            return True

    repo3 = _FakeDeepRepo()
    got3 = _main_subjects(400, log_reader=repo3.log, shallow_probe=repo3.probe,
                          deepener=repo3.deepen)
    cases.append(("full window skips the heal path entirely",
                  len(got3) == 400 and "deepen:MUST-NOT-RUN" not in repo3.calls,
                  f"visible={len(got3)} calls={repo3.calls}"))

    class _FakeShortRepo(_FakeDeepRepo):
        def log(self, depth, git_bin):
            self.calls.append(f"log:{depth}")
            return ["only-commit"]

        def probe(self):
            self.calls.append("probe:False")
            return False

    repo4 = _FakeShortRepo()
    got4 = _main_subjects(400, log_reader=repo4.log, shallow_probe=repo4.probe,
                          deepener=repo4.deepen)
    cases.append(("genuinely short history is not mistaken for truncation",
                  got4 == ["only-commit"] and repo4.calls == ["log:400", "probe:False"]
                  and "deepen:MUST-NOT-RUN" not in repo4.calls,
                  f"got={got4} calls={repo4.calls}"))

    # ── apply-leg honest close (false-OK class, cycle-21) ─────────────────
    class _Proc:
        def __init__(self, rc: int, err: str = "") -> None:
            self.returncode, self.stderr, self.stdout = rc, err, ""

    line = _close_result(7, "c", closer=lambda n, c: _Proc(0))
    cases.append(("apply leg reports OK only on a real exit-0 close",
                  line == "  [OK] Auto-closed #7", f"got={line!r}"))
    line = _close_result(7, "c", closer=lambda n, c: _Proc(1, "HTTP 403: Resource not accessible by integration"))
    cases.append(("apply leg reports FAIL echoing gh's own error on nonzero exit",
                  line == "  [FAIL] #7 not closed (gh exit 1): HTTP 403: Resource not accessible by integration"
                  and "[OK]" not in line, f"got={line!r}"))

    def _boom(n: int, c: str) -> subprocess.CompletedProcess:
        raise FileNotFoundError("gh: command not found")

    line = _close_result(7, "c", closer=_boom)
    cases.append(("apply leg degrades loudly when gh is missing",
                  line == "  [WARN] Failed to close #7: gh: command not found",
                  f"got={line!r}"))
    return cases


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Bridge WO landing watchdog (#1964 gap)")
    p.add_argument("--self-test", action="store_true",
                   help="hermetic verdict-matrix proof (roster mode)")
    p.add_argument("--at-risk-hours", type=float, default=DEFAULT_AT_RISK_HOURS,
                   help=f"age past which an unmatched WO flags (default {DEFAULT_AT_RISK_HOURS:g}h)")
    p.add_argument("--strict", action="store_true",
                   help="exit 1 on at-risk/aging findings (report-only default)")
    p.add_argument("--apply", action="store_true",
                   help="auto-close work orders that are MERGED_ON_MAIN or FALSE_REJECTION")
    args = p.parse_args(argv)

    if args.self_test:
        cases = self_test()
        failed = [c for c in cases if not c[1]]
        for name, ok, ev in cases:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {ev}" if not ok else ""))
        print(f"\n==== {len(cases) - len(failed)}/{len(cases)} self-test cases PASS ====")
        return 1 if failed else 0

    try:
        wos, queue_rung = _fetch_work_orders()
        subjects = _main_subjects()
        pr_titles = _open_pr_titles()
    except Exception as e:  # noqa: BLE001 - unreachable planes are a skip, never a pass
        print(f"SKIP: board/history unreachable ({e.__class__.__name__}: {e})")
        return 2

    rung_s = "default" if queue_rung is None else str(queue_rung)
    print(f"QUEUE PLANE: {len(wos)} rows (limit rung {rung_s})")
    listing_numbers = {w.get("number") for w in wos}
    rejected_rows, rejected_note = _load_rejected_plane()
    wos, rejected_joined = _join_rejected_plane(wos, rejected_rows)
    print(f"REJECTED PLANE: {len(rejected_rows)} open '{REJECTED_LABEL}' rows "
          f"enumerated ({rejected_joined} queue-omitted joined; {rejected_note})")
    integrity, integrity_note = _load_queue_integrity(listing_numbers)
    if integrity is None:
        print(f"QUEUE INTEGRITY: unchecked ({integrity_note})")
    else:
        label_n, missing, phantom = integrity
        shape = (f"{label_n} '{QUEUED_LABEL}' label rows vs "
                 f"{len(listing_numbers)} listing rows")
        if not missing and not phantom:
            print(f"QUEUE INTEGRITY: {shape} — consistent")
        else:
            bits = []
            if missing:
                head = ", ".join(f"#{n}" for n in missing[:10])
                if len(missing) > 10:
                    head += f" (+{len(missing) - 10} more)"
                bits.append(f"{len(missing)} missing from listing: {head}")
            if phantom:
                head = ", ".join(f"#{n}" for n in phantom[:10])
                if len(phantom) > 10:
                    head += f" (+{len(phantom) - 10} more)"
                bits.append(f"{len(phantom)} phantoms: {head}")
            print(f"QUEUE INTEGRITY: {shape} — " + "; ".join(bits))
    now = time.mktime(time.gmtime())
    verdicts = run_verdicts(wos, subjects, pr_titles, now, args.at_risk_hours)
    verdicts = refine_satellites(verdicts)
    verdicts = enrich_tower_verdicts(verdicts)
    if not verdicts:
        print("REPORT: no open row's deliverable is on main and no queued WO needs "
              "reconciliation (board clean).")
        return 0
    order = {"FALSE_REJECTION": 0, "LANDING_AT_RISK": 1, "MERGED_ON_MAIN": 2,
             "OPEN_PR": 3, "IN_GATES": 4, "SATELLITE_TARGET": 5, "NO_SLUG": 6}
    for v in sorted(verdicts, key=lambda v: (order.get(v["verdict"], 9), v["number"] or 0)):
        flag = "!!" if v["verdict"] in ("LANDING_AT_RISK", "FALSE_REJECTION") else "  "
        age_s = "?" if v["age_hours"] is None else f"{v['age_hours']:.1f}h"
        tv_s = f" tower_verdict={v['tower_verdict']}" if "tower_verdict" in v else ""
        nt_s = " never-touched" if v.get("never_touched") else ""
        lp_s = " plane=outside-queued" if v.get("label_plane") == "outside-queued" else ""
        print(f"{flag} #{v['number']} [{v['verdict']}] age={age_s} "
              f"slug={v['slug']}{tv_s}{nt_s}{lp_s} — {v['evidence'][:100]}")
    counts: dict[str, int] = {}
    for v in verdicts:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    print("VERDICT: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    merged_total = sum(1 for v in verdicts if v["verdict"] == "MERGED_ON_MAIN")
    # বাংলা: #2516-র দ্বিতীয় প্রতিকার-মুখ — authoritative git-join census লাইন।
    # label-plane never-touched ফিগার updatedAt==createdAt ফিঙ্গারপ্রিন্টের উপর
    # দাঁড়ায় — স্পর্শক্তরো (claim/label/কমেন্ট) census থেকে বাদ পড়ে, ফলে
    # ড্রেনেজ-প্ল্যানিং ভুল ফিগারে চলত (লাইভ: label-plane ১৪ বনাম git-join ৩৪,
    # #2516)। দুই প্লেনের ফিগার পাশাপাশি প্রিন্ট করায় পার্থক্য এখন প্রতি রানে
    # দৃশ্যমান — আর কখনো অদৃশ্যভাবে জমা হবে না।
    outside_q_n = sum(1 for v in verdicts
                      if v["verdict"] == "MERGED_ON_MAIN"
                      and v.get("label_plane") == "outside-queued")
    never_touched_n = sum(1 for v in verdicts if v.get("never_touched"))
    print(f"DRAINAGE CENSUS (git-join, full-board): {merged_total}/{len(wos)} open rows "
          f"self-fulfilled on main ({outside_q_n} outside the queued-label plane — the rows "
          f"label-scoped sweeps never see); label-plane never-touched={never_touched_n}. "
          f"git-join is authoritative (#2516: label-plane counts under-count by design) — "
          f"report-only.")
    unstamped = [v for v in verdicts if v.get("tower_unstamped") is True]
    unreadable = sum(1 for v in verdicts if v.get("tower_unstamped") is None)
    if unstamped:
        print(f"TOWER VERDICT PLANE: {len(unstamped)}/{merged_total} merged WOs carry NO Tower "
              f"verdict stamp" + (f" ({unreadable} unreadable)" if unreadable else "") +
              " — bookkeeping blackout, report-only.")
    untouched = [v for v in verdicts if v.get("never_touched")]
    if untouched:
        print(f"NEVER-TOUCHED SIGNATURE: {len(untouched)} landed WOs untouched since creation — "
              "close-on-merge flap fingerprint (#2401/#2430 class), the reconciler's "
              "exact worklist, report-only.")

    if args.apply:
        to_close = [v for v in verdicts if v["verdict"] in ("MERGED_ON_MAIN", "FALSE_REJECTION")]
        print(f"APPLY: Auto-closing {len(to_close)} landed / false-rejected work orders...")
        for item in to_close:
            num = item.get("number")
            evidence = item.get("evidence", "")
            if not num:
                continue
            comment = f"<!-- watchdog:auto-close --> Closed: work order deliverable landed on main ({evidence[:120]})."
            print(_close_result(num, comment))
    risky = [v for v in verdicts
             if v["verdict"] in ("LANDING_AT_RISK", "FALSE_REJECTION")
             or (v["verdict"] == "MERGED_ON_MAIN" and (v["age_hours"] or 0) >= args.at_risk_hours)]
    if not risky:
        return 0
    if args.strict:
        print(f"STRICT: {len(risky)} work order(s) need reconciliation — file/claim the triage lane "
              "(tracker class: #1964 eviction / #1972 false rejection; recipe: #1940 rebase+regen).")
        return 1
    print("REPORT-ONLY findings (exit 0) — rerun with --strict for a fail-closed verdict.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
