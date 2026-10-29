# Spec Kit Pilot (R25 → #1710) — Idea-Assessment Template × 3 Open Feature WOs

> **Task ID:** `bridge-20261029-speckit-pilot-1710`
> **Lane:** docs-only process pilot (R25 `quarantine_eval` adoption path, step 1 of 3)
> **Template source:** github/spec-kit idea-assessment extension as live-probed 2026-10-28
> (SCOUT_RADAR_2026-10-28-VI.md, R25 section: "evidence-backed go, clarify, or stop decision")
> **Scope guard:** process-artifact borrowing only — no code, no dependencies, no tool
> adoption, no constitution contact (R25 conflict-by-default rule).
> **Honesty note:** verdicts below are this agent's doc-only assessments of the cited work
> orders as read on 2026-10-29; they bind no maintainer and no other agent.

## Template shape (borrowed fields, renamed to bridge vocabulary)

| Spec Kit field | Pilot field used below |
|---|---|
| idea / problem statement | Problem |
| evidence for the decision | Evidence (dated) |
| go / clarify / stop | Decision |
| clarifications required | Clarify gate |
| criteria that kill the idea | Kill criteria |
| criteria that prove convergence | Convergence signal |

---

## Instantiation 1 — #1520 (feat(studio): connect Jarvis console to LLM orchestration backend)

- **Problem:** the admin console responds from static/rule-based logic; the roadmap audit
  (Phase 0, last-mile wiring) names live backend orchestration as the fix, with two target
  files declared in the WO.
- **Evidence (dated):** WO body cites the roadmap audit report and names
  `JarvisAdminConsolePage.tsx` + `JarvisService.ts` (read 2026-10-29, issue state open,
  P1-high, unclaimed). No dated live probe of the console's current behavior exists
  issue-side.
- **Decision:** **CLARIFY.**
- **Clarify gate:** which gateway/orchestration endpoint is the intended backend contract,
  and what auth model applies (admin session vs. per-user key)? The WO declares target
  files but not the API surface the console should call; wiring to an undefined contract
  is how ghost fixes happen.
- **Kill criteria:** if no stable orchestration endpoint exists on the gateway after a
  contract survey, or the only path requires shipping provider keys to the browser
  plane, stop — the feature then needs a design WO of its own, not a code PR.
- **Convergence signal:** one live LLM round-trip from the console through the declared
  backend, denied-by-default without credentials, verified by the 3-tier contract.

## Instantiation 2 — #1523 (feat(marketplace): mcp_plugins registry schema + one-click BYO connect flow)

- **Problem:** plugin onboarding is operator-grade today; the roadmap Phase 1 wants a
  registry schema plus a zero-risk BYO-credential connect flow for five named integrations
  (GitHub, Telegram, Web-Search, Drive, Notion).
- **Evidence (dated):** WO names existing surfaces to wire — `client_register_mcp_server`
  and `client_discover_mcp_server` — both observed present in the live tower tools surface
  (this cycle's zero-credential tools/list, 2026-10-29: 151 tools, both client.* lanes
  listed). The registry table itself does not exist yet issue-side.
- **Decision:** **CLARIFY** (leaning go).
- **Clarify gate:** who owns the Supabase migration for `mcp_plugins`, and where do BYO
  credentials rest — existing slot/credential plane or a new store? The slot_* and
  client_* tools already cover provisioning and rotation; a parallel secret store would
  duplicate a solved problem.
- **Kill criteria:** if BYO credentials cannot ride the existing slot/client plane without
  introducing a second secret store, stop and re-scope to the registry rows + UI discovery
  half only.
- **Convergence signal:** one plugin connected end-to-end by a non-operator through the
  marketplace UI, with the credential verifiable in the existing audit trail.

## Instantiation 3 — #1685 (feat(gateway): wire 4 live-verified OpenAI-compatible provider lanes into dynamic_ai registry)

- **Problem:** four OpenAI-compatible providers (Z.ai GLM, DashScope Qwen, Mistral,
  Cerebras) are verified live but absent from the dynamic_ai registry.
- **Evidence (dated):** the strongest of the three — the WO itself carries four dated
  protocol probes (2026-10-28): unauthenticated POSTs returned 401/400 (endpoint speaks
  the protocol) rather than 404, with docs bases cited per provider; parent anchor #750;
  scout cycle III provenance.
- **Decision:** **GO.**
- **Clarify gate:** none blocking — the slice is bounded (registry rows + config), the
  evidence is primary-source and dated, and the failure mode (bad key at deploy time) is
  orthogonal to the wiring correctness.
- **Kill criteria:** any lane whose live probe stops speaking the protocol (404/5xx on
  re-probe) post-key-provisioning drops out of the slice; the remaining lanes land
  independently.
- **Convergence signal:** per-lane health check green against the registry, no hardcoded
  keys, docs updated in the same PR per the bridge contract.

---

## Pilot reading (one paragraph)

The template earned its keep on this trio: identical P1-family feature WOs produced three
different verdicts (2 clarify, 1 go) purely by asking what evidence exists and what is
missing before any code moves. The clarify gates above are exactly the questions that, if
skipped, historically produced intake-rejected or stale-patch lanes in this repo's recent
history. Cost: one doc. Value: repeatable pre-flight for feature RFCs. This matches the
R25 verdict — borrow the artifact, not the toolchain.
