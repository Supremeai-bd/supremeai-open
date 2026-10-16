#!/usr/bin/env python3
"""tests/test_smart_context_selector.py — suite for scripts/agents/smart_context_selector.py (#329).

Dual-mode by design (zero-dependency doctrine, AGENT_RULES.md §13):
  - pytest:  pytest tests/test_smart_context_selector.py -v
  - stdlib:  python3 tests/test_smart_context_selector.py   (plain runner, no pytest import)

Every test is offline and deterministic. Coverage mirrors the issue #329
acceptance criteria: Layer 1-8 ranked priority token pruning, token boundary
truncation, fail-closed validation, schema conformance of the wire payload
(against the REAL api-schemas/context-assembly.schema.json via the repo's own
stdlib validator), and the continuous_agent_loop env-gated wiring (byte-compat
when disabled, deterministic digest when enabled).
"""
from __future__ import annotations

import io
import json
import os
import sys
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO / "scripts" / "agents"
for p in (str(AGENTS_DIR), str(REPO / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from smart_context_selector import (  # noqa: E402
    CONTEXT_KINDS,
    LAYER_NAMES,
    AssemblyError,
    Candidate,
    CandidateError,
    PolicyError,
    assemble_context,
    build_selection_policy,
    check_invariants,
    estimate_tokens,
    layer_priority,
    render_context_assembly,
)


@contextmanager
def _env(**overrides):
    """Temporarily set/unset env vars (stdlib-mode friendly, no pytest fixture)."""
    saved = {k: os.environ.get(k) for k in overrides}
    try:
        for key, value in overrides.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def cand(kind: str, label: str, tokens: int, ref: dict | None = None) -> Candidate:
    return Candidate(kind, label, tokens, ref)


AT = "2026-10-16T00:00:00Z"  # fixed clock for byte-deterministic payloads


# --- policy (SelectionPolicy) --------------------------------------------------

def test_decay_math_i3():
    """priority(L) = round(base · decay^(L-1), 3) — spec §3 worked example."""
    policy = build_selection_policy(6000, 1.0, 0.8)
    expected = {1: 1.0, 2: 0.8, 3: 0.64, 4: 0.512, 5: 0.41, 6: 0.328, 7: 0.262, 8: 0.21}
    for layer, want in expected.items():
        assert layer_priority(policy, layer) == want, f"layer {layer}"
    assert layer_priority(build_selection_policy(6000, 1.0, 1.0), 8) == 1.0


def test_policy_fail_closed():
    for kwargs in (
        {"token_budget": 0},
        {"token_budget": -1},
        {"token_budget": 1000001},
        {"token_budget": 10, "base_priority": 1.01},
        {"token_budget": 10, "base_priority": -0.01},
        {"token_budget": 10, "decay_factor": 0},
        {"token_budget": 10, "decay_factor": 1.01},
        {"token_budget": 10, "strategy": "greedy_knapsack"},
    ):
        try:
            build_selection_policy(**kwargs)
            raise AssertionError(f"policy accepted {kwargs}")
        except PolicyError:
            pass


# --- candidates: closed enums, kind↔layer pins, path safety (spec §8) ----------

def test_candidate_fail_closed():
    cases = [
        lambda: cand("not-a-kind", "x", 5),                            # closed kind enum
        lambda: cand("file-scope", "x", 5),                            # missing required ref
        lambda: cand("adjacent-test", "x", 5, {"memory": {}}),         # wrong pin shape
        lambda: cand("memory-ref", "x", 5, {"path": "a.py"}),          # wrong pin key
        lambda: cand("adr-ref", "x", 5, {"adr_id": "ADR-12"}),         # id pattern
        lambda: cand("adr-ref", "x", 5),                               # missing adr ref
        lambda: cand("constitution-doc", "x", 5, {"path": "a.md"}),    # stray pin (§8)
        lambda: cand("issue-contract", "", 5),                         # empty label
        lambda: cand("issue-contract", "x" * 257, 5),                  # label > 256
        lambda: cand("issue-contract", "x", 0),                        # tokens < 1
        lambda: cand("issue-contract", "x", 100001),                   # tokens > 100000
        lambda: cand("file-scope", "x", 5, {"path": "../etc/passwd"}),  # traversal
        lambda: cand("file-scope", "x", 5, {"path": "/absolute"}),     # absolute
        lambda: cand("file-scope", "x", 5, {"path": "a/../../b"}),     # inner traversal
    ]
    for builder in cases:
        try:
            builder()
            raise AssertionError(f"candidate accepted: {builder}")
        except CandidateError:
            pass


def test_candidate_kind_layer_mapping_i6():
    """A kind filed under the wrong layer is structurally rejected (I-6)."""
    try:
        assemble_context(
            "t", build_selection_policy(50),
            {3: [cand("issue-contract", "misfiled", 5)]},  # issue-contract is L2
            generated_at=AT,
        )
        raise AssertionError("misfiled kind accepted")
    except CandidateError:
        pass


# --- token boundary truncation (issue acceptance criterion 2) -------------------

def test_boundary_exact_fit_includes_everything():
    policy = build_selection_policy(30, 1.0, 0.5)
    payload = assemble_context(
        "t", policy,
        {
            1: [cand("constitution-doc", "AGENTS.md", 10)],
            2: [cand("issue-contract", "contract", 10)],
            3: [cand("file-scope", "x.py", 10, {"path": "x.py"})],
        },
        generated_at=AT,
    )
    a = payload["assembly"]
    assert a["tokens_used"] == 30 and a["budget_clipped"] is False and a["clipped_layers"] == []
    assert all(it["included"] for l in a["layers"] for it in l["items"])


def test_boundary_one_over_clips_and_no_backfill():
    """R1: the first non-fitting item marks the clip point; a later tiny item
    stays excluded even though it would fit in the leftover budget."""
    policy = build_selection_policy(30, 1.0, 0.5)
    payload = assemble_context(
        "t", policy,
        {
            1: [cand("constitution-doc", "AGENTS.md", 10)],
            3: [cand("file-scope", "big.py", 21, {"path": "big.py"})],   # needs 21, 20 left
            4: [cand("memory-ref", "tiny", 1, {"memory": {"namespace": "n", "document_id": "d"}})],
        },
        generated_at=AT,
    )
    a = payload["assembly"]
    assert a["tokens_used"] == 10
    assert a["budget_clipped"] is True and a["clipped_layers"] == [3, 4]
    verdicts = {it["label"]: (it["included"], it["inclusion_reason"])
                for l in a["layers"] for it in l["items"]}
    assert verdicts["big.py"] == (False, "budget_clipped")
    assert verdicts["tiny"] == (False, "budget_clipped"), "backfill forbidden by R1"


def test_boundary_budget_exactly_admits_l1():
    """R2 edge: budget == L1 total ⇒ L1 fully included, everything else clipped."""
    policy = build_selection_policy(15, 1.0, 0.8)
    payload = assemble_context(
        "t", policy,
        {
            1: [cand("constitution-doc", "AGENTS.md", 10),
                cand("constitution-doc", "AGENT_RULES.md", 5)],
            2: [cand("issue-contract", "contract", 5)],
        },
        generated_at=AT,
    )
    a = payload["assembly"]
    assert a["tokens_used"] == 15 and a["clipped_layers"] == [2]
    l1_items = a["layers"][0]["items"]
    assert all(it["inclusion_reason"] == "constitution_never_clipped" for it in l1_items)


def test_constitution_never_clipped_but_impossible_budget_fails_loud():
    try:
        assemble_context(
            "t", build_selection_policy(9, 1.0, 0.8),
            {1: [cand("constitution-doc", "AGENTS.md", 10)]},
            generated_at=AT,
        )
        raise AssertionError("budget smaller than L1 must raise (R2 fail-loud)")
    except AssemblyError:
        pass


# --- verdicts, accounting, invariants -------------------------------------------

def test_verdict_pairs_r4():
    payload = assemble_context(
        "t", build_selection_policy(50, 1.0, 0.8),
        {
            1: [cand("constitution-doc", "AGENTS.md", 10)],
            2: [cand("issue-contract", "body", 50)],
        },
        generated_at=AT,
    )
    for l in payload["assembly"]["layers"]:
        for it in l["items"]:
            assert isinstance(it["included"], bool)
            assert it["inclusion_reason"] in ("priority_rank", "constitution_never_clipped", "budget_clipped")
            assert it["included"] == (it["inclusion_reason"] != "budget_clipped")


def test_accounting_i1_i2_and_r3_bidirectional():
    policy = build_selection_policy(20, 1.0, 0.5)
    payload = assemble_context(
        "t", policy,
        {
            1: [cand("constitution-doc", "AGENTS.md", 10)],
            2: [cand("issue-contract", "fits exactly", 10)],
            3: [cand("file-scope", "x.py", 1, {"path": "x.py"})],
        },
        generated_at=AT,
    )
    a = payload["assembly"]
    assert a["tokens_used"] == sum(l["tokens"] for l in a["layers"]) == 20
    assert a["tokens_used"] <= policy["token_budget"]
    assert a["budget_clipped"] is True and a["clipped_layers"] == [3]
    assert check_invariants(payload) == []


def test_unclipped_payload_has_no_clip_state():
    payload = assemble_context(
        "t", build_selection_policy(100, 1.0, 0.8),
        {1: [cand("constitution-doc", "AGENTS.md", 10)]},
        generated_at=AT,
    )
    a = payload["assembly"]
    assert a["budget_clipped"] is False and a["clipped_layers"] == []  # R3 ⇐ direction
    assert check_invariants(payload) == []


def test_check_invariants_flags_corruption():
    payload = assemble_context(
        "t", build_selection_policy(50, 1.0, 0.8),
        {1: [cand("constitution-doc", "AGENTS.md", 10)],
         2: [cand("issue-contract", "b", 5)]},
        generated_at=AT,
    )
    corrupted = json.loads(json.dumps(payload))
    corrupted["assembly"]["tokens_used"] = 999  # break I-1/I-2
    violations = check_invariants(corrupted)
    assert any("I-1" in v for v in violations) and any("I-2" in v for v in violations)


# --- wire payload: schema conformance against the REAL contract ------------------

def test_payload_schema_conformance_real_contract():
    from validate_schemas import SchemaValidator  # repo stdlib validator, zero new deps

    schema_path = REPO / "api-schemas" / "context-assembly.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = SchemaValidator(schema)
    payload = assemble_context(
        "task-329",
        build_selection_policy(6000, 1.0, 0.8),
        {
            1: [cand("constitution-doc", "AGENTS.md — core constitution", 600),
                cand("constitution-doc", "AGENT_RULES.md — behavior rules", 300)],
            2: [cand("issue-contract", "Issue #329 — mission, acceptance criteria", 450)],
            3: [cand("file-scope", "scripts/agents/continuous_agent_loop.py", 700,
                     {"path": "scripts/agents/continuous_agent_loop.py"}),
                cand("adjacent-test", "tests/test_smart_context_selector.py", 500,
                     {"path": "tests/test_smart_context_selector.py"})],
            4: [cand("memory-ref", "Prior episode: strict-cutoff invariant gap", 700,
                     {"memory": {"namespace": "agent-episodes", "document_id": "ep-9f8e7d6c5a4b"}})],
            5: [cand("adr-ref", "ADR-001 — open foundation boundary", 600,
                     {"adr_id": "ADR-001"})],
            6: [cand("knowledge-doc", "docs/CONTEXT_SELECTOR_SPEC.md", 800)],
        },
        generated_at="2026-10-16T05:10:00Z",
    )
    errs = validator.validate(payload)
    assert errs == [], f"schema violations: {errs[:5]}"
    assert check_invariants(payload) == []
    # structural conventions from the sample payload: non-pinned kinds carry {}
    for l in payload["assembly"]["layers"]:
        for it in l["items"]:
            if it["kind"] in ("constitution-doc", "issue-contract", "knowledge-doc"):
                assert it.get("ref") == {}


# --- determinism -----------------------------------------------------------------

def test_determinism_payload_and_digest():
    def build():
        return assemble_context(
            "task-329", build_selection_policy(32000, 1.0, 0.8),
            {
                1: [cand("constitution-doc", "AGENTS.md — core constitution", 2492)],
                6: [cand("knowledge-doc", "docs/AGENT_LOOP_SPEC.md", 1244)],
            },
            generated_at=AT,
        )
    p1, p2 = build(), build()
    assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)
    assert render_context_assembly(p1) == render_context_assembly(p2)
    digest = render_context_assembly(p1)
    assert "generated_at" not in digest, "digest must be clock-free (loop tier-7 determinism)"
    assert digest.startswith("### 🧠 Assembled Context")
    assert p1["assembly"]["assembly_id"].startswith("asm-") and len(p1["assembly"]["assembly_id"]) == 16


def test_estimate_tokens_honest_and_stable():
    assert estimate_tokens("") == 1 and estimate_tokens("   \n\t ") == 1
    assert estimate_tokens("one two three") == 3
    assert estimate_tokens("a b") == estimate_tokens("a\tb") == estimate_tokens("a\nb")
    big = "word " * 1000
    assert estimate_tokens(big) == 1000


# --- continuous_agent_loop wiring (#329): env-gated, byte-compat, fail-open ------

def _loop_module():
    import continuous_agent_loop as loop  # script-mode import via AGENTS_DIR
    return loop


_ADHOC_TASK = {
    "id": "adhoc",
    "title": "Autonomous Contribution Task",
    "body": "Implement smallest safe change adhering to AGENTS.md contracts.",
    "state": "ADHOC",
    "labels": [],
}


def _contract():
    return _loop_module().build_task_contract("task-adhoc", group="agent-orchestration")


def test_loop_disabled_is_byte_compat():
    loop = _loop_module()
    with _env(SUPREME_CONTEXT_SELECTOR=None):
        prompt = loop.build_agent_prompt(_ADHOC_TASK, "coder", _contract())
    assert "Assembled Context" not in prompt
    assert prompt.endswith("Satisfy the 3-Tier Verification Contract before handoff.\n")


def test_loop_enabled_appends_deterministic_digest():
    loop = _loop_module()
    with _env(SUPREME_CONTEXT_SELECTOR=None):
        base = loop.build_agent_prompt(_ADHOC_TASK, "coder", _contract())
    with _env(SUPREME_CONTEXT_SELECTOR="1"):
        out = io.StringIO()
        with redirect_stderr(out):
            one = loop.build_agent_prompt(_ADHOC_TASK, "coder", _contract())
            two = loop.build_agent_prompt(_ADHOC_TASK, "coder", _contract())
    assert one == two, "enabled runs must be byte-deterministic"
    assert one.startswith(base), "digest is a pure append to the legacy prompt"
    assert "Assembled Context" in one and "Budget " in one
    assert "- [L1 " in one and "constitution" in one
    # stdout purity: the selector logged to stderr only (#63 envelope contract)
    stdout_probe = io.StringIO()
    with _env(SUPREME_CONTEXT_SELECTOR="1"), redirect_stderr(out), redirect_stdout(stdout_probe):
        loop.build_agent_prompt(_ADHOC_TASK, "coder", _contract())
    assert stdout_probe.getvalue() == "", "selector must never write to stdout"
    assert "Smart Context Selector" in out.getvalue()


def test_loop_enabled_clips_honestly_with_tight_budget():
    loop = _loop_module()
    with _env(SUPREME_CONTEXT_SELECTOR="1", SUPREME_CONTEXT_BUDGET="100"):
        out = io.StringIO()
        with redirect_stderr(out):
            prompt = loop.build_agent_prompt(_ADHOC_TASK, "coder", _contract())
    # constitution (~6k estimated) can never fit a 100-token budget: R2 fail-loud
    # inside the selector surfaces as the loop's fail-open contract → digest
    # omitted, prompt unchanged, warning on stderr.
    assert "Assembled Context" not in prompt
    assert "fail-open" in out.getvalue()


def test_loop_env_gate_truthiness():
    loop = _loop_module()
    for value in ("1", "true", "ON", "Yes"):
        with _env(SUPREME_CONTEXT_SELECTOR=value):
            assert loop.context_selector_enabled() is True, value
    for value in ("", "0", "off", "maybe"):
        with _env(SUPREME_CONTEXT_SELECTOR=value):
            assert loop.context_selector_enabled() is False, value


def test_loop_envelope_disabled_matches_legacy_bytes():
    """End-to-end: with the gate off, --task-envelope output must be exactly the
    pre-#329 envelope (byte-compat parity contract, AGENT_LOOP_SPEC.md §4b)."""
    loop = _loop_module()
    import argparse

    args = argparse.Namespace(
        issue=None, allow_adhoc=True, group=None, task_type="IMPLEMENT",
        priority="P2", touching_files=None, role=None,
        task_envelope=True, emit_prompt=False, emit_contract=False,
    )
    out = io.StringIO()
    with _env(SUPREME_CONTEXT_SELECTOR=None), redirect_stdout(out):
        assert loop.emit_task_envelope(args) == 0
    envelope = json.loads(out.getvalue())["task_envelope"]
    assert "Assembled Context" not in envelope["specialist_prompt"]
    assert envelope["envelope_version"] == 1


# --- stdlib plain runner ----------------------------------------------------------

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS | {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL | {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 — honest failure reporting
            failed += 1
            print(f"  ERROR | {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"{len(fns) - failed}/{len(fns)} tests passed")
    sys.exit(1 if failed else 0)
