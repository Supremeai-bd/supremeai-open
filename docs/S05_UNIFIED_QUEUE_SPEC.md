# S05 — Unified Queue Listing Spec (bridge.work_queue, #474)

Status: r1 · 2026-10-17 · Author: Z.ai Code (session web-26454b1b)
Scope: `infrastructure/mcp-control-plane/src/tools/bridge.tools.ts`
(+ `test_bridge_onboarding.ts`, `docs/TOOL-EXPOSURE.md` in the same
subsystem). Reference implementation + offline contract tests ship with
this spec (pure-new-file lane). The TS edit itself follows the exact
hunks in §4.

## 1. Problem

`bridge.work_queue` hardcodes `&labels=bridge:queued` in its GitHub
issues query. Any valid open task issue that does not carry that exact
label (e.g. fresh task contracts #469–#471, which carry
`status:unclaimed`) is invisible to zero-credential agents — the tower
then only shows bridge work orders, and agents cannot discover
claimable work. This defeats the self-serve loop (#468 / S0.1).

## 2. Behavior contract

- Default (no args): list **all open issues** in
  `Supremeai-bd/supremeai-open` (`state=open`), newest first.
- Optional `label: string`: when provided (non-empty), append
  `&labels=<encodeURIComponent(label)>` — identical filtering
  semantics to `gh issue list --label`.
  - `label=""` or `label=undefined` MUST behave as default (all open).
- Retained filters (unchanged): `is:issue is:not-pull-request` and
  open-state checks — PRs and closed issues are always excluded.
- Response shape unchanged: `{repo, label|null, authenticatedRead, count,
  workOrders[]}` where `label` is the applied filter or `null`.
- Deterministic ordering: by `number` descending (newest first).

## 3. Why not just relabel every task issue

Adding `bridge:queued` to every task issue would fix visibility but
corrupts the label's meaning (it is the intake state "a bridge WO exists
for this"), feeds auto_bridge_pr_opener the wrong set, and breaks the
bridge:queued → in-gates → landed label chain observability. Query-side
fix is the single source of truth (SSOT).

## 4. Exact TS hunks (bridge.tools.ts)

Hunk A — schema (add optional label after existing args):

```ts
label: z.string().optional()
  .describe("Optional label filter; omit or empty = all open issues"),
```

Hunk B — query construction (replace the hardcoded labels line):

```ts
// BEFORE:
const url = `${REPO}/issues?state=open&labels=bridge:queued&per_page=100`;
// AFTER:
const params = new URLSearchParams({ state: "open", per_page: "100" });
if (args.label && args.label.trim().length > 0) {
  params.set("labels", args.label.trim());
}
const url = `${REPO}/issues?${params.toString()}`;
```

Hunk C — description:

```ts
"List OPEN issues and Bridge Work Orders in the public open-source repo
(supremeai-open). By default returns all open issues; optionally filter
by label."
```

Hunk D — response `label` field becomes `args.label?.trim() || null`.

## 5. Parity contract (reference implementation)

`scripts/tower/work_queue_query_reference.py` mirrors the URL/param
construction + issue normalization as an executable spec;
`tests/test_s05_unified_queue.py` asserts the same edge cases the TS
onboarding test must cover: unlabeled issues included by default, empty
string label = default, custom label filter, PR exclusion, closed
exclusion, response shape with label null, deterministic ordering.

## 6. TS onboarding test additions (test_bridge_onboarding.ts)

1. queue normalization with an unlabeled open issue → included, `label: null`
2. multi-label issue → included by default; included when any requested
   label matches (GitHub semantics: `labels=` matches ALL listed labels)
3. custom label filter → only matching issues; `label` echoes the filter
4. PR objects and closed issues never appear
