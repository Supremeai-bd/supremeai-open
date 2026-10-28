#!/usr/bin/env python3
"""bridge_landing_watchdog.py — bridge work-order landing watchdog (#1964 gap).

The measured failure class (#1964, 2026-10-28): run 4532 failed main preflight
on index drift and main was force-pushed back, EVICTING the R42 deliverable
(d9d9385/7f8d8df, unfetchable by SHA) while its work order #1953 stayed
`bridge:queued` with an empty verdict — a landing can now silently vanish
between "bridge accepted the patch" and "CI Guardian lands it", and nothing
reconciles the two planes. This is the watchdog mirror the triage asked for.

Reconciliation model (three planes, one join key):
  - board plane   : open WOs labeled `bridge:queued` (Tower bridge_work_queue,
                    zero-credential) — each title carries the lane slug
                    `(bridge-YYYYMMDD-<slug>)`.
  - history plane : landed commit subjects on origin/main (squash-merge
                    convention embeds the same slug and the PR number).
  - flight plane  : open PR titles (Tower github_list_prs) — same slug token.

Verdict per open bridge:queued WO (any-slug match wins):
  MERGED_ON_MAIN   slug found in main history — WO should close; flagged as
                   bookkeeping lag when it ages past the threshold.
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

Modes:
  --self-test   hermetic verdict-matrix proof (fixture WOs/history/flight;
                miss=0, false-positive=0). No network. (roster mode)
  --strict      exit 1 when any LANDING_AT_RISK (or MERGED_ON_MAIN lagging past
                the threshold) exists; report-only default exits 0 with the
                table so a transient Tower condition never reds a gate.
Exit codes: 0 = report OK, 1 = strict findings, 2 = board/history unreachable
            (honest skip — never reported as pass).

Zero credentials, read-only (Tower queries + local git log). No mutation.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

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
               "Accept": "application/json, text/event-stream"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(TOWER, data=json.dumps(payload).encode(),
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
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
                except Exception:  # noqa: BLE001
                    continue
    if not body.strip():
        return {"accepted": True}, sid
    return json.loads(body), sid


def _text_of(res) -> str:
    content = res.get("result", {}).get("content", []) if isinstance(res, dict) else []
    return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))


def _tower_text(name: str, arguments: dict) -> str:
    _, sid = _rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                 "clientInfo": {"name": "bridge-landing-watchdog", "version": "1.0"}})
    _rpc("notifications/initialized", {}, session_id=sid, notify=True)
    res, _ = _rpc("tools/call", {"name": name, "arguments": arguments}, session_id=sid)
    return _text_of(res)


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
        return {**base, "verdict": "MERGED_ON_MAIN", "evidence": f"slug {merged[0]} in main history"}

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
    """Classify every open bridge:queued WO; skip anything else (labels SSOT)."""
    out = []
    for wo in work_orders:
        labels = wo.get("labels") or []
        if isinstance(labels, str):
            labels = [labels]
        if "bridge:queued" not in labels:
            continue
        out.append(classify(wo, main_subjects, open_pr_titles, now_epoch, at_risk_hours))
    return out


# ── IO wrappers (live mode) ──────────────────────────────────────────────────

def _main_subjects(depth: int = LOG_DEPTH) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "log", "--format=%s", "-n", str(depth), "origin/main"],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"git log failed: {out.stderr.strip()[:120]}")
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def _open_pr_titles() -> list[str]:
    txt = _tower_text("github_list_prs", {"state": "open", "per_page": 50})
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
        return json.loads(_tower_text("bridge_work_order", {"number": number})).get("body")
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

    # 10. label filter: non-bridge:queued WOs are not classified at all
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

    return cases


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Bridge WO landing watchdog (#1964 gap)")
    p.add_argument("--self-test", action="store_true",
                   help="hermetic verdict-matrix proof (roster mode)")
    p.add_argument("--at-risk-hours", type=float, default=DEFAULT_AT_RISK_HOURS,
                   help=f"age past which an unmatched WO flags (default {DEFAULT_AT_RISK_HOURS:g}h)")
    p.add_argument("--strict", action="store_true",
                   help="exit 1 on at-risk/aging findings (report-only default)")
    args = p.parse_args(argv)

    if args.self_test:
        cases = self_test()
        failed = [c for c in cases if not c[1]]
        for name, ok, ev in cases:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {ev}" if not ok else ""))
        print(f"\n==== {len(cases) - len(failed)}/{len(cases)} self-test cases PASS ====")
        return 1 if failed else 0

    try:
        queue_txt = _tower_text("bridge_work_queue", {})
        wos = json.loads(queue_txt).get("workOrders", [])
        subjects = _main_subjects()
        pr_titles = _open_pr_titles()
    except Exception as e:  # noqa: BLE001 - unreachable planes are a skip, never a pass
        print(f"SKIP: board/history unreachable ({e.__class__.__name__}: {e})")
        return 2

    now = time.mktime(time.gmtime())
    verdicts = run_verdicts(wos, subjects, pr_titles, now, args.at_risk_hours)
    verdicts = refine_satellites(verdicts)
    if not verdicts:
        print("REPORT: no open bridge:queued WOs to reconcile (queue clean).")
        return 0
    order = {"LANDING_AT_RISK": 0, "MERGED_ON_MAIN": 1, "OPEN_PR": 2, "IN_GATES": 3,
             "SATELLITE_TARGET": 4, "NO_SLUG": 5}
    for v in sorted(verdicts, key=lambda v: (order.get(v["verdict"], 9), v["number"] or 0)):
        flag = "!!" if v["verdict"] == "LANDING_AT_RISK" else "  "
        age_s = "?" if v["age_hours"] is None else f"{v['age_hours']:.1f}h"
        print(f"{flag} #{v['number']} [{v['verdict']}] age={age_s} "
              f"slug={v['slug']} — {v['evidence'][:100]}")
    counts: dict[str, int] = {}
    for v in verdicts:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    print("VERDICT: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    risky = [v for v in verdicts
             if v["verdict"] == "LANDING_AT_RISK"
             or (v["verdict"] == "MERGED_ON_MAIN" and (v["age_hours"] or 0) >= args.at_risk_hours)]
    if not risky:
        return 0
    if args.strict:
        print(f"STRICT: {len(risky)} work order(s) need reconciliation — file/claim the triage lane "
              "(tracker class: #1964 eviction; recipe: #1940 rebase+regen).")
        return 1
    print("REPORT-ONLY findings (exit 0) — rerun with --strict for a fail-closed verdict.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
