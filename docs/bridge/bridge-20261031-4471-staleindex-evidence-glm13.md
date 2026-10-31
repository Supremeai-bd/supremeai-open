# Audit evidence — #4471 (GLM Agent 13, Job 486783): fast-lint index regen defeats the #1644 fail-closed gate by ordering

Finding VERIFIED LIVE on main (5a665fbb→ec716826 era, window 16:13–16:26Z
2026-10-31 UTC). Report-only evidence for the verdict plane/admin. The
remedy file is `.github/workflows/pipeline.yml` — a protected path per the
agent envelope — so this row is **evidence-only: no claim, no Closes line,
closure left to the verdict plane**. All claims below were executed, not
inferred.

## 1. The mechanism is an ORDERING regression, not just `|| true`

`fast-lint-syntax-preflight` (.github/workflows/pipeline.yml:551) runs:

```yaml
      - name: Run Fast Lint & Syntax Guard
        run: |
          set -euo pipefail
          # Self-healing for script index freshness if scripts/ changed
          python3 scripts/ops/generate_script_index.py || true      # line 571
          python3 scripts/ci/deploy_preflight_guard.py --step1-syntax  # line 573
```

The regen (571) runs **before** the #1644 fail-closed freshness gate
(573, `_script_index_freshness()` inside `--step1-syntax`). The runner
regenerates `_INDEX.md` in its own ephemeral workspace and discards it —
so by the time the gate reads the index, it is **always fresh in that
workspace**, and a PR whose committed `_INDEX.md` is stale passes CI.
Nothing is "healed": the comment is misleading because healing only
exists on a dev checkout; the runner's write goes nowhere.

**Blame chain (git log -S):** the `|| true` regen line was introduced by
#3418 (48412172, 2026-10-30, "strengthen auto-landing fallback loop…")
— AFTER the #1644 gate (bc9bc989, 2026-10-28) existed. #4471 is
therefore a **regression of #1644 by #3418**, which is exactly why the
#1630 stale-index family keeps recurring: each generation fixed one face
(#1644 staleness gate → #1824 coverage/SCAN_ROOT → #4271 tracked-only
phantom cure) and the ordering hole re-armed behind them.

## 2. The proposed remedy is correct, minimal, and already built

`generate_script_index.py` already ships `--check`: it regenerates **in
memory only** (no write), exits **1** with a loud `STALE: … Run:
python3 scripts/ops/generate_script_index.py` message when the committed
index differs, **0** when fresh. Verified live this window:

- Fresh main: `--check` → `OK: … up to date (559 scripts, 6 hand
  sections)`, exit 0. Main is currently clean — the hole is latent, the
  family is recurring.
- Staleness sim: new tracked script staged (`git add` of a probe file;
  untracked strays are structurally excluded per the 2026-10-31
  phantom-row cure) → `--check` exit **1** with the STALE banner.
  Probe removed, tree restored clean, re-verified exit 0.

The script's own docs have advertised this for two generations
("…`--check` fails CI when somebody forgets"; usage: "CI gate, exit 1
when stale") — **the gate exists but the pipeline never wired it**.

## 3. Exact remedy (admin to apply; one line + one comment)

```diff
       - name: Run Fast Lint & Syntax Guard
         run: |
           set -euo pipefail
-          # Self-healing for script index freshness if scripts/ changed
-          python3 scripts/ops/generate_script_index.py || true
+          # Fail-closed index freshness gate (#1644 semantics, restored).
+          # A PR that changes tracked scripts/ without regenerating
+          # scripts/ops/_INDEX.md must fail here (runner writes are
+          # ephemeral — regeneration in CI heals nothing).
+          python3 scripts/ops/generate_script_index.py --check
           python3 scripts/ci/deploy_preflight_guard.py --step1-syntax
```

`--check` subsumes both roles: it cannot mask a failure (`|| true`
removed), it writes nothing (no ordering defeat possible), and it makes
line 571 itself the staleness gate, restoring #1644's intended
fail-closed semantics with zero new code. Dev-machine "self-healing"
regen stays available as the bare invocation (documented in the script
header) — it just must not run in CI before the gate.

## 4. Scope note (zero cross-agent collateral)

Only pipeline.yml line 571 is in finding scope. The file's other
`|| true` occurrences (lines 156, 238, 273, 306, 353, 374–376, 399) are
grep/notify fallbacks with different failure semantics and are NOT
evaluated here. Companion open row #4272 (script-index phantom
root-cause PR, GLM-04) touches the same subsystem from the discovery
side; the ordering fix above is independent of it.
