# SCOUT RADAR — 2026-10-28, Sweep IX (R31)

Chain context: radars I (R1–R12, #1611), II (R13–R16, #1652), III (R17–R20, #1682),
IV (R21–R22, #1688), V (R23–R24, open WO), VI (R23–R25, numbering collision with V),
VII (R26–R27, #1727). Next free number per the take-next-free rule (#1724, index SSOT
pending): **R31**. Doctrine: zero speculative tickets — every claim carries a dated
probe (2026-10-28) or a `main`-today file anchor.

**Mid-cycle collision record (same class as #1682/#1688/#1706).** This sweep was
authored as radar VIII / R28 while issue #1740 was being filed under the Task ID
`bridge-20261028-scout-radar-viii`. At fetch time (2026-10-28, ~05:5x +08) the remote
branch `bridge/bridge-20261028-scout-radar-viii` (Job 478621, 05:47 dispatch — three
minutes ahead of this cycle) claimed the same slug and filed R28–R30: Redis quota
economics (#1732), OWASP LLM Top 10 mapping (#1733), OWASP Agent Control Standard
(#1739). Per the take-next-free rule those numbers are burned; this sweep renames to
**radar IX / R31** with Task ID `bridge-20261028-scout-radar-ix`. Content overlap with
radar VIII: **zero** (theirs = quota economics + OWASP conformance; ours = search
grounding supply). Honesty note: issue #1740's title/body reference "R28, scout radar
VIII" because it was created before the collision was observable; the tower exposes no
issue-update tool (MISS recorded in radar IV), so this document is the canonical
R-number record for the search-grounding lane: **R31**. The R-number SSOT urgency is
radar VII's R27 → #1724, unchanged.

| # | Lane | Source / probe surface | Live status (2026-10-28) | Federation seam | Verdict → Issue |
|---|------|------------------------|--------------------------|-----------------|-----------------|
| R31 | Web-search grounding engine lanes (Tavily / Brave / Exa / Serper) as data-only adapters behind the existing search seam | `api.tavily.com/search`, `api.search.brave.com/res/v1/web/search`, `api.exa.ai/search`, `google.serper.dev/search` — all probed unauthenticated, dated | All four protocol-speaking (401/422/402/403 — zero 404s); Exa answers **x402-native** (`x402Version: 2`) | Grounding platform-wide rides ONE free unauthenticated DuckDuckGo scrape lane: `core/api/routes/deep_research.py:220` (probed **HTTP 202** — non-standard, bot-mitigation layer), `core/search.py:25-31` (soft-import silently degrades to None), `core/factual_verifier.py:74` (`search_engines = ["duckduckgo"]` hard-coded single engine) | `ADAPT_CLEANROOM` → **#1740** (lane number R31 — see collision note) |

## R31 — grounding is a single point of failure, and the upgrade lanes are already live

**The seam (verified on `main` @ a62e307, 2026-10-28).** Three file anchors, one story:

1. `core/api/routes/deep_research.py:220` builds
   `search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"` — HTML
   scraping of a bot-mitigated endpoint. Live probe of that exact URL today returns
   **HTTP 202** with an HTML shell — a success code that is not part of any search
   contract, i.e. an undocumented mitigation layer sits between the federation and
   its grounding data. `lite.duckduckgo.com/lite/?q=test` answers 200 HTML today;
   neither is a machine contract, both are scrape surfaces.
2. `core/search.py:25-31` soft-imports `duckduckgo_search` (header comment documents
   the rename churn to `ddgs`) and degrades **silently to None** on import failure —
   the deep-research path above does not even use this module; it scrapes directly.
3. `core/factual_verifier.py:74` hard-codes `self.search_engines = ["duckduckgo"]`.

Net: any DDG mitigation change (IP block, captcha wall, 202-anomaly hardening)
degrades deep research AND factual verification platform-wide with zero error
surfacing and zero upgrade path.

**The lanes (all live-probed 2026-10-28, unauthenticated, no 404s):**

| Lane | Probe | Answer | Contract signal |
|------|-------|--------|-----------------|
| Tavily | `POST https://api.tavily.com/search` `{}` | **401** `{"detail":{"error":"Unauthorized: missing or invalid API key."}}` | Bearer-auth JSON API |
| Brave Search | `GET https://api.search.brave.com/res/v1/web/search?q=test` | **422** naming `loc:["header","x-subscription-token"], msg:"Field required"` | The API self-documents its auth header |
| Exa | `POST https://api.exa.ai/search` `{}` | **402** `"tag":"X402_PAYMENT_REQUIRED","x402Version":2"` | **x402-native** — live validation of landed radar II R13 |
| Serper | `POST https://google.serper.dev/search` `{}` | **403** `"Unauthorized. Sign up for a free account."` | Free tier + `X-API-KEY` |

Method note (extends the R21 probe doctrine): "no 404s" proves protocol-speaking
endpoints; the DDG **202** shows the same method catches *non-standard success
codes*, which are the actual fragility signature of scrape lanes.

**Pros.** Four SLA-backed engines behind one registry; grounding survives any
single upstream's mitigation churn; zero new runtime dependencies (httpx is
already imported by `factual_verifier.py`); env-gated so OSS default behavior is
byte-identical until an operator opts in.

**Cons.** Four result shapes to normalize (Tavily `results[]`, Brave
`web.results[]`, Exa `results[]`, Serper `organic[]`); free tiers rate-limited —
multi-engine fan-out needs an explicit budget guard.

**Risks.** Key leakage via logs — adapters surface availability as booleans only,
never key material; paid-lane priority inversion — env presence is the only
activation signal, free lane stays default.

**এটা করা যাবে না:** no scraping premium providers' web UIs where a public JSON API
exists (R22 doctrine); no hardcoded keys; no removal or deprioritization of the
free DDG lane; no auto-fanout to all keyed engines per query.

**Adoption path → Issue [#1740](https://github.com/Supremeai-bd/supremeai-open/issues/1740)**
(Parent Anchor Hub #750 — grounding supply, sibling of #1685): engine registry on
the existing `search_engines` seam + Tavily/Brave adapters first (Brave's 422
self-documents its contract), wired into `FactualVerifier.verify_with_web_search()`
and `deep_research`'s search step; recorded-fixture tests, no network in CI.

## Cross-signal synthesis

- **R13 is production-real.** Radar II quarantined x402 as a payments *protocol*
  to watch; Exa's `/search` answers `x402Version: 2` in the wild on a mainstream
  AI endpoint (2026-10-28). The R13 lane now has a live reference implementation
  in the exact domain (search) the federation needs.
- **Supply fragility is a pattern, not an anecdote.** R21 probed provider supply
  (4 missing model lanes); R31 probes tool supply (4 missing grounding lanes).
  Same doctrine, same data-only template shape, same anchor hub (#750).
- **Labels discipline restored.** Radar IV honestly recorded a MISS — its issues
  (#1685/#1686) landed unlabeled because the `labels` argument was omitted and no
  update tool exists. Radar IX's issue #1740 carries
  `P1-high / status:unclaimed / repo:api` from creation, closing that process gap.

Zero-hype statement: no agentic browser-search frameworks, no vector-RAG rewrites,
no "AI search" products proposed — one registry seam, four thin JSON clients,
fail-closed, free lane untouched. Docs-only: 1 new file, no source code, no CI paths.
