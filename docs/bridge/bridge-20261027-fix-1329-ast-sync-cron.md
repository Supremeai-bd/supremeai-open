# chore(ci): [P0] Graphify AST graph never generated — nightly sync template for #1329 (codebase_graph_query not_indexed)

## Problem
`codebase_graph_query` on the live tower returns `status: not_indexed` with
"graph.json not found. Run 'graphify extract .' or the sync script first."
`scripts/ci/sync_graph_to_memory.py` exists (210 lines, self-tested parser) but
nothing ever invokes it — no workflow references it, so the zero-token AST
capability (audit-to-code root cause, call-graph trace, non-regression guard) is
dead weight on the advertised surface.

## Fix
Template shipped at `docs/ci-templates/graphify-ast-sync.yml` (add to
`.github/workflows/` — protected path, same lane as #1384/#1446):
nightly cron → graphify install → built-in self-test → extract studio+gateway+core
→ commit `.cache/graphify/**` so the deployed tower finds graph.json.

## Acceptance criteria
- [ ] Workflow added as `.github/workflows/graphify-ast-sync.yml`
- [ ] First run: self-test OK; three graph.json artifacts committed
- [ ] `codebase_graph_query` on the tower returns a real graph (nodes > 0, status indexed)
- [ ] `graphify` CLI resolves in CI (if internal, pin the internal index)

## Reflection Evidence
**Why:** The AST graph is a P0 self-capability commitment (in-gates audits resolve
failures to source lines only if the graph exists); the sync script was built and
self-tested but never scheduled — a one-workflow activation of already-verified code.
**Alternatives rejected:**
- Run extraction inside the control-plane deploy (Render build step): couples
  deploy latency to AST extraction and hides failures from CI visibility.
- Sync entities into the memory sidecar instead of committing graph.json: the
  memory graph (#1341) covers project knowledge; the AST graph serves code
  queries — different consumers, both valid.
- Commit only on-demand (workflow_dispatch): guarantees staleness; nightly keeps
  audit root-cause resolution current.
