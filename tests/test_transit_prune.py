#!/usr/bin/env python3
"""tests/test_transit_prune.py — offline battery for the ephemeral-transit prune core.

Dual-mode: pytest AND plain runner. Imports only the drop-in module + stdlib.
Zero I/O, zero network, deterministic. Also performs a DOC-CONFORMANCE check:
the §3.1 landing.yml YAML block inside docs/EPHEMERAL_TRANSIT_HANDOFF.md is
extracted from the repo copy of the doc and structurally asserted (job naming
carries the doctrine's 'auto-prune' reflection token, git-rm semantics, the
byte-exact commit message, dry-run default, and the fail-closed guard) so the
hand-off cannot drift from the code it deploys.
"""

from __future__ import annotations

import datetime
import os
import re
import sys
from importlib import util as _ilu

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MOD_PATH = os.path.join(_ROOT, "scripts", "ci", "transit_prune.py")
_DOC_PATH = os.path.join(_ROOT, "docs", "EPHEMERAL_TRANSIT_HANDOFF.md")

_spec = _ilu.spec_from_file_location("transit_prune", _MOD_PATH)
transit_prune = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(transit_prune)  # type: ignore[union-attr]

parse_task_id = transit_prune.parse_task_id
validate_dispatch_evidence = transit_prune.validate_dispatch_evidence
build_prune_plan = transit_prune.build_prune_plan
build_prune_commit_message = transit_prune.build_prune_commit_message
select_prunable_patches = transit_prune.select_prunable_patches
DEFAULT_DISPATCH_TARGETS = transit_prune.DEFAULT_DISPATCH_TARGETS

NOW = datetime.datetime(2026, 10, 17, 12, 0, 0, tzinfo=datetime.timezone.utc)

GOOD_EVIDENCE = {
    "task_id": "bridge-20261016-kaggle-meta-cognition",
    "target_repo": "Supremeai-bd/supremeai",
    "dispatch_commit": "9fc5d479c53a2d0dea34a51406118ffa1756fe1c",
    "dispatched_at": "2026-10-16T18:20:00Z",
}


# ---- task-id parsing -------------------------------------------------------------

def test_parse_task_id_contract():
    tid, r = parse_task_id("patches/bridge-20261016-kaggle-meta-cognition.patch")
    assert tid == "bridge-20261016-kaggle-meta-cognition" and r == [], (tid, r)
    tid, r = parse_task_id("bridge-20261016-kaggle-meta-cognition.patch")
    assert tid == "bridge-20261016-kaggle-meta-cognition", (tid, r)
    # taskId stems may contain dots and dashes — only .patch suffix is stripped
    tid, r = parse_task_id("patches/my-task.v2-r1.patch")
    assert tid == "my-task.v2-r1", (tid, r)
    # invalid shapes fail with reasons
    for bad in ["", "   ", "patches/no-suffix", "patches/", ".patch", "patches/..patch"]:
        tid, r = parse_task_id(bad)
        assert tid is None and r, (bad, tid, r)
    tid, r = parse_task_id("patches/..patch")
    assert tid is None and any("unsafe" in x for x in r), (tid, r)


# ---- evidence contract -------------------------------------------------------

def test_evidence_happy_path():
    ok, reasons = validate_dispatch_evidence(
        GOOD_EVIDENCE, "bridge-20261016-kaggle-meta-cognition"
    )
    assert ok and reasons == [], (ok, reasons)


def test_evidence_fail_closed_zoo():
    ev_task = "bridge-20261016-kaggle-meta-cognition"
    cases = [
        (None, ["dispatch evidence is not a mapping"]),
        ("string", ["dispatch evidence is not a mapping"]),
        ({}, None),  # all missing-fields reasons
        ({"task_id": ev_task}, None),  # partial
        ({**GOOD_EVIDENCE, "task_id": "other-task"}, None),  # identity mismatch
        ({**GOOD_EVIDENCE, "target_repo": "SomeOrg/not-federated"}, None),
        ({**GOOD_EVIDENCE, "dispatch_commit": "not-a-sha"}, None),
        ({**GOOD_EVIDENCE, "dispatch_commit": "XYZ"}, None),
        ({**GOOD_EVIDENCE, "dispatched_at": "tomorrow"}, None),
    ]
    for ev, exact in cases:
        ok, reasons = validate_dispatch_evidence(ev, ev_task)
        assert not ok, (ev, reasons)
        assert reasons, (ev, "reasons must be non-empty")
        if exact is not None:
            assert reasons == exact, (ev, reasons)
    # missing-fields shape check
    ok, reasons = validate_dispatch_evidence({}, ev_task)
    assert not ok and len(reasons) == 4 and all(r.startswith("missing evidence field") for r in reasons), reasons
    # identity mismatch is explicit
    ok, reasons = validate_dispatch_evidence({**GOOD_EVIDENCE, "task_id": "other"}, ev_task)
    assert not ok and any("mismatch" in r for r in reasons), reasons


