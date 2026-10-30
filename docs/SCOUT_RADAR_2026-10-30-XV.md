# SCOUT RADAR — 2026-10-30 — XV (R85)

**Sweep:** ecosystem-scout cycle, GLM Agent 10, Job 486755, 2026-10-30 ~15:30–15:55Z (+08 23:10 dispatch)
**Doctrine:** read-only scout (#1658) — live-evidence-only, zero hype, zero code edits.
**Radar file:** `SCOUT_RADAR_2026-10-30-XV.md` (this file) — lands in the same bridge submission as its registry row + drift pass 43, per the pass-5 same-cycle registration contract.

## 0. Provenance & allocation (fail-loud ledger)

| item | value |
|---|---|
| Advertised pointer at read time | `next free: R81` — **found STALE two-deep** (the pass-26 adoption-staleness class, first two-slot recurrence) |
| R81 | NOT advertisable — peer scout (GLM Agent 31) filed `scout(R81)` = **#3368** (`github.list_prs` single-PR addressability); in-tree citations in `docs/bridge/bridge-20261030-identity-glm31.md` + `infrastructure/mcp-control-plane/src/adapters/github/index.ts:149`; live fix WO **#3393** captured in the queue this cycle |
| R82 | NOT advertisable — scout receipt **#3386** (pipeline.yml `timeout-minutes` gap, GLM Agent 20 / Job 486804); genuine lane citations in `scripts/ci/pipeline_timeout_guard.py`, `tests/test_pipeline_timeout_guard.py`, `docs/CI_MINIMUM_PIPELINE_STANDARD.md` |
| R85 | **ALLOCATED by this lane** — defining ticket **#3478** (filed via tower `github.create_issue` before this doc was written, labels `scout`+`radar`) |
| Post-write pointer | at registration time the advertisement stands where the peer pass in the same pull window put it — one above this lane's number (verified free under the disclosed non-claim class: sole tracked-tree hits are lockfile integrity-hash substrings, pass-9 rules + the R50 precedent) — see index drift pass 43 |
| Numbers NOT used | none beyond the ledger above; no reservation; the mid-window race (a peer consumed the first hash-adjacent slot between R82 and this lane via #3483/#3481 while this registration was in flight — the pass-33 race class witnessed live) and the further peer consumption one above the pointer (#3487, GLM Agent 14) are reconciled in the same registration |

**Freeness verification for this lane's number (three planes):** tracked tree `git grep` → zero citations at `aae817ff` (sole substring neighbors are base64 hash coincidences in `studio/src/components/jarvis/avatarAssets.ts` / lockfiles — the disclosed non-claim class, pass-9 honesty rules + the R50 precedent in radar XIV); open-issue queue → 0 hits over 8 label-sliced sub-captures (count==len complete per the capture contract R76 hardened); origin/main subjects+bodies → 0 hits.

## 1. Lane summary

| R | Lane (one line) | Issue | Status |
|---|---|---|---|
| R85 | **MCP Apps (SEP-1865) is live as an official MCP extension** — MCP tools can return sandboxed interactive UIs (iframe + JSON-RPC `postMessage`) rendered inside the host conversation, supported by Claude (web+desktop), ChatGPT, VS Code (Insiders), Goose; SupremeAI's tool plane is text-only today (0/151 tower tools carry structured content per R65; the tower advertises zero capability surface per R74) — adoption is two-plane: **studio host-plane** (embed the `ext-apps` client so `_meta.ui`-bearing tool results render inside SupremeAI's own UX) + **control-plane serve-plane** (admin lane attaches `ui://` resources for high-traffic tools) | #3478 | open (filed + registered same-cycle by the filer; verdict `adapt`, action `integrate_mcp`) |

**Why one lane this cycle:** the board's open candidates are fully covered by in-flight receipt WOs (loop U5 demotions: 6 rows skipped this dispatch); the scout contract's highest-value move is a single implementation-ready ecosystem lane, not volume.

## 2. Evidence digest (all zero-credential, captured 2026-10-30)

- **E1 (official MCP blog, HTTP 200):** `blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps` — "MCP Apps is now live as an official MCP extension. Tools can now return interactive UI components that render directly in the conversation." Client list quoted verbatim: Claude (web + desktop), Goose, VS Code (Insiders), ChatGPT ("starting this week"). Security model quoted: iframe sandboxing, pre-declared templates, auditable JSON-RPC messages, user consent for UI-initiated tool calls.
- **E2 (npm registry probe, HTTP 200):** `@modelcontextprotocol/ext-apps` latest **2.0.4**, license **MIT**, published **2026-10-27** (3 days before this sweep — actively maintained); description "MCP Apps SDK — Enable MCP servers to display interactive user interfaces in conversational clients"; repo `github.com/modelcontextprotocol/ext-apps`.
- **E3 (GitHub repo, tower `github_repo_info`):** official description "Official repo for spec & SDK of MCP Apps protocol - standard for UIs embedded AI chatbots, served by MCP servers"; LICENSE page HTTP 200.
- **E4 (repo-side gap, in-tree + this cycle's live calls):** every zero-credential tower call this cycle returned `content[].text` only; R65/#2423 recorded 0/151 tools with `structuredContent`/`outputSchema`; the studio satellite (Next.js) is the natural host-plane; the vscode satellite exists and its upstream client supports the extension per E1. No code edits filed — both adoption planes are out-of-lane (studio + admin).
- **E5 (non-duplication, U5):** zero citations of "MCP Apps" / "SEP-1865" / "ext-apps" across tracked tree, captured open queue, and origin/main subjects+bodies. Registry-adjacent lanes R22/R52/R80 own ingest/census concerns, not the tool-UI plane; R49 owns the protocol-ceiling lane — distinct surfaces.

## 3. Held back (observed, live-proven, NOT filed — anti-spam)

- **Pointer staleness is two-deep, not one-deep.** Both consumed slots were consumed by *receipt-style* lanes (an issue-side defining ticket + a receipt with in-tree code citations), while the pointer advertised the first of them. The freshness guard's board-sweep already names the class; the drift log entry documents the recurrence depth. No separate guard lane filed — the existing invariant F + board-sweep machinery already owns it.
- **`github_repo_info` returns `None` metadata fields** (license/stars/pushed_at) for external repos while description resolves — a thin caller-side normalization gap, R66-adjacent (default-repo drift family). Too thin to file standalone; recorded for a future platform-guardian pass.

## 4. Method notes

- Zero-credential end-to-end: repo reads (local clone at `aae817ff`, 0-behind), tower (`github.create_issue`, `github_repo_info`, `bridge.work_queue`), npm registry probe (urllib), one blog fetch. No keys, no admin surfaces, no `.github/**` writes.
- Queue half of the predicate used the label-sliced sub-capture procedure with a count==len completeness check (the documented workaround for the ~4000-char response truncation discovered by R76's lane).
- The lower verified-free slots were deliberately left OUT of this lane's allocation: their only tracked-tree hits are base64 substring coincidences (disclosed non-claim class), and the filer allocates the next clean number after them rather than re-using the coincidence-adjacent zone. One of them was consumed mid-window by a peer lane (the #3483/#3481 race — live witness to the pass-33 class), the other remains advertised to the next filer; a further peer lane one above the pointer (#3487) was reconciled into the registry in this same registration after its landed receipt ghosted the citation plane.

## এটা করা যাবে না (never-do — this radar)

- স্কাউট কোনো কোড এডিট করবে না — host-plane/serve-plane বাস্তবায়ন আলাদা লেনের কাজ।
- কোনো অটো-ক্লোজ নয় — এই lane-এর defining ticket বাস্তবায়ন ছাড়া বন্ধ হবে না।
- MCP Registry পাবলিশিং দাবি নয় (R22/R52/R80-এর লেন আলাদা); protocol-ceiling দাবি নয় (R49 আলাদা)।
- Protected path (`.github/**`) লেখা নয়; admin-lane সম্মান বজায় থাকবে।
