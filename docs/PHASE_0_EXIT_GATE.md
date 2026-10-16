# Phase 0 Exit Gate — Completion Audit & Phase 1 Unlock (#405 / Phase 0)

> **English Summary:** The Phase 0 (Emergency Repairs & Gateway Verification) exit machinery demanded by #405: a live completion audit of Seq 0.1–0.4 (#401–#404), a sign-off checklist that stays PENDING until every predecessor closes with verifiable evidence, and the procedure that unlocks Phase 1 (Self-Serve Onboarding & Studio Console) issue creation. This file never claims completion it cannot verify.
>
> **বাংলা:** Phase 0-এর এক্সিট মেশিনারি — #401–#404-এর সত্য-নিরীক্ষা (§১), স্বাক্ষর-চেকলিস্ট (§২, সব PENDING), আর Phase 1 আনলক পদ্ধতি (§৩)। যাচাই না করা কোনো সমাপ্তি-দাবি এই ফাইল কখনো করবে না — এটাই ফেডারেশনের সততা-মতবাদ।

**Status: GATE CLOSED (nothing signs off).** Every checklist row in §2 is
PENDING by construction on first delivery. This file is the gate's *machinery*
plus its *current honest state* — not a completion certificate.

---

## §1 Predecessor audit matrix (live, evidence-dated)

| Seq | Issue | Deliverable | Board state at audit | Live/process evidence | Gate verdict |
|---|---|---|---|---|---|
| 0.1 | #401 | Render gateway deployment debugging, live `/healthz` probe & CORS fix | **OPEN** | Probe `2026-10-16T20:47Z`: `GET /healthz` → **HTTP 404**, header `x-render-routing: no-server` (Render service UNBOUND); identical result at `2026-10-16T20:09Z` | **FAIL — gateway not live** |
| 0.2 | #402 | Multi-provider failover chain (Groq + Gemini), budget caps, Honest Ledger | **OPEN** | Substance rides sibling WO #411 (`bridge:in-gates`, gateway/* single-target r3: failover chain, 429/5xx/401/403 failover, redacted `providers_tried` ledger) | **PENDING — implementation in gates, not landed** |
| 0.3 | #403 | E2E verification suite — 10 real-world calls & SSE validation | **OPEN**, `status:unclaimed` | Hard dependency: real-world calls require a live gateway (§1 row 0.1 = FAIL) — claiming this before #401 lands cannot produce genuine evidence | **BLOCKED — depends on 0.1** |
| 0.4 | #404 | Broken-link audit + CONSUMERS.md copy-paste quickstart | **OPEN** | WO **#434** (`bridge:queued`, first-try): byte-exact quickstart replacement + `scripts/ci/validate_links.py`; scoped audit 0 dead links; doc sha256 origin-verified | **PENDING — delivered, queued at intake** |

Audit method note: board states read per-row from the issue tracker (labels +
assignees + linked branches), gateway evidence from direct HTTP probes with
UTC timestamps. No status is inferred from titles or summaries alone.

## §2 Sign-off checklist (all rows PENDING until closed with evidence)

- [ ] **#401 closed with a live probe** — fresh `GET /healthz` → HTTP 200 from
      `https://supremeai-api.onrender.com` with no `x-render-routing: no-server`
      header, timestamp recorded in this file's §4 amendment log.
- [ ] **#402 closed with chain evidence** — failover ledger demonstrable
      (429/5xx → next provider; exhaustion = honest 502 `providers_tried`),
      sourced from the landed WO that carried it (#411 lineage or successor).
- [ ] **#403 closed with suite output** — 10 real-world calls + SSE streaming
      validation green against the live gateway (only possible after row 1).
- [ ] **#404 closed with link-integrity proof** — `python3
      scripts/ci/validate_links.py` exits 0 on the landed tree; CONSUMERS.md
      quickstart live (mirror-parity operator action from WO #434 §3 done or
      consciously waived by admin).
- [ ] **Amendment log entry** added per closure (§4), each with issue number,
      closing PR/WO, and verifiable artifact link.

**Sign-off rule (fail-closed):** the Phase 0 Gate Sign-Off block below may be
flipped only when **all five** checkboxes are checked. Any agent or operator
flipping it otherwise violates the federation's honesty doctrine — partial
completion does not exist here.

```text
PHASE 0 GATE SIGN-OFF — PENDING (0/5 checks satisfied as of 2026-10-16T20:47Z)
Sign-off authority: repo admin (paykaribazaronline) or the documented
zero-admin flow once Phase 1 machinery supersedes it.
```

## §3 Phase 1 unlock procedure

1. All §2 checkboxes GREEN with amendment-log entries.
2. Flip the §2 sign-off block, embedding the five evidence links verbatim.
3. Phase 1 (Self-Serve Onboarding & Studio Console) issue creation unlocks —
   parent epic #400 governs; Seq 0.5 is the last Phase 0 row.
4. This file then becomes historical record (append-only from that point).

## §4 Amendment log

| Date (UTC) | Event | Evidence |
|---|---|---|
| 2026-10-16T20:47Z | Gate machinery delivered (#405 / this file); audit §1 executed; 0/5 checks satisfied | gateway probe 404 + `x-render-routing: no-server`; WO #434 queued; #411 in-gates |

## §5 Non-goals

- No gateway repair, E2E suite, or quickstart work inside this file — each
  belongs to its own Seq issue (atomic-slice discipline).
- No pricing/quota invention beyond the #405 contract's quoted defaults —
  binding values are admin-ratified (see `docs/MARKET_STRATEGY.md` §5).
- No Phase 1 issue creation before the sign-off flips.
