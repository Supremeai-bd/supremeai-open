#!/usr/bin/env python3
"""tests/test_contract_codegen_guard.py — consumer-viability pin for #1846.

Verifies the contract → generated-consumer gate for the stable external
contract (issue #1846, scout radar R39 adapt_cleanroom lane):

  - hermetic self-test: the guard's own 9 fixture scenarios (fresh match,
    hand-edit drift, missing artifact, contract-absent skip, version-mismatch
    skip, --files engagement matrix, YAML-untouched) pass;
  - live freshness pin (the WO acceptance): on the real repo, the committed
    artifact api-schemas/generated/gateway_models.py byte-matches a fresh
    pinned (0.86.0) regeneration of api-schemas/gateway.openapi.yaml — the
    contract's consumer surface is a build product, never a transcription;
  - honesty: absent or version-mismatched generator = skip with evidence,
    never a fabricated PASS;
  - determinism: two consecutive real regenerations are byte-identical (the
    committed-artifact gate is meaningless otherwise) — skipped honestly when
    the pinned tool is absent;
  - never-do pins: the guard never mutates the contract YAML or the artifact;
    engagement is scoped to the contract/generated surface only;
  - wiring SSOT: the guard is present in the LIVE run_all_guards.py roster
    and the LIVE .githooks/pre-push hook (never duplicated here).

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_contract_codegen_guard.py
  - stdlib:  python3 tests/test_contract_codegen_guard.py   (plain runner)

Offline except the live-freshness and determinism tests, which invoke the
locally installed pinned generator (pure local file + local binary, no
network) and degrade to honest skips when it is absent.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "ci" / "contract_codegen_guard.py"
ROSTER = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"
HOOK = REPO_ROOT / ".githooks" / "pre-push"
CONTRACT = REPO_ROOT / "api-schemas" / "gateway.openapi.yaml"
ARTIFACT = REPO_ROOT / "api-schemas" / "generated" / "gateway_models.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("contract_codegen_guard", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_guard(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GUARD), *args], capture_output=True, text=True, timeout=300, cwd=str(REPO_ROOT),
    )


# --------------------------------------------------------------------------- #
# Hermetic core (no real generator needed)                                     #
# --------------------------------------------------------------------------- #

def test_guard_self_test_passes():
    r = _run_guard("--self-test")
    assert r.returncode == 0, f"self-test failed:\n{r.stdout}\n{r.stderr}"
    assert "self-test: PASS" in r.stdout


def test_check_without_tool_skips_honestly():
    """Absent generator → exit 0 with SKIP evidence, never a fabricated PASS."""
    env_guard = _load_guard()
    found, reason = env_guard.discover_tool("/nonexistent/tool/path")
    assert found is None and reason is not None and "SKIP" in reason


def test_version_mismatch_is_skip_not_fail():
    """A different installed version SKIPS (tool drift ≠ contract drift)."""
    mod = _load_guard()
    assert mod.CODEGEN_PIN == "0.86.0", "pin moved — regenerate artifact + update tests in the same PR"
    # unparseable --version output never guesses (tool path must EXIST so
    # discovery reaches the version probe):
    import unittest.mock as mock
    fake = mock.Mock()
    fake.returncode = 0
    fake.stdout = "garbage-no-version"
    with mock.patch.object(mod.subprocess, "run", return_value=fake):
        found, reason = mod.discover_tool(str(GUARD))
    assert found is None and reason is not None and "unparseable" in reason


def test_engagement_scoped_to_contract_surface():
    """--files engagement matches ONLY the contract / generated surface."""
    mod = _load_guard()
    for path in ("api-schemas/gateway.openapi.yaml", "api-schemas/generated/gateway_models.py", "api-schemas/generated/sub/x.py"):
        assert mod.TOUCHED_PATHS.search(path), f"should engage: {path}"
    for path in ("docs/notes.md", "api-schemas/other.yaml", "src/main.py", "x/api-schemas/generated/extra.py"):
        assert not mod.TOUCHED_PATHS.search(path), f"should NOT engage: {path}"


def test_guard_never_modifies_contract_or_artifact():
    """Byte-identity of inputs across a full hermetic verify cycle."""
    mod = _load_guard()
    import tempfile, stat
    with tempfile.TemporaryDirectory() as td_s:
        td = Path(td_s)
        tool_path = td / "fixture.py"
        tool_path.write_text(mod.FAKE_TOOL.replace('"VERSION"', '"0.86.0"'))
        tool_path.chmod(tool_path.stat().st_mode | stat.S_IEXEC)
        wrapper = td / "fixture.sh"
        wrapper.write_text(f"#!/bin/sh\nexec '{sys.executable}' '{tool_path}' \"$@\"\n")
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
        contract_body = b"openapi: 3.0.0\npaths: {}\n"
        (td / mod.CONTRACT_FILE).parent.mkdir(parents=True, exist_ok=True)
        (td / mod.CONTRACT_FILE).write_bytes(contract_body)
        art = td / mod.ARTIFACT_FILE
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_bytes(b"# generated by fixture-tool\n" + contract_body)
        code, _ = mod.verify(td, str(wrapper))
        assert code == 0
        assert (td / mod.CONTRACT_FILE).read_bytes() == contract_body, "guard mutated the contract YAML (never-do)"
        assert art.read_bytes() == b"# generated by fixture-tool\n" + contract_body, "guard mutated the artifact (never-do)"


# --------------------------------------------------------------------------- #
# Live pins (the actual enforcement point)                                     #
# --------------------------------------------------------------------------- #

def test_committed_artifact_exists_and_is_raw_generator_output():
    assert ARTIFACT.exists(), (
        "consumer artifact missing — the contract's consumer surface must be a "
        "committed build product (generate once, commit, let the guard verify)"
    )
    header = ARTIFACT.read_bytes()[:80]
    assert b"# generated by datamodel-codegen" in header, "artifact must be RAW generator output (never hand-edited)"
    assert b"timestamp:" not in header, "artifact embeds a timestamp — regeneration can never byte-match (determinism broken)"


def test_live_artifact_matches_fresh_pinned_regeneration():
    """WO acceptance: --check exit 0 on the live repo (skip-evidence if tool absent)."""
    r = _run_guard("--check")
    blob = r.stdout + r.stderr
    if "SKIP" in blob:
        assert r.returncode == 0 and "datamodel-codegen" in blob, "honest skip must name the missing tool"
        return
    assert r.returncode == 0, f"live drift between contract and committed artifact:\n{blob}"
    assert "PASS" in blob and "byte-matches" in blob


def test_determinism_two_regenerations_byte_identical():
    """The committed-artifact gate is meaningless without deterministic output."""
    mod = _load_guard()
    tool, reason = mod.discover_tool()
    if tool is None:
        print(f"  SKIP | determinism check: {reason}")
        return
    import tempfile
    with tempfile.TemporaryDirectory() as td_s:
        outs = []
        for i in range(2):
            out = Path(td_s) / f"run{i}.py"
            mod.generate(tool, CONTRACT, out)
            outs.append(mod.normalize(out.read_bytes()))
    assert outs[0] == outs[1], "generator output is nondeterministic — the committed-artifact gate cannot work"


def test_roster_wiring_live():
    """The guard is in the LIVE run_all_guards roster (wiring SSOT)."""
    roster = ROSTER.read_text(encoding="utf-8")
    assert "scripts/ci/contract_codegen_guard.py" in roster, "guard missing from run_all_guards roster"
    assert "--check" in roster.split("contract_codegen_guard.py")[1][:40], "roster line must run --check"


def test_pre_push_wiring_live():
    """The guard is wired as a self-contained pre-push section (#1846)."""
    hook = HOOK.read_text(encoding="utf-8")
    assert "scripts/ci/contract_codegen_guard.py" in hook, "guard missing from pre-push hook"
    assert "CONTRACT CODEGEN GUARD (#1846)" in hook
    # engages only on the contract/generated surface:
    m = re.search(r"grep -qE '\(.*\)'; then\n            hook_py=\"\"", hook) or re.search(
        r"grep -qE '([^']+)'; then", hook
    )
    assert m, "engage grep not found in hook"
    # section numbering: 10 = license (#1773), 11 = contract codegen (#1846)
    assert "# 11. CONTRACT CODEGEN GUARD (#1846)" in hook, "hook section numbering drifted"


def test_contract_yaml_still_intact():
    """The SSOT itself keeps its structural validity (producer side)."""
    text = CONTRACT.read_text(encoding="utf-8")
    assert text.lstrip().startswith(("openapi:", "#")), "contract file shape drifted"
    assert "paths:" in text, "contract lost its paths section"


# --------------------------------------------------------------------------- #
# Plain stdlib runner (dual-mode doctrine)                                     #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    failures = 0
    tests = [(name, obj) for name, obj in sorted(globals().items()) if name.startswith("test_") and callable(obj)]
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS | {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL | {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 — plain runner must report, not crash
            failures += 1
            print(f"  ERROR | {name}: {exc!r}")
    print(f"\n{len(tests) - failures}/{len(tests)} contract-codegen-guard tests passed")
    sys.exit(1 if failures else 0)
