#!/usr/bin/env python3
"""tests/test_smart_context_selector.py — suite for scripts/agents/smart_context_selector.py (#329).

Dual-mode by design (zero-dependency doctrine, AGENT_RULES.md §13):
  - pytest:  pytest tests/test_smart_context_selector.py
  - stdlib:  python3 tests/test_smart_context_selector.py   (plain runner)

Every test is offline and deterministic. Coverage maps to issue #329's
acceptance criteria: Layer 1-8 ranked priority token pruning (engine),
token boundary truncation (boundary tests), loop injection into task
instructions (envelope/prompt wiring), plus the fail-closed vocabulary,
the spec §7 semantic invariants, and (when jsonschema is available) Draft
2020-12 validation of emitted payloads against
api-schemas/context-assembly.schema.json.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "agents"))

from smart_context_selector import (  # noqa: E402
    ADR_ID_RE,
    CandidateError,
    ConstitutionBudgetError,
    ContextSelectorError,
    DEFAULT_DECAY_FACTOR,
    DEFAULT_TOKEN_BUDGET,
    KIND_TO_LAYER,
    LAYER_NAMES,
    PolicyError,
    REASON_CLIPPED,
    REASON_CONSTITUTION,
    REASON_PRIORITY_RANK,
    assemble,
    build_context_assembly,
    estimate_tokens,
    harvest_candidates,
    layer_priority,
    normalize_candidate,
)

import continuous_agent_loop as loop  # noqa: E402

try:
    import jsonschema

    HAVE_JSONSCHEMA = True
except ImportError:  # honest skip — the engine itself is zero-dependency
    HAVE_JSONSCHEMA = False


def _verdicts(payload: dict) -> dict[str, tuple[bool, str]]:
    return {
        item["label"]: (item["included"], item["inclusion_reason"])
        for layer in payload["assembly"]["layers"]
        for item in layer["items"]
    }


# ---------------------------------------------------------------- engine ---

def test_decay_worked_example() -> None:
    """Spec §3: base 1.0, decay 0.8 -> the exact published priority table."""
    expected = [1.0, 0.8, 0.64, 0.512, 0.41, 0.328, 0.262, 0.21]
    for layer, want in enumerate(expected, start=1):
        assert layer_priority(layer, 1.0, 0.8) == want, f"L{layer}"


def test_policy_fail_closed() -> None:
    ok = [{"kind": "issue-contract", "label": "x", "tokens": 1}]
    for kwargs in (
        {"token_budget": 0},
        {"token_budget": True},
        {"token_budget": "6000"},
        {"base_priority": 1.5},
        {"base_priority": -0.1},
        {"decay_factor": 0},
        {"decay_factor": 1.5},
    ):
        try:
            assemble(ok, task_id="t", **kwargs)
        except PolicyError:
            continue
        raise AssertionError(f"policy {kwargs} did not fail closed")


def test_strict_cutoff_no_backfill() -> None:
    """R1: after the clip point, EVERY later item is excluded (no backfill)."""
    cands = [
        {"kind": "constitution-doc", "label": "A", "tokens": 100},
        {"kind": "issue-contract", "label": "B", "tokens": 50},
        {"kind": "file-scope", "label": "C", "tokens": 40, "ref": {"path": "src/c.py"}},
        {"kind": "knowledge-doc", "label": "D", "tokens": 10, "ref": {"path": "docs/d.md"}},
    ]
    v = _verdicts(assemble(cands, token_budget=185, task_id="t"))
    assert v["C"] == (False, REASON_CLIPPED)  # remaining 35 < 40 -> clip point
    assert v["D"] == (False, REASON_CLIPPED)  # would fit alone; still excluded
    v2 = _verdicts(assemble(cands, token_budget=190, task_id="t"))
    assert v2["C"] == (True, REASON_PRIORITY_RANK)  # exact fit boundary
    assert v2["D"] == (False, REASON_CLIPPED)


def test_token_boundary_truncation() -> None:
    """Acceptance criterion 2: exact-fit in, off-by-one out."""
    cands = [
        {"kind": "constitution-doc", "label": "A", "tokens": 10},
        {"kind": "issue-contract", "label": "B", "tokens": 5},
    ]
    assert _verdicts(assemble(cands, token_budget=15, task_id="t"))["B"][0] is True
    assert _verdicts(assemble(cands, token_budget=14, task_id="t"))["B"][0] is False


def test_constitution_never_clipped() -> None:
    """R2: Layer-1 is included even when nothing else fits."""
    cands = [
        {"kind": "constitution-doc", "label": "A", "tokens": 100},
        {"kind": "issue-contract", "label": "B", "tokens": 30},
    ]
    v = _verdicts(assemble(cands, token_budget=100, task_id="t"))
    assert v["A"] == (True, REASON_CONSTITUTION)
    assert v["B"] == (False, REASON_CLIPPED)


def test_constitution_overflow_fails_loud() -> None:
    """R2: budget must admit the constitution — assembler fails loud."""
    try:
        assemble(
            [{"kind": "constitution-doc", "label": "A", "tokens": 101}],
            token_budget=100,
            task_id="t",
        )
    except ConstitutionBudgetError:
        return
    raise AssertionError("constitution overflow did not fail loud")


def test_clipping_state_bidirectional() -> None:
    """R3: budget_clipped == true iff clipped_layers non-empty (both ways)."""
    clipped = assemble(
        [
            {"kind": "constitution-doc", "label": "A", "tokens": 10},
            {"kind": "issue-contract", "label": "B", "tokens": 999},
        ],
        token_budget=100,
        task_id="t",
    )["assembly"]
    assert clipped["budget_clipped"] is True and clipped["clipped_layers"] == [2]
    clean = assemble(
        [{"kind": "constitution-doc", "label": "A", "tokens": 10}],
        token_budget=100,
        task_id="t",
    )["assembly"]
    assert clean["budget_clipped"] is False and clean["clipped_layers"] == []


def test_verdict_reason_pairing() -> None:
    """R4: every verdict carries a legal, honest reason."""
    payload = assemble(
        [
            {"kind": "constitution-doc", "label": "A", "tokens": 10},
            {"kind": "issue-contract", "label": "B", "tokens": 999},
        ],
        token_budget=100,
        task_id="t",
    )
    for layer in payload["assembly"]["layers"]:
        for item in layer["items"]:
            reason = item["inclusion_reason"]
            assert reason in (REASON_PRIORITY_RANK, REASON_CONSTITUTION, REASON_CLIPPED)
            if reason == REASON_CLIPPED:
                assert item["included"] is False
            else:
                assert item["included"] is True
            if item["kind"] == "constitution-doc":
                assert reason == REASON_CONSTITUTION


def test_invariants_tokens_used() -> None:
    """I-1: tokens_used == Σ layer.tokens == Σ included item tokens; I-2: ≤ budget."""
    cands = [
        {"kind": "constitution-doc", "label": "A", "tokens": 100},
        {"kind": "issue-contract", "label": "B", "tokens": 50},
        {"kind": "file-scope", "label": "C", "tokens": 40, "ref": {"path": "src/c.py"}},
        {"kind": "transcript", "label": "noise", "tokens": 900},
    ]
    payload = assemble(cands, token_budget=200, task_id="t")
    asm = payload["assembly"]
    assert asm["tokens_used"] == sum(l["tokens"] for l in asm["layers"])
    assert asm["tokens_used"] == sum(
        i["tokens"] for l in asm["layers"] for i in l["items"] if i["included"]
    )
    assert asm["tokens_used"] <= payload["selection"]["token_budget"]


def test_layer_name_pins_and_i6_mapping() -> None:
    cands = [
        {"kind": "constitution-doc", "label": "A", "tokens": 100},
        {"kind": "file-scope", "label": "C", "tokens": 40, "ref": {"path": "src/c.py"}},
        {"kind": "memory-ref", "label": "M", "tokens": 20,
         "ref": {"memory": {"namespace": "agent-episodes", "document_id": "ep-1"}}},
        {"kind": "adr-ref", "label": "adr", "tokens": 30, "ref": {"adr_id": "ADR-001"}},
        {"kind": "knowledge-doc", "label": "K", "tokens": 25, "ref": {"path": "docs/k.md"}},
        {"kind": "runtime-state", "label": "CI", "tokens": 900},
    ]
    payload = assemble(cands, token_budget=150, task_id="t")
    for layer in payload["assembly"]["layers"]:
        assert layer["name"] == LAYER_NAMES[layer["layer"]]
        assert layer["priority"] == layer_priority(layer["layer"], 1.0, DEFAULT_DECAY_FACTOR)
        for item in layer["items"]:
            assert KIND_TO_LAYER[item["kind"]] == layer["layer"]
    # only layers with candidates appear; here L1/L3/L4/L5/L6/L7
    assert [l["layer"] for l in payload["assembly"]["layers"]] == [1, 3, 4, 5, 6, 7]


def test_ordering_priority_desc_layer_asc_label_asc() -> None:
    """I-4 global order: priority DESC, layer ASC, label ASC; included prefix."""
    cands = [
        {"kind": "transcript", "label": "z", "tokens": 500},
        {"kind": "knowledge-doc", "label": "b", "tokens": 10, "ref": {"path": "docs/b.md"}},
        {"kind": "knowledge-doc", "label": "a", "tokens": 10, "ref": {"path": "docs/a.md"}},
        {"kind": "constitution-doc", "label": "A", "tokens": 10},
        {"kind": "issue-contract", "label": "B", "tokens": 10},
    ]
    payload = assemble(cands, token_budget=45, task_id="t")
    ordered = []
    for layer in payload["assembly"]["layers"]:
        for item in layer["items"]:
            ordered.append(
                (-layer_priority(layer["layer"], 1.0, DEFAULT_DECAY_FACTOR),
                 layer["layer"], item["label"], item["included"])
            )
    keys = [t[:3] for t in ordered]
    assert keys == sorted(keys), f"global order violated: {keys}"
    included_flags = [t[3] for t in ordered]
    assert included_flags == sorted(included_flags, reverse=True), "included items must precede clipped"


# ------------------------------------------------------------ fail-closed ---

def test_unknown_kind_rejected() -> None:
    try:
        normalize_candidate({"kind": "nope", "label": "x", "tokens": 1})
    except CandidateError:
        return
    raise AssertionError("unknown kind accepted")


def test_path_fail_closed() -> None:
    # Drive-letter fixture via concatenation: the tier-8 machine-path guard
    # scans source for literal "X:/" strings; a validator REJECTION fixture
    # is not a hardcoded path (documented false-positive class).
    drive = "C" + ":/x"
    for bad in ("a/../b", "../x", "x/..", "/etc/passwd", drive, "", "a b"):
        try:
            normalize_candidate(
                {"kind": "file-scope", "label": "x", "tokens": 1, "ref": {"path": bad}}
            )
        except CandidateError:
            continue
        raise AssertionError(f"illegal path accepted: {bad!r}")


def test_memory_ref_fail_closed() -> None:
    good = {"namespace": "agent-episodes", "document_id": "ep-9f8e7d6c5a4b"}
    normalize_candidate(
        {"kind": "memory-ref", "label": "x", "tokens": 1, "ref": {"memory": good}}
    )  # must not raise
    for bad_mem in (
        {"namespace": "Bad Space", "document_id": "d"},
        {"namespace": "ns", "document_id": "bad id!"},
        {"namespace": "ns"},
        "not-a-dict",
    ):
        try:
            normalize_candidate(
                {"kind": "memory-ref", "label": "x", "tokens": 1, "ref": {"memory": bad_mem}}
            )
        except CandidateError:
            continue
        raise AssertionError(f"illegal memory ref accepted: {bad_mem!r}")


def test_adr_ref_fail_closed() -> None:
    assert ADR_ID_RE.fullmatch("ADR-001") and ADR_ID_RE.fullmatch("ADR-1234")
    for bad in ("ADR-12", "ADR-12345", "adr-001", "ADR-001-extra"):
        try:
            normalize_candidate(
                {"kind": "adr-ref", "label": "x", "tokens": 1, "ref": {"adr_id": bad}}
            )
        except CandidateError:
            continue
        raise AssertionError(f"illegal ADR id accepted: {bad!r}")


def test_unpinned_ref_shapes() -> None:
    """Unpinned kinds: {} or exactly one legal locator; never two/unknown/illegal."""
    normalize_candidate({"kind": "constitution-doc", "label": "x", "tokens": 1})  # ref {}
    normalize_candidate(
        {"kind": "knowledge-doc", "label": "x", "tokens": 1, "ref": {"path": "docs/k.md"}}
    )
    for bad_ref in (
        {"path": "a", "memory": {"namespace": "ns", "document_id": "d"}},
        {"bogus": 1},
        {"path": "../x"},
    ):
        try:
            normalize_candidate(
                {"kind": "transcript", "label": "x", "tokens": 1, "ref": bad_ref}
            )
        except CandidateError:
            continue
        raise AssertionError(f"illegal unpinned ref accepted: {bad_ref!r}")


def test_candidate_tokens_and_label_bounds() -> None:
    try:
        normalize_candidate({"kind": "issue-contract", "label": "x" * 257, "tokens": 1})
    except CandidateError:
        pass
    else:
        raise AssertionError("label > 256 accepted")
    try:
        normalize_candidate({"kind": "issue-contract", "label": "x", "tokens": 100_001})
    except CandidateError:
        pass
    else:
        raise AssertionError("tokens > 100000 accepted")
    try:
        normalize_candidate({"kind": "issue-contract", "label": "x", "tokens": True})
    except CandidateError:
        pass
    else:
        raise AssertionError("bool tokens accepted")
    est = normalize_candidate({"kind": "issue-contract", "label": "x", "text": "a" * 8})
    assert est["tokens"] == estimate_tokens("a" * 8) == 2


def test_zero_candidates_fails_loud() -> None:
    try:
        assemble([], task_id="t")
    except ContextSelectorError:
        return
    raise AssertionError("empty assembly did not fail loud")


def test_wire_edge_patterns() -> None:
    payload = assemble(
        [{"kind": "issue-contract", "label": "x", "tokens": 1}], task_id="t"
    )
    assert re.fullmatch(r"asm-[0-9a-f]{12}", payload["assembly"]["assembly_id"])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", payload["assembly"]["generated_at"])
    injected = assemble(
        [{"kind": "issue-contract", "label": "x", "tokens": 1}],
        task_id="t",
        assembly_id="asm-0123456789ab",
        generated_at="2026-10-16T08:00:00Z",
    )
    assert injected["assembly"]["assembly_id"] == "asm-0123456789ab"
    assert injected["assembly"]["generated_at"] == "2026-10-16T08:00:00Z"


def test_determinism_byte_identical() -> None:
    cands = [
        {"kind": "constitution-doc", "label": "A", "tokens": 100},
        {"kind": "knowledge-doc", "label": "K", "tokens": 50, "ref": {"path": "docs/k.md"}},
        {"kind": "transcript", "label": "noise", "tokens": 900},
    ]
    p1 = assemble(cands, token_budget=120, task_id="t", assembly_id="asm-0123456789ab",
                  generated_at="2026-10-16T08:00:00Z")
    p2 = assemble(cands, token_budget=120, task_id="t", assembly_id="asm-0123456789ab",
                  generated_at="2026-10-16T08:00:00Z")
    assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)


# ----------------------------------------------------------------- schema ---

def test_payload_schema_valid() -> None:
    if not HAVE_JSONSCHEMA:
        print("SKIP: jsonschema unavailable — schema validation not run")
        return
    schema = json.loads(
        (ROOT / "api-schemas" / "context-assembly.schema.json").read_text(encoding="utf-8")
    )
    cands = [
        {"kind": "constitution-doc", "label": "A", "tokens": 100},
        {"kind": "issue-contract", "label": "B", "tokens": 50},
        {"kind": "file-scope", "label": "C", "tokens": 40, "ref": {"path": "src/c.py"}},
        {"kind": "adjacent-test", "label": "T", "tokens": 30, "ref": {"path": "tests/test_c.py"}},
        {"kind": "memory-ref", "label": "M", "tokens": 20,
         "ref": {"memory": {"namespace": "agent-episodes", "document_id": "ep-1"}}},
        {"kind": "adr-ref", "label": "adr", "tokens": 30, "ref": {"adr_id": "ADR-001"}},
        {"kind": "knowledge-doc", "label": "K", "tokens": 25, "ref": {"path": "docs/k.md"}},
        {"kind": "runtime-state", "label": "CI", "tokens": 900},
        {"kind": "transcript", "label": "chat", "tokens": 400},
    ]
    payload = assemble(cands, token_budget=260, task_id="t", assembly_id="asm-0123456789ab",
                       generated_at="2026-10-16T08:00:00Z")
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(payload)
    # clipped case validates too (if/then both directions)
    clipped = assemble(cands, token_budget=150, task_id="t", assembly_id="asm-0123456789ab",
                       generated_at="2026-10-16T08:00:00Z")
    jsonschema.Draft202012Validator(schema).validate(clipped)


# -------------------------------------------------------------- harvester ---

def _make_fake_repo(base: Path) -> Path:
    (base / "docs" / "adrs").mkdir(parents=True)
    (base / "scripts").mkdir()
    (base / "tests").mkdir()
    (base / "AGENTS.md").write_text("constitution body", encoding="utf-8")
    (base / "AGENT_RULES.md").write_text("rules body", encoding="utf-8")
    (base / "docs" / "GUIDE.md").write_text("guide body", encoding="utf-8")
    (base / "docs" / "adrs" / "ADR-001-BOUNDARY.md").write_text("adr body", encoding="utf-8")
    (base / "docs" / "adrs" / "ADR-notes.md").write_text("not an ADR", encoding="utf-8")
    (base / "scripts" / "widget.py").write_text("def main():\n    pass\n", encoding="utf-8")
    (base / "tests" / "test_widget.py").write_text("def test_widget():\n    assert True\n", encoding="utf-8")
    return base


def test_harvester_offline_sources() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_fake_repo(Path(tmp))
        task = {"id": "329", "title": "wire selector", "body": "do it"}
        contract = {"task_contract": {"scope": {"touching_files": ["scripts/widget.py"]}}}
        cands = harvest_candidates(task, contract, repo)
        by_label = {c["label"]: c for c in cands}
        # L1 constitution
        assert "AGENTS.md — core constitution" in by_label
        assert "AGENT_RULES.md — behavior rules" in by_label
        # L2 issue contract
        assert any(c["kind"] == "issue-contract" for c in cands)
        # L3 file scope + adjacent test
        assert by_label["scripts/widget.py"]["kind"] == "file-scope"
        assert by_label["scripts/widget.py"]["ref"] == {"path": "scripts/widget.py"}
        assert "tests/test_widget.py" in by_label
        assert by_label["tests/test_widget.py"]["kind"] == "adjacent-test"
        # L5 ADR (id extracted; non-numeric ADR-* excluded)
        assert by_label["ADR-001-BOUNDARY.md"]["ref"] == {"adr_id": "ADR-001"}
        assert "ADR-notes.md" not in by_label
        # L6 knowledge docs
        assert by_label["docs/GUIDE.md"]["kind"] == "knowledge-doc"
        # no L4/L7/L8 without hooks
        assert not any(c["kind"] in ("memory-ref", "runtime-state", "transcript") for c in cands)


def test_harvester_injected_hooks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_fake_repo(Path(tmp))
        cands = harvest_candidates(
            {"id": "1", "title": "t", "body": "b"},
            {"task_contract": {"scope": {"touching_files": []}}},
            repo,
            memory_hits=[
                {"namespace": "agent-episodes", "document_id": "ep-1",
                 "label": "prior episode", "tokens": 40}
            ],
            runtime_state=[{"label": "CI snapshot", "tokens": 500}],
            noise_items=[{"label": "chat", "text": "hello"}],
        )
        kinds = {c["kind"] for c in cands}
        assert {"memory-ref", "runtime-state", "transcript"} <= kinds
        full = build_context_assembly(
            task={"id": "1", "title": "t", "body": "b"},
            contract={"task_contract": {"scope": {"touching_files": []}}},
            repo_root=repo,
            memory_hits=[{"namespace": "agent-episodes", "document_id": "ep-1",
                          "label": "prior episode", "tokens": 40}],
            runtime_state=[{"label": "CI snapshot", "tokens": 500}],
            noise_items=[{"label": "chat", "text": "hello"}],
            token_budget=120,
            assembly_id="asm-0123456789ab",
            generated_at="2026-10-16T08:00:00Z",
        )
        assert full["assembly"]["tokens_used"] <= 120, full["assembly"]["tokens_used"]
        assert full["assembly"]["budget_clipped"] is True, full["assembly"]["clipped_layers"]
        assert set(full["assembly"]["clipped_layers"]) <= {7, 8}


def test_harvester_missing_files_skipped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)  # TemporaryDirectory already exists — no mkdir
        cands = harvest_candidates(
            {"id": "1", "title": "t", "body": "b"},
            {"task_contract": {"scope": {"touching_files": ["ghost/missing.py"]}}},
            repo,
        )
        # only the L2 issue contract survives; ghost paths contribute nothing
        assert [c["kind"] for c in cands] == ["issue-contract"]


# ------------------------------------------------------------ loop wiring ---

def _with_env(name: str, value: str | None, fn) -> None:
    saved = os.environ.get(name)
    try:
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
        fn()
    finally:
        if saved is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = saved


def _adhoc_task() -> dict:
    return {
        "id": "adhoc",
        "title": "Autonomous Contribution Task",
        "body": "Implement smallest safe change adhering to AGENTS.md contracts.",
        "state": "ADHOC",
        "labels": [],
    }


def test_loop_gate_parsing() -> None:
    for off in ("", "0", "false", "no", "off", "  ", "OFF"):
        _with_env("SUPREME_CONTEXT_SELECTOR", off,
                  lambda: assert_equal(loop._context_selector_enabled(), False, off))
    for on in ("1", "true", "yes", "on", "enabled"):
        _with_env("SUPREME_CONTEXT_SELECTOR", on,
                  lambda: assert_equal(loop._context_selector_enabled(), True, on))


def assert_equal(got, want, ctx) -> None:
    assert got == want, f"gate value {ctx!r}: got {got}, want {want}"


def test_loop_gate_off_byte_compat() -> None:
    """Acceptance criterion 3 (negative): gate off -> NO context_assembly key,
    prompt unchanged — byte-compat with pre-#329 envelopes."""
    contract = loop.build_task_contract("task-329", group="agent-orchestration")
    envelope = loop.build_task_envelope(_adhoc_task(), "coder", contract)
    assert "context_assembly" not in envelope["task_envelope"]
    assert "Assembled Context" not in envelope["task_envelope"]["specialist_prompt"]


