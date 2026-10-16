# Market Strategy — SupremeAI Commercial Launch Positioning (#405 / Phase 0)

> **English Summary:** Formalizes the two market pillars, the free-tier quota boundary, and the abuse defenses mandated by the Phase 0 Seq 0.5 contract (#405, parent epic #400). Pillar 1 targets the Bangladesh ecosystem (local payment aggregators); Pillar 2 targets global indie & agent developers (MCP-native, zero-lock-in, multi-provider failover edge). Quotas and defenses quoted from the contract; binding values remain admin-ratified.
>
> **বাংলা:** দুই স্তম্ভ — (১) বাংলাদেশ ইকোসিস্টেম: লোকাল পেমেন্ট অ্যাগ্রিগেটর (bKash/Nagad) দিয়ে পেমেন্ট-বাধা সমাধান; (২) গ্লোবাল indie ও agent ডেভেলপার: MCP-native, zero-lock-in, মাল্টি-প্রোভাইডার failover এজ। কোটা ও অ্যাবিউজ-প্রতিরোধ §৩–§৪-এ; চূড়ান্ত মূল্যায়ন admin-সিদ্ধান্ত।

**Ratification status (honesty note):** every normative value below is quoted from
the #405 task contract (the admin's own words, marked "e.g." there). This file
formalizes them for review; it does **not** invent pricing, vendor picks, or
budgets — §৫ lists what stays ADMIN_DECISION.

---

## §1 Pillar 1 — Bangladesh Ecosystem

| Aspect | Decision (contract-quoted) |
|---|---|
| Core problem | The **payment barrier** for local software houses, freelancers, and indie devs |
| Solution direction | Local gateway integrations through **bKash/Nagad aggregators** |
| Audience | Local software houses · freelancers · indie developers |

**Derived implications (implementation-facing, still admin-ratified):**

- Onboarding must succeed without an international credit card — wallet-first
  payment UX (bKash/Nagad) precedes card flows for this pillar.
- Billing surfaces in BDT alongside USD; aggregator settlement cadence is an
  operations concern (ADMIN_DECISION, §৫).
- The gateway contract itself needs **no change** for this pillar — consumers
  pay for SupremeAI keys (`X-SupremeAI-Key`, `docs/CONSUMERS.md` §২ key
  lifecycle); the payment rail is upstream of key issuance
  (`/api/api-keys/create` is JWT-gated monolith admin UI today; a self-serve
  front for it is Phase 1 territory, not this file).

## §2 Pillar 2 — Global Indie & Agent Developers

| Aspect | Decision (contract-quoted) |
|---|---|
| Edge | **MCP-native, zero-lock-in, multi-provider failover** |
| Audience | Indie hackers · agent developers · tooling authors |

**Derived implications:**

- Distribution surface = the MCP Control Tower tool plane
  (`https://supremeai-mcp-tower.onrender.com/mcp`) plus the OpenAI-compatible
  gateway surface (`api-schemas/gateway.openapi.yaml`) — both already public.
- "Zero-lock-in" is contractual honesty, not marketing copy: the stable surface
  is OpenAI-compatible, `model: "auto"` routing is server-side, provider
  credentials never leave the server side, and consumers can leave with a
  base_url swap (CONSUMERS §০ snippets are drop-in portable).
- Failover semantics (429/5xx → next provider, exhaustion = honest 502 ledger)
  are the product story for agents that cannot tolerate silent fallbacks.

## §3 Free-tier quota boundary (working defaults, pending ratification)

| Parameter | Working default (contract "e.g.") | Enforcement point |
|---|---|---|
| Free-tier monthly volume | **500 requests / month** | per-key counter at the gateway key-plane (300 s cache-TTL propagation, CONSUMERS §২) |
| Free-tier burst rate | **10 req / min sliding window** | per-key sliding window at the gateway edge |
| Key identity | one key per consumer/agent identity (`<CONSUMER>_SUPREMEAI_API_KEY`) | existing key-plane; quota attribution via `key_id` in usage logs |

Rules this file pins (derived, not invented):

1. Quota counters are **per-key**, never per-IP — IP limits punish shared
   egress (offices, CI runners) and contradict the key-plane model.
2. Exhaustion responses reuse the existing error contract: `429` + `Retry-After`
   (CONSUMERS §০.৫/§৩) — **no new header families** for the free tier.
3. Paid-tier quotas are out of scope here (ADMIN_DECISION, §৫).

## §4 Abuse & bot defenses

| Defense (contract-quoted) | Scope note |
|---|---|
| **Cloudflare Turnstile on signup** | human-verification gate at account creation, ahead of key issuance |
| Quota-exhaustion prevention | §3 per-key caps are the first wall; Turnstile blocks industrial key-farming at the source |

Derived guardrails (fail-honest additions, same class as the contract's intent):

- Signup → key issuance stays behind verification; free keys are never minted
  anonymously.
- Rate-limit signals remain the canonical `429`/`Retry-After` pair; WAF/DDoS
  scrubbing itself is Cloudflare/Render operations (out of this repo's scope).
- Abuse telemetry = existing usage-log `key_id` attribution; no new tracking
  surface is created by this strategy file.

## §5 Explicitly OUT of this file (ADMIN_DECISION list)

- Actual paid-tier pricing (BDT/USD), tier names, and upgrade nudges.
- Aggregator vendor selection (bKash direct vs aggregator platform) and
  settlement/chargeback ops.
- Turnstile site-key provisioning and Render/Cloudflare account ops.
- Marketing budget, launch channels, and the Phase 1 feature backlog itself —
  Phase 1 issue creation unlocks only via the
  `docs/PHASE_0_EXIT_GATE.md` sign-off procedure.

## §6 Verification contract mapping (#405)

| Contract tier | How this file satisfies it |
|---|---|
| Reflection: `git grep -n "MARKET_STRATEGY" docs/` | matches this file (and cross-ref from PHASE_0_EXIT_GATE) |
| Schema & policy lint | markdown tables are pipe-consistent; no checklist syntax used here; no dead relative links (`scripts/ci/validate_links.py` run as WO evidence) |
| Gate verification | this file takes **no position** on Phase 0 completion — that lives exclusively in `docs/PHASE_0_EXIT_GATE.md` |
