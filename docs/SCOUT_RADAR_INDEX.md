# Scout Radar Index — R-Number SSOT

> **Allocation rule:** before filing a new radar lane, take the next free R-number **FROM this index** (next free: **R45**), and update this index **in the same PR that lands a radar** — the same freshness contract the script-index gate (#1644) applies to `scripts/`. Cross-references in issues and PR bodies must use the disambiguated form (`R23-V`, `R23-VI`) whenever a collision row exists below, and the issue-number form (`#1745`) for any lane listed in §3 (contested numbers).
>
> **Collision notice (radar V ↔ radar VI):** both landed within the same day and independently assigned **R23** and **R24** to different lanes. The numbers are NOT re-issued (rewriting landed history for zero operational gain); they are disambiguated by radar suffix: `R23-V` (A2A v1.0.0 exit-quarantine RFC) vs `R23-VI` (agents.md constitution portability), `R24-V` (OpenRouter aggregator tier) vs `R24-VI` (CI Python matrix honesty). Any new work must cite the suffixed form.
>
> **Second collision notice (the "radar V" name):** a later issue-only sweep re-used the radar-V name (issues #1735–#1738, no landed file) and assigned its own R-numbers, later corrected by #1746. §3 adjudicates those contested numbers. Landed radar docs on `main` are the allocation ground truth; this file is the registry that makes that truth legible without re-reading every sweep.
>
> **Status provenance:** every filed-issue status below was probed live on **2026-10-28** via the Tower `bridge.work_order` read surface (issue states re-probed at each same-day freshness pass; pass 4 re-verified #2029, #2042, #1938 from main-history evidence: 0506b9b, 94008df, 0141166+5f1575e+40ac0bf). Statuses drift; the R-number → issue mapping does not.
>
> **Drift log:** *2026-10-28, pass 2* — R40/R41 were adopted issue-side (#1898, #1913) before any index row existed, skipping the allocation rule. Registered below as issue-filed placeholders by the freshness pass; R37–R39 remain free and are NOT retro-claimed by the R40/R41 adopters' count. Rule 1 stands: never derive your number by counting runs, sweeps, or issues — the only count that exists is this registry.
>
> **Drift log:** *2026-10-28, pass 3* — within hours of pass 2, R37 (#1969 py-dep CVE gate) and R38 (#1792 satellite-dispatch parity gate) were adopted issue-side AND landed without registry rows, while the index still advertised next free = R37 — the first occurrence where the advertised next-free number was itself already taken (collision-imminent, not merely stale). R42 (#1938) was adopted issue-side and its WO #1953 deliverable was then evicted from main (run 4532; triaged by #1964). This pass registers R37/R38 (landed) and R42 (evicted, in author-side retry), refreshes R40/R41 to landed, and moves next free to R39. Rule 7 stands: the index is the only counter.
>
> **Drift log:** *2026-10-28, pass 4* — within hours of pass 3, R39 (#2029 typecheck vacuum — mypy adopt-grade annotations, landed as 0506b9b/PR #2037 with a DEFER verdict + 3 registered preconditions) and R44 (#2042 live Render surface auditable — browser deps pinned, landed as 94008df/PR #2050) were adopted issue-side AND landed without registry rows, while the index still advertised next free = R39 — the **second** collision-imminent occurrence, same-day recurrence of the pass-3 failure mode (§5's predicted freshness-gate CI-check mirror is now demonstrated to be warranted; proposal deferred to a future guard lane, scout cycle files findings only). R42 (#1938) closed end-to-end in the window: re-land r3 (0141166, "Closes #1938"), genesis ratchet shrunk to 0 (5f1575e), and the guard-vs-guard ALLOWLIST interop registration landed (40ac0bf/PR #2044) — row refreshed to landed (closed). This pass registers R39/R44 (landed), refreshes R42, and moves next free to R43 — NOT R45: R44 being adopted does not consume R43, and R43 is verified free repo-wide (no radar doc, issue, or main-history citation); the free pool is {43} until it is claimed. Rule 7 stands: the index is the only counter.
>
> **Drift log:** *2026-10-28, pass 5* — R43 was filed issue-side (#2064, ecosystem-scout cycle 14, Job 478338; inline-install blindspot class: gateway Dockerfile OR-fallback silently degrades to 5 unpinned floats — a gate-defeat path where the build can never fail on manifest install — plus swarm-worker's 4 unpinned packages with no manifest at all, and a partial pin in core/Dockerfile.ci; fix options A-D routed to maintainer/future-guard lanes per the #2042 never-do) **AND registered in this index within the same cycle** — the first lane to close the pass-3/pass-4 failure mode (adoption without registration) at filing time instead of at a later freshness pass. This pass moves next free to R45: the free pool {43} is consumed by #2064's adoption, and 44 remains consumed by R44. Rule 7 stands: the index is the only counter.

## 1. R-number registry (radars I–XI + issue-filed lanes)

| R# | Radar file | Lane (one line) | Filed issue | Verdict | Status (2026-10-28) |
|----|-----------|-----------------|-------------|---------|---------------------|
| R1 | `SCOUT_RADAR_2026-10-28.md` (I) | GPT-5.6 family (Sol/Terra/Luna) + ChatGPT Work — tiered, cyber-capable model family | not filed | `adapt_cleanroom` | — |
| R2 | I | GPT-6 + Intelligent UI; "dot" always-on agent | not filed | `quarantine_eval` | — |
| R3 | I | Codex Security CLI open-sourced (Apache-2.0) — CI-integrable security scan | not filed | `accept_verbatim` (pattern) | — |
| R4 | I | Claude Opus 4.6 / Opus 5.5 / Fable 5.1 — SOTA agentic coding | not filed | `adapt_cleanroom` | — |
| R5 | I | Gemini 3.5–3.8 Flash cadence + Gemini 4 Argon — price-per-task −71% | not filed | `adapt_cleanroom` | — |
| R6 | I | Muse Spark (Avocado) hybrid open/closed strategy | not filed | `reject_hype` | — |
| R7 | I | DeepSeek V4 — efficiency-first frontier, open weights + cheap API | not filed | `adapt_cleanroom` | — |
| R8 | I | MCP spec 2026-07-28 — stateless, OAuth 2.1+PKCE enterprise semantics | not filed | `accept_verbatim` | — |
| R9 | I | ALMA — meta-learning memory architecture selection | not filed | `adapt_cleanroom` | — |
| R10 | I | DualPath — agentic inference storage bottleneck (I/O-aware serving) | not filed | `quarantine_eval` | — |
| R11 | I | Eval studies: reasoning effort ≠ better; passing tests ≠ integration | not filed | `accept_verbatim` (method) | — |
| R12 | I | Anthropic risk disclosures — IPO prospectus names cyber + self-replication | not filed | `quarantine_eval` | — |
| R13 | `SCOUT_RADAR_2026-10-28-II.md` | x402 — HTTP-402-native per-call payments for agents | #1647 | `adapt_cleanroom` | landed (closed) |
| R14 | II | OpenTelemetry GenAI `gen_ai.*` semantic conventions | #1648 | `accept_verbatim` (taxonomy) | landed (closed) |
| R15 | II | A2A protocol → Agentic AI Foundation (quarantined pre-1.0) | #1649 | `quarantine_eval` | landed (closed) |
| R16 | II | Firecracker microVM as agent-sandbox baseline | #1650 | `adapt_cleanroom` | landed (closed) |
| R17 | `SCOUT_RADAR_2026-10-28-III.md` | Agent Skills open standard (SKILL.md) — 3 coexisting metadata conventions | #1672 | `ADOPT_IMMEDIATELY` | open |
| R18 | III | chrome-devtools-mcp — Chrome DevTools as MCP tool server | #1673 | `ADOPT_IMMEDIATELY` | open |
| R19 | III | Sigstore / artifact attestations for agent-produced patches | #1674 | `EXTRACT_PATTERNS_ONLY` | open |
| R20 | III | Web Bot Auth — IETF signed-agent HTTP identity | #1675 | `ADAPT_CLEANROOM` | open |
| R21 | `SCOUT_RADAR_2026-10-28-IV.md` | Four missing OpenAI-compatible provider lanes (Z.ai GLM, DashScope Qwen, Mistral, Cerebras) | #1685 | `adapt_cleanroom` | open |
| R22 | IV | Official MCP Registry wired into marketplace discovery (read-only ingest) | #1686 | `accept_verbatim` | open |
| R23-**V** | `SCOUT_RADAR_2026-10-28-V.md` | A2A reached v1.0.0 stable — exit-quarantine RFC for the R15 lane | #1703 | `adapt_cleanroom` (RFC-only) | open |
| R24-**V** | V | Aggregator routing supply — OpenRouter meta-lane subsumes R21 per-provider work | #1705 | `adapt_cleanroom` | open |
| R23-**VI** | `SCOUT_RADAR_2026-10-28-VI.md` | agents.md de-facto standard — constitution portability (⚠ collides with R23-V) | #1702 | `adapt_cleanroom` | landed (closed) |
| R24-**VI** | VI | CI Python matrix honesty + supply-chain freshness (⚠ collides with R24-V) | #1709 | `adapt_cleanroom` (admin lane) | open |
| R25 | VI | GitHub Spec Kit process primitives as bridge-WO lifecycle overlay | #1710 | `quarantine_eval` | open |
| R26 | `SCOUT_RADAR_2026-10-28-VII.md` | Agent-component security scanning (Snyk Agent Scan, ex-mcp-scan) over skills + MCP | #1723 | `ADAPT_CLEANROOM` | **landed (closed — PR #1923, scan baseline in `SKILLS_AGENT_SCAN_BASELINE_2026-10-28.md`)** |
| R27 | VII | Radar index — R-number SSOT for the scout artifact chain (**this file**) | #1724 | `ACCEPT_VERBATIM` | **landed (closed — PR #1900)** |
| R28 | `SCOUT_RADAR_2026-10-28-VIII.md` | Upstash quota economics — rotation bought availability, not quota | #1732 | `adapt_cleanroom` | open |
| R29 | VIII | OWASP LLM Top 10 as the guard chain's canonical risk vocabulary | #1733 | `adapt_cleanroom` | open |
| R30 | VIII | OWASP Agent Control Standard as declarative vocabulary for the policy chain | #1739 | `quarantine_eval` | open |
| R31 | `SCOUT_RADAR_2026-10-28-IX.md` | Memory tiering asymmetry — 21 tower `memory_*` tools vs flat repo-side consumers | #1747 | `adapt_cleanroom` | open |
| R32 | IX | Search supply consolidation + fail-closed env-keyed fallback | #1751 | `adapt_cleanroom` | open |
| R33 | IX | Runtime behavioral-probe trust lane (NVIDIA garak) for golden evals | #1748 | `quarantine_eval` | open |
| R34 | *(issue-filed — radar-X doc pending landing; allocation recorded by radar XI's register)* | Machine license-SSOT drift gate for ECOSYSTEM_MAP §2.3 (SPDX-anchored) | #1773 | `adapt_cleanroom` | **landed (closed)** |
| R35 | *(issue-filed — radar-X doc pending landing)* | Admin-lane workflow hardening — zizmor 60 findings (report-only, admin-owned) | #1776 | `adapt_cleanroom` (admin lane) | open |
| R36 | `SCOUT_RADAR_2026-10-28-XI.md` | Free-text PII redaction gap — Microsoft Presidio report-only pilot → `adapt_cleanroom` | #1784 | `adapt_cleanroom` | open (claimed) |
| R37 | *(issue-filed — guard lane, no radar doc; adopted issue-side pre-registration, see Drift log pass 3)* | Python-dependency CVE gate — pip-audit 2.10.1 live sweep (6 manifests, 0 known vulns; c34f309 hermetic self-test follow-up) | #1969 | `adapt_cleanroom` | **landed (closed)** |
| R38 | *(issue-filed — landed WO doc `docs/workorders/bridge-20261028-satellite-parity-gate.md`; adopted issue-side pre-registration, see Drift log pass 3)* | Scheduled satellite-dispatch parity gate — extend the in-tree parity_guard + 7-sentinel SHA baseline | #1792 | `adapt_cleanroom` | **landed (closed)** |
| R39 | *(issue-filed — guard lane, no radar doc; adopted issue-side post-pass-3, see Drift log pass 4)* | Typecheck vacuum — mypy adopt-grade annotation corrections (11→6 errors on 4 files, 0 new); gate verdict DEFER with 3 registered preconditions (`docs/EVAL_2026-10-28-r39-typecheck-verdict.md`) | #2029 | `adapt_cleanroom` | **landed (closed)** |
| R40 | *(issue-filed — radar doc pending landing; adopted issue-side pre-registration, see Drift log)* | Runtime contract-fuzzing gate — Schemathesis 4.32.7 (MIT) live in-memory over the gateway API | #1898 | `adapt_cleanroom` | **landed (closed)** |
| R41 | *(issue-filed — radar doc pending landing; adopted issue-side pre-registration, see Drift log)* | JS-dependency CVE gate — OSV querybatch baseline (719 pkgs, 6 vulnerable / 13 findings) | #1913 | `adapt_cleanroom` | **landed (closed)** |
| R42 | *(issue-filed — WO #1953 evicted then re-landed r3; see Drift log pass 4)* | R42 link-integrity gate — stdlib live sweep post-#1909 prune (244 md files); r3 wired roster+pre-push §15, genesis ratchet shrunk to 0 (endgame) | #1938 | `adapt_cleanroom` | **landed (closed)** |
| R44 | *(issue-filed — guard lane, no radar doc; adopted issue-side post-pass-3, see Drift log pass 4)* | Live Render surface auditable — browser deps pinned (23-pkg closure, Dockerfile COPY fix); py_dep_cve_guard tracked discovery covers it with zero guard changes (surface 10→11); options B/C DEFER maintainer lanes (`docs/EVAL_2026-10-28-r44-live-browser-deps-verdict.md`) | #2042 | `adapt_cleanroom` | **landed (closed)** |
| R43 | *(issue-filed — guard lane, no radar doc; adopted issue-side post-pass-4, see Drift log pass 5)* | Inline-install blindspot, post-R44 — gateway Dockerfile OR-fallback degrades to 5 unpinned floats (gate-defeat: build never fails on manifest install); swarm-worker 4 unpinned pkgs with no manifest; core/Dockerfile.ci partial pin (wheel floats); py_dep guard manifest-plane doctrine sees none of it (surface 11 receipt at bab42ec); fix precedent in-repo (#2525 uv pin, R44 browser pattern); options A-D routed | #2064 | `adapt_cleanroom` | open (filed 2026-10-28) |

## 2. Radar cycle anchors (filed under each sweep)

| Sweep | Radar file | Anchor / tracking issue | Note |
|-------|-----------|------------------------|------|
| I | `SCOUT_RADAR_2026-10-28.md` (R1–R12) | #1611 (landed as PR) | |
| II | `SCOUT_RADAR_2026-10-28-II.md` (R13–R16) | #1652 (landed as PR) | |
| III | `SCOUT_RADAR_2026-10-28-III.md` (R17–R20) | #1682 (landed as PR) | |
| IV | `SCOUT_RADAR_2026-10-28-IV.md` (R21–R22) | #1688 (landed as PR) | filename rename mid-cycle, recorded in #1688 |
| V | `SCOUT_RADAR_2026-10-28-V.md` (R23-V, R24-V) | *(issues filed directly)* | the *landed* radar V |
| VI | `SCOUT_RADAR_2026-10-28-VI.md` (R23-VI, R24-VI, R25) | *(issues filed directly)* | |
| VII | `SCOUT_RADAR_2026-10-28-VII.md` (R26–R27) | *(issues filed directly)* | |
| VIII | `SCOUT_RADAR_2026-10-28-VIII.md` (R28–R30) | *(issues filed directly)* | renamed from radar-vii after #1726 claimed that name mid-cycle |
| IX | `SCOUT_RADAR_2026-10-28-IX.md` (R31–R33) | *(issues filed directly)* | §0 of the file is its own correction register |
| X | *(no landed file — issues only)* | #1773 (R34), #1776 (R35) | allocation attested by radar XI's non-duplication register |
| XI | `SCOUT_RADAR_2026-10-28-XI.md` (R36) | #1784 | carries the full R1–R36 register; see §3 for its contested line |
| XII | *(no landed file)* | WO #1793 (closed) | closed with index seeding explicitly deferred to #1724 (this file) |
| *(issue-filed guard lanes)* | *(no landed radar file)* | #1898 (R40), #1913 (R41) | registered by the 2026-10-28 drift pass (pass 2) |

## 3. Contested-number adjudication (the #1746 correction map)

Issue #1746 ("correction note for radar-V run #1735–#1738") filed a renumbering table deferring its final numbers to this index ("final numbers deferred to the #1724 index SSOT"). This section is that deferred resolution. While the correction run awaited it, radars VIII and IX landed and occupied R29–R30 and R31–R32 respectively with their own lanes — landing order is ground truth, and the R27 charter (#1724's own spec) forbids renumbering landed history. The adjudication is therefore:

- **R29–R32 remain owned by the landed radar VIII/IX lanes** (R29 = #1733, R30 = #1739, R31 = #1747, R32 = #1751).
- **The four correction-run lanes are cited by issue number, not R-number** — their contested labels are recorded here as withdrawn, so no future scout re-uses them:

| Contested label | Lane (one line) | Canonical citation | Status (2026-10-28) |
|-----------------|-----------------|--------------------|---------------------|
| ~~R26-c~~ → ~~R30-c~~ | Dead dep-CVE gate — `security_gate.py --trivy` had zero callers → trivy-action SHA-pinned | **#1735** | closed (landed) |
| ~~R29-c~~ | uv toolchain — uv 0.13.6 replaces raw pip at 3 CI sites | **#1745** | open |
| ~~R31-c~~ | Dependabot config gap — Tier-6 merger routes app/dependabot PRs, bot unconfigured | **#1736** | open (claimed) |
| ~~R32-c~~ | Cache data-layer economics — Valkey BSD-3 vs Redis 8 AGPL lock-in angle | **#1737** | open (partial-supersede suggestion: fold licensing section into #1732, per #1746 §2) |
| ~~R25-c~~ | (row in #1738's table whose filing 403'd; canonical link = the R29-c issue) | **#1745** | — |

Two consistency notes this adjudication settles: (1) radar XI's register line saying radar V's four lanes "were renumbered R29–R32 by the #1724 index SSOT" was written in anticipation of this index and is **superseded by this section** — the renumbering did not happen because VIII/IX landed first; (2) #1746's own note that "R26 [was] double-booked with radar VII #1726" is resolved the same way: R26 = radar VII's Snyk Agent Scan lane (#1723), and the correction-run row cites by issue number (#1735).

## 4. How to extend this index (the contract)

1. **Claim the next free number from the table above** — the next free number is printed in the allocation rule at the top. Do not scan individual radar files to guess; that is the failure mode this index exists to prevent (radar IV's own #1688 records a filename collision caught only by rebase luck; the V/VI R-collision was not caught at all — and the "second radar V" name reuse in §3 was caught only by a post-hoc correction note).
2. **Update the index in the same PR that lands the radar** — a radar doc merged without its index row is an incomplete landing.
3. **Disambiguate collisions, never renumber** — if two sweeps independently take the same number (as V and VI did), keep both rows with the radar suffix and require the suffixed citation everywhere.
4. **Issue-filed lanes get placeholder radar rows** — R34/R35 were filed as issues before their radar doc landed; they hold their numbers and show a placeholder radar-file cell until the doc lands and the row is completed.
5. **Contested numbers cite by issue** — if a correction note (like #1746) proposes renumbering into occupied space, record the contested label as withdrawn in §3 and cite the lane by its issue number thereafter. Never re-issue a contested label into the free-number pool.
6. **Machine-checkable invariant:** every registry row must start with `| R<digits>` in column 1; a collision-free pre-flight is `rg -c "^\| R[0-9]+" docs/SCOUT_RADAR_INDEX.md` cross-checked against `rg -h "^\| R[0-9]+" docs/SCOUT_RADAR_2026-10-28*.md` (radar summary tables remain the lane SSOT; this file is the allocation registry).
7. **The index is the only counter** — the R40/R41 drift (see Drift log) shows what happens when a lane derives its number from run/sweep counts instead of this file: the number skips registered state and the freshness pass has to reconcile it after the fact. If you cannot take a number from this table (because the index is not landed where you are), file the lane by issue number and register the R-number here in the same PR — do not guess.

## 5. Honest limitations

An index is only as fresh as its last update — exactly the drift the script-index gate (#1644) solved for `scripts/`, and exactly the failure the Drift log records on day one (R40/R41 adopted issue-side before registration; reconciled same-day by pass 2). If allocation drift recurs, a later cycle can mirror that freshness-gate pattern onto this file (CI check: every `R<number>` defined in a radar summary table must appear exactly once here, and every `R<number>` cited in an issue body must exist in this registry). Statuses in the "Status" columns are point-in-time probe results (2026-10-28), not live state; the R-number → issue mapping and the §3 adjudication are the stable half of this registry. The R1–R12 rows carry no filed issue because radar I predates the issue-filing cadence; their verdicts are recorded in the radar-I file itself and are reproducible from it.