def test_loop_gate_on_injects_into_instructions() -> None:
    """Acceptance criterion 3 (positive): gate on -> payload injected BOTH as
    the machine field and as the prompt's Assembled Context section."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_fake_repo(Path(tmp))
        saved_root = loop.REPO_ROOT
        try:
            loop.REPO_ROOT = repo
            contract = loop.build_task_contract("task-329", group="agent-orchestration")
            payload = loop._assemble_task_context(_adhoc_task(), contract)
            assert payload is not None
            assert payload["assembly"]["tokens_used"] > 0
            envelope = loop.build_task_envelope(
                _adhoc_task(), "coder", contract, context_assembly=payload
            )
            assert envelope["task_envelope"]["context_assembly"] == payload
            prompt = envelope["task_envelope"]["specialist_prompt"]
            assert "**6. Assembled Context" in prompt
            assert "[L1 constitution]" in prompt
        finally:
            loop.REPO_ROOT = saved_root


def test_loop_fail_open() -> None:
    """Selector failure -> None + loud log; envelope stays pre-#329 byte-compat."""
    saved = loop._build_context_assembly
    try:
        def _boom(**kwargs):
            raise RuntimeError("boom")
        loop._build_context_assembly = _boom
        contract = loop.build_task_contract("task-329", group="agent-orchestration")
        assert loop._assemble_task_context(_adhoc_task(), contract) is None
        envelope = loop.build_task_envelope(_adhoc_task(), "coder", contract)
        assert "context_assembly" not in envelope["task_envelope"]
    finally:
        loop._build_context_assembly = saved


