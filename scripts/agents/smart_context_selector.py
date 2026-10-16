#!/usr/bin/env python3
"""Smart Context Selector — deterministic Layer 1-8 priority-ranked context assembly.

Implements the landed SSOT contract (issue #29 spec, wired per issue #329):
  - docs/CONTEXT_SELECTOR_SPEC.md             (decay, strict cutoff, verdicts, invariants)
  - api-schemas/context-assembly.schema.json  (wire payload, closed enums, ref pins)

Zero-dependency (stdlib only, AGENT_RULES.md §13). Fail-closed here: invalid
policies, candidates or budgets raise before any payload is produced. The
continuous_agent_loop wiring is deliberately fail-open and env-gated
(SUPREME_CONTEXT_SELECTOR) — when disabled or on any wiring failure the task
envelope stays byte-identical to pre-#329 output (AGENT_LOOP_SPEC.md §4b
parity).

Core rules implemented (spec §4):
  R1 strict cutoff   — the first non-fitting item marks the clip point; every
                       later item is excluded even if it would fit alone.
  R2 L1 unclippable  — constitution items are always included; a budget that
                       cannot admit them fails loudly (AssemblyError).
  R3 bidirectional   — budget_clipped == true  <=>  clipped_layers non-empty.
  R4 honest verdicts — every item carries included + inclusion_reason.

Self-test (offline, no network, no pytest):
  python3 scripts/agents/smart_context_selector.py --self-test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTEXT_SELECTOR_VERSION = "smart-context-selector/1"
SCHEMA_VERSION = "1.0"  # mirrors api-schemas/context-assembly.schema.json

# Closed vocabulary (spec §2/§5 — the schema pins these; drift here is a bug).
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
NAME_TO_LAYER: dict[str, int] = {name: layer for layer, name in LAYER_NAMES.items()}
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
CONTEXT_KINDS = frozenset(KIND_TO_LAYER)

# Closed verdict vocabulary (spec §4 R4).
INCLUSION_REASONS = ("priority_rank", "constitution_never_clipped", "budget_clipped")
STRATEGY_V1 = "priority_decay_strict_cutoff"

# Mirrors ItemRef.properties.path pattern: repo-relative, no traversal, no
# absolute paths, no leading dot/slash segments (fail-closed, spec §8).
REF_PATH_PATTERN = re.compile(r"^(?!.*\.\.)[A-Za-z0-9_][A-Za-z0-9_./-]{0,255}$")
ADR_ID_PATTERN = re.compile(r"^ADR-\d{3,4}$")


class PolicyError(ValueError):
    """Invalid SelectionPolicy (budget/priority/decay/strategy) — fail-closed."""


class CandidateError(ValueError):
    """Invalid context candidate (kind, label, tokens, ref, layer mapping)."""


class AssemblyError(ValueError):
    """Assembly cannot proceed honestly (e.g. budget cannot admit Layer 1)."""


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate: whitespace-delimited chunk count, min 1.

    A coarse but stable proxy (≈ words) — good enough to rank sources against
    a budget, and byte-stable across runs/platforms (no locale, no clock).
    """
    if not text or not text.strip():
        return 1
    return max(1, len(text.split()))


