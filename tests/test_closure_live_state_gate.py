#!/usr/bin/env python3
"""Offline tests for the closure-time live-state gate (#2925 Option A).

The measured failure class (2026-10-29 23:18:17Z): #2225 was closed
`completed` a second time 65 minutes after the boundary template fix
(#2886) landed, while the #2738 recovery criterion was mechanically FAILED
on both named services — the proof plane (#2897) and the witness plane
(C49 #2916) recorded the violation in real time, but no mechanism consumed
either plane at the closing act. The gate pins the mechanical contract:

  - criterion evaluation (status planes + evidence-substring plane — the
    `update_failed`-behind-HTTP-200 signature must FAIL even when the
    coarse status reads healthy);
  - fail-closed verification (a declared provider/resource absent from the
    live snapshot is a refusal, never an implicit pass);
  - platform-audit label scoping (fix-lane closures stay un-gated);
  - verdict routing (NO_CRITERION report-only vs --strict; UNREACHABLE is
    an honest skip, exit 2, never a fake pass — #1760 doctrine);
  - malformed criteria are rejected loudly, not silently accepted;
  - roster wiring (run_all_guards.py).

Zero network. Dual-mode (pytest + stdlib runner), mirroring
test_bridge_intake_gate_watchdog.py.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE = REPO_ROOT / "scripts" / "ci" / "closure_live_state_gate.py"
ROSTER = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"

PASS = 0
FAIL = 1


def _load_gate_module():
    spec = importlib.util.spec_from_file_location("closure_live_state_gate",
                                                  GATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mod():
    global _CACHED
    try:
        return _CACHED
    except NameError:
        _CACHED = _load_gate_module()
        return _CACHED


CRIT_OK = {
    "version": 1,
    "declaredBy": "#2738",
    "services": [
        {"resourceId": "render/render-primary", "allowedStatuses": ["healthy"]},
        {"resourceId": "render/render-worker", "allowedStatuses": ["healthy"]},
    ],
    "sweepProviders": [
        {"provider": "render-primary", "allowedStatuses": ["healthy"],
         "evidenceForbiddenSubstrings": ["update_failed"]},
    ],
}
RES_OK = {"render/render-primary": "healthy",
          "render/render-worker": "healthy"}
SWEEP_OK = {"render-primary": {
    "status": "healthy",
    "evidence": {"kind": "provider_response",
                 "summary": "Container running latest build"}}}
SWEEP_FALSE_OK = {"render-primary": {
    "status": "healthy",
    "evidence": {"kind": "provider_response",
                 "summary": "Container running previous build, but latest "
                            "deployment update_failed"}}}


def test_roster_wiring():
    src = ROSTER.read_text(encoding="utf-8")
    assert ('["python", "scripts/ci/closure_live_state_gate.py", "--self-test"]'
            in src), "gate missing from run_all_guards.py GUARDS roster"


def test_contract_pins():
    mod = _mod()
    # Zero-credential Tower surface, not api.github.com (anonymous 60/h cap,
    # CONTRIBUTING §11 trap).
    assert mod.DEFAULT_TOWER_URL.startswith(
        "https://supremeai-mcp-tower.onrender.com")
    # The #2925 scope note: platform-audit scoping keeps fix-lane closures
    # un-gated — pin the default scope set.
    assert mod.DEFAULT_AUDIT_LABELS == ("audit:finding",)


def test_evaluate_pass_and_fail_matrix():
    mod = _mod()
    # 1 — recovered platform: PASS
    ev = mod.evaluate_criterion(CRIT_OK, RES_OK, SWEEP_OK)
    assert ev["verdict"] == "PASS" and ev["failedCount"] == 0
    # 2 — degraded resource plane: FAIL
    ev = mod.evaluate_criterion(CRIT_OK,
                                {**RES_OK, "render/render-worker": "degraded"},
                                SWEEP_OK)
    assert ev["verdict"] == "FAIL" and ev["failedCount"] == 1
    # 3 — the exact #2225 signature: healthy coarse status, forbidden
    #     substring inside live evidence — must FAIL
    ev = mod.evaluate_criterion(CRIT_OK, RES_OK, SWEEP_FALSE_OK)
    assert ev["verdict"] == "FAIL"
    assert "update_failed" in json.dumps(ev["checks"])
    # 4/5 — fail-closed: declared resource / provider absent from snapshot
    ev = mod.evaluate_criterion(CRIT_OK,
                                {"render/render-primary": "healthy"}, SWEEP_OK)
    assert ev["verdict"] == "FAIL"
    assert any("absent from live snapshot" in c["reason"]
               for c in ev["checks"])
    ev = mod.evaluate_criterion(CRIT_OK, RES_OK, {})
    assert ev["verdict"] == "FAIL"


def test_unregistered_resource_echo_cannot_rescue():
    # Live-grounded (2026-10-30): tower resource_status answers
    # {"status": "healthy"} even for a BOGUS resource id. The gate marks
    # unregistered resources from resource_list; the pleasant echo must
    # never convert an unverifiable predicate into a PASS (that conversion
    # is the false-close hole this gate exists to close).
    mod = _mod()
    ev = mod.evaluate_criterion(
        {"version": 1, "services": [
            {"resourceId": "render/definitely-not-a-resource",
             "allowedStatuses": ["healthy"]}]},
        {"render/definitely-not-a-resource": mod.UNREGISTERED}, {})
    assert ev["verdict"] == "FAIL"
    assert any("not in tower resource inventory" in c["reason"]
               for c in ev["checks"])


def test_scope_applies_platform_audit_only():
    mod = _mod()
    assert mod.scope_applies(["audit:finding", "P1-major"],
                             list(mod.DEFAULT_AUDIT_LABELS)) is True
    assert mod.scope_applies(["status:unclaimed"],
                             list(mod.DEFAULT_AUDIT_LABELS)) is False
    # Case-insensitive, whitespace-tolerant label join.
    assert mod.scope_applies([" Audit:Finding "], ["audit:finding"]) is True


def test_route_verdict_matrix():
    mod = _mod()
    labels = ["audit:finding"]
    # NO_CRITERION report-only (default): loud note, exit 0.
    verdict, code, note = mod.route_verdict(
        labels, list(mod.DEFAULT_AUDIT_LABELS), None, False, strict=False)
    assert (verdict, code) == ("NO_CRITERION", 0)
    assert "manual" in note or "criterion" in note
    # NO_CRITERION strict: refused.
    verdict, code, _ = mod.route_verdict(
        labels, list(mod.DEFAULT_AUDIT_LABELS), None, False, strict=True)
    assert (verdict, code) == ("NO_CRITERION", 1)
    # NOT_APPLICABLE: fix-lane subject, gate off.
    verdict, code, note = mod.route_verdict(
        ["status:unclaimed"], list(mod.DEFAULT_AUDIT_LABELS), None, False)
    assert (verdict, code) == ("NOT_APPLICABLE", 0)
    # UNREACHABLE: honest skip regardless of scope, exit 2, never a pass.
    for lab in (labels, ["status:unclaimed"], []):
        verdict, code, _ = mod.route_verdict(
            lab, list(mod.DEFAULT_AUDIT_LABELS), None, True)
        assert (verdict, code) == ("UNREACHABLE", 2), (lab, verdict, code)


def test_malformed_criterion_rejected():
    mod = _mod()
    for bad in ({"version": 2}, {}, {"services": [{}]},
                {"version": 1, "services": [{"nope": 1}]},
                {"version": 1, "sweepProviders": [{"nope": 1}]}):
        raised = False
        try:
            mod.evaluate_criterion(bad, RES_OK, SWEEP_OK)
        except ValueError:
            raised = True
        assert raised, f"malformed criterion accepted: {bad}"


def test_forbidden_substring_case_insensitive():
    mod = _mod()
    sweep = {"render-primary": {
        "status": "healthy",
        "evidence": {"summary": "Latest deployment UPDATE_FAILED"}}}
    ev = mod.evaluate_criterion(
        {"version": 1, "sweepProviders": [
            {"provider": "render-primary", "allowedStatuses": ["healthy"],
             "evidenceForbiddenSubstrings": ["update_failed"]}]},
        {}, sweep)
    assert ev["verdict"] == "FAIL"


def test_self_test_roster_mode():
    proc = subprocess.run(
        [sys.executable, str(GATE), "--self-test"],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "self-test" in proc.stdout and "passed" in proc.stdout


def test_render_surface_fail_is_loud():
    # Hermetic: a FAIL evidence document must print the refusal banner on
    # stderr with the full evidence JSON attached (#2704 shape, applied to
    # the closing act) — captured via swap of sys streams, zero network.
    mod = _mod()
    evidence = {
        "gate": "closure_live_state_gate", "subject": 2225,
        "verdict": "FAIL", "exitCode": 1,
        "note": mod.REFUSAL_BANNER,
        "evaluation": {"verdict": "FAIL", "failedCount": 1,
                       "checks": [{"predicate": "render/render-worker",
                                   "verdict": "FAIL",
                                   "reason": "status 'update_failed' not in "
                                             "allowedStatuses ['healthy']",
                                   "status": "update_failed"}]},
    }
    import io
    out, err = io.StringIO(), io.StringIO()
    stdout, stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        mod.render_surface(evidence)
    finally:
        sys.stdout, sys.stderr = stdout, stderr
    assert "verdict=FAIL" in out.getvalue()
    assert "CLOSING ARTIFACT REFUSED" in err.getvalue()
    assert "render/render-worker" in err.getvalue(), \
        "refusal must attach the per-predicate criterion output"


def test_live_gate_honest_skip_or_verdict():
    # Live integration smoke (zero-credential): in an offline sandbox the
    # tower is unreachable -> exit 2 honest skip; when the tower answers,
    # the gate must land on a real verdict (0/1) — never a silent pass that
    # claims evaluation without a live plane.
    proc = subprocess.run(
        [sys.executable, str(GATE), "--subject", "2225",
         "--criterion-json", json.dumps(
             {"version": 1, "services": [
                 {"resourceId": "render/render-primary",
                  "allowedStatuses": ["healthy"]}]})],
        capture_output=True, text=True, timeout=300,
    )
    combined = (proc.stdout + proc.stderr).lower()
    assert "closure-live-state-gate" in combined
    if proc.returncode == 2:
        assert "unreachable" in combined, \
            "exit 2 must print the honest-skip note"
    else:
        assert proc.returncode in (0, 1), \
            f"unexpected exit code {proc.returncode}: {combined[:300]}"
        assert f"verdict=" in proc.stdout


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
    total = sum(1 for n in globals()
                if n.startswith("test_") and callable(globals()[n]))
    print(f"\n==== {total - failures}/{total} PASS ====")
    sys.exit(FAIL if failures else PASS)
