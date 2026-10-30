#!/usr/bin/env python3
"""Hollow-read guard — emptiness assertions at the consumption boundary.

Lineage: #2673 (the silent-empty class: six 200-but-hollow reads across five
planes defeat their guards). Implements the class filing's Unified remedy
items 1/2/3 (+5 minimal) as standing assertions so the NEXT hollow read is
caught by a guard, not by an agent's ad-hoc census — the #2673 falsification
clause names exactly this as the class-absorption condition.

Remedy mapping (#2673 numbering + #3031 addendum):
  1. assert_non_empty        — domain semantics imply data, read returns n=0
  2. assert_live_implies_fresh — timestamp advanced but content identically
                                 empty across reads (#2665 signature)
  3. assert_truncation_flagged — every paginated face must carry a first-class
                                 truncation signal (work_queue has
                                 windowTruncated; faces without one are
                                 structural blind pages)
  5. assert_ci_coverage      — a green run with zero jobs/assertions is not
                               green (green-but-blind, #2529 class)
  #3031 addendum: assert_parsable — emptiness alone misses the NON-EMPTY but
                               INVALID class: a 66-byte SSE body cut mid-string
                               passes every emptiness check yet is unparseable
                               JSON (error=False throughout). Parseability is
                               now a standing boundary assertion, and tower_call
                               raises TowerHollowReadError instead of silently
                               returning a {"raw": ...} fallback.
  6. assert_incidents_consistent — intra-payload plane agreement (#3111 class):
                               a health sweep whose snapshots/overallStatus say
                               degraded-or-worse while its own incidents array
                               stays [] is silently suppressing incidents.
                               Observed live for 8+ consecutive sentry passes
                               (#3049, #3077, #3111: incidents=[] while THREE
                               rows were degraded/down). The two planes inside
                               ONE payload must not contradict each other.

Scope honesty: this is the repo-reachable standing guard. It cannot fix the
tower-side planes themselves (owner lane); it makes their hollow answers loud
at the moment of consumption (#2704 shape: a silently under-scanned sweep is
worse than a loud failure).

Verdict contract:
    exit 0  CLEAN           — no hollow signature on the probed planes
    exit 1  HOLLOW_DETECTED — at least one assertion fired (stderr fail-loud,
                              JSON evidence on stdout)
    exit 2  USAGE/INTERNAL  — bad invocation or internal error, never silent

Usage:
    python3 scripts/ci/hollow_read_guard.py --probe live \
        [--tower-url https://supremeai-mcp-tower.onrender.com/mcp] \
        [--evidence-out /tmp/hollow_probe.json]
    (offline tests inject fakes directly; see tests/test_hollow_read_guard.py)
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone

TOWER_URL_DEFAULT = "https://supremeai-mcp-tower.onrender.com/mcp"

GUARD = "hollow_read_guard"
LINEAGE = ("#2673 silent-empty class, Unified remedy 1/2/3(+5); #2704 fail-loud "
           "shape; #3031 parseability addendum (66B SSE mid-body cut class); "
           "#3111 incidents-plane suppression class (assertion 6)")

EXIT_CLEAN = 0
EXIT_HOLLOW = 1
EXIT_USAGE = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Assertion core (pure — fetchers injected; offline-testable)
# ---------------------------------------------------------------------------

def assert_non_empty(plane: str, payload, semantic_floor: int, context: str = "") -> dict:
    """Remedy 1: n=0 while domain semantics imply >= semantic_floor rows."""
    if isinstance(payload, list):
        count = len(payload)
    elif isinstance(payload, dict):
        rows = payload.get("rows", payload.get("items", payload.get("workOrders")))
        count = len(rows) if isinstance(rows, list) else None
    else:
        count = None
    if count is None:
        return {
            "assertion": "non_empty", "plane": plane, "verdict": "UNREADABLE",
            "detail": f"payload shape not a recognizable row container {context}".strip(),
        }
    if count == 0 and semantic_floor > 0:
        return {
            "assertion": "non_empty", "plane": plane, "verdict": "HOLLOW",
            "observed": 0, "semanticFloor": semantic_floor,
            "detail": f"{plane} returned 0 rows while domain semantics imply >={semantic_floor} {context}".strip(),
        }
    return {"assertion": "non_empty", "plane": plane, "verdict": "CLEAN", "observed": count}


def assert_live_implies_fresh(snapshot_a: dict, snapshot_b: dict, content_key: str = "content") -> dict:
    """Remedy 2 (#2665 signature): timestamp advanced + payload still identically
    empty => live timestamp is decorating hollow data."""
    ta, tb = snapshot_a.get("checkedAt"), snapshot_b.get("checkedAt")
    if not ta or not tb or ta == tb:
        return {"assertion": "live_implies_fresh", "verdict": "NOT_APPLICABLE",
                "detail": "need two snapshots with distinct checkedAt"}
    advanced = str(tb) > str(ta)
    ca, cb = snapshot_a.get(content_key), snapshot_b.get(content_key)
    both_empty = (ca in (None, [], {}, "")) and (cb in (None, [], {}, ""))
    if advanced and both_empty:
        return {
            "assertion": "live_implies_fresh", "verdict": "HOLLOW",
            "detail": (f"checkedAt advanced {ta} -> {tb} while content stayed "
                       f"identically empty — live timestamp decorating hollow data"),
        }
    return {"assertion": "live_implies_fresh", "verdict": "CLEAN"}


def assert_truncation_flagged(plane: str, payload, requested_limit: int | None = None) -> dict:
    """Remedy 3: a paginated face must carry a first-class truncation signal.
    A face returning exactly its requested page size with NO truncation signal
    is a structural blind page (#2190/#2609 class)."""
    if isinstance(payload, dict) and "windowTruncated" in payload:
        total = payload.get("totalOpen")
        flag = payload["windowTruncated"]
        if total is not None and requested_limit is not None and requested_limit >= total and flag:
            return {
                "assertion": "truncation_flagged", "plane": plane, "verdict": "HOLLOW",
                "detail": (f"windowTruncated=true while limit {requested_limit} >= totalOpen "
                           f"{total} — truncation flag miscalibrated (#2190 signature)"),
            }
        return {"assertion": "truncation_flagged", "plane": plane, "verdict": "CLEAN",
                "flag": flag, "totalOpen": total}
    if isinstance(payload, list):
        n = len(payload)
        if requested_limit is not None and n == requested_limit and n > 0:
            return {
                "assertion": "truncation_flagged", "plane": plane, "verdict": "HOLLOW",
                "detail": (f"{plane} returned exactly requested page size {n} with no "
                           f"truncation signal — structural blind page (#2609 class)"),
            }
        return {"assertion": "truncation_flagged", "plane": plane, "verdict": "CLEAN", "rows": n}
    return {"assertion": "truncation_flagged", "plane": plane, "verdict": "UNREADABLE",
            "detail": "payload neither dict with windowTruncated nor list"}


def assert_ci_coverage(run: dict) -> dict:
    """Remedy 5 (minimal, #2529 class): a green run with zero executed jobs is
    not green."""
    conclusion = str(run.get("conclusion", "")).lower()
    jobs = run.get("jobs") or []
    if conclusion == "success" and isinstance(jobs, list) and len(jobs) == 0:
        return {
            "assertion": "ci_coverage", "verdict": "HOLLOW",
            "detail": ("run success with zero executed jobs — green-but-blind "
                       "(#2529 class); verdict plane coverage violated"),
        }
    return {"assertion": "ci_coverage", "verdict": "CLEAN",
            "conclusion": conclusion or None, "jobs": len(jobs) if isinstance(jobs, list) else None}


class TowerHollowReadError(RuntimeError):
    """#3031 66B class: consumed tower body was non-empty but unparseable.

    The silent-consumption hazard is precisely error=False with a truncated
    body (cut mid-string, e.g. at `{"repo": "Supremeai-bd`), so the boundary
    must raise instead of laundering the body into a {"raw": ...} dict."""

    def __init__(self, tool: str, body: str):
        self.tool = tool
        self.body_length = len(body or "")
        self.excerpt = (body or "")[:60]
        super().__init__(
            f"hollow-read ({tool}): non-empty but unparseable body "
            f"({self.body_length}B, excerpt={self.excerpt!r}) — #3031 66B class")


# Statuses that do NOT imply an incident. Everything else that is a non-empty
# string status (degraded, down, unhealthy, error, failed, update_failed,
# timeout, unreachable, ...) counts as a non-OK row. Unknown/excluded are
# neutral: an unprobed or intentionally excluded face is not, by itself,
# evidence of a suppressed incident (keeps the guard false-positive-safe).
_INCIDENT_OK_STATUSES = frozenset({
    "ok", "healthy", "operational", "up", "alive", "passing", "green",
    "nominal", "unknown", "skipped", "excluded", "disabled", "not_configured",
})


def _incident_non_ok_rows(snapshots) -> dict:
    """Extract non-OK rows from either snapshots shape (dict or list)."""
    non_ok: dict = {}
    if isinstance(snapshots, dict):
        pairs = list(snapshots.items())
    elif isinstance(snapshots, list):
        pairs = [(f"row-{i}", row) for i, row in enumerate(snapshots)]
    else:
        return non_ok
    for name, row in pairs:
        if not isinstance(row, dict):
            continue
        status = row.get("status")
        if not isinstance(status, str):
            continue
        s = status.strip().lower()
        if s and s not in _INCIDENT_OK_STATUSES:
            non_ok[str(name)] = status
    return non_ok


def assert_incidents_consistent(plane: str, sweep) -> dict:
    """Assertion 6 (#3111 class): incident/data plane agreement in ONE payload.

    A health sweep that reports overallStatus=degraded-or-worse, or >=1
    non-OK snapshot row, while its own incidents array is empty is silently
    suppressing incidents — the exact defect-shaped datum platform-guardian
    sentries reported live for 8+ consecutive passes (#3049 -> #3077 ->
    #3111: incidents=[] while THREE rows degraded/down, hollow-signature
    checklist explicitly NOT tripped because per-row statuses were fully
    populated). Emptiness assertions cannot see this class: every individual
    plane is populated; the LIE is the contradiction between two populated
    planes inside the same payload. Fail-loud at the consumption boundary.

    Verdicts: HOLLOW (contradiction), UNREADABLE (shape unknown — never a
    silent pass), CLEAN (planes agree or no non-OK datum exists)."""
    if not isinstance(sweep, dict):
        return {
            "assertion": "incidents_consistent", "plane": plane, "verdict": "UNREADABLE",
            "detail": "sweep payload is not a dict — shape unknown",
        }
    incidents = sweep.get("incidents")
    if not isinstance(incidents, list):
        return {
            "assertion": "incidents_consistent", "plane": plane, "verdict": "UNREADABLE",
            "detail": "incidents field missing or not a list — shape unknown",
        }
    snapshots = sweep.get("snapshots")
    if not isinstance(snapshots, (dict, list)):
        return {
            "assertion": "incidents_consistent", "plane": plane, "verdict": "UNREADABLE",
            "detail": "snapshots neither dict nor list — shape unknown",
        }
    non_ok = _incident_non_ok_rows(snapshots)
    overall = str(sweep.get("overallStatus", "") or "").strip().lower()
    overall_bad = bool(overall) and overall not in _INCIDENT_OK_STATUSES
    if (non_ok or overall_bad) and not incidents:
        rows_note = ", ".join(f"{k}={v}" for k, v in sorted(non_ok.items())[:5]) or "(rows ok)"
        overall_note = f"overallStatus={overall}" if overall_bad else "overallStatus ok"
        return {
            "assertion": "incidents_consistent", "plane": plane, "verdict": "HOLLOW",
            "nonOkRows": non_ok, "overallStatus": sweep.get("overallStatus"),
            "incidentsCount": 0,
            "detail": (f"{plane}=[] while the same payload reports degraded-or-worse "
                       f"({overall_note}; non-OK rows: {rows_note}) — incident plane "
                       f"contradicts data plane, #3111 suppression class"),
        }
    return {
        "assertion": "incidents_consistent", "plane": plane, "verdict": "CLEAN",
        "incidentsCount": len(incidents), "nonOkRowCount": len(non_ok),
        "overallStatus": sweep.get("overallStatus"),
    }


def assert_parsable(plane: str, raw_body: str, context: str = "") -> dict:
    """#3031 addendum: parseability alongside emptiness at the boundary.

    An empty body and a non-empty-but-unparseable body are BOTH hollow —
    the latter is worse because it passes every emptiness check while
    carrying error=False."""
    body = raw_body or ""
    if not body.strip():
        return {
            "assertion": "parsable", "plane": plane, "verdict": "HOLLOW",
            "bodyLength": len(body),
            "detail": (f"{plane} returned an empty body at the consumption "
                       f"boundary {context}").strip(),
        }
    try:
        json.loads(body)
    except (json.JSONDecodeError, ValueError) as exc:
        return {
            "assertion": "parsable", "plane": plane, "verdict": "HOLLOW",
            "bodyLength": len(body), "excerpt": body[:60],
            "detail": (f"{plane} body non-empty ({len(body)}B) but unparseable "
                       f"JSON ({exc.__class__.__name__}) — silent-consumption "
                       f"hazard, #3031 66B class {context}").strip(),
        }
    return {"assertion": "parsable", "plane": plane, "verdict": "CLEAN",
            "bodyLength": len(body)}


# ---------------------------------------------------------------------------
# Live probe plane (zero-credential tower reads)
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
                   "clientInfo": {"name": "hollow-read-guard", "version": "1.0"}},
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
            # #3031: a non-empty but unparseable body must be LOUD, never
            # laundered through a {"raw": ...} fallback dict.
            try:
                return json.loads(out)
            except (json.JSONDecodeError, ValueError):
                raise TowerHollowReadError(tool, out)
    raise RuntimeError("tower returned no SSE data payload")


def run_live_probe(fetch, owner: str = "Supremeai-bd", repo: str = "supremeai-open") -> dict:
    """Probe the roster planes with remedy assertions; evidence JSON out."""
    findings: list[dict] = []

    # Roster plane: github.list_prs — page-size face with no truncation signal.
    try:
        prs = fetch("github.list_prs", {"owner": owner, "repo": repo, "state": "open", "per_page": 30})
        rows = prs if isinstance(prs, list) else []
        # Domain-semantics cross-check FIRST: workflow_runs side-channel implies
        # PR lanes exist, so an empty page gets a positive semantic floor.
        floor = 0
        sidechannel = ""
        try:
            runs = fetch("github.workflow_runs", {"owner": owner, "repo": repo, "per_page": 30})
            branches = {(r or {}).get("head_branch", "") for r in runs.get("workflow_runs", []) if isinstance(r, dict)}
            bridge_branches = sorted(b for b in branches if b.startswith("bridge/"))
            if bridge_branches:
                floor = 1
                sidechannel = (f"workflow_runs side-channel shows {len(bridge_branches)} "
                               f"bridge PR branches in-window (e.g. {bridge_branches[0][:40]})")
        except Exception:
            sidechannel = "side-channel unavailable; floor stays 0"
        findings.append(assert_non_empty("github.list_prs", rows, semantic_floor=floor,
                                         context=sidechannel))
        findings.append(assert_truncation_flagged("github.list_prs", rows, requested_limit=30))
    except TowerHollowReadError as exc:
        findings.append({"assertion": "parsable", "plane": "github.list_prs",
                         "verdict": "HOLLOW", "detail": str(exc)[:200]})
    except Exception as exc:
        findings.append({"assertion": "probe", "plane": "github.list_prs", "verdict": "UNREADABLE",
                         "detail": str(exc)[:200]})

    # Roster plane: work_queue — truncation flag presence AND calibration.
    try:
        q = fetch("bridge.work_queue", {"limit": 120})
        findings.append(assert_truncation_flagged("bridge.work_queue", q, requested_limit=120))
        if isinstance(q, dict):
            total = q.get("totalOpen")
            returned = len(q.get("workOrders", []))
            if isinstance(total, int) and total > returned and not q.get("windowTruncated"):
                findings.append({
                    "assertion": "cross_face_count", "plane": "bridge.work_queue", "verdict": "HOLLOW",
                    "detail": (f"totalOpen {total} > returned {returned} "
                               f"yet windowTruncated=false — flag/data divergence (#2190)"),
                })
    except TowerHollowReadError as exc:
        findings.append({"assertion": "parsable", "plane": "bridge.work_queue",
                         "verdict": "HOLLOW", "detail": str(exc)[:200]})
    except Exception as exc:
        findings.append({"assertion": "probe", "plane": "bridge.work_queue", "verdict": "UNREADABLE",
                         "detail": str(exc)[:200]})

    # Roster plane: health-style sweep — live stamp must not decorate an empty
    # check table (#2665), and the incident plane must agree with the data
    # plane inside the same payload (#3111).
    try:
        sweep = fetch("health_full_sweep", {})
        snaps = sweep.get("snapshots") if isinstance(sweep, dict) else None
        findings.append(assert_non_empty(
            "health_full_sweep.snapshots",
            {"rows": sorted(snaps.keys()) if isinstance(snaps, dict) else None},
            semantic_floor=1,
        ))
        findings.append(assert_incidents_consistent("health_full_sweep.incidents", sweep))
    except TowerHollowReadError as exc:
        findings.append({"assertion": "parsable", "plane": "health_full_sweep",
                         "verdict": "HOLLOW", "detail": str(exc)[:200]})
    except Exception as exc:
        findings.append({"assertion": "probe", "plane": "health_full_sweep", "verdict": "UNREADABLE",
                         "detail": str(exc)[:200]})

    hollow = [f for f in findings if f.get("verdict") == "HOLLOW"]
    return {
        "guard": GUARD,
        "lineage": LINEAGE,
        "checkedAt": _now(),
        "verdict": "HOLLOW_DETECTED" if hollow else "CLEAN",
        "findings": findings,
        "hollowCount": len(hollow),
    }


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="Hollow-read guard (#2673 standing assertions)")
    ap.add_argument("--probe", default="live", choices=["live"])
    ap.add_argument("--tower-url", default=TOWER_URL_DEFAULT)
    ap.add_argument("--evidence-out", default=None)
    args = ap.parse_args(argv)

    def fetch(tool, arguments):
        return tower_call(tool, arguments, args.tower_url)

    evidence = run_live_probe(fetch)
    payload = json.dumps(evidence, indent=2, ensure_ascii=False)
    if args.evidence_out:
        with open(args.evidence_out, "w") as fh:
            fh.write(payload + "\n")
    if evidence["verdict"] == "HOLLOW_DETECTED":
        print(f"HOLLOW READ GUARD: {evidence['hollowCount']} hollow signature(s) detected "
              f"(fail-loud, #2704 shape) — planes lie in success shape; evidence JSON attached",
              file=sys.stderr)
    print(payload)
    return EXIT_HOLLOW if evidence["verdict"] == "HOLLOW_DETECTED" else EXIT_CLEAN


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"HOLLOW READ GUARD: INTERNAL ERROR — {exc}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
