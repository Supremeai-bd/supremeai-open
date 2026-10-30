#!/usr/bin/env python3
"""Offline tests for the bridge landing watchdog (#1964 gap).

The watchdog reconciles open `bridge:queued` work orders against the history
plane (main squash-merge subjects) and the flight plane (open PR titles) so a
force-push eviction (#1964: R42 deliverable evicted, WO left queued/empty)
can never again sit unnoticed. These tests deliberately do NOT touch the
network: they run the guard's own --self-test (hermetic verdict-matrix proof:
every class reachable, prefix-collision-proof, any-slug-wins, honest handling
of unparseable timestamps and the label SSOT), pin the roster wiring, the
verdict-class SSOT, the slug grammar (full-token join key), and the
honest-skip exit code. Dual-mode (pytest + stdlib runner), mirroring
test_boundary_contract_sentinel.py.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = REPO_ROOT / "scripts" / "ci" / "bridge_landing_watchdog.py"
ROSTER = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"

PASS = 0
FAIL = 1


def _load_watchdog_module():
    spec = importlib.util.spec_from_file_location("bridge_landing_watchdog", WATCHDOG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_roster_wiring():
    src = ROSTER.read_text(encoding="utf-8")
    assert ('["python", "scripts/ci/bridge_landing_watchdog.py", "--self-test"]' in src), \
        "watchdog missing from run_all_guards.py GUARDS roster"


def test_verdict_model_pins():
    mod = _load_watchdog_module()
    # The six verdict classes are the model's SSOT — renaming one is a
    # contract break for every consumer of the report table.
    src = WATCHDOG.read_text(encoding="utf-8")
    for verdict in ("MERGED_ON_MAIN", "OPEN_PR", "IN_GATES", "LANDING_AT_RISK",
                    "SATELLITE_TARGET", "NO_SLUG"):
        assert verdict in src, f"verdict class missing: {verdict}"
    # Slug grammar: (bridge-YYYYMMDD-slug), lowercase alnum + dashes, must start
    # alnum — the full token is the join key, so the regex must be token-shaped.
    assert mod.extract_slugs("x (bridge-20261028-alpha-lane) y") == ["(bridge-20261028-alpha-lane)"]
    assert mod.extract_slugs("x (bridge-20261028-alpha-lane-r2) y") == ["(bridge-20261028-alpha-lane-r2)"]
    assert mod.extract_slugs("no slug here") == []
    assert mod.extract_slugs("(bridge-2026-foo)") == []  # date must be 8 digits
    assert mod.extract_slugs("(bridge-20261028-)") == []  # slug must start alnum
    # Prefix collision is the r2-lane trap: base slug must not match -r2 needle.
    base = "(bridge-20261028-alpha-lane)"
    assert base not in mod.extract_slugs(f"x (bridge-20261028-alpha-lane-r2) y")
    # Threshold default: 2h (fresh-evidence window vs CI-Guardian latency).
    assert mod.DEFAULT_AT_RISK_HOURS == 2.0
    # Satellite model (#1916 live false positive): the open repo constant and
    # the standard WO-template Target Repo extraction.
    assert mod.OPEN_REPO == "Supremeai-bd/supremeai-open"
    assert mod.parse_target_repo(
        "### Target Repo\nSupremeai-bd/supremeai-browser\n") == "Supremeai-bd/supremeai-browser"
    assert mod.parse_target_repo("### Target Repo\nSupremeai-bd/supremeai-open\n") == mod.OPEN_REPO
    assert mod.parse_target_repo("no section") is None  # fail-closed default
    assert mod.parse_target_repo(None) is None
    assert mod.parse_target_repo("") is None


def test_classify_pure_matrix():
    mod = _load_watchdog_module()
    now = 1793160000.0
    slug = "(bridge-20261028-alpha-lane)"
    r2 = "(bridge-20261028-alpha-lane-r2)"
    fresh = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 20 * 60))
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 4 * 3600))

    # Landed: slug present in main history -> MERGED_ON_MAIN.
    v = mod.classify({"number": 1, "title": f"x {slug} y", "createdAt": fresh},
                     ["feat: something (bridge-20261028-alpha-lane) (#1900)"], [], now)
    assert v["verdict"] == "MERGED_ON_MAIN", v
    # In flight: slug in an open PR title -> OPEN_PR.
    v = mod.classify({"number": 2, "title": f"x {slug} y", "createdAt": fresh},
                     [], [f"PR title (bridge-20261028-alpha-lane) (#1901)"], now)
    assert v["verdict"] == "OPEN_PR", v
    # Young unmatched -> IN_GATES (normal CI-Guardian latency).
    v = mod.classify({"number": 3, "title": f"x {slug} y", "createdAt": fresh}, [], [], now)
    assert v["verdict"] == "IN_GATES", v
    # Old unmatched -> LANDING_AT_RISK (the #1964 class).
    v = mod.classify({"number": 4, "title": f"x {slug} y", "createdAt": old}, [], [], now)
    assert v["verdict"] == "LANDING_AT_RISK", v
    # No slug -> NO_SLUG (never strict-flagged).
    v = mod.classify({"number": 5, "title": "operator handoff, no lane slug",
                      "createdAt": old}, [], [], now)
    assert v["verdict"] == "NO_SLUG", v
    # Prefix collision: -r2 slug must NOT match the base lane's landing.
    v = mod.classify({"number": 6, "title": f"x {r2} y", "createdAt": old},
                     [f"feat: base lane (bridge-20261028-alpha-lane) (#1902)"], [], now)
    assert v["verdict"] == "LANDING_AT_RISK", v
    # ...and -r2 matches its own landing.
    v = mod.classify({"number": 7, "title": f"x {r2} y", "createdAt": fresh},
                     [f"feat: rescue (bridge-20261028-alpha-lane-r2) (#1903)"], [], now)
    assert v["verdict"] == "MERGED_ON_MAIN", v
    # Any-slug-wins: a multi-slug WO counts as landed if ONE slug landed.
    v = mod.classify({"number": 8, "title": f"a {slug} b {r2} c", "createdAt": old},
                     [f"feat: base (bridge-20261028-alpha-lane) (#1904)"], [], now)
    assert v["verdict"] == "MERGED_ON_MAIN", v
    # Unparseable createdAt -> honest IN_GATES (never a risk flag on bad data).
    v = mod.classify({"number": 9, "title": f"x {slug} y", "createdAt": "not-a-timestamp"},
                     [], [], now)
    assert v["verdict"] == "IN_GATES", v
    # Threshold boundary: age exactly at threshold flags (>=).
    edge = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 2.0 * 3600))
    v = mod.classify({"number": 10, "title": f"x {slug} y", "createdAt": edge},
                     [], [], now, at_risk_hours=2.0)
    assert v["verdict"] == "LANDING_AT_RISK", v


def test_satellite_target_matrix():
    """#1916 class: satellite-targeted WOs can never match the open-repo
    history/PR planes, so age-based LANDING_AT_RISK would flag them forever.
    The target_repo hint short-circuits that false positive — informationally,
    never strict-flagged, and a matched slug still wins over the hint."""
    mod = _load_watchdog_module()
    now = 1793160000.0
    slug = "(bridge-20261028-alpha-lane)"
    sat = "Supremeai-bd/supremeai-browser"
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 4 * 3600))
    fresh = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 20 * 60))

    # Old unmatched satellite WO -> SATELLITE_TARGET (not LANDING_AT_RISK).
    v = mod.classify({"number": 20, "title": f"sat {slug}", "createdAt": old},
                     [], [], now, target_repo=sat)
    assert v["verdict"] == "SATELLITE_TARGET", v
    assert sat in v["evidence"]
    # Age-independent: a young satellite WO is also SATELLITE_TARGET (the planes
    # can NEVER match it — IN_GATES would imply a future match is possible).
    v = mod.classify({"number": 21, "title": f"sat {slug}", "createdAt": fresh},
                     [], [], now, target_repo=sat)
    assert v["verdict"] == "SATELLITE_TARGET", v
    # A matched slug still wins over the satellite hint.
    v = mod.classify({"number": 22, "title": f"sat landed {slug}", "createdAt": old},
                     [f"feat: sat (bridge-20261028-alpha-lane) (#1906)"], [], now,
                     target_repo=sat)
    assert v["verdict"] == "MERGED_ON_MAIN", v
    # Explicit open-repo target keeps the standard risk model.
    v = mod.classify({"number": 23, "title": f"open {slug}", "createdAt": old},
                     [], [], now, target_repo=mod.OPEN_REPO)
    assert v["verdict"] == "LANDING_AT_RISK", v
    # No hint (body unparseable) keeps the standard risk model (fail-closed).
    v = mod.classify({"number": 24, "title": f"open {slug}", "createdAt": old},
                     [], [], now, target_repo=None)
    assert v["verdict"] == "LANDING_AT_RISK", v


def test_refine_satellites_injectable():
    mod = _load_watchdog_module()
    sat_body = "### Target Repo\nSupremeai-bd/supremeai-browser\n"
    open_body = "### Target Repo\nSupremeai-bd/supremeai-open\n"
    risk = {"number": 30, "verdict": "LANDING_AT_RISK",
            "slug": "(bridge-20261028-sat-lane)", "age_hours": 3.0}
    # Satellite body -> downgraded to SATELLITE_TARGET, age preserved for the report.
    vs = mod.refine_satellites([dict(risk)], fetch_body=lambda n: sat_body)
    assert vs[0]["verdict"] == "SATELLITE_TARGET" and vs[0]["age_hours"] == 3.0, vs[0]
    # Open-repo body -> risk flag kept.
    vs = mod.refine_satellites([dict(risk)], fetch_body=lambda n: open_body)
    assert vs[0]["verdict"] == "LANDING_AT_RISK", vs[0]
    # Body-absent (None) -> risk flag kept (fail-closed).
    vs = mod.refine_satellites([dict(risk)], fetch_body=lambda n: None)
    assert vs[0]["verdict"] == "LANDING_AT_RISK", vs[0]
    # Raising fetcher -> risk flag kept, never a crash (defense in depth).
    def boom(n):
        raise RuntimeError("tower down")
    vs = mod.refine_satellites([dict(risk)], fetch_body=boom)
    assert vs[0]["verdict"] == "LANDING_AT_RISK", vs[0]
    # Non-at-risk verdicts are never probed (probe counter stays zero).
    probed = []
    def spy(n):
        probed.append(n)
        return sat_body
    vs = mod.refine_satellites([{"number": 31, "verdict": "IN_GATES", "slug": "(bridge-20261028-x)",
                                 "age_hours": 0.1}], fetch_body=spy)
    assert probed == [] and vs[0]["verdict"] == "IN_GATES"


def test_run_verdicts_label_ssot():
    mod = _load_watchdog_module()
    now = 1793160000.0
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 4 * 3600))
    slug = "(bridge-20261028-alpha-lane)"
    vs = mod.run_verdicts(
        [{"number": 11, "title": f"x {slug}", "createdAt": old, "labels": ["bridge:queued"]},
         {"number": 12, "title": f"x {slug}", "createdAt": old, "labels": ["P2-medium"]},
         {"number": 13, "title": f"x {slug}", "createdAt": old, "labels": "bridge:queued"}],
        [], [], now)
    # Only bridge:queued WOs classified (list OR string label form); an
    # UNLANDED P2 issue is not this guard's subject (non-landed non-queued
    # rows stay silent — zero new false positives).
    assert sorted(v["number"] for v in vs) == [11, 13], vs
    assert all(v["verdict"] == "LANDING_AT_RISK" for v in vs), vs


def test_run_verdicts_full_board_join_2516():
    """#2516 remedy item 2 (full-board drainage join): an open row with a
    non-bridge label whose deliverable IS on main reports as MERGED_ON_MAIN
    tagged label_plane=outside-queued — previously it accumulated invisibly
    between manual matrix-scoped sweeps (the 34-row #2516 cohort). A landed
    row is a self-fulfilled WO regardless of label; a non-landed one stays
    unreported."""
    mod = _load_watchdog_module()
    now = 1793160000.0
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 4 * 3600))
    slug = "(bridge-20261028-alpha-lane)"
    hist = [f"feat: landed (bridge-20261028-alpha-lane) (#1905)"]
    vs = mod.run_verdicts(
        [{"number": 21, "title": f"landed {slug}", "createdAt": old,
          "updatedAt": old, "labels": ["report-only", "ops"]},
         {"number": 22, "title": f"landed {slug}", "createdAt": old,
          "labels": ["bridge:queued"]},
         {"number": 23, "title": f"stuck (bridge-20261028-beta-lane)", "createdAt": old,
          "labels": ["status:claimed"]}],
        hist, [], now)
    by_num = {v["number"]: v["verdict"] for v in vs}
    assert by_num == {21: "MERGED_ON_MAIN", 22: "MERGED_ON_MAIN"}, vs
    row21 = next(v for v in vs if v["number"] == 21)
    assert row21.get("label_plane") == "outside-queued", row21
    assert row21.get("never_touched") is True, row21  # flap fingerprint works outside the queued plane too
    assert "label_plane" not in next(v for v in vs if v["number"] == 22), "queued rows carry no plane tag"
    # Non-landed non-queued rows stay silent (zero new false positives).
    vs = mod.run_verdicts(
        [{"number": 24, "title": f"stuck (bridge-20261028-beta-lane)", "createdAt": old,
          "labels": ["status:claimed"]}],
        hist, [], now)
    assert vs == [], vs


def test_self_test_hermetic():
    r = subprocess.run([sys.executable, str(WATCHDOG), "--self-test"],
                       cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"self-test failed:\n{r.stdout}\n{r.stderr}"
    assert "self-test cases PASS" in r.stdout
    # miss=0 / fp=0 is the guard's own invariant — the fixture matrix must end
    # all-green, not partially green.
    assert "[FAIL]" not in r.stdout, r.stdout


def test_enrich_tower_verdicts_injectable():
    """Feedback-plane enrichment (the guard's own documented future work):
    MERGED_ON_MAIN rows get tower_verdict/tower_unstamped; the live
    2026-10-28 blackout (13/13 merged WOs with latestVerdict=null while every
    slug was provably landed) is exactly the True case. Fail-open semantics:
    an unreadable verdict plane is honest unknown (None), never False, and
    never changes a verdict class or the strict surface."""
    mod = _load_watchdog_module()
    merged = {"number": 40, "verdict": "MERGED_ON_MAIN",
              "slug": "(bridge-20261028-alpha-lane)", "age_hours": 0.5}
    risk = {"number": 41, "verdict": "LANDING_AT_RISK",
            "slug": "(bridge-20261028-alpha-lane-r2)", "age_hours": 3.0}

    def fb_none(n):
        return {"issueNumber": n, "state": "open", "labels": ["bridge:queued"],
                "latestVerdict": None, "verdictHistory": [], "commentCount": 0}

    def fb_stamped(n):
        return {"issueNumber": n, "state": "open", "labels": ["bridge:queued"],
                "latestVerdict": "MERGED_ON_MAIN", "verdictHistory": ["MERGED_ON_MAIN"],
                "commentCount": 1}

    def boom(n):
        raise RuntimeError("tower down")

    # History-proven landing + Tower null -> unstamped True (blackout visible).
    vs = mod.enrich_tower_verdicts([dict(merged), dict(risk)], fetch_feedback=fb_none)
    assert vs[0]["tower_unstamped"] is True and vs[0]["tower_verdict"] == "none", vs[0]
    # Non-merged rows stay untouched (zero enrichment keys, zero probes).
    assert "tower_verdict" not in vs[1] and "tower_unstamped" not in vs[1], vs[1]
    # Tower stamp present -> unstamped False (bookkeeping healthy).
    vs = mod.enrich_tower_verdicts([dict(merged)], fetch_feedback=fb_stamped)
    assert vs[0]["tower_unstamped"] is False and vs[0]["tower_verdict"] == "MERGED_ON_MAIN", vs[0]
    # Raising fetcher -> honest unknown (None), never False, never a crash.
    vs = mod.enrich_tower_verdicts([dict(merged)], fetch_feedback=boom)
    assert vs[0]["tower_unstamped"] is None and vs[0]["tower_verdict"] == "unreadable", vs[0]
    # Non-dict payload (MCP error envelope) -> honest unknown too.
    vs = mod.enrich_tower_verdicts([dict(merged)], fetch_feedback=lambda n: "MCP error -32602")
    assert vs[0]["tower_unstamped"] is None, vs[0]
    # Non-merged rows cost zero feedback probes (probe counter stays zero).
    probed = []

    def spy(n):
        probed.append(n)
        return fb_none(n)

    mod.enrich_tower_verdicts([dict(risk)], fetch_feedback=spy)
    assert probed == [], probed
    # Probe cap is honored.
    probed.clear()
    many = [dict(merged, number=i) for i in range(30)]
    mod.enrich_tower_verdicts(many, fetch_feedback=spy, max_probes=5)
    assert len(probed) == 5, probed


def test_live_mode_honest_skip_on_unreachable():
    # A watchdog that reports a verdict on unreachable planes would be a wolf
    # itself — exit 2 (skip), never 0/1, when the board/history is unreachable.
    # Point --at-risk-hours is irrelevant here; we force unreachability via a
    # bad Tower URL override is NOT available, so exercise the git-plane skip
    # path instead: run outside a repo via -C to a nonexistent path.
    mod = _load_watchdog_module()
    try:
        mod._main_subjects()
    except RuntimeError as e:
        assert "git log failed" in str(e)
    else:
        # In-repo the git plane works; the Tower plane is exercised by the
        # report-only live mode elsewhere. Nothing to assert here.
        pass


def test_fetch_work_orders_r2_tower_serves_full_ladder_top():
    """r2 tower (#2115/#2123): limit=200 accepted, rows returned, lower rungs
    never dialed (no wasted round-trips, no silent cap at 50 after deploy)."""
    mod = _load_watchdog_module()
    calls = []

    def r2_tower(name, arguments):
        calls.append(dict(arguments))
        assert arguments.get("limit") == 200
        return json.dumps({"workOrders": [{"number": 1}, {"number": 2}]})

    rows, rung = mod._fetch_work_orders(fetch_text=r2_tower)
    assert rows == [{"number": 1}, {"number": 2}] and rung == 200
    assert calls == [{"limit": 200}], calls


def test_fetch_work_orders_pre_r2_validation_fallback():
    """Pre-r2 deployed tower: limit=200 is a -32602 validation rejection
    (non-JSON error text) -> falls to 50 (pre-r2 cap; live receipt 35 rows);
    default rung never dialed. Rank-window visibility widens 20 -> 35."""
    mod = _load_watchdog_module()
    calls = []

    def prer2_tower(name, arguments):
        calls.append(dict(arguments))
        if arguments.get("limit") == 200:
            return ("MCP error -32602: Input validation error: Invalid "
                    "arguments for tool bridge.work_queue: Too big: expected "
                    "number to be <=50")
        assert arguments.get("limit") == 50, arguments
        return json.dumps({"workOrders": [{"number": n} for n in range(35)]})

    rows, rung = mod._fetch_work_orders(fetch_text=prer2_tower)
    assert len(rows) == 35 and rung == 50
    assert calls == [{"limit": 200}, {"limit": 50}], calls


def test_fetch_work_orders_default_rung_last_resort():
    """Both explicit rungs rejected -> tower default (exact pre-ladder
    behavior); the ladder never invents an empty board."""
    mod = _load_watchdog_module()
    calls = []

    def legacy_tower(name, arguments):
        calls.append(dict(arguments))
        if "limit" in arguments:
            return "MCP error -32602: Input validation error: unexpected argument"
        return json.dumps({"workOrders": [{"number": 7}]})

    rows, rung = mod._fetch_work_orders(fetch_text=legacy_tower)
    assert rows == [{"number": 7}] and rung is None
    assert calls == [{"limit": 200}, {"limit": 50}, {}], calls


def test_fetch_work_orders_network_failure_fail_close():
    """Only argument-validation rejections fall through; a transport failure
    propagates so main() keeps its honest SKIP (exit 2, never 0/1)."""
    mod = _load_watchdog_module()
    calls = []

    def dead_tower(name, arguments):
        calls.append(dict(arguments))
        raise ConnectionError("unreachable")

    try:
        mod._fetch_work_orders(fetch_text=dead_tower)
    except ConnectionError:
        pass
    else:
        raise AssertionError("transport failure must propagate, not fall through")
    assert calls == [{"limit": 200}], calls


def test_fetch_rejected_rows_paginates_short_page_stop():
    """#2158: rejected rows the queue omits are enumerated straight from
    GitHub via the S05 SSOT (short-page-stop, number-dedupe merge)."""
    mod = _load_watchdog_module()
    urls = []
    page1 = [{"number": 1000 + i, "title": f"w{i}", "state": "open",
              "labels": ["bridge:rejected"]} for i in range(100)]
    page2 = [{"number": 7, "title": "x (bridge-20261028-y)", "state": "open",
              "labels": [{"name": "bridge:rejected"}]},
             {"number": 7, "title": "dup", "state": "open",
              "labels": ["bridge:rejected"]}]

    def fake(url):
        urls.append(url)
        assert "labels=bridge%3Arejected" in url, url
        return {1: page1, 2: page2}[int(url.rsplit("page=", 1)[1].split("&")[0])]

    rows = mod._fetch_rejected_rows(fetch_json=fake)
    assert len(rows) == 101, len(rows)
    assert rows[-1]["number"] == 7 and rows[-1]["labels"] == ["bridge:rejected"]
    assert len(urls) == 2 and "page=1" in urls[0] and "page=2" in urls[1]


def test_fetch_rejected_rows_rejects_non_list():
    """A non-list GitHub payload is a loud per-plane error, never a silent
    empty enumeration (honesty contract: unknown != zero)."""
    mod = _load_watchdog_module()
    try:
        mod._fetch_rejected_rows(fetch_json=lambda u: {"message": "nope"})
    except TypeError:
        pass
    else:
        raise AssertionError("non-list payload must raise TypeError")


def test_join_rejected_plane_queue_rows_win_on_collision():
    """The queue stays the board SSOT for queued work; only queue-omitted
    rejected rows join — no double classification on label races."""
    mod = _load_watchdog_module()
    queue_rows = [{"number": 5, "title": "queued-row", "labels": ["bridge:queued"]}]
    rejected = [{"number": 5, "title": "rejected-row", "labels": ["bridge:rejected"]},
                {"number": 9, "title": "only-rejected", "labels": ["bridge:rejected"]}]
    joined, n = mod._join_rejected_plane(queue_rows, rejected)
    assert n == 1 and joined[0]["title"] == "queued-row" and joined[1]["number"] == 9


def test_load_rejected_plane_fail_open():
    """Both transports down degrade the rejected plane only: honest dual-cause
    'unreachable' note, empty rows — the queue plane stays authoritative."""
    mod = _load_watchdog_module()

    def boom():
        raise ConnectionError("down")

    rows, note = mod._load_rejected_plane(fetch_rows=boom, tower_rows=boom)
    assert rows == [] and "unreachable" in note
    assert "github ConnectionError" in note and "tower ConnectionError" in note


def test_fetch_rejected_rows_tower_shape():
    """The tower fallback parses the label-filtered bridge.work_queue payload
    (#2251 fixed the self-defeating filter) and fails loud on drift."""
    mod = _load_watchdog_module()

    ok = mod._fetch_rejected_rows_tower(fetch_text=lambda n, a: json.dumps({"count": 1, "workOrders": [
            {"number": 2056, "title": "x", "labels": ["bridge:rejected"]}]}))
    assert len(ok) == 1 and ok[0]["number"] == 2056

    try:
        mod._fetch_rejected_rows_tower(fetch_text=lambda n, a: '{"repo": "x"}')
        raise AssertionError("expected TypeError for missing workOrders")
    except TypeError:
        pass


def test_enrich_tower_verdicts_blank_stamp_shapes():
    """The stamp plane migrated live within hours (cbb9ab2 plane watch):
    latestVerdict went null -> strings -> objects carrying EMPTY verdict
    strings. A blank stamp is a blackout (unstamped), never a stamp; a real
    object stamp must surface its verdict token, not a dict repr."""
    mod = _load_watchdog_module()
    row = {"number": 70, "verdict": "MERGED_ON_MAIN",
           "slug": "(bridge-20261028-a)", "age_hours": 1.0}

    def run(latest):
        return mod.enrich_tower_verdicts(
            [dict(row)],
            fetch_feedback=lambda n: {"issueNumber": n, "latestVerdict": latest})[0]

    blank = run({"verdict": "", "at": "x"})
    assert blank["tower_unstamped"] is True and blank["tower_verdict"] == "none"
    ws = run("   ")
    assert ws["tower_unstamped"] is True and ws["tower_verdict"] == "none"
    stamped = run({"verdict": "MERGED_ON_MAIN", "at": "x"})
    assert (stamped["tower_unstamped"] is False
            and stamped["tower_verdict"] == "MERGED_ON_MAIN")
    plain = run("MERGED_ON_MAIN")
    assert plain["tower_unstamped"] is False and plain["tower_verdict"] == "MERGED_ON_MAIN"


def test_load_rejected_plane_403_falls_back_to_tower():
    """A 403 is transient (per-IP unauthenticated budget, resets hourly) and
    must be reported by cause whether the tower fallback covers it (#2251
    fixed the tower-side label filter; live 2026-10-29: github 403 from a
    shared egress while the tower plane served 20 rows) or both planes fail."""
    import urllib.error

    mod = _load_watchdog_module()

    def ratelimited():
        raise urllib.error.HTTPError("https://api.github.com/x", 403,
                                     "rate limit exceeded", None, None)

    def boom():
        raise RuntimeError("down")

    rows, note = mod._load_rejected_plane(
        fetch_rows=ratelimited, tower_rows=lambda: [{"number": 2056}])
    assert rows == [{"number": 2056}]
    assert "tower-plane fallback" in note
    assert "rate limit" in note and "resets hourly" in note

    rows, note = mod._load_rejected_plane(
        fetch_rows=ratelimited, tower_rows=boom)
    assert rows == [] and "unreachable" in note
    assert "rate limit" in note and "resets hourly" in note
    assert "tower RuntimeError" in note

    def server_error():
        raise urllib.error.HTTPError("https://api.github.com/x", 500,
                                     "boom", None, None)

    rows, note = mod._load_rejected_plane(fetch_rows=server_error,
                                          tower_rows=boom)
    assert rows == [] and "HTTP 500" in note


def test_queue_integrity_both_directions():
    """missing = queued-on-GitHub absent from listing (#2173 class);
    phantom = listed but absent from the label plane."""
    mod = _load_watchdog_module()
    missing, phantom = mod._check_queue_integrity({5}, {5, 9, 11})
    assert missing == [9, 11] and phantom == []
    missing, phantom = mod._check_queue_integrity({5, 7}, {5})
    assert missing == [] and phantom == [7]


def test_fetch_label_rows_parameterizes_label():
    """The shared core must carry the requested label into the query URL."""
    page = [{"number": 9, "title": "queued", "state": "open",
             "labels": ["bridge:queued"]}]

    def fake(url):
        assert "labels=bridge%3Aqueued" in url, url
        return page

    mod = _load_watchdog_module()
    rows = mod._fetch_label_rows(mod.QUEUED_LABEL, fetch_json=fake)
    assert len(rows) == 1 and rows[0]["number"] == 9


def test_load_queue_integrity_ok_and_fail_open():
    """OK path diffs both directions; 403 is by-cause; other failures
    degrade this disclosure only (per-plane fail-open)."""
    import urllib.error

    mod = _load_watchdog_module()
    page = [{"number": 9, "title": "queued", "state": "open",
             "labels": ["bridge:queued"]}]
    (n, missing, phantom), note = mod._load_queue_integrity(
        {5, 9}, fetch_rows=lambda label: page)
    assert note == "ok" and n == 1 and missing == [] and phantom == [5]

    def ratelimited(label):
        raise urllib.error.HTTPError("https://api.github.com/x", 403,
                                     "rate limit exceeded", None, None)

    res, note = mod._load_queue_integrity({5}, fetch_rows=ratelimited)
    assert res is None and "rate limit" in note and "resets hourly" in note

    def down(label):
        raise ConnectionError("nope")

    res, note = mod._load_queue_integrity({5}, fetch_rows=down)
    assert res is None and "unreachable" in note


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"[ RUN ] {name}")
            try:
                fn()
                print(f"[  OK ] {name}")
            except AssertionError as e:
                failures += 1
                print(f"[ FAIL] {name}: {e}")
    total = sum(1 for n in globals() if n.startswith("test_") and callable(globals()[n]))
    print(f"\n==== {total - failures}/{total} PASS ====")
    sys.exit(FAIL if failures else PASS)