def test_loop_unavailable_selector_fail_open() -> None:
    saved = loop._build_context_assembly
    try:
        loop._build_context_assembly = None
        contract = loop.build_task_contract("task-329", group="agent-orchestration")
        assert loop._assemble_task_context(_adhoc_task(), contract) is None
    finally:
        loop._build_context_assembly = saved


def test_loop_budget_override_parsing() -> None:
    """SUPREME_CONTEXT_BUDGET: valid int honored; invalid -> default + loud stderr."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_fake_repo(Path(tmp))
        saved_root = loop.REPO_ROOT
        contract = loop.build_task_contract("task-329", group="agent-orchestration")
        try:
            loop.REPO_ROOT = repo

            def _check_valid() -> None:
                payload = loop._assemble_task_context(_adhoc_task(), contract)
                assert payload is not None
                assert payload["selection"]["token_budget"] == 50, payload["selection"]

            _with_env("SUPREME_CONTEXT_BUDGET", "50", _check_valid)

            def _check_invalid() -> None:
                payload = loop._assemble_task_context(_adhoc_task(), contract)
                assert payload is not None  # falls back to default, still works
                assert payload["selection"]["token_budget"] > 1

            _with_env("SUPREME_CONTEXT_BUDGET", "not-a-number", _check_invalid)
            _with_env("SUPREME_CONTEXT_BUDGET", "0", _check_invalid)
        finally:
            loop.REPO_ROOT = saved_root


# ------------------------------------------------------------ plain runner --

if __name__ == "__main__":
    tests = sorted(
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    )
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 — honest reporting
            failures += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    total = len(tests)
    print(f"{total - failures}/{total} passed")
    sys.exit(1 if failures else 0)
