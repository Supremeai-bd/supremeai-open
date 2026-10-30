#!/usr/bin/env python3
"""Offline tests for the open→core sync staleness watchdog (#2756 guard).

#2756's RCA proved the observability gap: the open→core sync stalled for
~3 days (core main last moved 2026-10-27T16:53:58Z; fix PR #2724 merged on
open 2026-10-29T18:51:37Z stayed absent from core; the render pair stayed
update_failed frozen since 10-24) while every receipt in the #2225/#2597/
#2738 family read ONE plane and concluded from it. This guard is the
mechanical detector those tests pin:

  - the verdict decision core (same-SHA short-circuit, core-newer direction,
    catching-up window, the >= threshold boundary, the live #2756 shape);
  - the honest-skip paths (unreadable heads, unparseable dates → INCONCLUSIVE,
    never a false green — #1760 doctrine) and the 0/1/2 exit-code contract;
  - the Tower push-run fallback extraction (newest event=push run on the
    branch wins; schedule runs and foreign branches never answer the
    push-recency question — observed live 2026-10-30 where schedule runs sat
    on top of the list at a stale SHA while the true head was a newer push);
  - the REST commit payload normalization (missing date/SHA rejected);
  - the roster wiring (run_all_guards.py) — wiring must not outrun the tree.

Zero network. Dual-mode (pytest + stdlib runner), mirroring
test_bridge_intake_gate_watchdog.py.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = REPO_ROOT / "scripts" / "ci" / "open_core_sync_staleness_watchdog.py"
ROSTER = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"

PASS = 0
FAIL = 1


def _load_watchdog_module():
    spec = importlib.util.spec_from_file_location("open_core_sync_staleness_watchdog", WATCHDOG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _h(sha: str, date: str):
    return {"sha": sha, "date": date}


NOW = datetime(2026, 10, 30, 14, 32, 0, tzinfo=timezone.utc)
TH = 48.0


def _cases(mod) -> list[tuple[str, bool, str]]:
    evaluate = mod.evaluate
    parse_utc = mod.parse_utc
    cases: list[tuple[str, bool, str]] = []

    # --- verdict decision core -------------------------------------------------
    v, _ = evaluate(_h("a" * 40, "2026-10-01T00:00:00Z"),
                    _h("a" * 40, "2026-10-01T00:00:00Z"), NOW, TH)
    cases.append(("same-SHA short-circuit is HEALTHY even when old",
                  v == mod.VERDICT_HEALTHY, v))

    v, _ = evaluate(_h("b" * 40, "2026-10-28T00:00:00Z"),
                    _h("c" * 40, "2026-10-29T00:00:00Z"), NOW, TH)
    cases.append(("core-newer-than-open is HEALTHY (nothing pending)",
                  v == mod.VERDICT_HEALTHY, v))

    v, _ = evaluate(_h("d" * 40, "2026-10-30T14:20:00Z"),
                    _h("e" * 40, "2026-10-30T13:00:00Z"), NOW, TH)
    cases.append(("open ahead + young core head is CATCHING_UP",
                  v == mod.VERDICT_CATCHING_UP, v))

    # The live #2756 shape: core head 2026-10-27T16:53:58Z, open ahead,
    # now 2026-10-30T14:32Z → core head age ≈ 69.6h ≥ 48h → stalled.
    v, rows = evaluate(_h("f" * 40, "2026-10-30T14:30:00Z"),
                       _h("0" * 40, "2026-10-27T16:53:58Z"), NOW, TH)
    cases.append(("live #2756 shape (core head ~70h old, open ahead) is SYNC_STALLED",
                  v == mod.VERDICT_STALLED, v))
    cases.append(("stalled verdict carries the no-redeploy warning",
                  any("Do NOT redeploy render" in r for r in rows), "; ".join(rows)))

    v, _ = evaluate(_h("1" * 40, "2026-10-30T14:30:00Z"),
                    _h("2" * 40, "2026-10-28T14:30:00Z"), NOW, TH)
    cases.append(("exactly-at-threshold core head counts as stalled (>=)",
                  v == mod.VERDICT_STALLED, v))

    v, _ = evaluate(_h("3" * 40, "2026-10-30T14:30:00Z"),
                    _h("4" * 40, "2026-10-28T15:30:00Z"), NOW, TH)
    cases.append(("core head 1h under threshold is CATCHING_UP",
                  v == mod.VERDICT_CATCHING_UP, v))

    # --- honest-skip paths ------------------------------------------------------
    v, _ = evaluate(None, _h("5" * 40, "2026-10-28T00:00:00Z"), NOW, TH)
    cases.append(("unreadable open head is INCONCLUSIVE",
                  v == mod.VERDICT_INCONCLUSIVE, v))

    v, _ = evaluate(_h("6" * 40, "2026-10-28T00:00:00Z"), None, NOW, TH)
    cases.append(("unreadable core head is INCONCLUSIVE",
                  v == mod.VERDICT_INCONCLUSIVE, v))

    v, _ = evaluate(_h("7" * 40, "not-a-date"),
                    _h("8" * 40, "2026-10-28T00:00:00Z"), NOW, TH)
    cases.append(("unparseable open date is INCONCLUSIVE",
                  v == mod.VERDICT_INCONCLUSIVE, v))

    ok = (parse_utc("2026-10-30T14:30:00Z") is not None
          and parse_utc("2026-10-30T14:30:00+00:00") is not None
          and parse_utc("garbage") is None)
    cases.append(("parse_utc accepts Z/offset, rejects garbage", ok, str(ok)))

    ok = (mod.EXIT_OK == 0 and mod.EXIT_FINDING == 1 and mod.EXIT_SKIP == 2)
    cases.append(("exit-code contract 0/1/2 pinned", ok,
                  str((mod.EXIT_OK, mod.EXIT_FINDING, mod.EXIT_SKIP))))

    # --- tower push-run fallback extraction --------------------------------------
    runs = [
        {"event": "schedule", "head_branch": "main", "head_sha": "a1",
         "created_at": "2026-10-30T08:09:25Z"},
        {"event": "push", "head_branch": "main", "head_sha": "b2",
         "created_at": "2026-10-30T14:32:19Z"},
        {"event": "push", "head_branch": "feature-x", "head_sha": "c3",
         "created_at": "2026-10-30T15:00:00Z"},
    ]
    head = mod._head_from_tower_push_runs(runs, "main")
    ok = head is not None and head["sha"] == "b2" and head["date"] == "2026-10-30T14:32:19Z"
    cases.append(("tower fallback picks newest push run on the branch", ok, str(head)))

    ok = mod._head_from_tower_push_runs([r for r in runs if r["event"] != "push"], "main") is None
    cases.append(("tower fallback returns None with no push runs", ok, "non-None"))

    ok = mod._head_from_tower_push_runs(
        [{"event": "push", "head_branch": "main", "head_sha": "", "created_at": "2026-10-30T14:32:19Z"}],
        "main") is None
    cases.append(("push run without SHA is skipped (honest)", ok, "accepted"))

    # --- REST commit payload normalization ---------------------------------------
    ok = (mod._head_from_commit_payload(
        {"sha": "d4", "commit": {"committer": {"date": "2026-10-30T14:00:00Z"}}}) or {}).get("sha") == "d4"
    cases.append(("commit payload normalizer keeps a valid head", ok, "mangled"))

    ok = mod._head_from_commit_payload({"sha": "d4"}) is None
    cases.append(("commit payload without date is rejected", ok, "accepted"))

    ok = mod._head_from_commit_payload({}) is None
    cases.append(("empty commit payload is rejected", ok, "accepted"))

    return cases


def _roster_wired() -> tuple[bool, str]:
    try:
        text = ROSTER.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"roster unreadable: {exc}"
    needle = "scripts/ci/open_core_sync_staleness_watchdog.py"
    if needle not in text:
        return False, f"roster missing {needle}"
    if not WATCHDOG.exists():
        return False, "guard script missing from tree"
    return True, "roster wired and guard present"


def main() -> int:
    mod = _load_watchdog_module()
    cases = _cases(mod)
    ok, detail = _roster_wired()
    cases.append(("roster wiring (run_all_guards.py) pinned", ok, detail))

    failed = [(n, got) for n, ok2, got in cases if not ok2]
    for name, ok2, got in cases:
        print(f"  [{'PASS' if ok2 else 'FAIL'}] {name}" + ("" if ok2 else f" — {got}"))
    print(f"\n==== {len(cases) - len(failed)}/{len(cases)} test cases PASS ====")
    return FAIL if failed else PASS


def _pytest_entry():
    """Pytest surface: each case becomes one assert in one test function."""
    mod = _load_watchdog_module()
    cases = _cases(mod)
    ok, detail = _roster_wired()
    cases.append(("roster wiring (run_all_guards.py) pinned", ok, detail))
    for name, ok2, got in cases:
        assert ok2, f"{name} — got {got}"
    # guard self-test subprocess must also pass
    r = subprocess.run([sys.executable, str(WATCHDOG), "--self-test"],
                       capture_output=True, text=True, timeout=120, check=False)
    assert r.returncode == 0, f"guard --self-test failed: {r.stdout[-500:]} {r.stderr[-200:]}"


test_watchdog_cases = _pytest_entry


if __name__ == "__main__":
    sys.exit(main())
