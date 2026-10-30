#!/usr/bin/env python3
"""verdict_plane_gap_probe.py — mechanical verdict-gap worklist for the gate plane (#2538).

The measured failure class (#2538, 2026-10-29, re-verified live at +26h by
#3240): external code PRs sit in `bridge:in-gates` for 7h+ with a verdict
plane that holds nothing actionable — one EMPTY intake touch, zero state
changes, zero gate comments — while same-window receipt rows land in 1-2h.
Ask 3 of #2538 names the cost precisely: an empty verdict leaves the
submitter nothing to act on. Agents currently discover this class only by
hand-polling `bridge_read_feedback` hourly; no mechanical surface computes
the gap worklist. This probe is that surface.

Reconciliation model — WO-DRIVEN on purpose (r2, live lesson 2026-10-30):

The `bridge:in-gates` WO rows are the gate plane's OWN canonical worklist:
they survive PR-list window truncation (the supremeai-open list_prs window
holds ~100 recent rows; the 2026-10-28 stalled pair #2354/#2386 had already
aged OUT of it while their WOs stayed in-gates with dark verdicts — a
PR-driven probe would have silently missed the exact class it exists for).
The PR plane and the mirror plane are ENRICHMENT reads, never the driver.

  - WO plane      : open work orders (Tower bridge.work_queue, limit ladder
                    200->50->default, same fidelity window as the landing
                    watchdog #2115/#2123); rows labeled `bridge:in-gates`
                    are the probe's candidates. Titles carry the slug.
  - verdict plane : Tower bridge_read_feedback per candidate WO — latest
                    verdict + verdictHistory length. Probed ONLY for
                    in-gates candidates (cap 30); healthy steady state
                    probes a handful.
  - PR plane      : open PRs of Supremeai-bd/supremeai-open (Tower
                    github.list_prs, repo passed EXPLICITLY — the R66 drift
                    class #2452/#2469 silently retargets the account default
                    monorepo when repo is omitted). Slug-joined as
                    enrichment: a paired open PR row proves the deliverable
                    is still in flight; its absence from the visible window
                    is reported honestly (prVisible=false), never invented.
  - mirror plane  : open PRs of the monorepo Supremeai-bd/supremeai (the
                    mirror cohort of #2538 §3) — counted, never joined: the
                    mirror lane drains by a different authority and a
                    cross-repo slug join would manufacture false pairs.

Verdict normalization (the r2 live lesson): the tower's latestVerdict is
 EITHER a plain string or a DICT envelope {verdict, task, reason, repo, pr,
 at}. The stalled pair's envelope carries verdict:"" — an EMPTY verdict in
 dict clothing. A shape-blind check (`latestVerdict != null`) would
 classify the exact #2538 headline rows as healthy. Normalization extracts
 the dict's `verdict` field and treats a missing/empty one as empty.

Verdict-gap class per in-gates WO (age = hours since the intake touch `at`
 when present — the #2538 'post-intake-touch' age — else since WO
 updatedAt; rows with neither age source stay honestly untagged):

  ZERO_VERDICT_AGED  age >= threshold AND verdictHistory empty.
  INTAKE_TOUCH_ONLY  verdictHistory non-empty but the normalized verdict is
                     empty AND age >= threshold — the frozen single-touch
                     class (#2353/#2385: one EMPTY intake-bot touch at
                     02:31:25Z Oct 29, then 33h+ of silence).
  REJECTED_VERDICT   normalized verdict carries REJECTED — actionable
                     signal IS present; healthy-by-this-probe (the
                     submitter has something to act on, which is all this
                     probe demands of the plane).
  VERDICT_PRESENT    normalized verdict non-empty otherwise — healthy.
  YOUNG_IN_GATES     age < threshold — inside normal gate latency, never a
                     signal (freshness grace keeps the strict surface
                     minimal, same doctrine as LANDING_AT_RISK's threshold).
  AGE_UNKNOWN        no parseable age source — honestly untagged, never a
                     strict signal (watchdog doctrine on missing stamps).

Modes:
  --self-test   hermetic classification-matrix proof (fixture WOs/
                verdicts/PRs; every class exercised, dict-envelope shape
                included; no network).
  --json        machine-readable worklist on stdout (the awaiting-
                maintainer label candidates of #2538 ask 2 + the
                actionable-signal accounting of ask 3), stable field order,
                idempotent.
  --strict      exit 1 when any ZERO_VERDICT_AGED or INTAKE_TOUCH_ONLY row
                exists — for scheduled enforcement once the cadence
                question (#2538 ask 1, maintainer lane) is answered.
                Default is report-only: exit 0 with the table, because a
                transient Tower condition must never red a gate (watchdog
                doctrine).
  --at-hours H  age threshold override (default 7.0 — the #2538 observation).

Exit codes: 0 = report OK (report-only default), 1 = strict findings,
            2 = WO/PR plane unreachable (honest skip — never a false pass).

Zero credentials, read-only. One MCP session per run (not per call — the
tower caps concurrent sessions at 100, and the watchdog's per-call init
pattern spends ~24 sessions on a single feedback sweep; this probe holds a
single negotiated session for its whole run).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOWER = "https://supremeai-mcp-tower.onrender.com/mcp"
OPEN_REPO = "Supremeai-bd/supremeai-open"
MONOREPO = "Supremeai-bd/supremeai"

SLUG_RE = re.compile(r"\(bridge-\d{8}-[a-z0-9][a-z0-9-]*\)")
IN_GATES_LABEL = "bridge:in-gates"
DEFAULT_AT_HOURS = 7.0

# Per-WO feedback fetch cap: only in-gates candidates are probed; a runaway
# board must never fan out unbounded.
MAX_FEEDBACK_PROBES = 30

# Queue-limit ladder across the queue-fidelity deploy window (#2115/#2123) —
# same shape as the landing watchdog's ladder.
QUEUE_LIMIT_LADDER: tuple = (200, 50, None)

CLASSES = (
    "ZERO_VERDICT_AGED",
    "INTAKE_TOUCH_ONLY",
    "REJECTED_VERDICT",
    "VERDICT_PRESENT",
    "VERDICT_UNREAD",
    "YOUNG_IN_GATES",
    "AGE_UNKNOWN",
)
STRICT_CLASSES = ("ZERO_VERDICT_AGED", "INTAKE_TOUCH_ONLY")

# Verdict-plane read hygiene: the earlier r1 live run saw probes 7-23 all fail
# transiently after six rapid same-session calls — one-shot fail-open turned
# every one of them into a permanent unknown. Retry a few times with short
# backoff, and pace the sweep so the per-minute window is respected.
FEEDBACK_ATTEMPTS = 3
FEEDBACK_BACKOFF_S = 1.5
PROBE_PACE_S = 0.25


# ── minimal zero-credential MCP client (one session per run) ──────────────


def _try_json(text: str):
    """json.loads or None — malformed SSE lines are individually skippable."""
    try:
        return json.loads(text)
    except Exception:
        return None


class TowerSession:
    """Holds ONE negotiated MCP session for the whole probe run."""

    def __init__(self, client_name: str = "verdict-plane-gap-probe") -> None:
        self.client_name = client_name
        self.sid: str | None = None
        self._id = 100

    def _rpc(self, method: str, params=None, notify: bool = False, attempts: int = 4):
        payload: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notify:
            self._id += 1
            payload["id"] = self._id
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": "2025-11-25"}
        if self.sid:
            headers["Mcp-Session-Id"] = self.sid
        last: Exception | None = None
        for attempt in range(attempts):
            req = urllib.request.Request(
                TOWER, data=json.dumps(payload).encode(), headers=headers, method="POST")
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
            raise last
        if sid:
            self.sid = sid
        if "text/event-stream" in ctype:
            for line in body.splitlines():
                if line.startswith("data:"):
                    parsed = _try_json(line[5:].strip())
                    if parsed is not None:
                        return parsed
        if not body.strip():
            return {"accepted": True}
        return json.loads(body)

    def connect(self) -> None:
        self._rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                 "clientInfo": {"name": self.client_name, "version": "1.1"}})
        self._rpc("notifications/initialized", {}, notify=True)

    def tool_text(self, name: str, arguments: dict) -> str:
        res = self._rpc("tools/call", {"name": name, "arguments": arguments})
        content = res.get("result", {}).get("content", []) if isinstance(res, dict) else []
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")


# ── plane readers (each takes a fetch_text callable: live tower or fixture) ──


def _fetch_work_orders(fetch_text) -> tuple:
    """Open work orders across the queue-fidelity ladder (watchdog shape)."""
    last_err: Exception = RuntimeError("queue ladder exhausted")
    for limit in QUEUE_LIMIT_LADDER:
        arguments = {} if limit is None else {"limit": limit}
        try:
            payload = json.loads(fetch_text("bridge.work_queue", arguments))
        except json.JSONDecodeError as err:
            last_err = err
            continue
        if not isinstance(payload, dict) or payload.get("isError"):
            last_err = TypeError(f"queue rung {limit} answered a non-payload")
            continue
        return (payload.get("workOrders", []) or [], limit)
    raise last_err


def _fetch_open_prs(fetch_text, repo: str) -> list:
    """Open PRs of one repo. The tower answers a TOP-LEVEL JSON ARRAY of PR
    rows (live 2026-10-30); dict envelopes are accepted for drift tolerance."""
    raw = fetch_text("github.list_prs", {"repo": repo, "state": "open", "limit": 100})
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as err:
        # An unparseable PR plane must NOT fabricate an empty board (a false
        # 'cohort empty' would be a false pass) — surface as unreachable.
        raise ValueError(f"{repo} PR plane unparseable: {err}") from err
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        prs = payload.get("pullRequests") or payload.get("prs") or payload.get("rows") or []
        return [p for p in prs if isinstance(p, dict)]
    return []


def _fetch_verdict(fetch_text, wo_number: int) -> dict:
    """Machine-readable verdict state for one WO. A transient tower condition
    must not become a permanent unknown (r1 live lesson: 17 consecutive
    one-shot failures mid-sweep), so short retries precede the fail-open."""
    for attempt in range(FEEDBACK_ATTEMPTS):
        try:
            raw = fetch_text("bridge_read_feedback", {"number": wo_number})
            payload = json.loads(raw)
            break
        except Exception:
            if attempt == FEEDBACK_ATTEMPTS - 1:
                return {"unreachable": True}
            time.sleep(FEEDBACK_BACKOFF_S * (attempt + 1))
    if not isinstance(payload, dict):
        return {"unreachable": True}
    return {
        "latestVerdict": payload.get("latestVerdict"),
        "verdictCount": len(payload.get("verdictHistory") or []),
        "verdictSource": payload.get("verdictSource"),
    }


# ── classification (pure, hermetic-provable) ───────────────────────────────


def _slug_of(title: str) -> str | None:
    m = SLUG_RE.search(title or "")
    return m.group(0) if m else None


def normalize_verdict(latest) -> str | None:
    """Normalized verdict string; None = empty/no verdict.

    The tower's latestVerdict is either a plain string or a dict envelope
    {verdict, task, reason, repo, pr, at}. The #2353/#2385 envelope carries
    verdict:"" — empty in dict clothing; a shape-blind null-check calls
    those rows healthy. A NON-dict, non-str, non-None value degrades to its
    string form so nothing silently reads as healthy.
    """
    if latest is None:
        return None
    if isinstance(latest, dict):
        inner = latest.get("verdict")
        if inner is None or (isinstance(inner, str) and not inner.strip()):
            return None
        return str(inner)
    s = latest if isinstance(latest, str) else str(latest)
    return s if s.strip() else None


def _parse_ts(raw) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _age_hours(ts_raw, now: datetime) -> float | None:
    dt = _parse_ts(ts_raw)
    if dt is None:
        return None
    return max(0.0, (now - dt).total_seconds() / 3600.0)


def classify_in_gates_wo(verdict: dict, age_hours: float | None,
                         at_hours: float = DEFAULT_AT_HOURS) -> str:
    """Verdict-gap class for one in-gates WO given its verdict state and age."""
    if verdict.get("unreachable"):
        # Honest unknown: the verdict plane could not be read even after
        # retries — an unread row must never masquerade as VERDICT_PRESENT.
        return "VERDICT_UNREAD"
    if age_hours is None:
        # Missing age source: honestly untagged — never a strict signal.
        return "AGE_UNKNOWN"
    normalized = normalize_verdict(verdict.get("latestVerdict"))
    if isinstance(normalized, str) and "REJECT" in normalized.upper():
        return "REJECTED_VERDICT"
    if normalized is None:
        count = int(verdict.get("verdictCount") or 0)
        if age_hours < at_hours:
            return "YOUNG_IN_GATES"
        return "ZERO_VERDICT_AGED" if count == 0 else "INTAKE_TOUCH_ONLY"
    return "VERDICT_PRESENT"


def build_report(wos: list, open_prs: list, mirror_prs: list, fetch_verdict_fn,
                 at_hours: float, now: datetime) -> dict:
    """WO-driven three-read report: in-gates WOs → verdict plane; PR/mirror
    planes enrich and count."""

    in_gates = [w for w in wos if IN_GATES_LABEL in (w.get("labels") or [])]
    pr_by_slug: dict[str, dict] = {}
    for pr in open_prs:
        slug = _slug_of(pr.get("title") or "")
        if slug and slug not in pr_by_slug:
            pr_by_slug[slug] = pr

    rows: list[dict] = []
    probes = 0
    for wo in in_gates:
        wo_number = wo.get("number")
        slug = _slug_of(wo.get("title") or "")
        if probes < MAX_FEEDBACK_PROBES:
            verdict = fetch_verdict_fn(int(wo_number)) if wo_number is not None else {"unreachable": True}
            probes += 1
            if PROBE_PACE_S > 0:
                time.sleep(PROBE_PACE_S)
        else:
            verdict = {"unreachable": True}
        pr = pr_by_slug.get(slug) if slug else None
        # Age precedence: intake-touch `at` (the #2538 post-intake-touch age)
        # → PR createdAt (paired, visible) → WO updatedAt (honest fallback).
        latest = verdict.get("latestVerdict")
        touch_at = latest.get("at") if isinstance(latest, dict) else None
        age = _age_hours(touch_at, now)
        if age is None and pr is not None:
            age = _age_hours(pr.get("createdAt") or pr.get("created_at"), now)
        if age is None:
            age = _age_hours(wo.get("updatedAt"), now)
        cls = classify_in_gates_wo(verdict, age, at_hours)
        rows.append({
            "woNumber": wo_number,
            "slug": slug,
            "prNumber": pr.get("number") if pr else None,
            "prVisible": pr is not None,
            "ageHours": round(age, 2) if isinstance(age, float) else age,
            "class": cls,
            "verdictSource": verdict.get("verdictSource"),
            "verdictCount": verdict.get("verdictCount"),
        })

    open_mirror = [p for p in mirror_prs if not p.get("merged")]
    gaps = [r for r in rows if r["class"] in STRICT_CLASSES]
    return {
        "atHours": at_hours,
        "now": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "openWorkOrders": len(wos),
        "inGatesCandidates": len(in_gates),
        "feedbackProbes": probes,
        "openPrsVisible": len(open_prs),
        "mirrorCohort": {"repo": MONOREPO, "open": len(open_mirror),
                         "observedRows": len(mirror_prs)},
        "rows": rows,
        "gapWorklist": [
            {"woNumber": r["woNumber"], "prNumber": r["prNumber"], "class": r["class"],
             "ageHours": r["ageHours"]}
            for r in gaps
        ],
        "actionableSignalAccounting": {
            "rejectedRows": sum(1 for r in rows if r["class"] == "REJECTED_VERDICT"),
            "verdictPresentRows": sum(1 for r in rows if r["class"] == "VERDICT_PRESENT"),
            "unreadRows": sum(1 for r in rows if r["class"] == "VERDICT_UNREAD"),
        },
    }


def render_table(report: dict) -> str:
    lines = [
        f"verdict-plane gap probe @ {report['now']} (threshold {report['atHours']}h)",
        (f"open WOs: {report['openWorkOrders']} · in-gates candidates: "
         f"{report['inGatesCandidates']} · feedback probes: {report['feedbackProbes']} · "
         f"open PRs visible: {report['openPrsVisible']} · "
         f"mirror cohort open: {report['mirrorCohort']['open']}"),
        f"{'WO':>6}  {'PR':>6}  {'age(h)':>7}  {'class':<17}  {'src':<12}  slug",
        "-" * 100,
    ]
    for r in report["rows"]:
        age = "n/a" if r["ageHours"] is None else f"{r['ageHours']:.1f}"
        src = str(r.get("verdictSource") or "-")
        pr = str(r["prNumber"]) if r["prVisible"] else ("?" if r["prNumber"] is None else f"…{r['prNumber']}")
        lines.append(f"{r['woNumber']!s:>6}  {pr:>6}  {age:>7}  "
                     f"{r['class']:<17}  {src[:12]:<12}  {r['slug'] or '-'}")
    if report["gapWorklist"]:
        lines.append("")
        lines.append(f"GAP WORKLIST ({len(report['gapWorklist'])} row(s) — the #2538 ask-2 label candidates):")
        for g in report["gapWorklist"]:
            lines.append(f"  WO #{g['woNumber']} / PR {g['prNumber'] if g['prNumber'] else 'beyond-window'} — "
                         f"{g['class']} ({g['ageHours']}h)")
    else:
        lines.append("GAP WORKLIST: empty — no aged zero-verdict rows in this window.")
    return "\n".join(lines)


# ── hermetic self-test ─────────────────────────────────────────────────────

_NOW = datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC)


def _hours_ago(h: float) -> str:
    return (_NOW - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _self_test() -> int:
    """Hermetic classification-matrix proof: every class exercised, the
    dict-envelope verdict shape included; zero miss, zero false positive.
    No network."""
    failures: list[str] = []

    def check(name: str, got, want) -> None:
        if got != want:
            failures.append(f"{name}: got {got!r}, want {want!r}")

    at = DEFAULT_AT_HOURS

    # 1. normalize_verdict: the #2353/#2385 dict-envelope shape
    check("dict empty verdict -> None",
          normalize_verdict({"verdict": "", "task": "t", "at": _hours_ago(33)}), None)
    check("dict absent verdict -> None",
          normalize_verdict({"task": "t"}), None)
    check("dict real verdict kept",
          normalize_verdict({"verdict": "APPLIED"}), "APPLIED")
    check("str verdict kept", normalize_verdict("APPLIED"), "APPLIED")
    check("empty str verdict -> None", normalize_verdict("   "), None)
    check("None -> None", normalize_verdict(None), None)

    # 2. headline class: aged + zero verdict entries
    check("zero-verdict-aged", classify_in_gates_wo(
        {"latestVerdict": None, "verdictCount": 0}, 9.5), "ZERO_VERDICT_AGED")

    # 3. frozen single-touch class: aged + intake dict-envelope empty verdict
    intake_envelope = {"latestVerdict": {"verdict": "", "task": "t", "at": _hours_ago(33.0)},
                       "verdictCount": 1, "verdictSource": "intake-bot"}
    check("intake-touch-only", classify_in_gates_wo(intake_envelope, 33.0), "INTAKE_TOUCH_ONLY")

    # 4. rejected verdict = actionable signal present, NOT a gap
    check("rejected", classify_in_gates_wo(
        {"latestVerdict": "REJECTED: guard failure", "verdictCount": 2}, 30.0),
        "REJECTED_VERDICT")

    # 5. healthy verdict on an aged row: no false positive
    check("verdict-present", classify_in_gates_wo(
        {"latestVerdict": "APPLIED", "verdictCount": 3}, 12.0), "VERDICT_PRESENT")

    # 6. freshness grace: young row inside normal gate latency
    check("young", classify_in_gates_wo(
        {"latestVerdict": None, "verdictCount": 0}, 2.0), "YOUNG_IN_GATES")
    check("young touch-only", classify_in_gates_wo(
        {"latestVerdict": {"verdict": ""}, "verdictCount": 1}, 2.0), "YOUNG_IN_GATES")

    # 7. unreachable verdict plane (even after retries): honest unknown
    check("unreachable", classify_in_gates_wo({"unreachable": True}, 20.0),
          "VERDICT_UNREAD")

    # 8. ageless row: honestly untagged
    check("ageless", classify_in_gates_wo(
        {"latestVerdict": None, "verdictCount": 0}, None), "AGE_UNKNOWN")

    # 9. end-to-end report: WO-driven, pairing enrichment, worklist, mirror
    wos = [
        {"number": 21, "title": "WO a (bridge-20261029-alpha)",
         "labels": ["bridge:in-gates"], "updatedAt": _hours_ago(9.5)},
        {"number": 22, "title": "WO b (bridge-20261029-beta)",
         "labels": ["bridge:in-gates", "ops"], "updatedAt": _hours_ago(33.0)},
        {"number": 23, "title": "WO receipt", "labels": ["bridge:receipt"],
         "updatedAt": _hours_ago(1.0)},
    ]
    open_prs = [{"number": 11, "title": "a (bridge-20261029-alpha)",
                 "createdAt": _hours_ago(9.5)}]
    mirror = [{"number": 31, "merged": False}, {"number": 32, "merged": True}]

    def fake_verdict(n: int) -> dict:
        return {21: {"latestVerdict": None, "verdictCount": 0},
                22: {"latestVerdict": {"verdict": "", "task": "t",
                                       "pr": "#355", "at": _hours_ago(33.0)},
                     "verdictCount": 1, "verdictSource": "intake-bot"},
                23: {"latestVerdict": "APPLIED", "verdictCount": 1}}[n]

    rep = build_report(wos, open_prs, mirror, fake_verdict, at, _NOW)
    check("in-gates filter", rep["inGatesCandidates"], 2)
    check("row21 paired+aged", (rep["rows"][0]["prNumber"], rep["rows"][0]["class"]),
          (11, "ZERO_VERDICT_AGED"))
    check("row22 dict-envelope intake", rep["rows"][1]["class"], "INTAKE_TOUCH_ONLY")
    check("row22 pr beyond window", (rep["rows"][1]["prVisible"]), False)
    check("receipt row excluded", [r["woNumber"] for r in rep["rows"]], [21, 22])
    check("gap worklist len", len(rep["gapWorklist"]), 2)
    check("mirror open count", rep["mirrorCohort"]["open"], 1)
    check("probes counted", rep["feedbackProbes"], 2)

    # 10. idempotency: identical inputs → identical report
    rep2 = build_report(wos, open_prs, mirror, fake_verdict, at, _NOW)
    check("idempotent", rep == rep2, True)

    if failures:
        print("SELF-TEST FAIL:", len(failures))
        for f in failures:
            print("  -", f)
        return 1
    print("SELF-TEST PASS: 10/10 groups (verdict normalization, classification "
          "matrix, WO-driven report, pairing enrichment, idempotency)")
    return 0


# ── main ───────────────────────────────────────────────────────────────────


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verdict-plane gap probe (#2538)")
    ap.add_argument("--self-test", action="store_true", help="hermetic offline proof")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on aged zero-verdict / intake-touch-only rows")
    ap.add_argument("--at-hours", type=float, default=DEFAULT_AT_HOURS,
                    help=f"age threshold in hours (default {DEFAULT_AT_HOURS})")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    session = TowerSession()
    try:
        session.connect()

        def fetch_text(name: str, arguments: dict) -> str:
            return session.tool_text(name, arguments)

        wos, _serving = _fetch_work_orders(fetch_text)
        open_prs = _fetch_open_prs(fetch_text, OPEN_REPO)
        mirror_prs = _fetch_open_prs(fetch_text, MONOREPO)
    except Exception as e:
        print(f"PLANE UNREACHABLE: {e}", file=sys.stderr)
        return 2

    now = datetime.now(UTC)
    report = build_report(wos, open_prs, mirror_prs, lambda n: _fetch_verdict(fetch_text, n),
                          args.at_hours, now)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_table(report))

    if args.strict and report["gapWorklist"]:
        print(f"STRICT: {len(report['gapWorklist'])} verdict-gap row(s) present", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
