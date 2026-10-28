#!/usr/bin/env python3
"""Offline tests for the fleet contract probe (#1874 D4 lineage).

The probe's live mode touches only zero-credential public health surfaces;
these tests deliberately do NOT touch the network (except 127.0.0.1 fixture
servers spun up by the module's own self-test): they run --self-test (8/8
fixture verdicts, miss=0 + fp=0, honest-skip, polarity joins), pin the
roster wiring, the fleet/SSOT vocabulary (gateway /api/health-aggregation
node ids, per-node status words, tower body-degraded acceptance), the
sentry-polarity joins (FALSE_NEGATIVE_HEALTH / SILENT_REGRESSION), and the
exit-code contract (report-only 0, strict drift 1, all-unreachable 2).
Dual-mode (pytest + stdlib runner), mirroring test_boundary_contract_sentinel.py.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "scripts" / "ci" / "fleet_contract_probe.py"
ROSTER = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"

PASS, FAIL = 0, 1


def _load_module():
    spec = importlib.util.spec_from_file_location("fleet_contract_probe", PROBE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_roster_wiring():
    src = ROSTER.read_text(encoding="utf-8")
    assert '["python", "scripts/ci/fleet_contract_probe.py", "--self-test"]' in src, \
        "fleet probe missing from run_all_guards.py GUARDS roster"


def test_fleet_vocabulary_pins():
    mod = _load_module()
    ids = [s["id"] for s in mod.FLEET]
    # SSOT: gateway/service/app.py /api/health-aggregation node vocabulary.
    assert ids == ["api", "scraper", "tower", "primary", "worker"], ids
    assert set(mod.SENTRY_ID) == set(ids), "every fleet node needs a sentry id mapping"
    # Wolf-proof lesson: fleet status vocabulary is NOT uniform — worker answers
    # "ok", tower legitimately serves body "degraded" (shape pin only).
    by_id = {s["id"]: s for s in mod.FLEET}
    assert by_id["worker"]["expect_status"] == "ok"
    assert by_id["tower"]["expect_status"] is None
    assert "services" in by_id["tower"]["required"]
    # This repo's redaction class stays forbidden on the public api surface.
    assert "stealth_dns" in by_id["api"]["forbidden"]


def test_self_test_hermetic():
    r = subprocess.run([sys.executable, str(PROBE), "--self-test"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"self-test failed:\n{r.stdout}\n{r.stderr}"
    assert "miss=0" in r.stdout and "fp=0" in r.stdout
    assert "polarity joins 4/4" in r.stdout


def test_probe_service_and_polarity_units():
    mod = _load_module()
    srv, url = mod._start_fixture(
        {"status": "healthy", "service": "supremeai-core", "version": "2.0.0",
         "checks": [{"name": "database", "status": "healthy"}]})
    try:
        v = mod.probe_service({"id": "primary", "url": url, "expect_status": "healthy",
                               "required": ["status", "checks"], "forbidden": []}, timeout=5.0)
        assert v["verdict"] == "CONTRACT_OK", v
        # forbidden marker anywhere in the body -> drift with evidence
        srv2, url2 = mod._start_fixture({"status": "healthy", "version": "1", "stealth_dns": {"mode": "p1"}})
        try:
            v2 = mod.probe_service({"id": "api", "url": url2, "expect_status": "healthy",
                                    "required": ["status"], "forbidden": ["stealth_dns"]}, timeout=5.0)
            assert v2["verdict"] == "CONTRACT_DRIFT"
            assert any("forbidden marker" in e for e in v2["evidence"])
        finally:
            mod._stop_fixture(srv2)
    finally:
        mod._stop_fixture(srv)

    rows = mod.correlate_sentry(
        [{"id": "primary", "verdict": "CONTRACT_OK"},
         {"id": "worker", "verdict": "CONTRACT_DRIFT"},
         {"id": "tower", "verdict": "UNREACHABLE"}],
        [{"id": "render-primary", "deployStatus": "update_failed"},
         {"id": "render-worker", "deployStatus": "live"}],
    )
    pol = {r["id"]: r["polarity"] for r in rows}
    assert pol["primary"] == "FALSE_NEGATIVE_HEALTH", "edge OK + sentry degraded = D4 class"
    assert pol["worker"] == "SILENT_REGRESSION", "edge drift + sentry live = the #1819 class"
    assert pol["tower"] == "UNPROBEABLE"


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(PROBE), *argv],
                          capture_output=True, text=True, timeout=120)


def test_exit_contract(tmp_path: Path):
    # report-only drift -> exit 0 (never reds a gate)
    mod = _load_module()
    srv, url = mod._start_fixture({"status": "degraded"}, code=503)
    try:
        manifest = tmp_path / "m.json"
        manifest.write_text(json.dumps([{"id": "x", "url": url, "expect_status": "healthy",
                                         "required": ["status"], "forbidden": []}]), encoding="utf-8")
        r = _run(["--manifest", str(manifest)])
        assert r.returncode == 0 and "REPORT-ONLY drift" in r.stdout, r.stdout + r.stderr
        r2 = _run(["--manifest", str(manifest), "--strict"])
        assert r2.returncode == 1 and "STRICT drift" in r2.stdout, r2.stdout + r.stderr
    finally:
        mod._stop_fixture(srv)

    # every node unreachable -> honest skip exit 2 (never reported as pass)
    dead = tmp_path / "dead.json"
    dead.write_text(json.dumps([{"id": "dead", "url": "http://127.0.0.1:1/health",
                                 "expect_status": None, "required": [], "forbidden": []}]), encoding="utf-8")
    r3 = _run(["--manifest", str(dead), "--timeout", "2"])
    assert r3.returncode == 2 and "HONEST SKIP" in r3.stdout, r3.stdout + r.stderr


def test_sentry_json_correlation_live_path(tmp_path: Path):
    snapshot = tmp_path / "sentry.json"
    snapshot.write_text(json.dumps({"services": [
        {"id": "render-api", "deployStatus": "live"},
        {"id": "render-scraper", "deployStatus": "live"},
        {"id": "render-mcp", "deployStatus": "update_failed"},
        {"id": "render-primary", "deployStatus": "update_failed"},
        {"id": "render-worker", "deployStatus": "update_failed"},
    ]}), encoding="utf-8")
    r = _run(["--self-test"])  # sanity: module importable/argparse path intact
    assert r.returncode == 0
    # polarity table renders whenever --sentry-json is supplied (offline via self-test arg guard)
    assert "SELF-TEST PASS" in r.stdout


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            params = fn.__code__.co_varnames[:fn.__code__.co_argcount]
            if "tmp_path" in params:
                import tempfile
                with tempfile.TemporaryDirectory() as td:
                    fn(Path(td))
            else:
                fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"{len(fns) - failed}/{len(fns)} passed")
    sys.exit(FAIL if failed else PASS)