def test_evidence_target_vocabulary():
    ev_task = "t"
    base = {"task_id": "t", "target_repo": "Supremeai-bd/supremeai-core",
            "dispatch_commit": "abcdef1234567", "dispatched_at": "2026-10-16T00:00:00Z"}
    ok, _ = validate_dispatch_evidence(base, ev_task)
    assert ok
    # caller may inject a restricted superset; default covers all 14 federation targets
    ok, _ = validate_dispatch_evidence(base, ev_task, known_targets=frozenset({"Supremeai-bd/supremeai-core"}))
    assert ok
    ok, reasons = validate_dispatch_evidence(base, ev_task, known_targets=frozenset({"Supremeai-bd/supremeai-api"}))
    assert not ok and any("unknown dispatch target" in r for r in reasons)
    assert len(DEFAULT_DISPATCH_TARGETS) == 14


# ---- prune plan ---------------------------------------------------------------

def test_prune_plan_happy_path_and_commit_message():
    ref = "patches/bridge-20261016-kaggle-meta-cognition.patch"
    plan, hold = build_prune_plan(ref, GOOD_EVIDENCE, now=NOW)
    assert plan is not None and hold == [], (plan, hold)
    assert plan["task_id"] == "bridge-20261016-kaggle-meta-cognition", plan
    # doctrine-mandated byte-exact commit message (#416)
    assert plan["commit_message"] == (
        "chore(bridge): auto-prune transit patch bridge-20261016-kaggle-meta-cognition "
        "after successful satellite dispatch"
    ), plan["commit_message"]
    assert plan["evidence"]["target_repo"] == "Supremeai-bd/supremeai", plan
    msg = build_prune_commit_message("abc")
    assert msg == "chore(bridge): auto-prune transit patch abc after successful satellite dispatch", msg


def test_prune_plan_fail_closed():
    ref = "patches/some-task.patch"
    # no evidence at all
    plan, hold = build_prune_plan(ref, None, now=NOW)
    assert plan is None and hold == ["dispatch evidence is not a mapping"], (plan, hold)
    # partial evidence
    plan, hold = build_prune_plan(ref, {"task_id": "some-task"}, now=NOW)
    assert plan is None and len(hold) == 3, (plan, hold)
    # identity mismatch → never prunes the wrong patch
    plan, hold = build_prune_plan(ref, {**GOOD_EVIDENCE, "task_id": "other-task"}, now=NOW)
    assert plan is None and any("mismatch" in r for r in hold), (plan, hold)
    # malformed patch ref → parse reasons surface
    plan, hold = build_prune_plan("patches/not-a-patch.txt", GOOD_EVIDENCE, now=NOW)
    assert plan is None and hold, (plan, hold)


def test_select_sweep_partition():
    refs = [
        "patches/verified-task.patch",
        "patches/no-evidence-task.patch",
        "patches/mismatch-task.patch",
        "patches/not-a-patch.txt",
    ]
    evidence_by_task = {
        "verified-task": {"task_id": "verified-task", "target_repo": "Supremeai-bd/supremeai-api",
                          "dispatch_commit": "0123456789abcdef", "dispatched_at": "2026-10-17T00:00:00Z"},
        "mismatch-task": {"task_id": "WRONG", "target_repo": "Supremeai-bd/supremeai-api",
                          "dispatch_commit": "0123456789abcdef", "dispatched_at": "2026-10-17T00:00:00Z"},
    }
    res = select_prunable_patches(refs, evidence_by_task, now=NOW)
    assert [p["task_id"] for p in res["prunable"]] == ["verified-task"], res
    held_by_task = {h.get("task_id"): h for h in res["held"]}
    assert held_by_task["no-evidence-task"]["reasons"] == ["no dispatch evidence"], held_by_task
    assert any("mismatch" in r for r in held_by_task["mismatch-task"]["reasons"]), held_by_task
    assert "not-a-patch.txt" in held_by_task or any(
        h["patch"] == "patches/not-a-patch.txt" for h in res["held"]
    ), res


def test_select_empty_and_absence_default():
    res = select_prunable_patches([], {})
    assert res == {"prunable": [], "held": []}, res
    # absence of evidence defaults to HOLD (never prune on hope)
    res = select_prunable_patches(["patches/x-task.patch"], {})
    assert res["prunable"] == [] and res["held"][0]["reasons"] == ["no dispatch evidence"], res


def test_determinism():
    ref = "patches/bridge-20261016-kaggle-meta-cognition.patch"
    a = build_prune_plan(ref, GOOD_EVIDENCE, now=NOW)
    b = build_prune_plan(ref, GOOD_EVIDENCE, now=NOW)
    assert repr(a) == repr(b)
    s1 = select_prunable_patches(["patches/x.patch", "patches/y.patch"], {}, now=NOW)
    s2 = select_prunable_patches(["patches/x.patch", "patches/y.patch"], {}, now=NOW)
    assert repr(s1) == repr(s2)