class Candidate:
    """One candidate context item BEFORE the assembly verdict (spec §2)."""

    __slots__ = ("kind", "label", "tokens", "ref")

    def __init__(
        self,
        kind: str,
        label: str,
        tokens: int,
        ref: dict[str, Any] | None = None,
    ) -> None:
        if kind not in CONTEXT_KINDS:
            raise CandidateError(
                f"invalid kind '{kind}': must be one of {sorted(CONTEXT_KINDS)}"
            )
        if not isinstance(label, str) or not (1 <= len(label) <= 256):
            raise CandidateError(
                f"invalid label for kind '{kind}': must be a string of length 1..256"
            )
        if isinstance(tokens, bool) or not isinstance(tokens, int) or not (1 <= tokens <= 100000):
            raise CandidateError(
                f"invalid tokens {tokens!r} for '{label}': must be an integer in 1..100000"
            )
        ref = self._validate_ref(kind, ref)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "tokens", tokens)
        object.__setattr__(self, "ref", ref)

    @staticmethod
    def _validate_ref(kind: str, ref: dict[str, Any] | None) -> dict[str, Any] | None:
        """Kind→ref pins (spec §5/§8): wrong/missing shape for ref-carrying
        kinds is rejected; extra keys are never invented by the selector."""
        if ref is None:
            if kind in ("file-scope", "adjacent-test", "memory-ref", "adr-ref"):
                raise CandidateError(
                    f"kind '{kind}' requires a ref (file-scope/adjacent-test -> path, "
                    "memory-ref -> memory, adr-ref -> adr_id)"
                )
            return None
        if not isinstance(ref, dict):
            raise CandidateError(f"ref for kind '{kind}' must be an object")
        extra = set(ref) - {"path", "memory", "adr_id"}
        if extra:
            raise CandidateError(f"ref carries unknown keys for kind '{kind}': {sorted(extra)}")
        if kind not in ("file-scope", "adjacent-test", "memory-ref", "adr-ref"):
            # Non-pinned kinds (constitution-doc, issue-contract, knowledge-doc,
            # runtime-state, transcript) must carry no ref keys at all — the
            # sample payload convention is an explicit empty ref object. A
            # stray path/memory/adr_id is a kind/ref mismatch (spec §8).
            if ref:
                raise CandidateError(
                    f"kind '{kind}' must not carry ref keys {sorted(ref)} — "
                    "kind/ref mismatch (spec §8)"
                )
            return {}
        if kind in ("file-scope", "adjacent-test"):
            path = ref.get("path")
            if not isinstance(path, str):
                raise CandidateError(f"kind '{kind}' requires ref.path (string)")
            if not REF_PATH_PATTERN.match(path):
                raise CandidateError(
                    f"ref.path '{path}' rejected: must be repo-relative, traversal-free "
                    "('..' anywhere is refused) and never absolute"
                )
        if kind == "memory-ref":
            memory = ref.get("memory")
            if not isinstance(memory, dict):
                raise CandidateError("kind 'memory-ref' requires ref.memory (object)")
            missing = {"namespace", "document_id"} - set(memory)
            if missing:
                raise CandidateError(f"ref.memory missing keys: {sorted(missing)}")
        if kind == "adr-ref":
            adr_id = ref.get("adr_id")
            if not isinstance(adr_id, str) or not ADR_ID_PATTERN.match(adr_id):
                raise CandidateError(
                    f"ref.adr_id '{adr_id}' rejected: must match ADR-\\d{{3,4}}"
                )
        return dict(ref)

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return f"Candidate(kind={self.kind!r}, label={self.label!r}, tokens={self.tokens})"


def build_selection_policy(
    token_budget: int,
    base_priority: float = 1.0,
    decay_factor: float = 0.8,
    strategy: str = STRATEGY_V1,
) -> dict[str, Any]:
    """Build a validated SelectionPolicy (schema SelectionPolicy node)."""
    if isinstance(token_budget, bool) or not isinstance(token_budget, int) or not (
        1 <= token_budget <= 1000000
    ):
        raise PolicyError(f"token_budget must be an integer in 1..1000000 (got {token_budget!r})")
    if isinstance(base_priority, bool) or not isinstance(base_priority, (int, float)) or not (
        0 <= base_priority <= 1
    ):
        raise PolicyError(f"base_priority must be a number in [0,1] (got {base_priority!r})")
    if isinstance(decay_factor, bool) or not isinstance(decay_factor, (int, float)) or not (
        0 < decay_factor <= 1
    ):
        raise PolicyError(
            f"decay_factor must be a number in (0,1] (got {decay_factor!r}); "
            "0 would zero-out every layer after L1 and is refused"
        )
    if strategy != STRATEGY_V1:
        raise PolicyError(
            f"strategy must be '{STRATEGY_V1}' for schema_version {SCHEMA_VERSION}; "
            "new strategies require a contract version bump (spec §8)"
        )
    return {
        "token_budget": token_budget,
        "base_priority": float(base_priority),
        "decay_factor": float(decay_factor),
        "strategy": strategy,
    }


