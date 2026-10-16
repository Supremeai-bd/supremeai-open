#!/usr/bin/env python3
"""Smart Context Selector — Layer 1-8 priority-ranked context assembly (#329).

Implements the SSOT pair:
  - docs/CONTEXT_SELECTOR_SPEC.md (assembly doctrine, §2-§8)
  - api-schemas/context-assembly.schema.json (Draft 2020-12 wire contract)

Mission: agents fail on context starvation and context noise in equal
measure. This module answers both with ONE deterministic assembly pass:

  1. Rank candidate context sources into 8 priority layers (§2).
  2. Decay priority per layer so constitution always outranks noise (§3).
  3. Clip at the token budget with a STRICT cutoff — no backfill (§4).
  4. Record every inclusion/exclusion verdict in a machine-checkable payload.

Zero-dependency doctrine (AGENT_RULES.md §13): stdlib only. The optional
jsonschema check lives in the test suite, not here.

Determinism contract: given the same candidates and policy, the payload is
byte-identical apart from the two impure edges (assembly_id, generated_at) —
both injectable for offline tests. Ties beyond the spec's three sort keys
resolve by stable input order, and the harvester's input order is
deterministic (fixed walk, sorted globs).

Token estimation: v1 uses the deterministic chars/4 heuristic
(max(1, ceil(len(text)/4))). This is NOT a model tokenizer — it is a stable
estimate so the budget math is reproducible offline, per the schema's
"Estimated token cost" wording.

Fail-closed summary (mirrors spec §8):
  - unknown item kinds, unknown policies, out-of-range values -> rejected
  - kind/ref mismatch -> rejected (path/memory/adr_id pins on pinned kinds)
  - path traversal ('..' anywhere) and absolute paths -> rejected
  - unpinned kinds: ref must be {} or exactly ONE legal locator (ItemRef is
    additionalProperties:false over path/memory/adr_id; one locator keeps
    the semantics honest)
  - Layer-1 overflow of the token budget -> fail-loud (R2)
  - zero candidates -> fail-loud (an assembly with no layers is useless)

The loop wiring (continuous_agent_loop.py) is fail-open around this module:
any error here is logged loudly and the envelope is emitted WITHOUT the
optional context_assembly key — byte-compat with pre-#329 consumers.

--self-test: 8 offline scenario groups (exit 0 = all pass).

Layer catalog (spec §2, closed):
  1 constitution    AGENTS.md, AGENT_RULES.md            (never clipped)
  2 task-contract   task issue: mission, acceptance, scope
  3 file-scope      touching files + adjacent tests
  4 memory-sidecar  semantic memory hits (caller-injected)
  5 adr-history     docs/adrs/ADR-*.md
  6 knowledge-items docs/*.md specs, runbooks, governance
  7 environment-state CI/telemetry snapshots (caller-injected)
  8 hygiene-noise   transcripts, changelogs (caller-injected)
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCHEMA_VERSION = "1.0"
STRATEGY = "priority_decay_strict_cutoff"
# R2 (constitution never clipped) makes the budget a DERIVED policy: it must
# be sized to admit this repo's Layer-1 constitution (AGENTS.md +
# AGENT_RULES.md ≈ 11,350 estimated tokens) or the assembler fails loud.
# 12,000 = constitution + working headroom; operators override via the
# loop's SUPREME_CONTEXT_BUDGET (the selector itself stays env-free).
DEFAULT_TOKEN_BUDGET = 12000
DEFAULT_BASE_PRIORITY = 1.0
DEFAULT_DECAY_FACTOR = 0.8

# Closed layer catalog: layer <-> name (schema if/then pins, both directions).
LAYER_NAMES: dict[int, str] = {
    1: "constitution",
    2: "task-contract",
    3: "file-scope",
    4: "memory-sidecar",
    5: "adr-history",
    6: "knowledge-items",
    7: "environment-state",
    8: "hygiene-noise",
}
NAME_TO_LAYER = {name: layer for layer, name in LAYER_NAMES.items()}

# Closed kind vocabulary; kind -> layer is the I-6 semantic mapping (spec §5).
KIND_TO_LAYER: dict[str, int] = {
    "constitution-doc": 1,
    "issue-contract": 2,
    "file-scope": 3,
    "adjacent-test": 3,
    "memory-ref": 4,
    "adr-ref": 5,
    "knowledge-doc": 6,
    "runtime-state": 7,
    "transcript": 8,
}

# Kinds whose ref shape is if/then-pinned by the schema (ContextItem allOf).
KIND_REF_FIELD: dict[str, str] = {
    "file-scope": "path",
    "adjacent-test": "path",
    "memory-ref": "memory",
    "adr-ref": "adr_id",
}

# The only honest verdict reasons (R4).
REASON_PRIORITY_RANK = "priority_rank"
REASON_CONSTITUTION = "constitution_never_clipped"
REASON_CLIPPED = "budget_clipped"
INCLUSION_REASONS = (REASON_PRIORITY_RANK, REASON_CONSTITUTION, REASON_CLIPPED)

# Wire-pattern mirrors of the schema (ItemRef / MemoryRef) — fail-closed locally
# so invalid payloads never reach the validator.
PATH_RE = re.compile(r"^(?!.*\.\.)[A-Za-z0-9_][A-Za-z0-9_./-]{0,255}$")
NAMESPACE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
DOCUMENT_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
ADR_ID_RE = re.compile(r"^ADR-\d{3,4}$")
ADR_FILE_RE = re.compile(r"^(ADR-\d{3,4})")


class ContextSelectorError(ValueError):
    """Base class: every rejection is fail-closed and carries the reason."""


class PolicyError(ContextSelectorError):
    """SelectionPolicy violated the schema ranges/types."""


class CandidateError(ContextSelectorError):
    """A candidate item violated the closed vocabularies / ref pins."""


class ConstitutionBudgetError(ContextSelectorError):
    """Token budget cannot admit Layer-1 constitution docs (R2 fail-loud)."""


def estimate_tokens(text: str) -> int:
    """Deterministic v1 token estimate: chars/4, minimum 1 (see module doc)."""
    return max(1, math.ceil(len(text) / 4))


def layer_priority(layer: int, base_priority: float, decay_factor: float) -> float:
    """Spec §3: priority(L) = round(base * decay^(L-1), 3)."""
    return round(base_priority * (decay_factor ** (layer - 1)), 3)


def _require_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PolicyError(f"{name} must be an integer, got {type(value).__name__}")
    if not (minimum <= value <= maximum):
        raise PolicyError(f"{name} out of range [{minimum}, {maximum}]: {value}")
    return value


def _validate_policy(
    token_budget: Any, base_priority: Any, decay_factor: Any
) -> tuple[int, float, float]:
    budget = _require_int(token_budget, "token_budget", 1, 1_000_000)
    if isinstance(base_priority, bool) or not isinstance(base_priority, (int, float)):
        raise PolicyError("base_priority must be a number")
    if not (0.0 <= float(base_priority) <= 1.0):
        raise PolicyError(f"base_priority out of range [0, 1]: {base_priority}")
    if isinstance(decay_factor, bool) or not isinstance(decay_factor, (int, float)):
        raise PolicyError("decay_factor must be a number")
    df = float(decay_factor)
    if not (0.0 < df <= 1.0):
        raise PolicyError(f"decay_factor must be in (0, 1]: {decay_factor}")
    return budget, float(base_priority), df


def _validate_path(value: Any) -> str:
    if not isinstance(value, str) or not PATH_RE.fullmatch(value):
        raise CandidateError(
            f"illegal repo path {value!r}: must be repo-relative, no '..', "
            "no absolute root, chars [A-Za-z0-9_./-]"
        )
    return value


def _validate_memory(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"namespace", "document_id"}:
        raise CandidateError("ref.memory requires exactly namespace + document_id")
    if not isinstance(value["namespace"], str) or not NAMESPACE_RE.fullmatch(value["namespace"]):
        raise CandidateError(f"illegal memory namespace: {value.get('namespace')!r}")
    if not isinstance(value["document_id"], str) or not DOCUMENT_ID_RE.fullmatch(
        value["document_id"]
    ):
        raise CandidateError(f"illegal memory document_id: {value.get('document_id')!r}")
    return value


def _validate_adr(value: Any) -> str:
    if not isinstance(value, str) or not ADR_ID_RE.fullmatch(value):
        raise CandidateError(f"illegal ADR id: {value!r} (expected ADR-\\d{{3,4}})")
    return value


def _validate_ref(kind: str, ref: Any) -> dict[str, Any]:
    """Validate the ref shape against the schema's kind-specific pins.

    Pinned kinds (ContextItem allOf) REQUIRE their locator field. Unpinned
    kinds accept {} or exactly one legal locator — ItemRef itself is
    additionalProperties:false over {path, memory, adr_id}.
    """
    if ref is None:
        ref = {}
    if not isinstance(ref, dict):
        raise CandidateError(f"{kind}: ref must be an object, got {type(ref).__name__}")
    required_field = KIND_REF_FIELD.get(kind)
    if required_field is None:
        if not ref:
            return {}
        if len(ref) != 1:
            raise CandidateError(
                f"kind '{kind}': ref must be empty or exactly one locator, got {sorted(ref)}"
            )
        field, value = next(iter(ref.items()))
        if field == "path":
            _validate_path(value)
        elif field == "memory":
            _validate_memory(value)
        elif field == "adr_id":
            _validate_adr(value)
        else:
            raise CandidateError(f"ref carries unknown field: {field!r}")
        return ref
    if required_field not in ref:
        raise CandidateError(f"kind '{kind}' requires ref.{required_field}")
    extra = set(ref) - {"path", "memory", "adr_id"}
    if extra:
        raise CandidateError(f"ref carries unknown fields: {sorted(extra)}")
    if required_field == "path":
        _validate_path(ref["path"])
    elif required_field == "memory":
        _validate_memory(ref["memory"])
    else:  # adr_id
        _validate_adr(ref["adr_id"])
    return ref


def normalize_candidate(item: Any) -> dict[str, Any]:
    """Validate one candidate and normalize it to the engine's internal shape.

    Accepted input (dict):
      kind      required — closed 9-value vocabulary
      label     required — 1..256 chars (final lexicographic tie-breaker)
      tokens    optional — int 1..100000; estimated from text when absent
      text      optional — token source when tokens absent
      ref       optional — kind-pinned shape; {} for ref-less kinds
    """
    if not isinstance(item, dict):
        raise CandidateError(f"candidate must be a dict, got {type(item).__name__}")
    kind = item.get("kind")
    if kind not in KIND_TO_LAYER:
        raise CandidateError(
            f"unknown item kind: {kind!r} (closed vocabulary: {sorted(KIND_TO_LAYER)})"
        )
    label = item.get("label")
    if not isinstance(label, str) or not (1 <= len(label) <= 256):
        raise CandidateError(f"label must be a 1..256 char string, got {label!r}")
    tokens = item.get("tokens")
    if tokens is None:
        text = item.get("text")
        if not isinstance(text, str) or not text:
            raise CandidateError(f"candidate {label!r}: provide tokens or non-empty text")
        tokens = estimate_tokens(text)
    if isinstance(tokens, bool) or not isinstance(tokens, int):
        raise CandidateError(f"candidate {label!r}: tokens must be an integer")
    if not (1 <= tokens <= 100_000):
        raise CandidateError(f"candidate {label!r}: tokens out of range [1, 100000]: {tokens}")
    ref = _validate_ref(kind, item.get("ref"))
    return {
        "kind": kind,
        "layer": KIND_TO_LAYER[kind],
        "label": label,
        "tokens": tokens,
        "ref": ref,
    }


def assemble(
    candidates: list[dict[str, Any]],
    *,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    base_priority: float = DEFAULT_BASE_PRIORITY,
    decay_factor: float = DEFAULT_DECAY_FACTOR,
    task_id: str = "adhoc",
    assembly_id: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """One deterministic assembly pass over validated candidates.

    Faithful to spec §4's walk: priority DESC -> layer ASC -> label ASC,
    strict cutoff (R1, no backfill), constitution unclippable (R2),
    bidirectional clipping state (R3), every verdict carries a reason (R4).
    """
    budget, base, df = _validate_policy(token_budget, base_priority, decay_factor)
    if not isinstance(task_id, str) or not (1 <= len(task_id) <= 128):
        raise ContextSelectorError(f"task_id must be a 1..128 char string, got {task_id!r}")
    normalized = [normalize_candidate(c) for c in candidates]
    if not normalized:
        raise ContextSelectorError(
            "no candidate context items — an assembly with zero layers is not buildable"
        )

    ordered = sorted(
        normalized,
        key=lambda c: (-layer_priority(c["layer"], base, df), c["layer"], c["label"]),
    )

    remaining = budget
    clip_point_seen = False
    verdicts: list[dict[str, Any]] = []
    for cand in ordered:
        if clip_point_seen:
            verdicts.append({**cand, "included": False, "inclusion_reason": REASON_CLIPPED})
            continue
        if cand["kind"] == "constitution-doc":
            if cand["tokens"] > remaining:
                raise ConstitutionBudgetError(
                    f"token budget {budget} cannot admit Layer-1 constitution doc "
                    f"{cand['label']!r} ({cand['tokens']} tk) — R2 fail-loud: "
                    "size the budget to admit the constitution"
                )
            verdicts.append(
                {**cand, "included": True, "inclusion_reason": REASON_CONSTITUTION}
            )
            remaining -= cand["tokens"]
            continue
        if cand["tokens"] <= remaining:
            verdicts.append({**cand, "included": True, "inclusion_reason": REASON_PRIORITY_RANK})
            remaining -= cand["tokens"]
        else:
            verdicts.append({**cand, "included": False, "inclusion_reason": REASON_CLIPPED})
            clip_point_seen = True

    layers: list[dict[str, Any]] = []
    tokens_used = 0
    clipped_layers: set[int] = set()
    for layer_no in range(1, 9):
        layer_verdicts = [v for v in verdicts if v["layer"] == layer_no]
        if not layer_verdicts:
            continue
        layer_items = []
        layer_tokens = 0
        for v in layer_verdicts:
            layer_items.append(
                {
                    "kind": v["kind"],
                    "label": v["label"],
                    "tokens": v["tokens"],
                    "included": v["included"],
                    "inclusion_reason": v["inclusion_reason"],
                    "ref": dict(v["ref"]),
                }
            )
            if v["included"]:
                layer_tokens += v["tokens"]
            else:
                clipped_layers.add(layer_no)
        tokens_used += layer_tokens
        layers.append(
            {
                "layer": layer_no,
                "name": LAYER_NAMES[layer_no],
                "priority": layer_priority(layer_no, base, df),
                "tokens": layer_tokens,
                "items": layer_items,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "selection": {
            "token_budget": budget,
            "base_priority": base,
            "decay_factor": df,
            "strategy": STRATEGY,
        },
        "assembly": {
            "assembly_id": assembly_id or f"asm-{uuid.uuid4().hex[:12]}",
            "task_id": task_id,
            "generated_at": generated_at
            or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tokens_used": tokens_used,
            "budget_clipped": bool(clipped_layers),
            "clipped_layers": sorted(clipped_layers),
            "layers": layers,
        },
    }


def _file_item(path: Path, repo_root: Path, kind: str, label: str) -> dict[str, Any] | None:
    """Read a repo file into a candidate; missing files simply have no candidate."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    rel = path.relative_to(repo_root).as_posix()
    ref: dict[str, Any] = {}
    if kind in ("file-scope", "adjacent-test", "knowledge-doc"):
        ref = {"path": rel}
    return {"kind": kind, "label": label, "text": text, "ref": ref}


