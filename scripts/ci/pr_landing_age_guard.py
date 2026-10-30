#!/usr/bin/env python3
"""pr_landing_age_guard.py — PR-lane strand tripwire (post-#3418 landing family).

The measured failure class (2026-10-31, audit snapshot 17:21Z): 27 open
non-draft PRs, oldest 5.7h, 20 of them never-touched (updatedAt == createdAt),
while PRs filed minutes earlier kept landing (#3599: filed 17:18:57Z, landed
~3min). Root cause: `auto-landing` in .github/workflows/pipeline.yml is
per-PR event-driven ONLY — a PR whose single pipeline run misses the landing
window (any required check fails -> job SKIPPED silently, so the in-job
failure watchdog never fires; or green-but-conflicting -> 3-attempt ladder
fails once) is NEVER revisited: no schedule trigger, no sweep, no retry.
Strand queue consequences are compounding: wired-but-absent roster rows
(verdict_plane_age_guard.py wired by #3267/#3316 while carrying PR #3257
stranded) and duplicate re-solves (#3484/#3490/#3497 re-attempt the same
dispatch class that is already stranded in the queue).

This guard is the PR-lane mirror of bridge_landing_watchdog.py (which treats
`OPEN_PR` as healthy and therefore cannot see this class) and
verdict_plane_age_guard.py (age-bounded verdict-plane SLA, #2567). It is a
tripwire ONLY: classification + census + strict exit code. The sweep/remedy
(scheduled re-evaluation, branch rebase, re-landing attempts) is a
.github/ pipeline change and stays owner-lane (#2512, #3527 precedent).

Verdicts (per open PR):
  IN_FLIGHT              age < threshold — pipeline may still be running
  STRANDED_NEVER_TOUCHED age >= threshold AND updatedAt == createdAt
                         (zero landing-plane progress signal: no rebase,
                         no comment, no label touch since creation)
  STRANDED_TOUCHED       age >= threshold, touched — progress exists but
                         the PR is still unlanded past the SLA

Exit codes: 0 report-only pass · 1 --strict findings · 2 honest-skip
(tower unreachable) — same semantics as bridge_landing_watchdog.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

TOWER = "https://supremeai-mcp-tower.onrender.com/mcp"
OPEN_REPO = "Supremeai-bd/supremeai-open"

# Strand SLA: an open non-draft PR older than this with no landing is a
# strand candidate. 2.0h matches bridge_landing_watchdog's at-risk horizon;
# the 2026-10-31 snapshot measured a 5.7h-old cohort against a ~3min median
# landing latency for fresh PRs, so 2h keeps the false-positive surface at
# zero for in-run pipelines (pipeline timeout-minutes max is 15).
DEFAULT_MAX_AGE_HOURS = 2.0

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_id = [100]


def _rpc(method, params=None, session_id=None, notify=False, attempts=3):
    """Minimal zero-credential MCP client (same protocol as the watchdog fleet)."""
    payload = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    if not notify:
        _id[0] += 1
        payload["id"] = _id[0]
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": "2025-11-25"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(TOWER, data=json.dumps(payload).encode(),
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:  # nosec B310 — pinned https tower constant
                sid = resp.headers.get("Mcp-Session-Id")
                body = resp.read().decode("utf-8", errors="replace")
                ctype = resp.headers.get("Content-Type") or ""
                break
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(5 * (attempt + 1))
    else:
        raise last  # noqa: TRY201 — caller maps to the honest-skip exit
    if "text/event-stream" in ctype:
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip()), sid
                except Exception:  # noqa: BLE001 — SSE lines are individually skippable by design
                    continue
    if not body.strip():
        return {"accepted": True}, sid
    return json.loads(body), sid


def _text_of(res) -> str:
    content = res.get("result", {}).get("content", []) if isinstance(res, dict) else []
    return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))


def _tower_text(name: str, arguments: dict) -> str:
    _, sid = _rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                 "clientInfo": {"name": "pr-landing-age-guard", "version": "1.0"}})
    _rpc("notifications/initialized", {}, session_id=sid, notify=True)
    res, _ = _rpc("tools/call", {"name": name, "arguments": arguments}, session_id=sid)
    return _text_of(res)


def _age_hours(created_at: str, now_epoch: float) -> float | None:
    """PR age in hours, or None on an unparseable timestamp (honest no-signal)."""
    if not created_at or not TS_RE.match(created_at):
        return None
    try:
        c = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return max(0.0, (now_epoch - c.timestamp()) / 3600.0)


def classify_pr(pr: dict, now_epoch: float,
                max_age_hours: float = DEFAULT_MAX_AGE_HOURS) -> dict:
    """Verdict one open PR row against the strand SLA.

    `touched` = updatedAt != createdAt — the only zero-credential progress
    signal github.list_prs exposes (a rebase, comment, label or review all
    bump updatedAt; check-run activity does not). Never-touched rows past
    the SLA are the purest strand fingerprint: the landing plane never came
    back and nobody else did either.
    """
    num = pr.get("number")
    created = pr.get("createdAt") or ""
    updated = pr.get("updatedAt") or ""
    age = _age_hours(created, now_epoch)
    base = {"number": num, "age_hours": age,
            "never_touched": bool(created and updated and created == updated)}
    if age is None:
        return {**base, "verdict": "NO_TIMESTAMP",
                "evidence": "unparseable createdAt (honest no-signal)"}
    if age < max_age_hours:
        return {**base, "verdict": "IN_FLIGHT",
                "evidence": f"age {age:.1f}h < SLA {max_age_hours:g}h"}
    kind = "STRANDED_NEVER_TOUCHED" if base["never_touched"] else "STRANDED_TOUCHED"
    return {**base, "verdict": kind,
            "evidence": f"open and unlanded {age:.1f}h >= SLA {max_age_hours:g}h; "
                        f"{'zero progress signal since creation' if base['never_touched'] else 'touched but still unlanded'}"}


def census(verdicts: list[dict]) -> dict:
    """Aggregate verdict counts (pure; self-test asserts the rollup)."""
    out = {"total": len(verdicts), "IN_FLIGHT": 0, "STRANDED_NEVER_TOUCHED": 0,
           "STRANDED_TOUCHED": 0, "NO_TIMESTAMP": 0}
    for v in verdicts:
        out[v["verdict"]] = out.get(v["verdict"], 0) + 1
    out["stranded_total"] = out["STRANDED_NEVER_TOUCHED"] + out["STRANDED_TOUCHED"]
    return out


def run_check(fetch_text=_tower_text, now_epoch: float | None = None,
              max_age_hours: float = DEFAULT_MAX_AGE_HOURS) -> tuple[list[dict], dict]:
    """Live plane read via tower github.list_prs; returns (verdicts, census)."""
    if now_epoch is None:
        now_epoch = datetime.now(timezone.utc).timestamp()
    txt = fetch_text("github.list_prs",
                     {"state": "open", "repo": OPEN_REPO, "per_page": 100})
    data = json.loads(txt)
    prs = data if isinstance(data, list) else data.get("prs", data.get("pullRequests", []))
    verdicts = [classify_pr(p, now_epoch, max_age_hours) for p in prs]
    return verdicts, census(verdicts)


def self_test() -> list[tuple[str, bool, str]]:
    """Hermetic verdict-matrix proof: every class reachable, zero network."""
    now = datetime.strptime("2026-10-31T17:22:00Z", "%Y-%m-%dT%H:%M:%SZ").timestamp()
    cases: list[tuple[str, bool, str]] = []

    v = classify_pr({"number": 1, "createdAt": "2026-10-31T17:18:57Z",
                     "updatedAt": "2026-10-31T17:18:57Z"}, now)
    cases.append(("fresh PR is IN_FLIGHT", v["verdict"] == "IN_FLIGHT", str(v)))

    v = classify_pr({"number": 2, "createdAt": "2026-10-30T11:37:01Z",
                     "updatedAt": "2026-10-30T11:37:01Z"}, now)
    ok = v["verdict"] == "STRANDED_NEVER_TOUCHED" and v["never_touched"]
    cases.append(("old never-touched flags with fingerprint", ok, str(v)))

    v = classify_pr({"number": 3, "createdAt": "2026-10-30T11:37:01Z",
                     "updatedAt": "2026-10-30T13:02:07Z"}, now)
    ok = v["verdict"] == "STRANDED_TOUCHED" and not v["never_touched"]
    cases.append(("old touched flags without fingerprint", ok, str(v)))

    v = classify_pr({"number": 4, "createdAt": "2026-10-31T15:22:00Z",
                     "updatedAt": "2026-10-31T15:22:00Z"}, now, max_age_hours=2.0)
    cases.append(("exact SLA boundary counts as stranded", v["verdict"] == "STRANDED_NEVER_TOUCHED", str(v)))

    v = classify_pr({"number": 5, "createdAt": "garbage", "updatedAt": "garbage"}, now)
    cases.append(("unparseable timestamp is NO_TIMESTAMP (honest)", v["verdict"] == "NO_TIMESTAMP", str(v)))

    vs = [classify_pr({"number": i, "createdAt": "2026-10-30T11:37:01Z",
                       "updatedAt": "2026-10-30T11:37:01Z"}, now) for i in range(3)]
    vs.append(classify_pr({"number": 9, "createdAt": "2026-10-31T17:00:00Z",
                           "updatedAt": "2026-10-31T17:00:00Z"}, now))
    c = census(vs)
    ok = c["total"] == 4 and c["STRANDED_NEVER_TOUCHED"] == 3 and c["IN_FLIGHT"] == 1 \
        and c["stranded_total"] == 3
    cases.append(("census rollup adds stranded_total", ok, str(c)))

    return cases


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="PR-lane strand tripwire (post-#3418 landing family)")
    p.add_argument("--self-test", action="store_true",
                   help="hermetic verdict-matrix proof (roster mode)")
    p.add_argument("--check", action="store_true",
                   help="live PR-plane read via tower github.list_prs (report-only unless --strict)")
    p.add_argument("--max-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS,
                   help=f"open-PR age past which an unlanded row flags (default {DEFAULT_MAX_AGE_HOURS:g}h)")
    p.add_argument("--strict", action="store_true",
                   help="exit 1 when stranded rows exist (report-only default)")
    args = p.parse_args(argv)

    if args.self_test:
        cases = self_test()
        failed = [c for c in cases if not c[1]]
        for name, ok, ev in cases:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {ev}" if not ok else ""))
        print(f"\n==== {len(cases) - len(failed)}/{len(cases)} self-test cases PASS ====")
        return 1 if failed else 0
    if not args.check:
        p.error("one of --self-test / --check is required (roster uses explicit modes)")

    try:
        verdicts, c = run_check(max_age_hours=args.max_age_hours)
    except Exception as e:  # noqa: BLE001 — unreachable planes are a skip, never a pass
        print(f"SKIP: PR plane unreachable ({e.__class__.__name__}: {e})")
        return 2

    print(f"PR PLANE: {c['total']} open rows (SLA {args.max_age_hours:g}h)")
    for v in sorted(verdicts, key=lambda x: -(x["age_hours"] if x["age_hours"] is not None else -1)):
        if v["verdict"] in ("IN_FLIGHT",):
            continue
        age_s = "?" if v["age_hours"] is None else f"{v['age_hours']:.1f}h"
        print(f"  #{v['number']} [{v['verdict']}] age={age_s} — {v['evidence']}")
    print(f"CENSUS: {c['stranded_total']} stranded "
          f"({c['STRANDED_NEVER_TOUCHED']} never-touched, {c['STRANDED_TOUCHED']} touched) "
          f"/ {c['IN_FLIGHT']} in-flight / {c['NO_TIMESTAMP']} no-signal")
    if c["stranded_total"]:
        print("Root cause pointer: auto-landing is event-driven-only — skipped landings "
              "are silent and failed landings are never retried; a scheduled sweep in "
              ".github/workflows/pipeline.yml is the owner-lane remedy (see the audit "
              "finding this guard ships with).")
    if args.strict and c["stranded_total"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
