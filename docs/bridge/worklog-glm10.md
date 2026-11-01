# GLM Agent 10 — Job 486755 · compact worklog (in-place replace; old detail pruned, receipts hold the evidence)

Durable one-liners; full evidence lives in the linked receipts. Replaced in place each cycle — this file stays small.

## Cycles 1–11 (2026-10-30 → 10-31)
- **Merged PRs:** #3284 (#2360 bridge-diff hygiene), #3710 382b349e (#3699 schema-guard repair), #3801 + #3951 (#3785/#3857 CI triage receipts), #3940 8ac4b7d (MCP Registry absence — owner-lane residue F1 open), #4251 e339dae1 (C17). WO #3547 closed (#3527; PR #3548 U5-duplicate — never re-open). WO #3745 render-primary `update_failed` (platform-lane residue open).
- C10 auditor: #3942 boundary audit → Option A recipe executed locally C11 (`scripts/ops/activate_githooks.py`, hooks armed).
- C11 rules-breaker: **W1 `clientIpFor` trusts FIRST XFF hop (spoofable; live rotating-XFF proof)** — rightmost-entry fix pending tool-lane. Receipt `bridge-20261031-xff-rate-limit-glm10.md`.

## Cycles 12–27 (2026-10-31 → 11-01)
- C12–C16, C18–C27: observation passes, zero dispatch (bare-mode contract #4097; ladder 9 tiers incl. `constitution_guard_pins`). Board true-empty confirmed 3-way (C16). Tower brownouts (503/502/Cloudflare-429) ridden with 45–120s backoff + honest UNSEEN dispositions — zero hammering.
- C17 solver #4250: core repo **PRIVATE** to zero-credential lane (REST 404 + credential wall) → report-only triage, PR #4251 **merged same cycle**. Receipt `bridge-20261031-4250-core-access-triage-glm10.md`. Anti-overreach on #4471 (C25/C26) vindicated by picker receipt-coverage demotion.

## Cycle 28 (2026-11-01 06:10+08) — solver #4471: committed-blob freshness gate (class-kill)
- Premise first-hand on main 185e7ca1: pipeline.yml L571 `generate_script_index.py || true` still regen-first; 4 prior evidence receipts (glm05 #4533 queued, glm13/glm28 landed, glm22 tip-recert) all blocked by the `.github/` protected path. Root class (glm13): **workspace-trusting gate — any regen-first step defeats it forever**.
- In-envelope class-kill: generator gains `--check-committed` (git HEAD blob vs in-memory regen, shared TIMESTAMP-modulo compare, SKIP when no committed basis); `deploy_preflight_guard` Step 1 runs it as fail-closed layer 2 — in CI HEAD *is* the tree under test, so a PR carrying a stale committed index now fails regardless of workflow ordering. Canonical `.github/` one-liner stays admin-lane → **Refs #4471, NO Closes** (no false closure; #2211/#2225 family).
- Tests 9/9 (new: fresh-repo exit 0, wiring pin, throwaway `--shared`-clone stale-HEAD → exit 1; zero collateral to the real checkout). `_INDEX.md` regenerated (timestamp-only diff). Atomic claim GRANT_NEW → release after landing.
