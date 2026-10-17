# S10 — Ecosystem Scout Agent: External Intelligence & Surgical Adoption

Implements **#497** — `feat(agents): [ecosystem-agent] Autonomous Ecosystem
Scout`. Companion of #489 (S09 dispatch matrix, WO #499) and #498 (S11
extraction engine).

## 1. Deliverables

| File | Kind | Purpose |
|---|---|---|
| `scripts/agents/role_registry.py` | new | Operational role registry (criterion 1): registers `ecosystem-scout` with scoped weapons — read-only URL reader, `ast_parser`, `repo_inspector`, `artifact_writer` — validated as a superset of the S09 SSOT dispatch weapons, zero code-write leakage, fail-closed registration. |
| `scripts/agents/ecosystem_scout_reference.py` | new | `EcosystemDossier` schema (field-for-field mirror of the issue's TypeScript interface), the 4-phase dissection methodology as a typed pipeline, the **Surgical Extraction Guard** (anti-vending invariant, Gold Pearl 20–100 line budget, native zero-dep fitting, vendor-marker rejection, provenance hygiene), `scout_analyze_repository()` MCP-tool core (offline, deterministic), and `render_dossier_markdown()` standard-artifact export. |
| `tests/test_s10_ecosystem_scout.py` | new | 32 offline contract tests (dual-mode unittest + pytest). |
| This document | new | Spec + integration appendices (MCP control plane; continuous loop). |

## 2. The Surgical Need-Driven Extraction Doctrine

> কতটুকু দরকার, কীভাবে দরকার — পুরো কপি নয়, সেরা কোডটুকু নেওয়া

Machine-enforced (`validate_surgical_extraction`, fail-closed):

1. **Anti-Vending Invariant** — `full_repo_vending_prohibited` must be
   `True`; vendor markers (`git clone`, `npm install`, `pip install git+`,
   `vendored tree`, …) in an adaptation blueprint are rejected.
2. **Surgical AST Slicing** — `exact_components_needed` must name the Gold
   Pearl; `validate_gold_pearl_budget()` bounds a slice to 20–100 lines.
3. **Native Adaptation** — the blueprint must name `python` or `typescript`
   as the zero-dependency target (Python for `scripts/agents/`,
   `scripts/ci/`; TypeScript for control-plane/studio/sdk).
4. **Clean-Room & Attribution Hygiene** — `provenance_header()` emits the
   mandatory provenance block; `ADOPT_IMMEDIATELY` verdicts are illegal
   with an unknown upstream license.

## 3. Four-Phase Dissection (typed pipeline)

`PHASE_1_EXTRACTION → PHASE_2_DISSECTION → PHASE_3_AUDIT → PHASE_4_RFC`,
validated in order (`run_methodology`). Phase-1 gates enforce zero-hype
truth: evidence that self-describes as marketing/landing-page-only is
rejected; the RFC phase must emit the dossier artifact.

## 4. Verdict & Satellite Routing

`verdict ∈ {ADOPT_IMMEDIATELY, EXTRACT_PATTERNS_ONLY, MONITOR, REJECT}`;
`action_type ∈ {adopt_library, replicate_pattern, integrate_mcp}`; routing
targets are validated against `CANONICAL_SATELLITES` (empty routing is
rejected — every dossier must route into the 11-satellite federation).
Verdict-specific gates: adoption requires a known license; `REJECT` must
document prohibited practices.

## 5. MCP Tool Reference (criterion 3)

`scout_analyze_repository(ScoutInputs) -> EcosystemDossier` is the
pure-core reference: manifests (`manifest_json` / `manifest_yaml`) and the
file tree are parsed into runtime truth (`tech_stack`, heavy-dependency
flags); missing manifests, empty trees, malformed JSON or an
empty parsed stack all raise `DossierError`. Network I/O stays in the
tower adapter — this module is offline and deterministic (no credential
surface, stdlib only).

## 6. Appendix A — MCP control-plane exposure (out-of-lane repo, spec hunk)

`infrastructure/mcp-control-plane` is outside the bridge lane; the tower
team applies the equivalent of this registration after review:

```typescript
// tools/scout.ts — expose scout_analyze_repository (issue #497 criterion 3)
server.tool("scout_analyze_repository", {
  repository: z.string().min(1),
  license: z.string().default("unknown"),
  manifest_json: z.string().optional(),
  manifest_yaml: z.string().optional(),
  file_tree: z.array(z.string()).default([]),
}, async (args) => {
  // Adapter responsibility: perform fetches, then hand structured facts
  // to the pure core (scripts/agents/ecosystem_scout_reference.py).
  const dossier = await fetchAndParse(args);            // network I/O here
  return { content: [{ type: "text",
                       text: renderDossierMarkdown(dossier) }] };
});
```

## 7. Appendix B — Continuous-loop integration (content-anchored hunks)

### B1 — `scripts/agents/continuous_agent_loop.py` (pre-existing on main;
anchors byte-verified against main @ 082fce0)

```python
     "platform-guardian": "External AI provider sentry & failover toggle",   # ← after S09 Hunk B lands
 }
```

becomes:

```python
     "platform-guardian": "External AI provider sentry & failover toggle",
+    # S10 (#497): Ecosystem Scout — benchmarking / evaluation requests.
+    "ecosystem-scout": "External intelligence, dissection & adoption RFC (read-only)",
 }
```

### B2 — label-plane trigger (applies to `scripts/agents/role_trigger_matrix.py`
**after WO #499 lands**; anchors are WO #499's delivered bytes)

```python
 LABEL_PRIORITY: Final = ("status:runway", "gate:pre-landing", "status:claimed")
```

becomes:

```python
-LABEL_PRIORITY: Final = ("status:runway", "gate:pre-landing", "status:claimed")
+LABEL_PRIORITY: Final = ("status:runway", "gate:pre-landing",
+                         "status:claimed", "area:ecosystem")
```

```python
     "status:claimed": "coder",          # priority 2 — claimed task execution
 })
```

becomes:

```python
     "status:claimed": "coder",          # priority 2 — claimed task execution
+    "area:ecosystem": "ecosystem-scout",  # priority 3 — #497 benchmarking requests
 })
```

This makes "issue or prompt requests repository benchmarking or ecosystem
evaluation" (criterion 4) a **deterministic label-plane dispatch** — the
issue labels itself `area:ecosystem` and the loop invokes the Scout role;
no keyword scanning is introduced.

## 8. Test evidence

32 offline tests green in dual mode (`python3 -m unittest
test_s10_ecosystem_scout -v` / `pytest -q`), plus `--self-test` green on
all three `scripts/agents/` modules. Coverage: registry fail-closed
registration + read-only invariant, anti-vending/vendor-marker matrix,
Gold Pearl budget bounds, provenance hygiene, verdict-specific gates,
4-phase order/marketing rejection/RFC artifact, manifest-driven core with
fail-closed inputs, artifact export with Bengali doctrine sections.