def layer_priority(policy: dict[str, Any], layer: int) -> float:
    """priority(L) = round(base_priority · decay_factor^(L-1), 3)   (spec §3, I-3)."""
    return round(
        float(policy["base_priority"]) * (float(policy["decay_factor"]) ** (layer - 1)), 3
    )


def _validate_layer_items(layer_items: dict[int, list[Candidate]]) -> dict[int, list[Candidate]]:
    """Layer↔candidate consistency: layer numbers closed 1..8, names pinned,
    kind→layer mapping holds (I-6), labels unique within a layer (deterministic
    tie-break needs distinguishable labels)."""
    clean: dict[int, list[Candidate]] = {}
    for layer, items in layer_items.items():
        if isinstance(layer, bool) or not isinstance(layer, int) or layer not in LAYER_NAMES:
            raise CandidateError(f"layer {layer!r} is outside the closed 1..8 range")
        if not items:
            continue  # empty layers are omitted from the payload (schema minItems: 1)
        seen_labels: set[str] = set()
        for item in items:
            if not isinstance(item, Candidate):
                raise CandidateError(f"layer {layer} carries a non-Candidate item: {item!r}")
            expected = KIND_TO_LAYER[item.kind]
            if expected != layer:
                raise CandidateError(
                    f"kind '{item.kind}' maps to layer {expected}, "
                    f"but was filed under layer {layer} (item: {item.label!r})"
                )
            if item.label in seen_labels:
                raise CandidateError(
                    f"duplicate label '{item.label}' within layer {layer} — "
                    "the lexicographic tie-break requires unique labels"
                )
            seen_labels.add(item.label)
        clean[layer] = list(items)
    return clean