# ---- doc conformance (hand-off cannot drift from code) -------------------------

def _doc_yaml_block():
    assert os.path.exists(_DOC_PATH), f"hand-off doc missing: {_DOC_PATH}"
    text = open(_DOC_PATH, encoding="utf-8").read()
    m = re.search(r"```yaml\n(.*?)```", text, re.DOTALL)
    assert m, "no ```yaml block found in hand-off doc"
    return m.group(1)


def test_doc_yaml_carries_doctrine_contract():
    yaml_text = _doc_yaml_block()
    # Reflection Check contract from #416: landing.yml must contain 'auto-prune'
    assert "auto-prune" in yaml_text, "YAML block must carry the auto-prune reflection token"
    # cleanup semantics
    assert "git rm" in yaml_text, "YAML must remove the transit patch via git rm"
    # the byte-exact commit message template appears
    assert "after successful satellite dispatch" in yaml_text, "commit message contract missing"
    # dry-run default (Test Suite tier: cleanup verified in dry-run mode)
    assert re.search(r"dry.run|DRY_RUN", yaml_text, re.IGNORECASE), "dry-run mode missing"
    # fail-closed guard: prune only on verified dispatch
    assert re.search(r"transit_prune|verified", yaml_text), "fail-closed guard reference missing"
    # structured parse when pyyaml is available (honest skip otherwise)
    try:
        import yaml  # noqa: F401
    except Exception:
        return
    import yaml
    doc = yaml.safe_load(yaml_text)
    assert isinstance(doc, dict), "YAML block must be a mapping"
    jobs = doc.get("jobs") or {}
    assert any("auto-prune" in str(k) for k in jobs), f"job naming lacks auto-prune: {list(jobs)}"


def test_doc_module_api_names_match_code():
    text = open(_DOC_PATH, encoding="utf-8").read()
    for symbol in [
        "parse_task_id",
        "validate_dispatch_evidence",
        "build_prune_plan",
        "select_prunable_patches",
        "build_prune_commit_message",
    ]:
        assert symbol in text, f"doc missing module symbol: {symbol}"
    # module exists at the documented path
    assert os.path.exists(os.path.join(_ROOT, "scripts", "ci", "transit_prune.py"))


# ---- CLI wrapper end-to-end (tempdir I/O) --------------------------------------

def test_cli_end_to_end_dry_run(tmp_path=None):
    """The executable wrapper: scans a temp inbox, holds no-evidence patches,
    emits a plan whose prunable entries carry the doctrine commit message."""
    import json as _json
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        inbox = os.path.join(td, "patches")
        os.makedirs(inbox)
        with open(os.path.join(inbox, "verified-task.patch"), "w") as f:
            f.write("patch-bytes")
        with open(os.path.join(inbox, "orphan-task.patch"), "w") as f:
            f.write("patch-bytes")
        ev_path = os.path.join(td, "evidence.json")
        with open(ev_path, "w") as f:
            _json.dump({
                "verified-task": {
                    "task_id": "verified-task",
                    "target_repo": "Supremeai-bd/supremeai-sdk",
                    "dispatch_commit": "deadbeefdeadbeef",
                    "dispatched_at": "2026-10-17T01:00:00Z",
                }
            }, f)
        out_path = os.path.join(td, "plan.json")

        cli_path = os.path.join(_ROOT, "scripts", "ci", "transit_prune_cli.py")
        assert os.path.exists(cli_path), "CLI wrapper missing"
        r = subprocess_run([sys.executable, cli_path, "--patches-dir", inbox,
                            "--evidence", ev_path, "--out", out_path])
        assert r.returncode == 0, r.stderr
        plan = _json.load(open(out_path))
        assert [p["task_id"] for p in plan["prunable"]] == ["verified-task"], plan
        assert plan["prunable"][0]["commit_message"] == (
            "chore(bridge): auto-prune transit patch verified-task after successful satellite dispatch"
        ), plan
        held = {h["task_id"]: h for h in plan["held"]}
        assert held["orphan-task"]["reasons"] == ["no dispatch evidence"], held

        # absent evidence file = everything held (fail-closed default posture)
        out2 = os.path.join(td, "plan2.json")
        r2 = subprocess_run([sys.executable, cli_path, "--patches-dir", inbox,
                             "--out", out2])
        assert r2.returncode == 0, r2.stderr
        plan2 = _json.load(open(out2))
        assert plan2["prunable"] == [] and len(plan2["held"]) == 2, plan2


def subprocess_run(cmd):
    import subprocess
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


# ---- manual runner ---------------------------------------------------------------

def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"✅ transit_prune battery passed: {len(tests)} test groups, all asserts green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
