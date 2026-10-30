#!/usr/bin/env python3
"""Health incident-plane coherence guard — the #3111 family standing tripwire.

Lineage: the platform-guardian sentry series (#1852 → … → #3111, ~2h cadence)
recorded **eight consecutive passes** of the same defect shape: the tower
health sweep reported non-OK rows (telegram-primary DOWN, render-pair
"update_failed") while the incidents plane answered `incidents: []`. A sweep
whose row plane screams but whose incident plane stays silent is a plane that
lies in success shape — degraded reality surfaces nowhere a consumer trusts,
so no alert, no escalation, no admin lane. #3111 logged the 8th pass on
2026-10-30T08:45Z; this guard is the Zero-Recurrence Invariant (U6) answer:
the NEXT occurrence must be caught mechanically at the consumption boundary,
not by an agent's ad-hoc eyeball.

Complement, not duplicate: `hollow_read_guard.py` (#2673) asserts the sweep's
snapshot table is *populated* (non-empty rows). This guard asserts the three
health planes *cohere* with each other:

  1. incidents_populated_when_rows_non_ok — >=1 non-OK snapshot row with an
     empty incidents array is the #3111 8-pass defect shape (HOLLOW).
  2. overall_status_cohere — overallStatus must agree with the row plane in
     both directions (non-OK rows ⇒ not "healthy"; all-healthy rows ⇒ not
     "degraded"/"down"). A summary contradicting its own rows is the same lie
     one level up (HOLLOW).
  3. per_row_status_coverage — every snapshot row carries a populated status
     (the hollow-signature checklist #3111 ran by hand each pass; #2704
     loud-failure shape) (HOLLOW).
  4. note_incident_without_non_ok_row — incidents present while every row
     reads healthy is recorded as an advisory NOTE (transition-lag window),
     never a failure: incident creation may legitimately precede the next
     row poll.

Scope honesty: this is the repo-reachable standing guard. It cannot fix the
tower-side planes themselves (owner lane); it makes their incoherence loud at
the moment of consumption — exactly the #2704 shape ("a silently under-scanned
sweep is worse than a loud failure").

Verdict contract (mirrors hollow_read_guard):
    exit 0  CLEAN            — planes cohere on the probed sweep
    exit 1  DEFECT_DETECTED  — at least one coherence assertion fired
                                (stderr fail-loud, JSON evidence on stdout)
    exit 2  USAGE/INTERNAL   — bad invocation or internal error, never silent

Usage:
    python3 scripts/ci/health_incident_plane_guard.py --probe live \
        [--tower-url https://supremeai-mcp-tower.onrender.com/mcp] \
        [--evidence-out /tmp/incident_plane_probe.json]
    python3 scripts/ci/health_incident_plane_guard.py --sweep-file sweep.json
    (offline tests inject fakes directly; see tests/test_health_incident_plane_guard.py)
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone

TOWER_URL_DEFAULT = "https://supremeai-mcp-tower.onrender.com/mcp"

GUARD = "health_incident_plane_guard"
LINEAGE = ("#3111 sentry family: 8 consecutive passes of incidents=[] while "
           "sweep rows non-OK (telegram DOWN, render-pair update_failed); "
           "U6 Zero-Recurrence; #2704 fail-loud shape; complements "
           "hollow_read_guard.py (#2673) population assertions")

EXIT_CLEAN = 0
EXIT_DEFECT = 1
EXIT_USAGE = 2

# Row-level statuses that mean "this provider/service is fine". Anything else
# (down, degraded, unreachable, update_failed, unknown-None…) is non-OK.
HEALTHY_ROW_STATUSES = {"healthy", "ok", "up"}
# Sweep-level healthy statuses; degraded/down/unhealthy are honest when rows
# are non-OK — the lie is only when they contradict the row plane.
HEALTHY_SWEEP_STATUSES = {"healthy", "ok"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows_non_ok(snapshots: dict) -> list[str]:
    """Names of snapshot rows whose status is missing or non-healthy.

    A MISSING status counts as non-OK on purpose: a row that hides its status
    is exactly the hollow signature #3111 checked by hand each pass, and
    assertion 3 fires on it separately.
    """
    non_ok = []
    for name, snap in snapshots.items():
        status = (snap or {}).get("status") if isinstance(snap, dict) else None
        if not isinstance(status, str) or status.strip().lower() not in HEALTHY_ROW_STATUSES:
            non_ok.append(str(name))
    return non_ok


def _incidents(payload: dict) -> list | None:
    inc = payload.get("incidents")
    return inc if isinstance(inc, list) else None


def assert_incidents_populated_when_rows_non_ok(payload: dict) -> dict:
    """Headline #3111 shape: non-OK rows present, incidents plane empty."""
    snapshots = payload.get("snapshots")
    if not isinstance(snapshots, dict):
        return {
            "assertion": "incidents_populated_when_rows_non_ok",
            "verdict": "UNREADABLE",
            "detail": "sweep payload has no dict snapshots table",
        }
    incidents = _incidents(payload)
    if incidents is None:
        return {
            "assertion": "incidents_populated_when_rows_non_ok",
            "verdict": "UNREADABLE",
            "detail": "sweep payload carries no incidents array",
        }
    non_ok = _rows_non_ok(snapshots)
    if non_ok and len(incidents) == 0:
        return {
            "assertion": "incidents_populated_when_rows_non_ok",
            "verdict": "HOLLOW",
            "nonOkRows": non_ok,
            "incidentCount": 0,
            "detail": (f"{len(non_ok)} non-OK snapshot row(s) {non_ok[:5]} while the "
                       f"incidents plane is EMPTY — degraded reality surfaces "
                       f"nowhere (the #3111 8-pass defect shape); alert/escalation "
                       f"lanes silently dark"),
        }
    return {
        "assertion": "incidents_populated_when_rows_non_ok",
        "verdict": "CLEAN",
        "nonOkRows": non_ok,
        "incidentCount": len(incidents),
    }


