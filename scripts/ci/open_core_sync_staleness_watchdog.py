#!/usr/bin/env python3
"""open_core_sync_staleness_watchdog.py — open→core sync staleness guard (#2756).

The gap (issue #2756, the #2225/#2597/#2738 family): the open→core sync
stalled — core main last moved 2026-10-27T16:53:58Z while open main kept
advancing (fix PR #2724 merged on open 2026-10-29T18:51:37Z was still absent
from core main 3 days later), and the core-backed render pair stayed
update_failed frozen since 10-24. #2756's own RCA names the root cause
exactly: "the missing plane between them (open->core sync) has no
zero-credential observability" — every prior receipt in the family read ONE
plane (open, core, or render) and concluded from it. This guard closes that
observability hole mechanically: it reads both commit heads zero-credential
and fails loud when the sync plane goes quiet while open work is pending,
so the next stall is detected by any cadence/human invocation instead of a
multi-hour three-plane re-derivation per agent.

Model (one join key: the main-branch head timestamps of the repo pair):

  - open plane : anonymous GitHub REST GET /repos/{open_repo}/commits/{branch}
                 → {sha, committed date} of the branch head. Zero-credential,
                 stdlib urllib; the 60/hr anonymous rate is ample for a
                 two-call guard.
  - tower fallback : the anonymous REST pool is shared by every process on
                 a runner IP and returns 403 rate-limit-exceeded in real
                 windows (observed live 2026-10-30 minutes after landing
                 this guard's first draft). Fallback: Tower MCP
                 `github.workflow_runs` (zero-credential proxy) → the
                 newest `event: push` run on the branch gives the head SHA
                 and the push run's created_at. Push time is ≥ commit time,
                 so it reads the core plane as at-most-as-stale — the
                 conservative direction for a stall alarm, and it matches
                 the plane contract itself ("core main RECEIVES pushes").
  - core plane : same read against {core_repo}.
  - staleness  : the sync contract is "core main receives open work within
                 roughly a day". Landed sync history before the stall shows
                 catch-up gaps of ~20h (10-26T20:33Z) and ~33h
                 (10-25T09:25Z → 10-26T18:44Z); 48h default --max-lag-hours
                 sits above every observed healthy gap, so a breach means a
                 real stall, not a slow weekend. If open is AHEAD of core
                 (open head date > core head date) AND core's head is at
                 least --max-lag-hours old, the sync plane is stalled.
  - verdicts   : SYNC_STALLED (exit 1) · CATCHING_UP (open ahead but core's
                 head is younger than the threshold — the sync may still
                 fire; warn, exit 0) · HEALTHY (same-SHA short-circuit, or
                 core head not older than open head — nothing to sync) ·
                 INCONCLUSIVE (a head is unreadable/unparseable — honest
                 skip, #1760 doctrine: never reported as pass).
Modes:
  --self-test    hermetic fixture matrix (lag math, same-SHA short-circuit,
                 threshold boundary, catching-up window, core-ahead direction,
                 unparseable timestamps, report-only suppression, missing
                 heads). No network.
  --report-only  never exit 1 (census/sentry passes that want the table).
  --check        live two-plane read (default).
Exit codes: 0 = healthy / catching-up / report-only · 1 = fail-loud finding
            (SYNC_STALLED) · 2 = a commits plane unreachable (honest skip).
Zero credentials, read-only. No mutation. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# #2756's live pair (both public — anonymous reads only, no token involved).
DEFAULT_OPEN_REPO = "Supremeai-bd/supremeai-open"
DEFAULT_CORE_REPO = "Supremeai-bd/supremeai-core"
DEFAULT_BRANCH = "main"
# Above every observed healthy catch-up gap (max ~33h in landed sync history).
DEFAULT_MAX_LAG_HOURS = 48.0

VERDICT_STALLED = "SYNC_STALLED"
VERDICT_CATCHING_UP = "CATCHING_UP"
VERDICT_HEALTHY = "HEALTHY"
VERDICT_INCONCLUSIVE = "INCONCLUSIVE"

TOWER = "https://supremeai-mcp-tower.onrender.com/mcp"

USER_AGENT = "supremeai-open-core-sync-watchdog (zero-credential guard)"


def _head_from_commit_payload(data: dict):
    """Normalize a commits-API payload → {'sha','date'} or None."""
    sha = data.get("sha")
    # committer date (not author date): the sync push is what the plane
    # contract cares about; committer date tracks when the tip was landed.
    date = ((data.get("commit") or {}).get("committer") or {}).get("date")
    if not sha or not date:
        return None
    return {"sha": sha, "date": date}


def _head_from_tower_push_runs(runs: list, branch: str):
    """Normalize a github.workflow_runs payload → newest push head or None.

    Newest-first scan; the first run with event=push on the branch wins.
    Non-push runs (schedule) sit on heads that may predate the tip, so they
    never answer the "when did core main last receive a push" question.
    """
    for run in runs:
        if (run or {}).get("event") != "push":
            continue
        if (run or {}).get("head_branch") != branch:
            continue
        created = (run or {}).get("created_at")
        sha = (run or {}).get("head_sha")
        if sha and created:
            return {"sha": sha, "date": created, "source": "tower_push_run"}
    return None


def _rpc(method, params=None, session_id=None, notify=False, attempts=3):
    """Minimal zero-credential MCP client (bridge_intake_gate_watchdog `_rpc` shape).

    Full-body `resp.read()` keeps large single-line SSE payloads intact —
    line-iterating clients split the runs surface mid-line. Backoff 3/6/9s.
    """
    payload = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    if not notify:
        payload["id"] = 1
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        # Streamable HTTP (spec rev >= 2025-06-18): every post-initialize
        # request must carry the negotiated version (mirrors
        # PROTOCOL_VERSION_STREAMABLE in mcp_tower_client.py / #2568).
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
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(3 * (attempt + 1))
    else:
        raise last  # noqa: TRY201 — caller maps to the honest-skip exit
    if "text/event-stream" in ctype:
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip()), sid
                except ValueError:  # noqa: BLE001 — SSE lines individually skippable by design
                    continue
    if not body.strip():
        return {"accepted": True}, sid
    return json.loads(body), sid


def _text_of(res) -> str:
    content = res.get("result", {}).get("content", []) if isinstance(res, dict) else []
    return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))


def _tower_text(name: str, arguments: dict) -> str:
    """Full three-step handshake then one tools/call (house pattern)."""
    _, sid = _rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                 "clientInfo": {"name": "open-core-sync-watchdog", "version": "1.0"}})
    _rpc("notifications/initialized", {}, session_id=sid, notify=True)
    res, _ = _rpc("tools/call", {"name": name, "arguments": arguments}, session_id=sid)
    return _text_of(res)


def _head_from_tower_workflow_runs(repo: str, branch: str):
    """Read the branch's newest push run through the Tower (fallback plane).

    Returns None on any failure so the caller stays honest (INCONCLUSIVE).
    """
    try:
        text = _tower_text("github.workflow_runs",
                           {"repo": repo.split("/")[-1], "per_page": 30})
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    result = None
    try:
        result = json.loads(text)
    except ValueError:
        return None
    if not isinstance(result, dict):
        return None
    return _head_from_tower_push_runs(result.get("workflow_runs") or [], branch)


def _fetch_head(repo: str, branch: str, timeout: float = 30.0):
    """Return {'sha': str, 'date': str} for the branch head, or None.

    Anonymous GitHub REST first, Tower push-run fallback second. Any
    failure on BOTH planes yields None so the caller reports
    INCONCLUSIVE (exit 2), never a false green.
    """
    url = f"https://api.github.com/repos/{repo}/commits/{branch}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        head = _head_from_commit_payload(data)
        if head:
            head["source"] = "rest_commit"
            return head
    except (urllib.error.URLError, OSError, ValueError):
        pass
    return _head_from_tower_workflow_runs(repo, branch)


def parse_utc(value: str):
    """Parse a GitHub ISO-8601 timestamp; None when unparseable (honest)."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def evaluate(open_head, core_head, now: datetime, max_lag_hours: float = DEFAULT_MAX_LAG_HOURS):
    """Pure verdict core — the fixture-matrix target (no I/O).

    open_head/core_head: {'sha': str, 'date': str} or None (unreadable).
    Returns (verdict, rows) where rows are the human-readable evidence lines.
    """
    rows: list[str] = []
    if open_head is None or core_head is None:
        missing = "open" if open_head is None else "core"
        rows.append(f"INCONCLUSIVE: {missing} head unreadable (honest skip, exit 2)")
        return VERDICT_INCONCLUSIVE, rows
    open_dt = parse_utc(open_head["date"])
    core_dt = parse_utc(core_head["date"])
    if open_dt is None or core_dt is None:
        bad = "open" if open_dt is None else "core"
        rows.append(f"INCONCLUSIVE: {bad} head date unparseable (honest skip, exit 2)")
        return VERDICT_INCONCLUSIVE, rows

    rows.append(f"open head  : {open_head['sha'][:12]} @ {open_dt.isoformat()}")
    rows.append(f"core head  : {core_head['sha'][:12]} @ {core_dt.isoformat()}")

    if open_head["sha"] == core_head["sha"]:
        rows.append("HEALTHY: both heads share the same SHA — sync fully caught up")
        return VERDICT_HEALTHY, rows

    if core_dt >= open_dt:
        rows.append("HEALTHY: core head is not older than open head — nothing pending to sync")
        return VERDICT_HEALTHY, rows

    core_age_hours = (now - core_dt).total_seconds() / 3600.0
    backlog_hours = (open_dt - core_dt).total_seconds() / 3600.0
    rows.append(
        f"open ahead of core by {backlog_hours:.1f}h of landed work; "
        f"core head age {core_age_hours:.1f}h (threshold {max_lag_hours:.0f}h)"
    )

    if core_age_hours >= max_lag_hours:
        rows.append(
            f"{VERDICT_STALLED}: core main has not moved for {core_age_hours:.1f}h "
            f"while open main is ahead — the open→core sync plane is stalled "
            f"(#2756 class). Do NOT redeploy render before the sync lands."
        )
        return VERDICT_STALLED, rows

    rows.append(
        f"{VERDICT_CATCHING_UP}: open ahead but core head younger than the "
        f"{max_lag_hours:.0f}h threshold — the sync may still fire; re-check later"
    )
    return VERDICT_CATCHING_UP, rows