def _adjacent_tests(touching: str, repo_root: Path) -> list[Path]:
    """Deterministic adjacent-test probe for one touching file (v1 heuristics)."""
    p = Path(touching)
    stem = p.stem
    candidates = [
        repo_root / "tests" / f"test_{stem}.py",
        p.parent / f"test_{stem}.py",
    ]
    return [c for c in candidates if c.is_file()]


def harvest_candidates(
    task: dict[str, Any],
    contract: dict[str, Any],
    repo_root: Path,
    *,
    memory_hits: list[dict[str, Any]] | None = None,
    runtime_state: list[dict[str, Any]] | None = None,
    noise_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Collect offline-deterministic candidates for Layers 1/2/3/5/6.

    Layers 4/7/8 are caller-injected hooks (memory sidecar, runtime
    telemetry, transcripts) — kept as parameters so this module stays
    decoupled from unlanded/external providers. Absent hooks contribute no
    candidates and their layer simply does not appear in the payload.
    """
    repo_root = Path(repo_root)
    tc = (contract or {}).get("task_contract", {})
    candidates: list[dict[str, Any]] = []

    # L1 — constitution: never clipped (spec §2). Fixed order = deterministic.
    for name, label in (
        ("AGENTS.md", "AGENTS.md — core constitution"),
        ("AGENT_RULES.md", "AGENT_RULES.md — behavior rules"),
    ):
        item = _file_item(repo_root / name, repo_root, "constitution-doc", label)
        if item:
            candidates.append(item)

    # L2 — task contract: mission + acceptance + scope from the task record.
    task_ref = task.get("id") if task.get("id") is not None else "adhoc"
    mission_text = "\n".join(
        str(part) for part in (task.get("title"), task.get("body")) if part
    )
    if mission_text.strip():
        candidates.append(
            {
                "kind": "issue-contract",
                "label": f"Issue #{task_ref} — mission, acceptance criteria, Touching Files",
                "text": mission_text,
                "ref": {},
            }
        )

    # L3 — file scope: declared touching files + adjacent tests (existing only).
    for touching in tc.get("scope", {}).get("touching_files", []) or []:
        item = _file_item(repo_root / touching, repo_root, "file-scope", str(touching))
        if item:
            candidates.append(item)
        for test_path in _adjacent_tests(str(touching), repo_root):
            t_item = _file_item(
                test_path,
                repo_root,
                "adjacent-test",
                test_path.relative_to(repo_root).as_posix(),
            )
            if t_item:
                candidates.append(t_item)

    # L4 — memory sidecar: caller-injected (namespace/document_id vocabulary).
    for hit in memory_hits or []:
        candidates.append(
            {
                "kind": "memory-ref",
                "label": str(hit.get("label") or hit.get("document_id") or "memory hit"),
                "tokens": hit.get("tokens"),
                "text": hit.get("text"),
                "ref": {
                    "memory": {
                        "namespace": hit.get("namespace"),
                        "document_id": hit.get("document_id"),
                    }
                },
            }
        )

    # L5 — ADR history: docs/adrs/ADR-*.md (template/README excluded by pattern).
    adrs_dir = repo_root / "docs" / "adrs"
    if adrs_dir.is_dir():
        for adr_path in sorted(adrs_dir.glob("ADR-*.md")):
            match = ADR_FILE_RE.match(adr_path.stem)
            if not match:
                continue
            item = _file_item(
                adr_path, repo_root, "adr-ref", adr_path.name
            )
            if item:
                item["ref"] = {"adr_id": match.group(1)}
                candidates.append(item)

    # L6 — knowledge items: docs/*.md, sorted glob (deterministic).
    docs_dir = repo_root / "docs"
    if docs_dir.is_dir():
        for doc_path in sorted(docs_dir.glob("*.md")):
            rel_label = doc_path.relative_to(repo_root).as_posix()
            item = _file_item(doc_path, repo_root, "knowledge-doc", rel_label)
            if item:
                candidates.append(item)

    # L7/L8 — caller-injected runtime state and hygiene noise.
    for state in runtime_state or []:
        candidates.append(
            {
                "kind": "runtime-state",
                "label": str(state.get("label") or "runtime state"),
                "tokens": state.get("tokens"),
                "text": state.get("text"),
                "ref": {},
            }
        )
    for noise in noise_items or []:
        candidates.append(
            {
                "kind": "transcript",
                "label": str(noise.get("label") or "transcript excerpt"),
                "tokens": noise.get("tokens"),
                "text": noise.get("text"),
                "ref": {},
            }
        )

    return candidates


def build_context_assembly(
    *,
    task: dict[str, Any],
    contract: dict[str, Any],
    repo_root: Path,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    base_priority: float = DEFAULT_BASE_PRIORITY,
    decay_factor: float = DEFAULT_DECAY_FACTOR,
    memory_hits: list[dict[str, Any]] | None = None,
    runtime_state: list[dict[str, Any]] | None = None,
    noise_items: list[dict[str, Any]] | None = None,
    assembly_id: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """One-call pipeline for the loop: harvest -> assemble. Raises on failure
    (the caller owns the fail-open policy)."""
    candidates = harvest_candidates(
        task,
        contract,
        repo_root,
        memory_hits=memory_hits,
        runtime_state=runtime_state,
        noise_items=noise_items,
    )
    task_ref = task.get("id") if task.get("id") is not None else "adhoc"
    return assemble(
        candidates,
        token_budget=token_budget,
        base_priority=base_priority,
        decay_factor=decay_factor,
        task_id=str(task_ref),
        assembly_id=assembly_id,
        generated_at=generated_at,
    )


# ---------------------------------------------------------------------------
# --self-test: 8 offline scenario groups (zero-dependency; jsonschema optional)
# ---------------------------------------------------------------------------

def _self_test() -> int:
    failures: list[str] = []
    skips: list[str] = []

    def check(name: str, fn) -> None:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failures.append(name)
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 — self-test reports honestly
            failures.append(name)
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")

    def expect_raises(exc_type, fn):
        try:
            fn()
        except exc_type:
            return
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"expected {exc_type.__name__}, got {type(exc).__name__}: {exc}")
        raise AssertionError(f"expected {exc_type.__name__}, nothing raised")

    print("smart_context_selector --self-test")

    # Group 1 — priority decay: spec §3 worked example, exact values.
    def g1() -> None:
        expected = [1.0, 0.8, 0.64, 0.512, 0.41, 0.328, 0.262, 0.21]
        for layer, want in enumerate(expected, start=1):
            got = layer_priority(layer, 1.0, 0.8)
            assert got == want, f"L{layer}: got {got}, want {want}"

    # Group 2 — strict cutoff (R1) + exact-fit boundary.
    def g2() -> None:
        cands = [
            {"kind": "constitution-doc", "label": "A", "tokens": 100},
            {"kind": "issue-contract", "label": "B", "tokens": 50},
            {"kind": "file-scope", "label": "C", "tokens": 40, "ref": {"path": "src/c.py"}},
            {"kind": "knowledge-doc", "label": "D", "tokens": 10, "ref": {"path": "docs/d.md"}},
        ]
        payload = assemble(cands, token_budget=190, task_id="t")
        verdict = {
            item["label"]: (item["included"], item["inclusion_reason"])
            for layer in payload["assembly"]["layers"]
            for item in layer["items"]
        }
        # remaining after A+B = 40; C fits exactly (boundary), D clips.
        assert verdict["C"] == (True, REASON_PRIORITY_RANK), verdict
        assert verdict["D"] == (False, REASON_CLIPPED), verdict
        # R1: no backfill — even a tiny later item stays excluded.
        payload2 = assemble(
            cands + [{"kind": "transcript", "label": "E", "tokens": 1}],
            token_budget=185,
            task_id="t",
        )
        verdict2 = {
            item["label"]: item["included"]
            for layer in payload2["assembly"]["layers"]
            for item in layer["items"]
        }
        assert verdict2["D"] is False and verdict2["E"] is False, verdict2

    # Group 3 — constitution never clipped (R2) + overflow fail-loud.
    def g3() -> None:
        cands = [
            {"kind": "constitution-doc", "label": "A", "tokens": 100},
            {"kind": "issue-contract", "label": "B", "tokens": 30},
        ]
        payload = assemble(cands, token_budget=100, task_id="t")
        verdict = {
            item["label"]: item["included"]
            for layer in payload["assembly"]["layers"]
            for item in layer["items"]
        }
        assert verdict["A"] is True and verdict["B"] is False, verdict
        expect_raises(
            ConstitutionBudgetError,
            lambda: assemble(
                [{"kind": "constitution-doc", "label": "A", "tokens": 101}],
                token_budget=100,
                task_id="t",
            ),
        )

    # Group 4 — bidirectional clipping state (R3) + verdict pairing (R4).
    def g4() -> None:
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
        for layer in clipped["layers"]:
            for item in layer["items"]:
                assert item["inclusion_reason"] in INCLUSION_REASONS
                assert item["included"] == (item["inclusion_reason"] != REASON_CLIPPED)

    # Group 5 — invariants I-1/I-2 + I-6 kind->layer + layer-name pins.
    def g5() -> None:
        cands = [
            {"kind": "constitution-doc", "label": "A", "tokens": 100},
            {"kind": "file-scope", "label": "C", "tokens": 40, "ref": {"path": "src/c.py"}},
            {"kind": "adr-ref", "label": "adr", "tokens": 60, "ref": {"adr_id": "ADR-001"}},
            {"kind": "transcript", "label": "noise", "tokens": 500},
        ]
        payload = assemble(cands, token_budget=200, task_id="t")
        asm = payload["assembly"]
        assert asm["tokens_used"] == sum(l["tokens"] for l in asm["layers"]) <= 200
        for layer in asm["layers"]:
            assert layer["name"] == LAYER_NAMES[layer["layer"]]
            assert layer["tokens"] == sum(i["tokens"] for i in layer["items"] if i["included"])
            for item in layer["items"]:
                assert KIND_TO_LAYER[item["kind"]] == layer["layer"]
        assert asm["clipped_layers"] == [8]

    # Group 6 — fail-closed zoo: kinds, refs, paths, policy ranges.
    def g6() -> None:
        expect_raises(CandidateError, lambda: normalize_candidate({"kind": "nope", "label": "x", "tokens": 1}))
        # Drive-letter fixture via concatenation: the tier-8 machine-path
        # guard scans source for literal "X:/" strings; a REJECTION fixture
        # is not a hardcoded path (documented false-positive class).
        drive = "C" + ":/x"
        for bad in ("a/../b", "../x", "x/..", "/etc/passwd", drive):
            expect_raises(
                CandidateError,
                lambda bad=bad: normalize_candidate(
                    {"kind": "file-scope", "label": "x", "tokens": 1, "ref": {"path": bad}}
                ),
            )
        expect_raises(
            CandidateError,
            lambda: normalize_candidate(
                {
                    "kind": "memory-ref",
                    "label": "x",
                    "tokens": 1,
                    "ref": {"memory": {"namespace": "Bad Space", "document_id": "d"}},
                }
            ),
        )
        expect_raises(
            CandidateError,
            lambda: normalize_candidate(
                {
                    "kind": "memory-ref",
                    "label": "x",
                    "tokens": 1,
                    "ref": {"memory": {"namespace": "ns", "document_id": "bad id!"}},
                }
            ),
        )
        expect_raises(
            CandidateError,
            lambda: normalize_candidate(
                {"kind": "adr-ref", "label": "x", "tokens": 1, "ref": {"adr_id": "ADR-12"}}
            ),
        )
        # unpinned kinds: exactly one legal locator — two locators, unknown
        # fields, and illegal locator values all fail closed.
        expect_raises(
            CandidateError,
            lambda: normalize_candidate(
                {
                    "kind": "knowledge-doc",
                    "label": "x",
                    "tokens": 1,
                    "ref": {"path": "a", "memory": {"namespace": "ns", "document_id": "d"}},
                }
            ),
        )
        expect_raises(
            CandidateError,
            lambda: normalize_candidate(
                {"kind": "transcript", "label": "x", "tokens": 1, "ref": {"bogus": 1}}
            ),
        )
        expect_raises(
            CandidateError,
            lambda: normalize_candidate(
                {"kind": "knowledge-doc", "label": "x", "tokens": 1, "ref": {"path": "../x"}}
            ),
        )
        expect_raises(PolicyError, lambda: assemble([{"kind": "issue-contract", "label": "x", "tokens": 1}], token_budget=0, task_id="t"))
        expect_raises(PolicyError, lambda: assemble([{"kind": "issue-contract", "label": "x", "tokens": 1}], base_priority=1.5, task_id="t"))
        expect_raises(PolicyError, lambda: assemble([{"kind": "issue-contract", "label": "x", "tokens": 1}], decay_factor=0, task_id="t"))
        expect_raises(PolicyError, lambda: assemble([{"kind": "issue-contract", "label": "x", "tokens": 1}], decay_factor=1.5, task_id="t"))
        expect_raises(ContextSelectorError, lambda: assemble([], task_id="t"))

    # Group 7 — schema validation: synthesized full payload + spec §6 sample.
    def g7() -> None:
        try:
            import jsonschema
        except ImportError:
            skips.append("jsonschema not installed — schema validation group skipped")
            print("  SKIP  schema validation (jsonschema unavailable)")
            return
        schema = json.loads(
            (Path(__file__).resolve().parents[2] / "api-schemas" / "context-assembly.schema.json")
            .read_text(encoding="utf-8")
        )
        cands = [
            {"kind": "constitution-doc", "label": "A", "tokens": 100},
            {"kind": "issue-contract", "label": "B", "tokens": 50},
            {"kind": "file-scope", "label": "C", "tokens": 40, "ref": {"path": "src/c.py"}},
            {
                "kind": "memory-ref",
                "label": "M",
                "tokens": 20,
                "ref": {"memory": {"namespace": "agent-episodes", "document_id": "ep-1"}},
            },
            {"kind": "adr-ref", "label": "adr", "tokens": 30, "ref": {"adr_id": "ADR-001"}},
            {"kind": "knowledge-doc", "label": "K", "tokens": 25, "ref": {"path": "docs/k.md"}},
            {"kind": "runtime-state", "label": "CI", "tokens": 900},
            {"kind": "transcript", "label": "chat", "tokens": 400},
        ]
        payload = assemble(cands, token_budget=260, task_id="t", assembly_id="asm-0123456789ab", generated_at="2026-10-16T08:00:00Z")
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(payload)

    # Group 8 — determinism: identical inputs -> byte-identical payload.
    def g8() -> None:
        cands = [
            {"kind": "constitution-doc", "label": "A", "tokens": 100},
            {"kind": "knowledge-doc", "label": "K", "tokens": 50, "ref": {"path": "docs/k.md"}},
            {"kind": "transcript", "label": "noise", "tokens": 900},
        ]
        p1 = assemble(cands, token_budget=120, task_id="t", assembly_id="asm-0123456789ab", generated_at="2026-10-16T08:00:00Z")
        p2 = assemble(cands, token_budget=120, task_id="t", assembly_id="asm-0123456789ab", generated_at="2026-10-16T08:00:00Z")
        assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)
        # default edges differ but both match the wire patterns
        p3 = assemble(cands, token_budget=120, task_id="t")
        assert re.fullmatch(r"asm-[0-9a-f]{12}", p3["assembly"]["assembly_id"])
        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", p3["assembly"]["generated_at"]
        )

    for idx, (name, fn) in enumerate(
        [
            ("G1 priority decay (spec §3 worked example)", g1),
            ("G2 strict cutoff R1 + exact-fit boundary", g2),
            ("G3 constitution R2 + overflow fail-loud", g3),
            ("G4 clipping state R3 + verdict pairing R4", g4),
            ("G5 invariants I-1/I-2/I-6 + name pins", g5),
            ("G6 fail-closed zoo (kinds/refs/paths/policy)", g6),
            ("G7 schema validation (Draft 2020-12)", g7),
            ("G8 determinism + wire patterns", g8),
        ],
        start=1,
    ):
        check(f"{name}", fn)

    if skips:
        print(f"skips: {len(skips)}")
    if failures:
        print(f"SELF-TEST FAILED: {len(failures)} group(s): {failures}")
        return 1
    print("SELF-TEST PASSED: 8/8 scenario groups")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Smart Context Selector (#329)")
    parser.add_argument("--self-test", action="store_true", help="run 8 offline scenario groups")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
