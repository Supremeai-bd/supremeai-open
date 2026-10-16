# Smart Context Selector — Layer 1-8 Priority-Ranked Context Assembly

> **Issue:** #29 · **Contract:** [`api-schemas/context-assembly.schema.json`](../api-schemas/context-assembly.schema.json) · **Status:** Specified (contract-first)
>
> This document is the SSOT for how a coding agent's working context is **assembled deterministically** before task start: which sources compete for the window, how priority decays across layers, and how the token budget clips — with every verdict recorded honestly in the payload.

---

## 1. Purpose & Scope

Agents fail on context starvation and context noise in equal measure. The Smart Context Selector answers both with one deterministic assembly pass:

1. **Rank** candidate context sources into 8 priority layers (§2).
2. **Decay** priority per layer so constitution always outranks noise (§3).
3. **Clip** at the token budget with a strict cutoff — no backfill, no cherry-picking (§4).
4. **Record** every inclusion/exclusion verdict in a machine-checkable payload (`context-assembly.schema.json`).

The output of the selector is a **ContextAssembly payload** — not prose. Downstream consumers (agent bootstraps, the [Agent Loop](AGENT_LOOP_SPEC.md), future MCP Tower tooling) read the payload, not a summary of it.

## 2. The Eight Layers

| # | Name | Sources | Rationale |
|---|------|---------|-----------|
| 1 | `constitution` | `AGENTS.md`, `AGENT_RULES.md` | The baseline every other document defers to. **Never clipped.** |
| 2 | `task-contract` | Task issue: mission, acceptance criteria, Touching Files | Defines "done" for this run. |
| 3 | `file-scope` | Declared Touching Files + adjacent tests/guards | The code surface this task may mutate. |
| 4 | `memory-sidecar` | Semantic memory hits (`memory-search.schema.json`, issue #36) | Prior episodes, resolved pitfalls, namespace-scoped facts. |
| 5 | `adr-history` | `docs/adr/ADR-*.md` | Prior architectural decisions that constrain the design. |
| 6 | `knowledge-items` | Specs, runbooks, governance docs (`docs/`) | Stable knowledge that shapes approach. |
| 7 | `environment-state` | CI check-run snapshots, telemetry samples (issue #38), branch state | Fresh runtime facts; useful but re-derivable. |
| 8 | `hygiene-noise` | Session transcripts, changelogs, chat excerpts | Lowest value per token; first to go. |

Layer numbers are **closed**: 1–8 only. The schema pins each layer number 1:1 to its name via `if/then` (mismatches are structurally impossible).

## 3. Priority Decay

```
priority(L) = round(base_priority · decay_factor^(L − 1), 3)      for L ∈ [1..8]
```

- `base_priority` ∈ [0, 1] — the priority of Layer 1.
- `decay_factor` ∈ (0, 1] — per-layer multiplier; `1` disables decay.
- Worked example with `base_priority = 1.0`, `decay_factor = 0.8`:

| L | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| priority | 1.0 | 0.8 | 0.64 | 0.512 | 0.41 | 0.328 | 0.262 | 0.21 |

Decay is a **policy, not a suggestion**: the schema carries the `SelectionPolicy` alongside the assembly so any validator can recompute and confirm every layer's `priority` (semantic invariant I-3, §7).

## 4. Deterministic Ordering & Strict-Cutoff Clipping

All candidate items across all layers are ordered by:

```
priority DESC → layer ASC → label ASC (lexicographic)
```

Inclusion then walks the ordered list once:

```text
remaining = token_budget
clip_point_seen = false
for item in ordered_items:
    if clip_point_seen:
        exclude(item, reason="budget_clipped")        # strict cutoff: no backfill
        continue
    if item.kind == "constitution-doc":
        include(item, reason="constitution_never_clipped")   # L1 is unclippable
        remaining -= item.tokens
        continue
    if item.tokens <= remaining:
        include(item, reason="priority_rank")
        remaining -= item.tokens
    else:
        exclude(item, reason="budget_clipped")
        clip_point_seen = true
```

**Rules:**

- **R1 — Strict cutoff.** The first item that does not fit marks the clip point; *every* later item is excluded even if it would fit alone. No backfill keeps the assembly honest and reproducible (a greedy knapsack would cherry-pick low-priority fragments and bury the clip point).
- **R2 — Constitution is unclippable.** Layer 1 items are always included; the token budget must be sized to admit them (fail-loud in the assembler if not).
- **R3 — Clipping state is bidirectional.** `budget_clipped == true` ⇔ `clipped_layers` non-empty (schema-enforced both ways).
- **R4 — Every verdict carries a reason.** `included: true/false` is always paired with `inclusion_reason` (`priority_rank`, `constitution_never_clipped`, `budget_clipped`).

## 5. Contract Reference

`api-schemas/context-assembly.schema.json` (Draft 2020-12, `additionalProperties: false` throughout):

| Node | Pins |
|------|------|
| `SelectionPolicy` | `token_budget` ≥ 1, `base_priority` ∈ [0,1], `decay_factor` ∈ (0,1], `strategy` closed to `priority_decay_strict_cutoff` (v1) |
| `ContextAssembly` | `assembly_id` = `asm-` + 12 hex, `generated_at` explicit RFC 3339 pattern, `layers` 1..8 entries, `tokens_used` ≥ 0, clipping state if/then (R3) |
| `ContextLayer` | `layer` ∈ 1..8, closed `name` enum, `priority` ∈ [0,1], layer↔name if/then pins (8 directions) |
| `ContextItem` | closed 9-value `kind` enum, `tokens` ≥ 1, verdict pair (`included` + `inclusion_reason`), kind→ref if/then pins |
| `ItemRef` | `path` (repo-relative, `..` rejected anywhere, absolute paths rejected), `memory` (`namespace` + `document_id` per memory-search vocabulary), `adr_id` (`ADR-\d{3,4}`) |

**Kind → layer mapping (semantic):** `constitution-doc`→L1, `issue-contract`→L2, `file-scope`/`adjacent-test`→L3, `memory-ref`→L4, `adr-ref`→L5, `knowledge-doc`→L6, `runtime-state`→L7, `transcript`→L8.

## 6. Sample Assembly Payload

Canonical example for task #29 with budget 6000, `base_priority = 1.0`, `decay_factor = 0.8`: Layers 1–6 fit (4650 tokens); the Layer-7 CI snapshot (1500 tokens) exceeds the remaining 1350 → strict cutoff clips L7 **and** L8 (R1).

```json
{
  "schema_version": "1.0",
  "selection": {
    "token_budget": 6000,
    "base_priority": 1.0,
    "decay_factor": 0.8,
    "strategy": "priority_decay_strict_cutoff"
  },
  "assembly": {
    "assembly_id": "asm-3f9c2a1d7b04",
    "task_id": "29",
    "generated_at": "2026-10-16T05:10:00Z",
    "tokens_used": 4650,
    "budget_clipped": true,
    "clipped_layers": [7, 8],
    "layers": [
      {
        "layer": 1,
        "name": "constitution",
        "priority": 1.0,
        "tokens": 900,
        "items": [
          {
            "kind": "constitution-doc",
            "label": "AGENTS.md — core constitution",
            "tokens": 600,
            "included": true,
            "inclusion_reason": "constitution_never_clipped",
            "ref": {}
          },
          {
            "kind": "constitution-doc",
            "label": "AGENT_RULES.md — behavior rules",
            "tokens": 300,
            "included": true,
            "inclusion_reason": "constitution_never_clipped",
            "ref": {}
          }
        ]
      },
      {
        "layer": 2,
        "name": "task-contract",
        "priority": 0.8,
        "tokens": 450,
        "items": [
          {
            "kind": "issue-contract",
            "label": "Issue #29 — mission, acceptance criteria, Touching Files",
            "tokens": 450,
            "included": true,
            "inclusion_reason": "priority_rank",
            "ref": {}
          }
        ]
      },
      {
        "layer": 3,
        "name": "file-scope",
        "priority": 0.64,
        "tokens": 1200,
        "items": [
          {
            "kind": "file-scope",
            "label": "api-schemas/context-assembly.schema.json",
            "tokens": 700,
            "included": true,
            "inclusion_reason": "priority_rank",
            "ref": { "path": "api-schemas/context-assembly.schema.json" }
          },
          {
            "kind": "adjacent-test",
            "label": "scripts/validate_schemas.py — schema guard",
            "tokens": 500,
            "included": true,
            "inclusion_reason": "priority_rank",
            "ref": { "path": "scripts/validate_schemas.py" }
          }
        ]
      },
      {
        "layer": 4,
        "name": "memory-sidecar",
        "priority": 0.512,
        "tokens": 700,
        "items": [
          {
            "kind": "memory-ref",
            "label": "Prior episode: schema mutation suite caught format-annotation gap",
            "tokens": 700,
            "included": true,
            "inclusion_reason": "priority_rank",
            "ref": {
              "memory": { "namespace": "agent-episodes", "document_id": "ep-9f8e7d6c5a4b" }
            }
          }
        ]
      },
      {
        "layer": 5,
        "name": "adr-history",
        "priority": 0.41,
        "tokens": 600,
        "items": [
          {
            "kind": "adr-ref",
            "label": "ADR-001 — founding decision record",
            "tokens": 600,
            "included": true,
            "inclusion_reason": "priority_rank",
            "ref": { "adr_id": "ADR-001" }
          }
        ]
      },
      {
        "layer": 6,
        "name": "knowledge-items",
        "priority": 0.328,
        "tokens": 800,
        "items": [
          {
            "kind": "knowledge-doc",
            "label": "AGENT_LOOP_SPEC.md — 8-tier verification contract",
            "tokens": 800,
            "included": true,
            "inclusion_reason": "priority_rank",
            "ref": {}
          }
        ]
      },
      {
        "layer": 7,
        "name": "environment-state",
        "priority": 0.262,
        "tokens": 0,
        "items": [
          {
            "kind": "runtime-state",
            "label": "CI check-runs snapshot (15 guards)",
            "tokens": 1500,
            "included": false,
            "inclusion_reason": "budget_clipped",
            "ref": {}
          }
        ]
      },
      {
        "layer": 8,
        "name": "hygiene-noise",
        "priority": 0.21,
        "tokens": 0,
        "items": [
          {
            "kind": "transcript",
            "label": "Previous session transcript excerpt",
            "tokens": 400,
            "included": false,
            "inclusion_reason": "budget_clipped",
            "ref": {}
          }
        ]
      }
    ]
  }
}
```

**Machine validation** (schema syntax + embedded sample, boundary-respecting — no fixture file):

```bash
python3 - <<'PY'
import json, re, jsonschema
doc = open('docs/CONTEXT_SELECTOR_SPEC.md').read()
payload = json.loads(re.search(
    r'## 6\. Sample Assembly Payload.*?```json\n(.*?)```', doc, re.S).group(1))
schema = json.load(open('api-schemas/context-assembly.schema.json'))
jsonschema.Draft202012Validator.check_schema(schema)
jsonschema.Draft202012Validator(schema).validate(payload)
print('sample payload: schema-valid (Draft 2020-12)')
PY
```

## 7. Semantic Invariants (cross-object; enforced by the verification suite)

JSON Schema cannot compare numbers across subtrees, so these are declared here and checked by the extraction suite above (extend the `PY` block to assert them):

- **I-1** `assembly.tokens_used == Σ layer.tokens` and each `layer.tokens == Σ included item.tokens`.
- **I-2** `assembly.tokens_used <= selection.token_budget`.
- **I-3** every `layer.priority == round(selection.base_priority · selection.decay_factor^(layer−1), 3)`.
- **I-4** included items precede excluded items in the global order (`priority DESC, layer ASC, label ASC`); excluded reasons are exactly `budget_clipped`.
- **I-5** every Layer-1 item has `inclusion_reason == "constitution_never_clipped"` (R2).
- **I-6** kind↔layer mapping of §5 holds for every item.

## 8. Fail-Closed Summary

- Unknown layer numbers/names → rejected (closed enums + 8 if/then pins).
- Unknown item kinds → rejected (closed 9-value enum).
- Kind/ref mismatch → rejected (`file-scope`/`adjacent-test` ⇒ `path`, `memory-ref` ⇒ `memory`, `adr-ref` ⇒ `adr_id`).
- Path traversal (`..` anywhere) and absolute paths → rejected by pattern.
- Clipping-state inconsistency (either direction) → rejected by if/then.
- New clipping strategies → require a `schema_version` bump; v1 admits exactly one.

## 9. Cross-Links

- [AGENT_LOOP_SPEC.md](AGENT_LOOP_SPEC.md) §4 — the 8-tier verification contract this spec's validation slots into.
- [instruction-envelope.schema.json](../api-schemas/instruction-envelope.schema.json) (issue #30) — the deterministic instruction envelope an assembled context feeds.
- [memory-search.schema.json](../api-schemas/memory-search.schema.json) (issue #36) — Layer-4 source vocabulary (namespace, document_id).
- [telemetry-log.schema.json](../api-schemas/telemetry-log.schema.json) (issue #38) — Layer-7 runtime-state provenance.
- [docs/adr/](adr/) (issue #44) — Layer-5 ADR history.