def assert_overall_status_cohere(payload: dict) -> dict:
    """overallStatus must agree with the row plane in BOTH directions."""
    snapshots = payload.get("snapshots")
    overall = payload.get("overallStatus")
    if not isinstance(snapshots, dict) or not isinstance(overall, str):
        return {
            "assertion": "overall_status_cohere",
            "verdict": "UNREADABLE",
            "detail": "need dict snapshots and a string overallStatus",
        }
    non_ok = _rows_non_ok(snapshots)
    overall_l = overall.strip().lower()
    if non_ok and overall_l in HEALTHY_SWEEP_STATUSES:
        return {
            "assertion": "overall_status_cohere", "verdict": "HOLLOW",
            "overallStatus": overall, "nonOkRows": non_ok,
            "detail": (f"overallStatus={overall!r} while {len(non_ok)} row(s) are "
                       f"non-OK {non_ok[:5]} — summary plane contradicting its own "
                       f"row plane (the #3111 lie one level up)"),
        }
    if not non_ok and overall_l not in HEALTHY_SWEEP_STATUSES:
        return {
            "assertion": "overall_status_cohere", "verdict": "HOLLOW",
            "overallStatus": overall, "nonOkRows": [],
            "detail": (f"overallStatus={overall!r} while every snapshot row reads "
                       f"healthy — sweep self-flagels without a single non-OK row "
                       f"(mirror-direction lie)"),
        }
    return {
        "assertion": "overall_status_cohere", "verdict": "CLEAN",
        "overallStatus": overall, "nonOkRows": non_ok,
    }


def assert_per_row_status_coverage(payload: dict) -> dict:
    """Every snapshot row carries a populated status (hollow-signature checklist)."""
    snapshots = payload.get("snapshots")
    if not isinstance(snapshots, dict):
        return {
            "assertion": "per_row_status_coverage",
            "verdict": "UNREADABLE",
            "detail": "sweep payload has no dict snapshots table",
        }
    unpopulated = [
        str(name) for name, snap in snapshots.items()
        if not (isinstance(snap, dict) and isinstance(snap.get("status"), str)
                and snap.get("status").strip())
    ]
    if unpopulated:
        return {
            "assertion": "per_row_status_coverage", "verdict": "HOLLOW",
            "unpopulatedRows": unpopulated,
            "detail": (f"{len(unpopulated)} snapshot row(s) carry no populated status "
                       f"{unpopulated[:5]} — hollow sweep signature (#2704 loud shape; "
                       f"the checklist #3111 ran by hand each pass)"),
        }
    return {
        "assertion": "per_row_status_coverage", "verdict": "CLEAN",
        "rows": len(snapshots),
    }


def note_incident_without_non_ok_row(payload: dict) -> dict:
    """Advisory: incidents present while all rows read healthy.

    Never fails the run — incident creation can legitimately precede the next
    row poll (transition windows). Recorded so the observation survives into
    the evidence JSON instead of being silently dropped.
    """
    snapshots = payload.get("snapshots")
    incidents = _incidents(payload) or []
    if isinstance(snapshots, dict) and incidents and not _rows_non_ok(snapshots):
        return {
            "assertion": "note_incident_without_non_ok_row", "verdict": "NOTE",
            "incidentCount": len(incidents),
            "detail": ("incidents plane populated while every row reads healthy — "
                       "likely transition-lag window; advisory only, never a failure"),
        }
    return {"assertion": "note_incident_without_non_ok_row", "verdict": "CLEAN"}