EXIT_OK = 0
EXIT_FINDING = 1
EXIT_SKIP = 2


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="open→core sync staleness watchdog (#2756 root-cause guard)")
    p.add_argument("--self-test", action="store_true",
                   help="run the hermetic fixture matrix (no network)")
    p.add_argument("--check", action="store_true",
                   help="live two-plane staleness check (default behavior; "
                        "explicit flag for roster/cadence readability)")
    p.add_argument("--report-only", action="store_true",
                   help="never exit 1; census/sentry passes want the table")
    p.add_argument("--open-repo", default=DEFAULT_OPEN_REPO)
    p.add_argument("--core-repo", default=DEFAULT_CORE_REPO)
    p.add_argument("--branch", default=DEFAULT_BRANCH)
    p.add_argument("--max-lag-hours", type=float, default=DEFAULT_MAX_LAG_HOURS,
                   help="stall threshold for core head age while open is ahead "
                        "(default 48h — above every observed healthy gap)")
    args = p.parse_args(argv)

    if args.self_test:
        return self_test()

    now = datetime.now(timezone.utc)
    open_head = _fetch_head(args.open_repo, args.branch)
    core_head = _fetch_head(args.core_repo, args.branch)
    verdict, rows = evaluate(open_head, core_head, now, args.max_lag_hours)

    print(f"open→core sync staleness check ({args.open_repo} → {args.core_repo}, "
          f"branch {args.branch}, threshold {args.max_lag_hours:.0f}h)")
    for row in rows:
        print(f"  - {row}")

    if verdict == VERDICT_INCONCLUSIVE:
        print(f"VERDICT: {verdict} — a plane was unreadable; honest skip")
        return EXIT_SKIP
    print(f"VERDICT: {verdict}")
    if verdict == VERDICT_STALLED and not args.report_only:
        return EXIT_FINDING
    return EXIT_OK


