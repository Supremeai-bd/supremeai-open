# S11 — Surgical Code & Pattern Extraction Engine

Implements **#498** — `feat(agents): [surgical-adoption]` (companion of
#489/S09 WO #499 and #497/S10 WO #501).

## 1. Deliverables

| File | Kind | Purpose |
|---|---|---|
| `scripts/agents/scout_extractor.py` | new | Gold Pearl extraction engine: Python AST slicing with usage-driven import analysis; TS brace-balanced slicing; native zero-bloat fitting (stdlib-only adaptation stubs with provenance headers); `scout_transplant_patch` generator (atomic single-new-file patches into canonical satellites); the two live benchmark blueprints (REA + Moli) as structured doctrine. Extraction SSOT for the Gold Pearl budget constants. |
| `scripts/ci/vendored_tree_guard.py` | new | CI sanitization guard (criterion 1): deterministic R1-R5 rules flag PRs adding large 3rd-party vendored trees; exit 0 clean / 2 violation, fail-closed on malformed input. |
| `tests/test_s11_surgical_adoption.py` | new | 28 offline contract tests (dual-mode), incl. CLI smoke tests with real exit codes. |
| This document | new | Spec + pipeline wiring appendix. |

## 2. Dimension 1 — "কতটুকু দরকার" (need-driven scope slicing)

`extract_python_slice(source, target)` — stdlib `ast`: unique module-level
function/class by exact name; returns the exact source segment, line span
and the imports **actually used** inside the slice (module-level import
bindings referenced by slice names). Missing, ambiguous and over-budget
targets raise `ExtractionError`.

`extract_typescript_slice(source, target)` — deterministic brace-balanced
scan over `function|class|const|let|var` declarations; no tree-sitter
dependency.

**Gold Pearl budget**: `GOLD_PEARL_MIN_LINES=20`, `GOLD_PEARL_MAX_LINES=100`
(extraction SSOT; the CI guard and tests import these). A 19-line or
101-line slice is rejected — slice smaller, never vendor.

## 3. Dimension 2 — "কীভাবে দরকার" (native zero-bloat fitting)

`generate_adaptation_stub()` emits a self-contained Python stub: language-
aware provenance header (github repo, upstream license, component, line
count), only allowlisted stdlib imports, fail-closed error contracts
preserved as authored. `verify_stub_standalone()` machine-verifies the
result: Python — AST import allowlist + compile check; TypeScript — no
network/dynamic-loader calls, comment-stripped brace balance. Foreign
markers (`import requests`, `require(`, playwright, torch, …) are rejected
everywhere. Uniform failure surface: everything raises
`ExtractionError` (SyntaxError is wrapped).

`generate_transplant_patch(satellite, path, stub)` — atomic
**single-new-file** patch (`new_file=True` is structural, not a flag),
routed to `CANONICAL_SATELLITES`, unsafe paths rejected, stub re-verified
at transplant time with language inferred from the path suffix.

## 4. Live Benchmark Blueprints (criterion: concrete zero-bloat plans)

`BENCHMARK_BLUEPRINTS` — validated structured doctrine, each carrying the
mandatory কতটুকু দরকার / কীভাবে দরকার pair, native target, zero-bloat plan
and prohibited list:

* **REA Evidence Ledger** (`morluto/rea`, MIT) → extract the ~30-line
  EvidenceRecord interface + SHA-256 fingerprinting as a stdlib-only
  Python dataclass; no JVM/Ghidra runtime, no engine vendoring.
* **Moli Semantic Tree** (`lexmount/moli`, Apache-2.0) → re-express the
  DOM→semantic-tree filter in TypeScript for the browser satellite over a
  structured DOM snapshot; no Cargo tree, no headless binary bundling,
  unknown node types fail closed.

## 5. Vendored-Tree Guard (criterion 1 — CI sanitization)

Deterministic rules over the structured `{path, bytes}` added-file list:

| Rule | Trigger |
|---|---|
| R1 | path under `vendor/`, `third_party/`, `node_modules/`, `bower_components/`, `vendors/` |
| R2 | single addition > 512 KiB or binary-library suffix (`.jar`, `.wasm`, `.node`, …) |
| R3 | > 50 new files under one first-level directory |
| R4 | dependency lockfile added (package-lock/yarn/pnpm/poetry/Cargo/Pipfile/composer) |
| R5 | total added mass > 2 MiB |

Exit `0` clean, `2` violation; malformed input is a violation
(fail-closed). Exactly-at-limit additions pass (tested).

## 6. Appendix — pipeline wiring (protected path, spec hunk)

`.github/workflows/pipeline.yml` is outside the bridge lane; the
maintainer applies the equivalent step (pattern identical to the landed
CI_GUARDS appendix):

```yaml
  vendored_tree_guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - name: Zero-Bloat Vendored-Tree Sanitization (#498)
        run: |
          git diff --numstat "$BASE_SHA..$HEAD_SHA" \
            | awk '$3 != "" {print $3}' \
            | while read -r f; do
                printf '{"path": "%s", "bytes": %s}\n' "$f" \
                  "$(stat -c%s "$f" 2>/dev/null || echo 0)";
              done \
            | jq -s . \
            | python3 scripts/ci/vendored_tree_guard.py
```

## 7. Test evidence

28 offline tests green in dual mode (`python3 -m unittest
test_s11_surgical_adoption -v` / `pytest -q`), `--self-test` green on both
new modules. Coverage: slice exactness & sibling isolation, budget bounds,
ambiguity/missing fail-closed, TS balancing, usage-driven imports,
standalone stub execution (real `exec`) incl. the fail-closed empty-payload
contract, foreign-import rejection, atomic transplant + satellite/unsafe-
path gates, guard R1-R5 + boundary + CLI exit codes (0/2), blueprint
doctrine for both live benchmarks.
