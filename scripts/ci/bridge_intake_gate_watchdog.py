#!/usr/bin/env python3
"""bridge_intake_gate_watchdog.py — Bridge Intake gate streak watchdog (#2792 guard 5).

The gap (docs/reports/INTAKE_RCA_2792_2026-10-30.md, guard 5, quoted from the
#2792 finding): "Optional guard once RCA lands: fail-loud alerting on 2+
consecutive intake failures (the sentry window relied on manual observation
this time — 3 runs passed before a scout note existed)." The RCA's guards 1-4
landed via scripts/bridge/bridge_intake.py (docs/reports/
BRIDGE_INTAKE_POISON_GUARD_2026-10-30.md); guard 5 stayed open because the
wiring note assumed .github/ — but DETECTION needs no workflow write: this
watchdog reads the runs plane zero-credential through the Tower and exits
non-zero, so any cadence/sentry/human invocation sees the red without a
scout having to re-derive the streak by hand.

Model (one join key: the workflow name needle):

  - runs plane : Tower `github.workflow_runs` on the private repo
                 (Supremeai-bd/supremeai), raw full-body MCP read — the
                 runs payload is a single large SSE data line that
                 iter_lines-based clients split at chunk boundaries
                 (the same transport discipline as
                 scripts/ci/bridge_landing_watchdog.py `_rpc`).
  - streak     : newest-first completed runs; every `failure` increments,
                 a `success` stops the scan, and INCONCLUSIVE runs
                 (cancelled/timed_out/anything not success|failure, plus
                 non-completed status) neither count nor reset — the
                 doctrine mirror of the #3050 stale-incident probe
                 ("cancelled must not read as red"), inverted for streaks:
                 a cancelled run between failures is not a recovery, so
                 the scan continues past it. The streak is the RCA alert
                 contract: 2+ consecutive failures = persistent outage,
                 1 = transient (warn, exit 0).
  - starvation : hours since the newest run of ANY conclusion (RCA §1:
                 "GitHub-side schedule drops; the hourly-cron assumption
                 in any latency SLO is false" — 3-8h gaps observed for
                 days). Informational by default; `--strict-stale-hours`
                 opts the invocation into failing loud on it, so the
                 strict surface stays minimal by default.
  - verdicts   : ALERT_STREAK (exit 1) · SINGLE_FAILURE (warn, exit 0) ·
                 HEALTHY · plus the STALE_RUN / IN_FLIGHT /
                 INCONCLUSIVE_PRESENT info rows.

Modes:
  --self-test  hermetic fixture matrix (streak math, inconclusive
               handling, threshold boundary, name filtering, honest
               window-exhaustion, unparseable timestamps). No network.
  --report-only  never exit 1 (census/sentry passes that want the table).
Exit codes: 0 = healthy / report-only · 1 = fail-loud finding ·
            2 = runs plane unreachable or workflow absent from the window
            (honest skip — never reported as pass, #1760 doctrine).

Zero credentials, read-only. No mutation. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOWER = "https://supremeai-mcp-tower.onrender.com/mcp"
# The intake gate lives in the PRIVATE repo (agents never touch it — the
# watchdog only READS its runs plane through the zero-credential Tower).
INTAKE_REPO = "Supremeai-bd/supremeai"
# Case-insensitive substring: the workflow's display name carries a unicode
# suffix ("Bridge Intake (public work orders → private gates)"); the needle
# must survive cosmetic renames of that suffix.
WORKFLOW_NEEDLE = "bridge intake"
DEFAULT_PER_PAGE = 30
# RCA guard-5 contract: "fail-loud alerting on 2+ consecutive intake failures".
DEFAULT_STREAK_THRESHOLD = 2
# RCA §1 starvation datum: hourly cron, but 3-8h gaps observed for days.
# Informational default; strict only via --strict-stale-hours.
DEFAULT_STALE_HOURS = 8.0

VERDICT_ALERT = "ALERT_STREAK"
VERDICT_SINGLE = "SINGLE_FAILURE"
VERDICT_HEALTHY = "HEALTHY"

_id = [100]


def _rpc(method, params=None, session_id=None, notify=False, attempts=3):
    """Minimal zero-credential MCP client (bridge_landing_watchdog `_rpc` shape).

    Full-body `resp.read()` keeps large single-line SSE payloads intact —
    the runs surface answers ~100KB+ for per_page>=12 and line-iterating
    clients split it mid-line (documented live 2026-10-30 in
    continuous_agent_loop._tower_board_rows). Backoff is 3/6/9s (worst case
    ~18s) — a cadence-invoked detector must not hang a runner lane.
    """
    payload = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    if not notify:
        _id[0] += 1
        payload["id"] = _id[0]
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        # Streamable HTTP (spec rev >= 2025-06-18): every post-initialize
        # request must carry the negotiated version (#2568, radar R70);
        # mirrors PROTOCOL_VERSION_STREAMABLE in mcp_tower_client.py.
        "MCP-Protocol-Version": "2025-11-25",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(TOWER, data=json.dumps(payload).encode(),
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:  # nosec B310 — pinned https module constant (house audit #2081 class)
                sid = resp.headers.get("Mcp-Session-Id")
                body = resp.read().decode("utf-8", errors="replace")
                ctype = resp.headers.get("Content-Type") or ""
                break
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(3 * (attempt + 1))
    else:
        raise last  # noqa: TRY201 — caller maps to the honest-skip exit
    if "text/event-stream" in ctype:
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip()), sid
                except Exception:  # noqa: BLE001  # nosec B112 — SSE lines individually skippable by design (#2081 audit class)
                    continue
    if not body.strip():
        return {"accepted": True}, sid
    return json.loads(body), sid


def _text_of(res) -> str:
    content = res.get("result", {}).get("content", []) if isinstance(res, dict) else []
    return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))


def _tower_text(name: str, arguments: dict) -> str:
    _, sid = _rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                 "clientInfo": {"name": "bridge-intake-gate-watchdog", "version": "1.0"}})
    _rpc("notifications/initialized", {}, session_id=sid, notify=True)
    res, _ = _rpc("tools/call", {"name": name, "arguments": arguments}, session_id=sid)
    return _text_of(res)


def parse_runs(text: str) -> list[dict]:
    """Extract the workflow_runs list from a tool text answer (tolerant)."""
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        return []
    return [r for r in runs if isinstance(r, dict)]


def filter_intake_runs(runs: list[dict], needle: str = WORKFLOW_NEEDLE) -> list[dict]:
    """Keep only the intake-gate workflow's rows, newest-first (as served).

    Match is case-insensitive substring on the run's workflow `name` — the
    display name's unicode suffix may be renamed without a contract break.
    """
    n = needle.strip().lower()
    out = []
    for r in runs:
        name = str(r.get("name") or "")
        if n in name.lower():
            out.append(r)
    return out


def age_hours(iso_ts: str | None, now_epoch: float) -> float | None:
    """Hours between an ISO-8601 Z timestamp and now; None when unparseable."""
    if not isinstance(iso_ts, str) or not iso_ts:
        return None
    try:
        import datetime as _dt

        ts = _dt.datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return max(0.0, (now_epoch - ts.timestamp()) / 3600.0)
    except Exception:  # noqa: BLE001 — honest-unknown on any shape drift
        return None


def summarize_streak(runs: list[dict]) -> dict:
    """Streak/health summary from newest-first intake runs (pure core).

    - streak: consecutive newest COMPLETED runs with conclusion == "failure";
      a "success" stops the scan; inconclusive rows (any other conclusion,
      or status not completed) neither count nor reset — cancelled between
      failures is not a recovery (#3050 doctrine inverted for streaks).
    - in_flight: a newest non-completed run is reported, never counted.
    """
    summary: dict = {
        "streak": 0,
        "first_failure": None,
        "last_success": None,
        "last_run": None,
        "in_flight": None,
        "inconclusive_skipped": 0,
        "scanned": 0,
    }
    streak_closed = False
    for r in runs:
        summary["scanned"] += 1
        status = str(r.get("status") or "").lower()
        conclusion = str(r.get("conclusion") or "").lower()
        if status != "completed":
            if summary["in_flight"] is None:
                summary["in_flight"] = r
            continue  # in-flight/pending/queued: never counts, never resets
        if summary["last_run"] is None:
            summary["last_run"] = r
        if conclusion not in ("success", "failure"):
            summary["inconclusive_skipped"] += 1
            continue  # cancelled/timed_out/etc: inconclusive, scan continues
        if conclusion == "success":
            if summary["last_success"] is None:
                summary["last_success"] = r
            streak_closed = True
            break  # newest success reached — streak is final
        # conclusion == "failure"
        if not streak_closed:
            summary["streak"] += 1
            if summary["first_failure"] is None:
                summary["first_failure"] = r
    return summary


def verdict_for(summary: dict, threshold: int, stale_hours: float | None,
                now_epoch: float, strict_stale: bool = False) -> tuple[str, int]:
    """Pure decision core: (verdict token, exit code) from a streak summary.

    RCA guard-5 contract: streak >= threshold (default 2) fails loud (1);
    a single failure is a transient warn (0); healthy is 0. The starvation
    datum is informational unless the caller opts in via strict_stale with
    a stale_hours bound.
    """
    if summary["streak"] >= threshold:
        return VERDICT_ALERT, 1
    if summary["streak"] == 1:
        return VERDICT_SINGLE, 0
    age = None
    if summary["last_run"] is not None:
        age = age_hours(summary["last_run"].get("created_at"), now_epoch)
    if strict_stale and stale_hours is not None and age is not None and age > stale_hours:
        return "STALE_RUN", 1
    return VERDICT_HEALTHY, 0


def fetch_intake_summary(fetch_text=_tower_text, per_page: int = DEFAULT_PER_PAGE) -> tuple[dict, list[dict], list[dict]]:
    """Live runs fetch + intake filter + streak summary.

    Returns (summary, intake_rows, all_rows). Raises on transport failure —
    main() maps that to the honest-skip exit 2.
    """
    text = fetch_text("github.workflow_runs", {"repo": INTAKE_REPO, "per_page": per_page})
    all_runs = parse_runs(text)
    intake = filter_intake_runs(all_runs)
    if not intake:
        raise LookupError(
            f"no '{WORKFLOW_NEEDLE}' runs in the {len(all_runs)}-row window "
            f"(per_page={per_page}) — renamed workflow or deep schedule starvation; "
            "widen --per-page before trusting any green")
    return summarize_streak(intake), intake, all_runs


def self_test() -> list[tuple[str, bool, str]]:
    """Hermetic fixture matrix — no network (house roster mode)."""
    cases: list[tuple[str, bool, str]] = []

    def _run(num, status="completed", conclusion="success", created="2026-10-30T08:43:11Z", name="Bridge Intake (public work orders → private gates)"):
        return {"id": num, "run_number": num, "name": name, "status": status,
                "conclusion": conclusion, "created_at": created}

    # streak math: 3 failures newest-first → 3 (the live #327-#329 shape)
    runs = [_run(329, conclusion="failure", created="2026-10-29T16:56:58Z"),
            _run(328, conclusion="failure", created="2026-10-29T10:05:10Z"),
            _run(327, conclusion="failure", created="2026-10-29T02:28:51Z"),
            _run(326, conclusion="success", created="2026-10-28T23:15:46Z")]
    s = summarize_streak(runs)
    cases.append(("three failures newest-first -> streak 3, first_failure=#329",
                  s["streak"] == 3 and s["first_failure"]["run_number"] == 329,
                  str(s["streak"])))
    v, code = verdict_for(s, DEFAULT_STREAK_THRESHOLD, DEFAULT_STALE_HOURS, 0.0)
    cases.append(("streak 3 >= threshold 2 -> ALERT exit 1",
                  v == VERDICT_ALERT and code == 1, f"{v}/{code}"))

    # healthy: newest success stops the scan immediately
    runs = [_run(332, conclusion="success", created="2026-10-30T08:43:11Z"),
            _run(331, conclusion="success"),
            _run(329, conclusion="failure")]
    s = summarize_streak(runs)
    cases.append(("newest success -> streak 0, last_success=#332, scan stopped",
                  s["streak"] == 0 and s["last_success"]["run_number"] == 332
                  and s["scanned"] == 1, str(s)))
    v, code = verdict_for(s, DEFAULT_STREAK_THRESHOLD, DEFAULT_STALE_HOURS, 0.0)
    cases.append(("streak 0 -> HEALTHY exit 0", v == VERDICT_HEALTHY and code == 0, f"{v}/{code}"))

    # single failure: transient warn, exit 0 (the threshold boundary)
    runs = [_run(340, conclusion="failure"), _run(339, conclusion="success")]
    s = summarize_streak(runs)
    v, code = verdict_for(s, DEFAULT_STREAK_THRESHOLD, DEFAULT_STALE_HOURS, 0.0)
    cases.append(("streak 1 < threshold 2 -> SINGLE_FAILURE exit 0",
                  v == VERDICT_SINGLE and code == 0, f"{v}/{code}"))

    # in-flight top run: reported, never counted, streak reads below it
    runs = [_run(341, status="in_progress", conclusion=None),
            _run(340, conclusion="failure"),
            _run(339, conclusion="failure"),
            _run(338, conclusion="success")]
    s = summarize_streak(runs)
    cases.append(("in-flight top -> streak 2 from below, in_flight=#341",
                  s["streak"] == 2 and s["in_flight"]["run_number"] == 341
                  and s["first_failure"]["run_number"] == 340, str(s["streak"])))

    # inconclusive between failures: cancelled neither counts nor resets
    runs = [_run(342, conclusion="failure"),
            _run(341, conclusion="cancelled"),
            _run(340, conclusion="failure"),
            _run(339, conclusion="success")]
    s = summarize_streak(runs)
    cases.append(("cancelled between failures -> streak 2, inconclusive_skipped=1",
                  s["streak"] == 2 and s["inconclusive_skipped"] == 1, str(s)))

    # threshold override: threshold=1 makes a single failure loud
    runs = [_run(340, conclusion="failure"), _run(339, conclusion="success")]
    s = summarize_streak(runs)
    v, code = verdict_for(s, 1, DEFAULT_STALE_HOURS, 0.0)
    cases.append(("threshold 1 -> single failure ALERTs", code == 1, f"{v}/{code}"))

    # strict-stale opt-in: old last_run + strict flag -> STALE_RUN exit 1
    runs = [_run(332, conclusion="success", created="2026-10-28T08:43:11Z")]
    s = summarize_streak(runs)
    now = 1793457600.0  # ~2026-10-31T04:00Z: >8h past the run
    v, code = verdict_for(s, DEFAULT_STREAK_THRESHOLD, DEFAULT_STALE_HOURS, now, strict_stale=True)
    cases.append(("strict-stale on 44h-old last run -> STALE_RUN exit 1",
                  v == "STALE_RUN" and code == 1, f"{v}/{code}"))
    v, code = verdict_for(s, DEFAULT_STREAK_THRESHOLD, DEFAULT_STALE_HOURS, now, strict_stale=False)
    cases.append(("default (no strict-stale) keeps starvation informational",
                  v == VERDICT_HEALTHY and code == 0, f"{v}/{code}"))

    # filtering: needle survives the unicode display suffix; other workflows drop
    runs = [_run(1, name="Bridge Intake (public work orders → private gates)"),
            _run(2, name="🔧 Nightly Ops & Maintenance"),
            _run(3, name="bridge intake (renamed suffix)")]
    intake = filter_intake_runs(runs)
    cases.append(("needle matches case-insensitively, foreign workflows drop",
                  [r["run_number"] for r in intake] == [1, 3], str([r["run_number"] for r in intake])))

    # payload parsing: tolerant of wrappers and junk
    cases.append(("parse_runs tolerates junk", parse_runs("not json") == [], ""))
    cases.append(("parse_runs reads workflow_runs shape",
                  parse_runs('{"workflow_runs": [{"name": "Bridge Intake"}]}') ==
                  [{"name": "Bridge Intake"}], ""))
    cases.append(("parse_runs drops non-dict rows",
                  parse_runs('{"workflow_runs": [1, {"name": "x"}]}') == [{"name": "x"}], ""))

    # age math: unparseable/missing timestamps are honest-unknown
    cases.append(("age_hours None on junk", age_hours("junk", 0.0) is None, ""))
    cases.append(("age_hours None on missing", age_hours(None, 0.0) is None, ""))
    ok_age = age_hours("2026-10-30T08:43:11Z", 1793436191.0)  # base epoch + 86400s = exactly +24h
    cases.append(("age_hours computes positive hours", ok_age is not None and 23.9 < ok_age < 24.1, str(ok_age)))

    # verdict_for on empty summary (no runs at all) stays healthy — the
    # window-exhaustion guard is fetch_intake_summary's LookupError, not here.
    v, code = verdict_for(summarize_streak([]), DEFAULT_STREAK_THRESHOLD, DEFAULT_STALE_HOURS, 0.0)
    cases.append(("empty summary -> HEALTHY exit 0 (window guard lives in fetch)",
                  v == VERDICT_HEALTHY and code == 0, f"{v}/{code}"))
    return cases


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Bridge Intake gate streak watchdog (#2792 guard 5)")
    p.add_argument("--self-test", action="store_true",
                   help="hermetic fixture matrix (roster mode, no network)")
    p.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE,
                   help=f"runs window size (default {DEFAULT_PER_PAGE})")
    p.add_argument("--threshold", type=int, default=DEFAULT_STREAK_THRESHOLD,
                   help=f"consecutive failures that fail loud (default {DEFAULT_STREAK_THRESHOLD})")
    p.add_argument("--stale-hours", type=float, default=DEFAULT_STALE_HOURS,
                   help=f"informational starvation bound in hours (default {DEFAULT_STALE_HOURS:g}h)")
    p.add_argument("--strict-stale-hours", action="store_true",
                   help="opt-in: hours-since-last-run past --stale-hours also exits 1")
    p.add_argument("--report-only", action="store_true",
                   help="never exit 1 (census/sentry table mode)")
    args = p.parse_args(argv)

    if args.self_test:
        cases = self_test()
        failed = [c for c in cases if not c[1]]
        for name, ok, ev in cases:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {ev}" if not ok else ""))
        print(f"\n==== {len(cases) - len(failed)}/{len(cases)} self-test cases PASS ====")
        return 1 if failed else 0

    try:
        summary, intake, _all = fetch_intake_summary(per_page=args.per_page)
    except Exception as e:  # noqa: BLE001 — unreachable planes are a skip, never a pass
        print(f"SKIP: intake runs plane unreachable ({e.__class__.__name__}: {e})")
        return 2

    now = time.mktime(time.gmtime())
    verdict, code = verdict_for(summary, args.threshold, args.stale_hours, now,
                                strict_stale=args.strict_stale_hours)
    print(f"RUNS PLANE: {len(intake)} '{WORKFLOW_NEEDLE}' rows in the per_page={args.per_page} window")
    for r in intake[:10]:
        status = str(r.get("status") or "?")
        concl = str(r.get("conclusion") or "-")
        print(f"  #{r.get('run_number')} {status}/{concl} {r.get('created_at')}")
    if summary["in_flight"] is not None:
        print(f"IN FLIGHT: run #{summary['in_flight'].get('run_number')} "
              f"({summary['in_flight'].get('status')}) — not counted")
    if summary["inconclusive_skipped"]:
        print(f"INCONCLUSIVE: {summary['inconclusive_skipped']} row(s) skipped "
              "(cancelled/timed-out — neither red nor recovery, #3050 doctrine)")
    last_age = age_hours(summary["last_run"].get("created_at"), now) if summary["last_run"] else None
    age_s = "?" if last_age is None else f"{last_age:.1f}h"
    print(f"LAST RUN: {age_s} ago (starvation INFO bound {args.stale_hours:g}h"
          + (", strict" if args.strict_stale_hours else ", report-only") + ")")
    if summary["streak"] == 0:
        print(f"VERDICT: {verdict} — intake gate green "
              f"(last success: {summary['last_success'].get('created_at') if summary['last_success'] else 'none in window'})")
    else:
        print(f"VERDICT: {verdict} — {summary['streak']} consecutive failure(s) "
              f"(newest #{summary['first_failure'].get('run_number') if summary['first_failure'] else '?'}); "
              f"threshold {args.threshold}")
    if verdict == VERDICT_ALERT:
        print("ALERT: persistent intake-gate outage — public work orders are not "
              "reaching the private gates. RCA: docs/reports/INTAKE_RCA_2792_2026-10-30.md "
              "(guards 1-4 landed in scripts/bridge/bridge_intake.py); triage lane: "
              "file/claim a scout(platform) row with the run ids above.")
    if args.report_only and code == 1:
        print("REPORT-ONLY: suppressing exit 1 by flag.")
        return 0
    return code


if __name__ == "__main__":
    sys.exit(main())