def _default_assembly_id(task_id: str, policy: dict[str, Any], items: list[Candidate]) -> str:
    """Deterministic assembly id: asm- + first 12 hex of the content digest.

    Keeps the payload reproducible (same inputs -> same id) without a clock.
    """
    digest_input = json.dumps(
        {
            "task_id": task_id,
            "policy": policy,
            "items": [
                {"kind": c.kind, "label": c.label, "tokens": c.tokens, "ref": c.ref}
                for c in items
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "asm-" + hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:12]


def assemble_context(
    task_id: str,
    policy: dict[str, Any],
    layer_items: dict[int, list[Candidate]],
    *,
    assembly_id: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble the ContextAssembly payload (spec §4 walk, schema-exact).

    Deterministic given (task_id, policy, layer_items, generated_at): the
    ordering walk and every verdict are pure functions of the inputs.
    """
    # Re-validate through the SSOT policy builder (fail-closed on any drift).
    policy = build_selection_policy(
        token_budget=policy["token_budget"],
        base_priority=policy["base_priority"],
        decay_factor=policy["decay_factor"],
        strategy=policy.get("strategy", STRATEGY_V1),
    )
    if not isinstance(task_id, str) or not (1 <= len(task_id) <= 128):
        raise AssemblyError(f"task_id must be a string of length 1..128 (got {task_id!r})")
    clean_layers = _validate_layer_items(layer_items)

    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not re.match(
        r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$",
        generated_at,
    ):
        raise AssemblyError(f"generated_at must be RFC 3339 (got {generated_at!r})")

    # Global order: priority DESC -> layer ASC -> label ASC (spec §4).
    priorities = {layer: layer_priority(policy, layer) for layer in clean_layers}
    ordered: list[tuple[int, Candidate]] = sorted(
        ((layer, item) for layer, items in clean_layers.items() for item in items),
        key=lambda pair: (-priorities[pair[0]], pair[0], pair[1].label),
    )

    remaining = policy["token_budget"]
    clip_point_seen = False
    verdicts: list[tuple[int, Candidate, bool, str]] = []
    for layer, item in ordered:
        if clip_point_seen:
            verdicts.append((layer, item, False, "budget_clipped"))  # R1: no backfill
            continue
        if item.kind == "constitution-doc":  # R2: L1 is unclippable
            verdicts.append((layer, item, True, "constitution_never_clipped"))
            remaining -= item.tokens
            continue
        if item.tokens <= remaining:
            verdicts.append((layer, item, True, "priority_rank"))
            remaining -= item.tokens
        else:
            verdicts.append((layer, item, False, "budget_clipped"))
            clip_point_seen = True

    # R2 fail-loud: a budget that cannot admit the constitution is a policy bug.
    l1_spent = sum(c.tokens for l, c, inc, _ in verdicts if l == 1 and inc)
    if l1_spent > policy["token_budget"]:
        raise AssemblyError(
            f"token_budget {policy['token_budget']} cannot admit Layer 1 "
            f"(constitution needs {l1_spent}) — size the budget to admit L1 (spec §4 R2)"
        )

    # Build layers (only those with candidates), layer ASC, schema-exact nodes.
    layers_out: list[dict[str, Any]] = []
    clipped_layers: list[int] = []
    tokens_used = 0
    for layer in sorted(clean_layers):
        layer_verdicts = [v for v in verdicts if v[0] == layer]
        included_tokens = sum(c.tokens for _, c, inc, _ in layer_verdicts if inc)
        items_out = []
        for _, cand, included, reason in layer_verdicts:
            entry: dict[str, Any] = {
                "kind": cand.kind,
                "label": cand.label,
                "tokens": cand.tokens,
                "included": included,
                "inclusion_reason": reason,
            }
            if cand.ref is not None:
                entry["ref"] = cand.ref
            elif cand.kind in ("constitution-doc", "issue-contract", "knowledge-doc",
                               "runtime-state", "transcript"):
                entry["ref"] = {}  # sample-payload convention: explicit empty ref object
            items_out.append(entry)
        tokens_used += included_tokens
        layers_out.append(
            {
                "layer": layer,
                "name": LAYER_NAMES[layer],
                "priority": priorities[layer],
                "tokens": included_tokens,
                "items": items_out,
            }
        )
        for _, _, included, reason in layer_verdicts:
            if not included and reason == "budget_clipped" and layer not in clipped_layers:
                clipped_layers.append(layer)

    clipped_layers.sort()
    budget_clipped = bool(clipped_layers)  # R3, both directions
    if assembly_id is None:
        assembly_id = _default_assembly_id(
            task_id,
            policy,
            [item for items in clean_layers.values() for item in items],
        )

    # I-2 fail-loud: accounting may never exceed the budget (L1 unclippable is
    # guarded above; this belt-and-braces check keeps the invariant honest).
    if tokens_used > policy["token_budget"]:
        raise AssemblyError(
            f"assembled {tokens_used} tokens exceeds budget {policy['token_budget']} — "
            "refusing to emit a payload that violates I-2"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "selection": dict(policy),
        "assembly": {
            "assembly_id": assembly_id,
            "task_id": task_id,
            "generated_at": generated_at,
            "tokens_used": tokens_used,
            "budget_clipped": budget_clipped,
            "clipped_layers": clipped_layers,
            "layers": layers_out,
        },
    }


# --- semantic invariants (spec §7) — reusable by tests and future validators --

def check_invariants(payload: dict[str, Any]) -> list[str]:
    """Recompute I-1..I-6 on a payload; return a list of violation strings
    (empty list = all invariants hold)."""
    violations: list[str] = []
    assembly = payload["assembly"]
    selection = payload["selection"]

    layer_sum = 0
    for layer in assembly["layers"]:
        item_sum = sum(it["tokens"] for it in layer["items"] if it["included"])
        if layer["tokens"] != item_sum:
            violations.append(
                f"I-1: layer {layer['layer']} tokens {layer['tokens']} != Σ included {item_sum}"
            )
        layer_sum += layer["tokens"]
        expected_priority = layer_priority(selection, layer["layer"])
        if layer["priority"] != expected_priority:
            violations.append(
                f"I-3: layer {layer['layer']} priority {layer['priority']} != "
                f"expected {expected_priority}"
            )
        for it in layer["items"]:
            expected_kind_layer = KIND_TO_LAYER[it["kind"]]
            if expected_kind_layer != layer["layer"]:
                violations.append(
                    f"I-6: kind '{it['kind']}' in layer {layer['layer']} "
                    f"(expected layer {expected_kind_layer})"
                )
            if it["included"] and it["inclusion_reason"] not in ("priority_rank", "constitution_never_clipped"):
                violations.append(
                    f"I-4: included item '{it['label']}' has reason "
                    f"'{it['inclusion_reason']}'"
                )
    if assembly["tokens_used"] != layer_sum:
        violations.append(
            f"I-1: tokens_used {assembly['tokens_used']} != Σ layers {layer_sum}"
        )
    if assembly["tokens_used"] > selection["token_budget"]:
        violations.append("I-2: tokens_used exceeds token_budget")

    # I-4: included items precede excluded items in the global order; excluded
    # reasons are exactly budget_clipped.
    flat = [
        (layer["layer"], it)
        for layer in assembly["layers"]
        for it in layer["items"]
    ]
    flat_sorted = sorted(
        flat,
        key=lambda pair: (
            -layer_priority(selection, pair[0]),
            pair[0],
            pair[1]["label"],
        ),
    )
    seen_excluded = False
    for _, it in flat_sorted:
        if not it["included"]:
            seen_excluded = True
            if it["inclusion_reason"] != "budget_clipped":
                violations.append(
                    f"I-4: excluded item '{it['label']}' carries reason "
                    f"'{it['inclusion_reason']}' (must be budget_clipped)"
                )
        elif seen_excluded:
            violations.append(
                f"I-4: included item '{it['label']}' appears after the clip point "
                "(strict cutoff forbids backfill)"
            )

    # I-5: every L1 item is constitution_never_clipped.
    for layer in assembly["layers"]:
        if layer["layer"] == 1:
            for it in layer["items"]:
                if it["inclusion_reason"] != "constitution_never_clipped":
                    violations.append(
                        f"I-5: L1 item '{it['label']}' has reason "
                        f"'{it['inclusion_reason']}'"
                    )

    # R3: clipping state is bidirectional.
    if assembly["budget_clipped"] != bool(assembly["clipped_layers"]):
        violations.append("R3: budget_clipped and clipped_layers disagree")
    if assembly["budget_clipped"] and not assembly["clipped_layers"]:
        violations.append("R3: budget_clipped true with empty clipped_layers")

    return violations


def render_context_assembly(payload: dict[str, Any]) -> str:
    """Render the deterministic prompt digest for a ContextAssembly payload.

    The digest is byte-stable for identical inputs (no clock, no randomness):
    generated_at is deliberately NOT rendered so the loop can embed the block
    into the specialist prompt without breaking envelope determinism. The
    full wire payload remains available to consumers that need the audit view.
    """
    assembly = payload["assembly"]
    selection = payload["selection"]
    lines: list[str] = []
    lines.append("### 🧠 Assembled Context (smart-context-selector)")
    clip_note = (
        f"clipped layers: {', '.join(str(l) for l in assembly['clipped_layers'])}"
        if assembly["budget_clipped"]
        else "no clipping (everything fit)"
    )
    lines.append(
        f"Budget {selection['token_budget']} tok · used {assembly['tokens_used']} tok · "
        f"strategy {selection['strategy']} · {clip_note}"
    )
    lines.append("")
    lines.append("Included sources (priority order — strict cutoff, no backfill):")
    ranked: list[tuple[float, int, str, str]] = []
    for layer in assembly["layers"]:
        for it in layer["items"]:
            if it["included"]:
                ranked.append(
                    (layer["priority"], layer["layer"], it["label"], it["tokens"])
                )
    for priority, layer_no, label, tokens in ranked:
        lines.append(f"- [L{layer_no} {priority:g}] {label} ({tokens} tok)")
    if assembly["budget_clipped"]:
        lines.append("")
        lines.append("Excluded (budget_clipped — strict cutoff, no backfill):")
        for layer in assembly["layers"]:
            for it in layer["items"]:
                if not it["included"]:
                    lines.append(
                        f"- [L{layer['layer']} {layer['priority']:g}] "
                        f"{it['label']} ({it['tokens']} tok)"
                    )
    lines.append("")
    lines.append(
        f"assembly {assembly['assembly_id']} · SSOT: docs/CONTEXT_SELECTOR_SPEC.md "
        "(wire payload: api-schemas/context-assembly.schema.json)"
    )
    return "\n".join(lines)


# --- offline self-test --------------------------------------------------------

def _self_test() -> int:
    """Offline scenario harness: 10 groups, fail-loud on the first breach."""
    failures: list[str] = []

    def check(name: str, fn) -> None:
        try:
            fn()
            print(f"  PASS | {name}")
        except AssertionError as exc:
            failures.append(f"{name}: {exc}")
            print(f"  FAIL | {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 — honest failure reporting
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"  ERROR | {name}: {type(exc).__name__}: {exc}")

    def cand(kind: str, label: str, tokens: int, ref: dict | None = None) -> Candidate:
        return Candidate(kind, label, tokens, ref)

    # G1 — decay math (I-3): spec §3 worked example table.
    def g1() -> None:
        policy = build_selection_policy(6000, 1.0, 0.8)
        expected = {1: 1.0, 2: 0.8, 3: 0.64, 4: 0.512, 5: 0.41, 6: 0.328, 7: 0.262, 8: 0.21}
        for layer, want in expected.items():
            got = layer_priority(policy, layer)
            assert got == want, f"layer {layer}: {got} != {want}"
        assert layer_priority(build_selection_policy(6000, 1.0, 1.0), 8) == 1.0, "d=1 disables decay"

    # G2 — deterministic ordering: priority DESC -> layer ASC -> label ASC.
    def g2() -> None:
        policy = build_selection_policy(100000, 1.0, 0.8)
        payload = assemble_context(
            "t",
            policy,
            {
                2: [cand("issue-contract", "b-item", 10), cand("issue-contract", "a-item", 10)],
                3: [cand("file-scope", "z.py", 10, {"path": "z.py"})],
            },
            generated_at="2026-10-16T00:00:00Z",
        )
        flat = [(l["layer"], it["label"]) for l in payload["assembly"]["layers"] for it in l["items"]]
        assert flat == [
            (2, "a-item"), (2, "b-item"), (3, "z.py"),
        ], f"unexpected order: {flat}"

    # G3 — strict cutoff, no backfill (R1): a later tiny item stays excluded.
    def g3() -> None:
        policy = build_selection_policy(30, 1.0, 0.8)
        payload = assemble_context(
            "t",
            policy,
            {
                1: [cand("constitution-doc", "AGENTS.md", 10)],
                3: [cand("file-scope", "big.py", 25, {"path": "big.py"})],
                4: [cand("memory-ref", "tiny memory", 1, {"memory": {"namespace": "n", "document_id": "d"}})],
            },
            generated_at="2026-10-16T00:00:00Z",
        )
        a = payload["assembly"]
        assert a["tokens_used"] == 10, f"L1 only should be included, got {a['tokens_used']}"
        assert a["budget_clipped"] is True and a["clipped_layers"] == [3, 4], a
        verdicts = {
            it["label"]: (it["included"], it["inclusion_reason"])
            for l in a["layers"] for it in l["items"]
        }
        assert verdicts["big.py"] == (False, "budget_clipped")
        assert verdicts["tiny memory"] == (False, "budget_clipped"), "no-backfill violated"

    # G4 — R2: constitution never clipped; impossible budget fails loudly.
    def g4() -> None:
        policy = build_selection_policy(15, 1.0, 0.8)
        payload = assemble_context(
            "t",
            policy,
            {1: [cand("constitution-doc", "AGENTS.md", 10), cand("constitution-doc", "AGENT_RULES.md", 5)]},
            generated_at="2026-10-16T00:00:00Z",
        )
        for it in payload["assembly"]["layers"][0]["items"]:
            assert it["included"] and it["inclusion_reason"] == "constitution_never_clipped", it
        try:
            assemble_context("t", build_selection_policy(9, 1.0, 0.8),
                             {1: [cand("constitution-doc", "AGENTS.md", 10)]},
                             generated_at="2026-10-16T00:00:00Z")
            raise AssertionError("budget smaller than L1 must fail loudly")
        except AssemblyError:
            pass

    # G5 — R4: every item carries a verdict pair; reasons from closed vocab.
    def g5() -> None:
        policy = build_selection_policy(50, 1.0, 0.8)
        payload = assemble_context(
            "t",
            policy,
            {
                1: [cand("constitution-doc", "AGENTS.md", 10)],
                2: [cand("issue-contract", "issue body", 50)],
            },
            generated_at="2026-10-16T00:00:00Z",
        )
        for l in payload["assembly"]["layers"]:
            for it in l["items"]:
                assert isinstance(it["included"], bool), it
                assert it["inclusion_reason"] in INCLUSION_REASONS, it
                assert it["included"] == (it["inclusion_reason"] != "budget_clipped"), it

    # G6 — accounting + R3 (I-1/I-2): exact sums, no-backfill edge at 0 remaining.
    def g6() -> None:
        policy = build_selection_policy(20, 1.0, 0.5)
        payload = assemble_context(
            "t",
            policy,
            {
                1: [cand("constitution-doc", "AGENTS.md", 10)],
                2: [cand("issue-contract", "fits exactly", 10)],
                3: [cand("file-scope", "x.py", 1, {"path": "x.py"})],
            },
            generated_at="2026-10-16T00:00:00Z",
        )
        a = payload["assembly"]
        assert a["tokens_used"] == 20 == sum(l["tokens"] for l in a["layers"])
        assert a["budget_clipped"] is True and a["clipped_layers"] == [3]
        assert check_invariants(payload) == [], check_invariants(payload)

    # G7 — fail-closed validation battery (spec §8).
    def g7() -> None:
        for kwargs in (
            {"token_budget": 0}, {"token_budget": -5},
            {"token_budget": 10, "base_priority": 1.5},
            {"token_budget": 10, "base_priority": -0.1},
            {"token_budget": 10, "decay_factor": 0},
            {"token_budget": 10, "decay_factor": -1},
            {"token_budget": 10, "strategy": "greedy_knapsack"},
        ):
            try:
                build_selection_policy(**kwargs)
                raise AssertionError(f"policy accepted: {kwargs}")
            except PolicyError:
                pass
        for builder in (
            lambda: Candidate("not-a-kind", "x", 5),
            lambda: Candidate("file-scope", "x", 5),                       # missing ref
            lambda: Candidate("file-scope", "x", 5, {"memory": {}}),       # wrong pin
            lambda: Candidate("adr-ref", "x", 5, {"adr_id": "ADR-12"}),    # bad id
            lambda: Candidate("constitution-doc", "x", 5, {"path": "a"}),  # stray pin
            lambda: Candidate("issue-contract", "", 5),                    # empty label
            lambda: Candidate("issue-contract", "x", 0),                   # tokens < 1
            lambda: Candidate("file-scope", "x", 5, {"path": "../etc"}),   # traversal
            lambda: Candidate("file-scope", "x", 5, {"path": "/abs"}),     # absolute
        ):
            try:
                builder()
                raise AssertionError(f"candidate accepted: {builder}")
            except CandidateError:
                pass
        try:  # kind ↔ layer mismatch (I-6) must be structurally impossible
            assemble_context("t", build_selection_policy(50),
                             {3: [cand("issue-contract", "misfiled", 5)]},
                             generated_at="2026-10-16T00:00:00Z")
            raise AssertionError("misfiled kind accepted")
        except CandidateError:
            pass

    # G8 — determinism: identical inputs -> byte-identical payload + digest.
    def g8() -> None:
        def build() -> dict:
            return assemble_context(
                "task-329",
                build_selection_policy(6000, 1.0, 0.8),
                {
                    1: [cand("constitution-doc", "AGENTS.md — core constitution", 600)],
                    3: [cand("file-scope", "scripts/agents/continuous_agent_loop.py", 1200,
                             {"path": "scripts/agents/continuous_agent_loop.py"})],
                },
                generated_at="2026-10-16T00:00:00Z",
            )
        p1, p2 = build(), build()
        assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)
        assert render_context_assembly(p1) == render_context_assembly(p2)
        assert "generated_at" not in render_context_assembly(p1), "digest must be clock-free"
        assert render_context_assembly(p1).startswith("### 🧠 Assembled Context")

    # G9 — estimate_tokens honesty: stable, min 1, monotone.
    def g9() -> None:
        assert estimate_tokens("") == 1 and estimate_tokens("   ") == 1
        assert estimate_tokens("one two three") == 3
        assert estimate_tokens("a" * 100) >= estimate_tokens("a" * 10)
        assert estimate_tokens("same input") == estimate_tokens("same " * 1 + "input")

    # G10 — schema conformance: payload validates against the REAL repo schema
    # via the repo's own stdlib validator (zero new dependencies).
    def g10() -> None:
        schema_path = Path(__file__).resolve().parents[2] / "api-schemas" / "context-assembly.schema.json"
        assert schema_path.is_file(), f"missing {schema_path}"
        sys.path.insert(0, str(schema_path.parents[1] / "scripts"))
        from validate_schemas import SchemaValidator  # noqa: E402

        validator = SchemaValidator(json.loads(schema_path.read_text(encoding="utf-8")))
        payload = assemble_context(
            "task-329",
            build_selection_policy(6000, 1.0, 0.8),
            {
                1: [cand("constitution-doc", "AGENTS.md — core constitution", 600)],
                2: [cand("issue-contract", "Issue #329 — mission", 450)],
                3: [cand("file-scope", "scripts/agents/continuous_agent_loop.py", 1200,
                         {"path": "scripts/agents/continuous_agent_loop.py"})],
                5: [cand("adr-ref", "ADR-001 — open foundation boundary", 300,
                         {"adr_id": "ADR-001"})],
            },
            generated_at="2026-10-16T00:00:00Z",
        )
        errs = validator.validate(payload)
        assert errs == [], f"schema violations: {errs[:5]}"
        assert check_invariants(payload) == []

    for name, fn in (
        ("G1 decay math (I-3)", g1),
        ("G2 deterministic ordering", g2),
        ("G3 strict cutoff, no backfill (R1)", g3),
        ("G4 constitution unclippable (R2)", g4),
        ("G5 honest verdict pairs (R4)", g5),
        ("G6 accounting + R3 (I-1/I-2)", g6),
        ("G7 fail-closed validation battery", g7),
        ("G8 determinism (payload + digest)", g8),
        ("G9 estimate_tokens honesty", g9),
        ("G10 schema conformance (real contract)", g10),
    ):
        check(name, fn)

    print(f"{10 - len(failures)}/10 self-test groups passed")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smart Context Selector (Layer 1-8 assembly)")
    parser.add_argument("--self-test", action="store_true", help="run the offline scenario harness and exit")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
