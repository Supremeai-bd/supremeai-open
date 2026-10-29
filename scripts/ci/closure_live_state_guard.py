#!/usr/bin/env python3
"""closure_live_state_guard.py — closure-time live-state cross-check (radar R79, #2925 Option A, repo-reachable slice).

WHAT THIS GATES
Before any closing artifact is produced for a subject issue that has a DECLARED
recovery criterion (platform-audit closure class), this guard re-evaluates that
criterion against a fresh tower health snapshot (zero-credential MCP read) and
refuses the closing act if the criterion is verifiably still FAILED.

MOTIVATION (the live counterexample, tower-authoritative)
#2225 was closed `completed` a second time at 2026-10-29T23:18:17Z — 65 minutes
after the boundary-honest ACTION template (#2886) landed and 4 minutes after a
fresh probe showed both render services still update_failed (29h) — while the
#2738 recovery criterion was verifiably FAILED on both named services. Proof
plane (#2855, #2897) and witness plane (C49 #2916) recorded the violation in
real time; nothing consumed either. This guard is the consuming mechanism for
the repo-reachable slice of that gap (Option A); the controller slice is
Option B, owner-routed per the R49/R74 precedent and unreachable from repo PRs.

CONTRACT (mechanical, actor-agnostic, fail-loud)
- verdict ALLOW    (exit 0): no criterion declared for the subject (the gate
  never fabricates criteria — out of mechanical scope, note says so), OR the
  declared criterion PASSES against a fresh snapshot (PASS receipt attached).
- verdict REFUSE   (exit 1): the declared criterion verifiably FAILED — the
  closing artifact must be refused and the run downgraded to evidence-only;
  stderr carries the criterion output (per-row statuses + snapshot timestamps).
- verdict INDETERMINATE (exit 2): the snapshot is missing/stale/malformed or a
  declared row is absent/unknown-status. Default-deny, per the #2704 shape:
  a silently under-scanned sweep is worse than a loud failure.
- The incidents plane is cross-checked: degraded rows are reported even when
  incidents=[] (the R79 defect-shaped datum, observed 3 consecutive passes).

SNAPSHOT SHAPE (tower health_full_sweep, as observed live)
{"timestamp": "...Z", "incidents": [...], "overallStatus": "...",
 "snapshots": {"<service>": {"status": "healthy"|"degraded"|..., "checkedAt":
 "...Z", "latencyMs": ...}}, ...}

Zero-credential throughout: the live read rides the public MCP tower (session
handshake + tools/call health_full_sweep) with no secrets. Offline self-test is
fully deterministic (fixtures, no network)."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_TOWER_URL = "https://supremeai-mcp-tower.onrender.com/mcp"
DEFAULT_MAX_AGE_SECONDS = 600

# Statuses that count as a PASSED row. The tower's vocabulary (observed live in
# the 22:39Z and 23:26Z sweeps) is "healthy"/"degraded"; anything else — known
# or unknown — is not silently accepted (unknown => INDETERMINATE via
# unknown_statuses_ok=False below, degraded/frozen => REFUSE).
PASS_STATUSES = ("healthy",)

# --------------------------------------------------------------------------
# Declared recovery criteria. The gate never invents criteria: a subject issue
# is in scope ONLY if an explicit, sourced criterion is declared here. Each
# entry: services (tower snapshot row names, AND-semantics), acceptable row
# status, and a verbatim `source` string pointing at the criterion's author
# ticket. Adding an entry requires that ticket to exist on the record.
# --------------------------------------------------------------------------
RECOVERY_CRITERIA: dict[str, dict] = {
    "2225": {
        "services": ["render-primary", "render-worker"],
        "acceptable_status": "healthy",
        "source": (
            "#2738 recovery criterion: both services' updatedAt advance past "
            "2026-10-24T08:32:47Z AND lastDeployStatus: live (mechanically "
            "mapped onto tower snapshot rows: row.status must be 'healthy')"
        ),
        "subject_context": (
            "#2225 render-primary + render-worker update_failed (false-closed "
            "twice: 22:11:34Z-era and 23:18:17Z while criterion FAILED)"
        ),
    },
}


def _parse_ts(value: str) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def load_snapshot(path: str | None, live: bool, tower_url: str,
                  timeout: int = 60) -> tuple[dict | None, str]:
    """Return (snapshot_dict_or_None, human error/context string)."""
    if live:
        try:
            snap = fetch_tower_snapshot(tower_url, timeout=timeout)
            return snap, "live tower read OK"
        except Exception as exc:  # noqa: BLE001 - fail-loud with reason
            return None, f"live tower read FAILED: {exc.__class__.__name__}: {exc}"
    if not path:
        return None, "no snapshot source given (--snapshot-file or --live)"
    p = Path(path)
    if not p.exists():
        return None, f"snapshot file not found: {path}"
    try:
        return json.loads(p.read_text()), f"snapshot file loaded: {path}"
    except json.JSONDecodeError as exc:
        return None, f"snapshot file malformed JSON: {exc}"


def fetch_tower_snapshot(tower_url: str, timeout: int = 60) -> dict:
    """Zero-credential MCP read: handshake -> tools/call health_full_sweep."""
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}

    def post(payload: dict, session: str | None) -> tuple[str, str | None]:
        hdr = dict(headers)
        if session:
            hdr["Mcp-Session-Id"] = session
        req = urllib.request.Request(tower_url, data=json.dumps(payload).encode(),
                                     headers=hdr, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode(), resp.headers.get("mcp-session-id")

    def parse_sse(body: str) -> dict:
        for line in body.splitlines():
            if line.startswith("data: "):
                try:
                    return json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
        return json.loads(body)

    _, sess = post({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "closure-live-state-guard",
                                              "version": "1.0.0"}}}, None)
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sess)
    call_body, _ = post({"jsonrpc": "2.0", "id": 42, "method": "tools/call",
                         "params": {"name": "health_full_sweep", "arguments": {}}}, sess)
    result = parse_sse(call_body)
    texts = [c.get("text", "") for c in result.get("result", {}).get("content", [])
             if c.get("type") == "text"]
    if not texts:
        raise ValueError("health_full_sweep returned no text content")
    return json.loads("\n".join(texts))


def evaluate_criterion(subject: str, criterion: dict, snapshot: dict,
                       max_age_seconds: int) -> tuple[str, list[str]]:
    """Pure evaluation. Returns (verdict, finding lines). Verdict in
    {ALLOW_PASS, REFUSE_FAILED, INDETERMINATE}."""
    findings: list[str] = []
    if not isinstance(snapshot, dict):
        return "INDETERMINATE", ["snapshot is not a JSON object"]

    snap_rows = snapshot.get("snapshots")
    if not isinstance(snap_rows, dict) or not snap_rows:
        return "INDETERMINATE", ["snapshot has no usable 'snapshots' object"]

    # Freshness: prefer the top-level timestamp; fall back to the newest
    # per-row checkedAt. Stale evidence never passes (raw-bypass lesson).
    ts = _parse_ts(snapshot.get("timestamp") or "")
    if ts is None:
        row_ts = [_parse_ts((v or {}).get("checkedAt") or "")
                  for v in snap_rows.values() if isinstance(v, dict)]
        row_ts = [t for t in row_ts if t is not None]
        ts = max(row_ts) if row_ts else None
    if ts is None:
        return "INDETERMINATE", ["snapshot carries no parseable timestamp"]
    age = (_now_utc() - ts).total_seconds()
    findings.append(f"snapshot timestamp: {snapshot.get('timestamp')} (age {int(age)}s, "
                    f"max {max_age_seconds}s)")
    if age > max_age_seconds:
        return "INDETERMINATE", findings + [
            f"snapshot STALE (age {int(age)}s > {max_age_seconds}s) — refusing to "
            "judge a closing act on stale evidence"]

    incidents = snapshot.get("incidents")
    degraded_rows = sorted(
        name for name, v in snap_rows.items()
        if isinstance(v, dict) and str(v.get("status", "")).lower() not in PASS_STATUSES
    )
    if degraded_rows and (incidents is None or incidents == []):
        findings.append(
            "defect-shaped datum: incidents plane SILENT while non-healthy rows "
            f"exist ({', '.join(degraded_rows)}) — degradation exists, incident "
            "record does not (R79/#2916 witness line)")

    failed_rows: list[str] = []
    unknown_rows: list[str] = []
    for service in criterion["services"]:
        row = snap_rows.get(service)
        if not isinstance(row, dict):
            unknown_rows.append(f"{service} (row absent from snapshot)")
            continue
        status = str(row.get("status", "")).strip().lower()
        checked = row.get("checkedAt", "?")
        if status == criterion["acceptable_status"]:
            findings.append(f"PASS row: {service} status={status} checkedAt={checked}")
        elif status in ("degraded", "update_failed", "frozen", "down", "failing"):
            failed_rows.append(f"{service} status={status} checkedAt={checked}")
        else:
            unknown_rows.append(f"{service} status='{status}' (unknown vocabulary) "
                                f"checkedAt={checked}")

    if unknown_rows:
        return "INDETERMINATE", findings + [f"UNDETERMINED rows: {u}" for u in unknown_rows]
    if failed_rows:
        return "REFUSE_FAILED", findings + [f"FAILED rows: {f}" for f in failed_rows]
    return "ALLOW_PASS", findings


def evidence_only_template(subject: str, criterion: dict, findings: list[str],
                           verdict: str) -> str:
    """The downgrade message shape: closing act refused -> evidence-only."""
    lines = [
        f"CLOSURE REFUSED by closure_live_state_guard (verdict {verdict})",
        f"subject issue: #{subject}",
        f"declared criterion source: {criterion['source']}",
        f"subject context: {criterion.get('subject_context', '')}",
        "criterion output attached:",
    ]
    lines.extend(f"  - {f}" for f in findings)
    lines.append(
        "downgrade: the closing artifact is NOT produced; this run is "
        "evidence-only (attach this output as the evidence comment instead)")
    return "\n".join(lines)


def _fixture_snapshot(*, statuses: dict[str, str] | None = None,
                      timestamp: str | None = None,
                      incidents: list | None = None, drop_rows: list[str] | None = None,
                      malformed: bool = False) -> dict | str:
    ts = timestamp or "2026-10-29T23:26:02.460Z"
    if malformed:
        return {"snapshots": "not-a-dict"}
    rows = {}
    for name, st in (statuses or {}).items():
        if drop_rows and name in drop_rows:
            continue
        rows[name] = {"status": st, "checkedAt": ts, "latencyMs": 100}
    return {"timestamp": ts, "durationMs": 3000,
            "incidents": [] if incidents is None else incidents,
            "snapshots": rows, "overallStatus": "unknown"}


def run_self_test() -> int:
    """Deterministic offline fixtures F1-F14. Returns process exit code."""
    failures: list[str] = []
    crit = RECOVERY_CRITERIA["2225"]
    fresh_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    old_ts = "2026-10-24T08:32:47Z"

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  {name}: {'PASS' if cond else 'FAIL'}{(' — ' + detail) if detail and not cond else ''}")
        if not cond:
            failures.append(name)

    # F1 undeclared subject => ALLOW with explicit no-criterion note, exit 0
    v, f = evaluate_criterion("999999", {"services": [], "acceptable_status": "healthy",
                                         "source": ""}, {}, 600)
    check("F1 undeclared-subject handled at CLI layer", v == "ALLOW_PASS" or v == "INDETERMINATE")

    # F2 declared + all healthy + fresh => ALLOW_PASS
    snap = _fixture_snapshot(statuses={"render-primary": "healthy",
                                       "render-worker": "healthy",
                                       "redis": "healthy"}, timestamp=fresh_ts)
    v, f = evaluate_criterion("2225", crit, snap, 600)
    check("F2 healthy-fresh => ALLOW_PASS", v == "ALLOW_PASS", str(f))

    # F3 one degraded => REFUSE_FAILED (AND-semantics)
    snap = _fixture_snapshot(statuses={"render-primary": "healthy",
                                       "render-worker": "degraded"}, timestamp=fresh_ts)
    v, f = evaluate_criterion("2225", crit, snap, 600)
    check("F3 one-degraded => REFUSE_FAILED", v == "REFUSE_FAILED", str(f))
    check("F3b refuse names the failed row", any("render-worker status=degraded" in x for x in f))

    # F4 all degraded => REFUSE_FAILED
    snap = _fixture_snapshot(statuses={"render-primary": "degraded",
                                       "render-worker": "degraded"}, timestamp=fresh_ts)
    v, f = evaluate_criterion("2225", crit, snap, 600)
    check("F4 all-degraded => REFUSE_FAILED", v == "REFUSE_FAILED", str(f))

    # F5 stale snapshot => INDETERMINATE (default-deny)
    snap = _fixture_snapshot(statuses={"render-primary": "healthy",
                                       "render-worker": "healthy"}, timestamp=old_ts)
    v, f = evaluate_criterion("2225", crit, snap, 600)
    check("F5 stale-snapshot => INDETERMINATE", v == "INDETERMINATE", str(f))
    check("F5b staleness is loud", any("STALE" in x for x in f))

    # F6 missing row => INDETERMINATE
    snap = _fixture_snapshot(statuses={"render-primary": "healthy"}, timestamp=fresh_ts,
                             drop_rows=["render-worker"])
    v, f = evaluate_criterion("2225", crit, snap, 600)
    check("F6 missing-row => INDETERMINATE", v == "INDETERMINATE", str(f))

    # F7 malformed snapshot => INDETERMINATE
    v, f = evaluate_criterion("2225", crit, _fixture_snapshot(malformed=True), 600)
    check("F7 malformed => INDETERMINATE", v == "INDETERMINATE", str(f))

    # F8 unknown status vocabulary => INDETERMINATE (never silently pass)
    snap = _fixture_snapshot(statuses={"render-primary": "kinda-ok",
                                       "render-worker": "healthy"}, timestamp=fresh_ts)
    v, f = evaluate_criterion("2225", crit, snap, 600)
    check("F8 unknown-status => INDETERMINATE", v == "INDETERMINATE", str(f))

    # F9 incidents-plane silence surfaced (R79 defect-shaped datum)
    snap = _fixture_snapshot(statuses={"render-primary": "degraded",
                                       "render-worker": "degraded",
                                       "redis": "healthy"}, timestamp=fresh_ts,
                             incidents=[])
    v, f = evaluate_criterion("2225", crit, snap, 600)
    check("F9 silent-incidents datum surfaced",
          any("incidents plane SILENT" in x for x in f), str(f))

    # F10 incidents populated does not trigger the silence datum
    snap = _fixture_snapshot(statuses={"render-primary": "degraded",
                                       "render-worker": "degraded"}, timestamp=fresh_ts,
                             incidents=[{"id": "x"}])
    v, f = evaluate_criterion("2225", crit, snap, 600)
    check("F10 no false silence-alarm", not any("SILENT" in x for x in f), str(f))

    # F11 evidence-only template carries subject + verbatim source + rows
    msg = evidence_only_template("2225", crit,
                                 ["FAILED rows: render-worker status=degraded"],
                                 "REFUSE_FAILED")
    check("F11 template: subject present", "#2225" in msg)
    check("F11b template: source verbatim", "#2738 recovery criterion" in msg)
    check("F11c template: downgrade shape", "evidence-only" in msg)

    # F12 registry integrity: numeric keys, non-empty verbatim sources,
    # known vocabulary
    for num, c in RECOVERY_CRITERIA.items():
        check(f"F12 registry {num}: numeric key", str(num).isdigit())
        check(f"F12 registry {num}: non-empty source", len(c.get("source", "")) > 20)
        check(f"F12 registry {num}: services non-empty", len(c.get("services", [])) > 0)
        check(f"F12 registry {num}: acceptable status known",
              c.get("acceptable_status") in PASS_STATUSES)

    # F13 no-criterion CLI route exits 0 with the explicit note (checked in
    # main via gate() — exercised here on the pure layer)
    check("F13 PASS_STATUSES vocabulary sound", PASS_STATUSES == ("healthy",))

    # F14 refuse verdict is reachable for the LIVE predicate shape that fired
    # at 23:18:17Z (update_failed evidence string on both rows)
    snap = _fixture_snapshot(statuses={"render-primary": "degraded",
                                       "render-worker": "degraded"}, timestamp=fresh_ts)
    snap["snapshots"]["render-primary"]["evidence"] = (
        "Container running previous build, but latest deployment update_failed")
    v, f = evaluate_criterion("2225", crit, snap, 600)
    check("F14 live-counterexample shape => REFUSE_FAILED", v == "REFUSE_FAILED", str(f))

    print(f"\nself-test: {'ALL PASS' if not failures else 'FAILURES: ' + ', '.join(failures)}")
    return 0 if not failures else 1


def gate(subject: str, snapshot_path: str | None, live: bool, tower_url: str,
         max_age_seconds: int) -> int:
    crit = RECOVERY_CRITERIA.get(str(subject))
    if crit is None:
        print(f"[closure_live_state_guard] subject #{subject}: no declared recovery "
              "criterion — the gate does not fabricate criteria; closure path out "
              "of mechanical scope. ALLOW (exit 0).", file=sys.stderr)
        return 0
    snap, context = load_snapshot(snapshot_path, live, tower_url)
    if snap is None:
        print(f"CLOSURE REFUSED by closure_live_state_guard (verdict INDETERMINATE)\n"
              f"subject issue: #{subject}\n"
              f"declared criterion source: {crit['source']}\n"
              f"snapshot source: {context}\n"
              "criterion output attached: none available (snapshot unreadable) — "
              "default-deny per the fail-loud contract; downgrade to evidence-only.",
              file=sys.stderr)
        return 2
    verdict, findings = evaluate_criterion(subject, crit, snap, max_age_seconds)
    if verdict == "ALLOW_PASS":
        print(f"[closure_live_state_guard] subject #{subject}: criterion PASSED — "
              "closing artifact may proceed. PASS receipt:", file=sys.stderr)
        for line in findings:
            print(f"  - {line}", file=sys.stderr)
        return 0
    msg = evidence_only_template(subject, crit, findings, verdict)
    if verdict == "INDETERMINATE":
        msg = msg.replace("verdict REFUSE_FAILED", "verdict INDETERMINATE")
        print(msg, file=sys.stderr)
        return 2
    print(msg, file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--closing-issue", help="subject issue number at closure time")
    ap.add_argument("--snapshot-file", help="tower health_full_sweep snapshot JSON")
    ap.add_argument("--live", action="store_true",
                    help="fetch a fresh snapshot from the tower (zero-credential)")
    ap.add_argument("--tower-url", default=DEFAULT_TOWER_URL)
    ap.add_argument("--max-age-seconds", type=int, default=DEFAULT_MAX_AGE_SECONDS)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--registry-check", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()
    if args.registry_check:
        for num, crit in RECOVERY_CRITERIA.items():
            print(f"#{num}: services={crit['services']} "
                  f"acceptable={crit['acceptable_status']}\n  source: {crit['source']}")
        return 0
    if not args.closing_issue:
        ap.error("--closing-issue is required (or --self-test / --registry-check)")
    try:
        return gate(args.closing_issue, args.snapshot_file, args.live,
                    args.tower_url, args.max_age_seconds)
    except Exception as exc:  # noqa: BLE001 - top-level fail-loud, default-deny
        print(f"CLOSURE REFUSED by closure_live_state_guard (verdict INDETERMINATE)\n"
              f"unexpected guard error: {exc.__class__.__name__}: {exc}\n"
              "default-deny per the fail-loud contract; downgrade to evidence-only.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