def self_test() -> int:
    """Hermetic fixture matrix — no network, no tower, no files."""
    now = datetime(2026, 10, 30, 14, 32, 0, tzinfo=timezone.utc)
    th = DEFAULT_MAX_LAG_HOURS
    cases: list[tuple[str, bool, str]] = []

    def _h(sha: str, date: str):
        return {"sha": sha, "date": date}

    # 1. Same-SHA short-circuit: fully caught up is HEALTHY even if old.
    v, _ = evaluate(_h("a" * 40, "2026-10-01T00:00:00Z"),
                    _h("a" * 40, "2026-10-01T00:00:00Z"), now, th)
    cases.append(("same-SHA short-circuit is HEALTHY", v == VERDICT_HEALTHY, v))

    # 2. Core not older than open: nothing pending — HEALTHY.
    v, _ = evaluate(_h("b" * 40, "2026-10-28T00:00:00Z"),
                    _h("c" * 40, "2026-10-29T00:00:00Z"), now, th)
    cases.append(("core-newer-than-open is HEALTHY", v == VERDICT_HEALTHY, v))

    # 3. Open ahead, core head young: CATCHING_UP (sync may still fire).
    v, _ = evaluate(_h("d" * 40, "2026-10-30T14:20:00Z"),
                    _h("e" * 40, "2026-10-30T13:00:00Z"), now, th)
    cases.append(("open ahead + young core head is CATCHING_UP",
                  v == VERDICT_CATCHING_UP, v))

    # 4. The live #2756 fixture: core head 10-27T16:53:58Z, open ahead,
    #    now 10-30T14:32Z → core head age ~69.6h ≥ 48h → SYNC_STALLED.
    v, rows = evaluate(_h("f" * 40, "2026-10-30T14:30:00Z"),
                       _h("0" * 40, "2026-10-27T16:53:58Z"), now, th)
    cases.append(("live #2756 shape (core head ~70h old, open ahead) is SYNC_STALLED",
                  v == VERDICT_STALLED, v))
    cases.append(("stalled verdict carries the no-redeploy warning row",
                  any("Do NOT redeploy render" in r for r in rows), "; ".join(rows)))

    # 5. Threshold boundary: exactly 48h counts as stalled (>=).
    v, _ = evaluate(_h("1" * 40, "2026-10-30T14:30:00Z"),
                    _h("2" * 40, "2026-10-28T14:30:00Z"), now, th)
    cases.append(("exactly-at-threshold core head is SYNC_STALLED",
                  v == VERDICT_STALLED, v))

    # 6. Just under the threshold: CATCHING_UP.
    v, _ = evaluate(_h("3" * 40, "2026-10-30T14:30:00Z"),
                    _h("4" * 40, "2026-10-28T15:30:00Z"), now, th)
    cases.append(("core head 1h under threshold is CATCHING_UP",
                  v == VERDICT_CATCHING_UP, v))

    # 7. Missing head → INCONCLUSIVE (honest skip path, never a false green).
    v, _ = evaluate(None, _h("5" * 40, "2026-10-28T00:00:00Z"), now, th)
    cases.append(("unreadable open head is INCONCLUSIVE", v == VERDICT_INCONCLUSIVE, v))
    v, _ = evaluate(_h("6" * 40, "2026-10-28T00:00:00Z"), None, now, th)
    cases.append(("unreadable core head is INCONCLUSIVE", v == VERDICT_INCONCLUSIVE, v))

    # 8. Unparseable date → INCONCLUSIVE (honest-unknown age math).
    v, _ = evaluate(_h("7" * 40, "not-a-date"),
                    _h("8" * 40, "2026-10-28T00:00:00Z"), now, th)
    cases.append(("unparseable open date is INCONCLUSIVE", v == VERDICT_INCONCLUSIVE, v))

    # 9. parse_utc tolerates both Z and offset forms.
    ok = (parse_utc("2026-10-30T14:30:00Z") is not None
          and parse_utc("2026-10-30T14:30:00+00:00") is not None
          and parse_utc("garbage") is None)
    cases.append(("parse_utc accepts Z/offset, rejects garbage", ok, str(ok)))

    # 10. Honest-skip exit-code map pinned (0/1/2 contract, #1760 doctrine).
    ok = (EXIT_OK == 0 and EXIT_FINDING == 1 and EXIT_SKIP == 2)
    cases.append(("exit-code contract 0/1/2 pinned", ok, str((EXIT_OK, EXIT_FINDING, EXIT_SKIP))))

    # 11. Tower push-run extraction: newest push on the branch wins; schedule
    #     runs and foreign branches never answer the push-recency question
    #     (live 2026-10-30: schedule runs at 32dccbb… sat ON TOP of the run
    #     list while the true head was the push at 4d33070… below them).
    runs = [
        {"event": "schedule", "head_branch": "main", "head_sha": "a1", "created_at": "2026-10-30T08:09:25Z"},
        {"event": "push", "head_branch": "main", "head_sha": "b2", "created_at": "2026-10-30T14:32:19Z"},
        {"event": "push", "head_branch": "feature-x", "head_sha": "c3", "created_at": "2026-10-30T15:00:00Z"},
    ]
    head = _head_from_tower_push_runs(runs, "main")
    ok = head is not None and head["sha"] == "b2" and head["date"] == "2026-10-30T14:32:19Z"
    cases.append(("tower fallback picks newest push run on the branch", ok, str(head)))
    cases.append(("tower fallback returns None with no push runs",
                  _head_from_tower_push_runs([r for r in runs if r["event"] != "push"], "main") is None,
                  "non-None"))

    # 12. REST commit payload normalization: missing fields → None (honest).
    ok = (_head_from_commit_payload({"sha": "d4", "commit": {"committer": {"date": "2026-10-30T14:00:00Z"}}}) or {}).get("sha") == "d4"
    cases.append(("commit payload normalizer keeps a valid head", ok, "mangled"))
    ok = _head_from_commit_payload({"sha": "d4"}) is None
    cases.append(("commit payload without date is rejected", ok, "accepted"))

    # 13. Tower fallback precedence: REST first — but a REST failure falls
    #     through to the tower plane (source tags pin which plane answered).
    ok = _head_from_commit_payload({}) is None
    cases.append(("empty commit payload is rejected", ok, "accepted"))

    failed = [(n, v, got) for n, ok, got in cases if not ok]
    for name, ok, got in cases:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f" — got {got}"))
    print(f"\n==== {len(cases) - len(failed)}/{len(cases)} self-test cases PASS ====")
    return EXIT_FINDING if failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