def run_assertions(payload: dict) -> list[dict]:
    """Pure assertion pipeline over one sweep payload (offline-testable)."""
    return [
        assert_incidents_populated_when_rows_non_ok(payload),
        assert_overall_status_cohere(payload),
        assert_per_row_status_coverage(payload),
        note_incident_without_non_ok_row(payload),
    ]


# ---------------------------------------------------------------------------
# Live probe plane (zero-credential tower read) + offline file mode
# ---------------------------------------------------------------------------

def _tower_rpc(tower_url: str, session, payload: dict, timeout: float = 30.0):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session:
        headers["mcp-session-id"] = session
    req = urllib.request.Request(tower_url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.headers.get("mcp-session-id"), resp.read().decode()


def tower_call(tool: str, arguments: dict, tower_url: str, timeout: float = 30.0) -> dict:
    sid, _ = _tower_rpc(tower_url, None, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "incident-plane-guard", "version": "1.0"}},
    }, timeout=timeout)
    _tower_rpc(tower_url, sid, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    _, body = _tower_rpc(tower_url, sid, {
        "jsonrpc": "2.0", "id": 99, "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }, timeout=timeout)
    for line in body.split("\n"):
        if line.startswith("data: "):
            data = json.loads(line[6:])
            if "error" in data:
                raise RuntimeError(f"tower tool error: {data['error']}")
            texts = [c.get("text", "") for c in data.get("result", {}).get("content", [])
                     if c.get("type") == "text"]
            out = "\n".join(texts)
            return json.loads(out)
    raise RuntimeError("tower returned no SSE data payload")


def run_live_probe(fetch, tool: str = "health_full_sweep") -> dict:
    """Probe the health sweep through the injected fetcher; evidence JSON out."""
    findings: list[dict] = []
    try:
        sweep = fetch(tool, {})
        findings.extend(run_assertions(sweep))
    except json.JSONDecodeError as exc:
        findings.append({"assertion": "parsable", "plane": tool, "verdict": "UNREADABLE",
                         "detail": f"{tool} body unparseable JSON: {exc}"[:200]})
    except Exception as exc:
        findings.append({"assertion": "probe", "plane": tool, "verdict": "UNREADABLE",
                         "detail": str(exc)[:200]})
    defects = [f for f in findings if f.get("verdict") == "HOLLOW"]
    return {
        "guard": GUARD,
        "lineage": LINEAGE,
        "checkedAt": _now(),
        "verdict": "DEFECT_DETECTED" if defects else "CLEAN",
        "findings": findings,
        "defectCount": len(defects),
    }


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Health incident-plane coherence guard (#3111 family standing tripwire)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--probe", default=None, choices=["live"],
                      help="live zero-credential probe of the tower sweep")
    mode.add_argument("--sweep-file", default=None, dest="sweep_file",
                      help="run the assertions offline against a saved sweep JSON")
    ap.add_argument("--tower-url", default=TOWER_URL_DEFAULT)
    ap.add_argument("--tool", default="health_full_sweep",
                    help="tower tool to probe (default health_full_sweep)")
    ap.add_argument("--evidence-out", default=None)
    args = ap.parse_args(argv)

    if args.probe == "live":
        def fetch(tool_name, arguments):
            return tower_call(tool_name, arguments, args.tower_url)
        evidence = run_live_probe(fetch, tool=args.tool)
    elif args.sweep_file:
        with open(args.sweep_file) as fh:
            sweep = json.load(fh)
        evidence = run_live_probe(lambda _tool, _args: sweep)
    else:
        print("USAGE: pass --probe live or --sweep-file <path.json>", file=sys.stderr)
        return EXIT_USAGE

    payload = json.dumps(evidence, indent=2, ensure_ascii=False)
    if args.evidence_out:
        with open(args.evidence_out, "w") as fh:
            fh.write(payload + "\n")
    if evidence["verdict"] == "DEFECT_DETECTED":
        print(f"INCIDENT PLANE GUARD: {evidence['defectCount']} coherence defect(s) detected "
              f"(fail-loud, #2704 shape) — health planes disagree in success shape; "
              f"evidence JSON attached",
              file=sys.stderr)
    print(payload)
    return EXIT_DEFECT if evidence["verdict"] == "DEFECT_DETECTED" else EXIT_CLEAN


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"INCIDENT PLANE GUARD: INTERNAL ERROR — {exc}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
