#!/usr/bin/env python3
"""tests/test_py_dep_cve_guard.py — fail-closed behavioral suite for #1969.

Verifies the Python dependency CVE ratchet gate delivered by #1969 (R37):

  - pip-audit JSON parser: the load-bearing ingestion contract — id sets are
    the union of primary id + aliases (primary-flip immunity), duplicate
    advisory entries within one dependency (observed live: the same PYSEC id
    emitted twice) collapse, empty-vuln deps are skipped, a dependency
    missing name/version fails loudly;
  - ratchet semantics: equal ids pass, a new pair and a new advisory id
    inside a known pair are drift, resolved ids and vanished pairs are
    improvements (shrink the baseline entry in the same change);
  - routing decision tree: NEW advisory ids fail-close (exit 1); a missing
    or malformed baseline fail-closes; an unreadable manifest fail-closes;
    pip-audit absent or failing (network unreachable) skips with evidence
    and NEVER fabricates a PASS (the #1760 honest-degradation pattern);
    --files mode with an off-surface changed set is an honest skip;
  - manifest discovery: deterministic sorted walk, vendored/venv trees
    pruned;
  - inline-install blindspot scan (#2064 R43 option D, report-only): spec
    classification vocabulary (pinned / unpinned / direct / dynamic /
    local), the gateway `||` gate-defeat shape, backslash continuations,
    mixed-pin sites, quoted+extras pins, comment-line immunity, manifest
    `-r` targets, non-blocking exit semantics, unreadable-Dockerfile
    anomaly (recorded, never raised);
  - live baseline pin: on the real repo the dated floor passes --check
    (the landing state, network permitting — skipped with evidence when
    pip-audit or PyPI is unreachable), and its meta provenance is intact;
  - wiring SSOT: the guard is present in the LIVE run_all_guards.py roster
    and the LIVE .githooks/pre-push hook (never duplicated here).

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_py_dep_cve_guard.py
  - stdlib:  python3 tests/test_py_dep_cve_guard.py   (plain runner)

Network-dependent paths are hermetic: audit_manifest is monkeypatched with
fixture findings AND the pip-audit presence check (shutil.which) is pinned
to "present" (or deliberately None for the missing-binary case), so every
structural test is offline and deterministic on ANY host — the same pattern
as the guard's own --self-test and the #1913 suite. The original suite
patched only audit_manifest, so on hosts without pip-audit installed the
decision-tree cases short-circuited on the presence check and went red
(observed live: 5 failures on a bare venv, green only on runners that
carry pip-audit) — an environment-coupled suite, fixed here and in the
guard's self-test symmetrically. The single live --check probe degrades
to a skip when pip-audit/PyPI is absent.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "ci" / "py_dep_cve_guard.py"
BASELINE = "scripts/ci/py_dep_cve_baseline.json"
TAG = "[py-dep-cve-guard]"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import py_dep_cve_guard as guard


@contextmanager
def _pip_audit_present():
    """Pin the pip-audit presence check to "present" for the block.

    evaluate() short-circuits on shutil.which(PIP_AUDIT_BIN) BEFORE the
    monkeypatched audit_manifest is ever consulted, so decision-tree tests
    must pin the binary present (or None) or they implicitly depend on the
    host environment — the opposite of hermetic.
    """
    real_which = guard.shutil.which
    guard.shutil.which = (
        lambda name, _bin=guard.PIP_AUDIT_BIN, _real=real_which: (
            "/usr/local/bin/" + _bin if name == _bin else _real(name)
        )
    )
    try:
        yield
    finally:
        guard.shutil.which = real_which


def _sandbox(tmp: Path, findings: dict[str, list[str]]) -> Path:
    """Sandbox repo: two manifests + baseline of the given findings."""
    (tmp / "scripts" / "ci").mkdir(parents=True)
    (tmp / "gateway" / "services" / "x").mkdir(parents=True)
    (tmp / "gateway" / "requirements.txt").write_text("fastapi>=0.110\n", encoding="utf-8")
    (tmp / "gateway" / "services" / "x" / "requirements.txt").write_text(
        "pytest>=7.4,<9.0\n", encoding="utf-8"
    )
    (tmp / guard.BASELINE_PATH).write_text(
        json.dumps({"meta": {"issue": 1969}, "findings": findings}), encoding="utf-8"
    )
    return tmp


# --------------------------------------------------------------------------- #
# Wiring SSOT: the live roster and the live hook carry the guard               #
# --------------------------------------------------------------------------- #

def test_guard_module_reachable_and_pinned() -> None:
    assert GUARD.is_file(), f"guard script missing: {GUARD}"
    src = GUARD.read_text(encoding="utf-8")
    assert BASELINE in src, "guard must name its versioned baseline file"
    assert "shrink-only" in src, "ratchet doctrine must be stated in the guard"
    assert TAG in src, "evidence tag must stay stable for CI grepping"
    assert "pip-audit" in src, "the PyPA scanner SSOT must be explicit"


def test_guard_in_roster_and_pre_push() -> None:
    roster = (REPO_ROOT / "scripts" / "ci" / "run_all_guards.py").read_text(encoding="utf-8")
    assert "scripts/ci/py_dep_cve_guard.py" in roster, "guard missing from roster"
    hook = (REPO_ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")
    assert "py_dep_cve_guard.py" in hook, "guard missing from pre-push hook"
    assert "14. PY-DEP CVE GUARD" in hook, "pre-push section header drifted"


# --------------------------------------------------------------------------- #
# Manifest discovery (deterministic, vendored trees pruned)                    #
# --------------------------------------------------------------------------- #

def test_discovery_sorted_and_pruned() -> None:
    with tempfile.TemporaryDirectory(prefix="pydep-disc-") as td:
        root = Path(td)
        (root / "gateway").mkdir()
        (root / "gateway" / "requirements.txt").write_text("x\n", encoding="utf-8")
        (root / "core" / "client" / "supreme-node").mkdir(parents=True)
        (root / "core" / "client" / "supreme-node" / "requirements.txt").write_text(
            "x\n", encoding="utf-8"
        )
        (root / "node_modules" / "leftpad").mkdir(parents=True)
        (root / "node_modules" / "leftpad" / "requirements.txt").write_text(
            "x\n", encoding="utf-8"
        )
        (root / ".venv").mkdir()
        (root / ".venv" / "requirements.txt").write_text("x\n", encoding="utf-8")
        found = guard.discover_manifests(root)
        assert found == [
            "core/client/supreme-node/requirements.txt",
            "gateway/requirements.txt",
        ], found


# --------------------------------------------------------------------------- #
# The load-bearing pip-audit JSON parser                                       #
# --------------------------------------------------------------------------- #

def test_parser_folds_alias_union_and_dedupes() -> None:
    doc = {
        "dependencies": [
            {"name": "fastapi", "version": "0.162.0", "vulns": []},
            {"name": "pytest", "version": "8.4.2", "vulns": [
                {"id": "PYSEC-2026-1845", "aliases": [
                    "GHSA-6w46-j5rx-g56g", "CVE-2025-71176"]},
                {"id": "PYSEC-2026-1845", "aliases": [
                    "GHSA-6w46-j5rx-g56g", "CVE-2025-71176"]},
            ]},
        ],
        "fixes": [],
    }
    found = guard.parse_pip_audit_json(doc)
    assert found == {
        "pytest@8.4.2": ["CVE-2025-71176", "GHSA-6w46-j5rx-g56g", "PYSEC-2026-1845"]
    }, "aliases must fold into the id union; duplicate advisory entries collapse"


def test_parser_rejects_malformed_documents() -> None:
    try:
        guard.parse_pip_audit_json({"dependencies": [{"name": "x"}]})
        raise SystemExit("missing version must raise")
    except ValueError:
        pass
    try:
        guard.parse_pip_audit_json({"nope": True})
        raise SystemExit("missing dependencies must raise")
    except ValueError:
        pass


# --------------------------------------------------------------------------- #
# Ratchet semantics                                                            #
# --------------------------------------------------------------------------- #

def test_ratchet_equal_state_is_clean() -> None:
    baseline = {"m:a@1.0.0": ["PYSEC-1"], "m:b@2.0.0": ["PYSEC-2", "PYSEC-3"]}
    drift, improvements = guard.compare(dict(baseline), baseline)
    assert not drift and not improvements


def test_ratchet_new_pair_and_new_id_are_drift() -> None:
    baseline = {"m:a@1.0.0": ["PYSEC-1"]}
    drift, _ = guard.compare({"m:c@3.0.0": ["PYSEC-9"]}, baseline)
    assert drift and drift[0]["kind"] == "new-pair" and drift[0]["ids"] == ["PYSEC-9"]
    drift, _ = guard.compare({"m:a@1.0.0": ["PYSEC-1", "PYSEC-new"]}, baseline)
    assert drift and drift[0]["kind"] == "new-id" and drift[0]["ids"] == ["PYSEC-new"]


def test_ratchet_resolved_ids_are_improvements() -> None:
    baseline = {"m:a@1.0.0": ["PYSEC-1", "PYSEC-gone"], "m:b@2.0.0": ["PYSEC-2"]}
    drift, improvements = guard.compare({"m:a@1.0.0": ["PYSEC-1"]}, baseline)
    assert not drift
    assert improvements and improvements[0]["resolved_ids"] == ["PYSEC-gone"]
    drift, improvements = guard.compare(
        {"m:a@1.0.0": ["PYSEC-1"]}, {"m:a@1.0.0": ["PYSEC-1"], "m:b@2.0.0": ["PYSEC-2"]}
    )
    assert not drift
    assert any(i["pair"] == "m:b@2.0.0" for i in improvements), "vanished pair is a shrink hint"


# --------------------------------------------------------------------------- #
# Decision tree (hermetic: audit_manifest monkeypatched)                       #
# --------------------------------------------------------------------------- #

def test_decision_tree_new_advisory_fail_closes() -> None:
    with tempfile.TemporaryDirectory(prefix="pydep-tree-") as td:
        root = _sandbox(Path(td), {"gateway/services/x/requirements.txt:pytest@8.4.2": ["PYSEC-old"]})
        saved = guard.audit_manifest
        guard.audit_manifest = lambda p: {
            "pytest@8.4.2": ["PYSEC-old"],
            "fastapi@0.162.0": ["PYSEC-fresh"],
        }
        try:
            with _pip_audit_present():
                code, drift, _imp, _notes = guard.evaluate(root)
            assert code == guard.EXIT_DRIFT, "new advisory pair must fail-close"
            assert drift[0]["pair"] == "gateway/requirements.txt:fastapi@0.162.0"
            assert drift[0]["kind"] == "new-pair"
        finally:
            guard.audit_manifest = saved


def test_decision_tree_pip_audit_failure_skips_with_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="pydep-skip-") as td:
        root = _sandbox(Path(td), {"gateway/services/x/requirements.txt:pytest@8.4.2": ["PYSEC-old"]})
        saved = guard.audit_manifest

        def _boom(p):
            raise RuntimeError("PyPI unreachable (simulated)")

        guard.audit_manifest = _boom
        try:
            with _pip_audit_present():
                code, drift, _imp, notes = guard.evaluate(root)
            assert code == guard.EXIT_PASS and not drift
            assert any("pip-audit unreachable" in n for n in notes), notes
        finally:
            guard.audit_manifest = saved


def test_decision_tree_pip_audit_missing_skips_with_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="pydep-nobin-") as td:
        root = _sandbox(Path(td), {"gateway/services/x/requirements.txt:pytest@8.4.2": ["PYSEC-old"]})
        real_which = guard.shutil.which
        guard.shutil.which = lambda name: None
        try:
            code, drift, _imp, notes = guard.evaluate(root)
            assert code == guard.EXIT_PASS and not drift
            assert any("pip-audit not installed" in n for n in notes), notes
        finally:
            guard.shutil.which = real_which


def test_decision_tree_unreadable_manifest_fail_closes() -> None:
    with tempfile.TemporaryDirectory(prefix="pydep-read-") as td:
        root = _sandbox(Path(td), {"gateway/services/x/requirements.txt:pytest@8.4.2": ["PYSEC-old"]})
        (root / "gateway" / "requirements.txt").chmod(0)
        try:
            with _pip_audit_present():
                code, drift, _imp, _notes = guard.evaluate(root)
            assert code == guard.EXIT_DRIFT and drift[0]["kind"] == "unreadable-manifest"
        finally:
            (root / "gateway" / "requirements.txt").chmod(0o644)


def test_decision_tree_malformed_baseline_fail_closes() -> None:
    with tempfile.TemporaryDirectory(prefix="pydep-base-") as td:
        root = _sandbox(Path(td), {"gateway/services/x/requirements.txt:pytest@8.4.2": ["PYSEC-old"]})
        (root / guard.BASELINE_PATH).write_text("{not json", encoding="utf-8")
        with _pip_audit_present():
            code, drift, _imp, _notes = guard.evaluate(root)
        assert code == guard.EXIT_DRIFT and drift[0]["ids"] == ["BASELINE"]


def test_files_mode_off_surface_is_honest_skip() -> None:
    with tempfile.TemporaryDirectory(prefix="pydep-off-") as td:
        root = _sandbox(Path(td), {"gateway/services/x/requirements.txt:pytest@8.4.2": ["PYSEC-old"]})
        saved = guard.audit_manifest
        guard.audit_manifest = lambda p: {"pytest@8.4.2": ["PYSEC-old"]}
        try:
            code, _drift, _imp, notes = guard.evaluate(root, files=["README.md", "core/x.py"])
            assert code == guard.EXIT_PASS
            assert any("nothing to check" in n for n in notes), notes
        finally:
            guard.audit_manifest = saved


# --------------------------------------------------------------------------- #
# Inline-install blindspot scan (#2064 R43 option D — report-only plane)        #
# --------------------------------------------------------------------------- #

def test_spec_classification_vocabulary() -> None:
    assert guard._classify_spec("torch==2.4.1") == "pinned"
    assert guard._classify_spec('"uvicorn[standard]==0.34.0"') == "pinned"
    assert guard._classify_spec("wheel") == "unpinned"
    assert guard._classify_spec("nats-py") == "unpinned"
    assert guard._classify_spec("git+https://x/y.git") == "direct"
    assert guard._classify_spec("https://x/y.whl") == "direct"
    assert guard._classify_spec("${PIP_EXTRAS}") == "dynamic"
    assert guard._classify_spec("./local") == "local"


def test_parser_gateway_fallback_and_gate_defeat() -> None:
    gw = guard.parse_pip_install_sites(
        "FROM python:3.11-slim\n"
        "# RUN pip install commented-out must not parse\n"
        "RUN pip install --no-cache-dir -r requirements.txt || "
        "pip install --no-cache-dir fastapi uvicorn httpx pydantic pyyaml\n"
    )
    assert len(gw) == 2, gw
    assert gw[0]["class"] == "manifest-backed" and gw[0]["manifest_refs"]
    assert gw[0]["gate_defeat_shape"] is True, "first branch sits on a || line"
    assert gw[1]["class"] == "inline-unpinned"
    assert [sp["spec"] for sp in gw[1]["specs"]] == [
        "fastapi", "uvicorn", "httpx", "pydantic", "pyyaml"]
    assert gw[1]["gate_defeat_shape"] is True


def test_parser_continuations_mixed_and_quoted_pins() -> None:
    swarm = guard.parse_pip_install_sites(
        "RUN pip install --upgrade pip && \\\n"
        "    pip install --no-cache-dir nats-py pydantic litellm langchain\n"
    )
    assert len(swarm) == 2, swarm
    assert all(s["class"] == "inline-unpinned" for s in swarm)
    ci = guard.parse_pip_install_sites(
        "RUN pip install --no-cache-dir setuptools==68.0.0 wheel\n"
    )
    assert len(ci) == 1 and ci[0]["class"] == "inline-mixed", ci
    assert [sp["class"] for sp in ci[0]["specs"]] == ["pinned", "unpinned"]
    eco = guard.parse_pip_install_sites(
        'RUN pip install --no-cache-dir fastapi==0.115.6 '
        '"uvicorn[standard]==0.34.0"\n'
    )
    assert len(eco) == 1 and eco[0]["class"] == "inline-pinned", eco


def test_scan_report_only_semantics() -> None:
    with tempfile.TemporaryDirectory(prefix="pydep-df-scan-") as td:
        root = Path(td)
        (root / "gateway").mkdir()
        (root / "gateway" / "Dockerfile").write_text(
            "RUN pip install -r requirements.txt || pip install fastapi uvicorn\n",
            encoding="utf-8",
        )
        (root / "core" / "docker").mkdir(parents=True)
        (root / "core" / "docker" / "swarm-worker.Dockerfile").write_text(
            "RUN pip install --upgrade pip && \\\n"
            "    pip install --no-cache-dir nats-py pydantic litellm langchain\n",
            encoding="utf-8",
        )
        (root / "node_modules" / "x").mkdir(parents=True)
        (root / "node_modules" / "x" / "Dockerfile").write_text(
            "RUN pip install nodejunk\n", encoding="utf-8")
        doc = guard.scan_inline_pip_installs(root)
        assert doc["dockerfiles_scanned"] == 2, doc["dockerfiles_scanned"]
        assert doc["summary"]["pip_install_sites"] == 4, doc["summary"]
        assert doc["summary"]["manifest_backed_sites"] == 1
        assert doc["summary"]["inline_unpinned_sites"] == 3
        assert doc["summary"]["gate_defeat_sites"] == 2
        blind = {(s["file"], s["line"]) for s in doc["sites"]
                 if s["class"] == "inline-unpinned"}
        assert blind == {("gateway/Dockerfile", 1),
                         ("core/docker/swarm-worker.Dockerfile", 1)}, blind
        (root / "gateway" / "Dockerfile").chmod(0)
        try:
            doc2 = guard.scan_inline_pip_installs(root)
            assert doc2["anomalies"] and doc2["anomalies"][0]["kind"] == "unreadable"
            assert doc2["dockerfiles_scanned"] == 2
        finally:
            (root / "gateway" / "Dockerfile").chmod(0o644)


def test_dockerfile_scan_mode_is_non_blocking() -> None:
    probe = subprocess.run(
        [sys.executable, str(GUARD), "--dockerfile-scan", "--json"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, check=False,
    )
    assert probe.returncode == guard.EXIT_PASS, (
        f"report-only scan must never block\n{probe.stdout[:800]}\n{probe.stderr[:800]}"
    )
    doc = json.loads(probe.stdout)
    assert doc["dockerfiles_scanned"] >= 1, "the live repo carries dockerfiles"
    assert "contract_note" in doc and "report-only" in doc["contract_note"]


# --------------------------------------------------------------------------- #
# Live baseline pin (landing state; honest-skip when pip-audit is absent)      #
# --------------------------------------------------------------------------- #

def test_live_baseline_provenance() -> None:
    bl = REPO_ROOT / BASELINE
    assert bl.is_file(), "the versioned baseline must be committed"
    data = json.loads(bl.read_text(encoding="utf-8"))
    meta = data["meta"]
    assert "pip-audit" in str(meta.get("tool", "")), "baseline must record the pip-audit SSOT"
    assert meta.get("doctrine", "").startswith("shrink-only"), "ratchet doctrine required"
    assert meta.get("issue") == 1969
    assert isinstance(data["findings"], dict) and data["findings"], "floor records live truth"
    for pair, ids in data["findings"].items():
        assert ":" in pair and "@" in pair, f"pair key must be manifest:name@version: {pair}"
        assert ids, f"ids must be advisory ids: {pair}"


def test_live_check_passes_at_landing_head() -> None:
    probe = subprocess.run(
        [sys.executable, str(GUARD), "--check"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=1200, check=False,
    )
    combined = (probe.stdout or "") + (probe.stderr or "")
    if "skipped with evidence" in combined:
        print("SKIP(with evidence): pip-audit/PyPI unreachable — honest degradation honored")
        return
    assert probe.returncode == guard.EXIT_PASS, (
        f"live --check must pass at the landing head\n{combined[:2000]}"
    )


def test_guard_self_test_suite_passes() -> None:
    r = subprocess.run(
        [sys.executable, str(GUARD), "--self-test"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, check=False,
    )
    assert r.returncode == 0, f"guard --self-test failed:\n{r.stdout}\n{r.stderr}"


# --------------------------------------------------------------------------- #
# stdlib plain runner (no pytest required)                                     #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS | {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL | {fn.__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} tests passed")
    sys.exit(1 if failed else 0)
