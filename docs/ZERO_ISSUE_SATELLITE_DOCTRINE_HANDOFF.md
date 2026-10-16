# Zero-Issue Satellite Doctrine — Operator Hand-Off (Phase 1 + Phase 3)

- **Issue:** #425 (`arch(governance): Zero-Issue Satellite Doctrine`)
- **WO:** `bridge-20261017-zero-issue-doctrine-handoff`
- **Author:** zai-autonomous-contributor
- **Date:** 2026-10-17
- **Lane:** pure-new-file doc hand-off (`.github/` paths are mechanically unbridgeable — measured hard block; existing-file hunks are the measured drift-death class #377/#415). Same proven pattern as `#393 §3`, `CLAIM_LEASE_DROPPIN §3`, `STUDIO_SATELLITE_IMPORT_DEPREFIX_HANDOFF`.
- **Claim state at intake:** #425 verified unclaimed (0 assignees, 0 PRs, 0 WOs, minutes old).

## 1. Scope contract — which phase rides where

| #425 Phase | Deliverable form | Why |
|---|---|---|
| **Phase 1** — satellite template lockdown | **This doc §2** (byte-exact `config.yml` + deployment matrix) | `.github/*` rejected by `bridge_submit_patch` (protected-path block, measured session-24); 11/12 satellites are private — only the studio satellite is publicly verifiable |
| **Phase 2** — monorepo issue drainage | **Operator-side, no public artifact** | Private monorepo issue board is not publicly readable (404); migration decisions need private context |
| **Phase 3** — constitution codification | **This doc §3** (byte-exact AGENTS.md + ECOSYSTEM_MAP.md blocks with placement anchors) | AGENTS.md/ECOSYSTEM_MAP.md are existing files — direct hunks die on private-main drift (#377 ECOSYSTEM_MAP:20, #415 :53) |
| **Phase 4** — dispatcher priority enforcement | **Blocked, non-goal** | `continuous_agent_loop.py` is double-booked (#378+#379) and declared unknowable without private access — the identical non-goal already recorded on WO #417 |
| CI-failure telemetry principle | Principle codified in §3.1(4); **mechanism deferred** | The issue names the invariant but specifies no event contract; the priority-ordering half is sibling territory (#374, WO #423). Designing an unsolicited dispatch workflow = scope creep — file a follow-up issue if the mechanism is wanted |

## 2. Phase 1 deliverable — satellite issue-template lockdown (byte-exact)

Create `.github/ISSUE_TEMPLATE/config.yml` on the **default branch of each of the 12 satellites** with EXACTLY:

```yaml
blank_issues_enabled: false
contact_links:
  - name: "SupremeAI Federation Central Issue Hub"
    url: "https://github.com/Supremeai-bd/supremeai-open/issues/new/choose"
    about: "All bug reports, feature requests, and agent tasks for this repository are centralized on supremeai-open."
```

Deployment matrix (the 12 satellites, matching the landing.yml `repo:` label arms):

| # | Repository | Apply mode |
|---|---|---|
| 1 | `Supremeai-bd/supremeai-studio` | **Verified clean-add**: studio `main` `.github/` contains only `workflows/` — no `ISSUE_TEMPLATE/` dir exists; the file is a new addition with zero merge concerns |
| 2-12 | `supremeai-core`, `supremeai-api`, `supremeai-skills`, `supremeai-command`, `supremeai-browser`, `supremeai-vscode`, `supremeai-agents`, `supremeai-sdk`, `supremeai-infrastructure`, `supremeai-mcp-control-plane`, `supremeai-archive` | Private — operator applies directly |

- **Hub exempt:** `supremeai-open` already runs a full `ISSUE_TEMPLATE/` set including a richer `config.yml` (it IS the canonical hub — its intake must stay open).
- **Optional operator extension:** the same file on the private monorepo (`Supremeai-bd/supremeai`) enforces Phase 2's drainage goal at the intake level. Operator discretion — the issue scopes Phase 1 to satellites.

**Verification (per satellite):**
1. `GET /repos/<satellite>/contents/.github/ISSUE_TEMPLATE/config.yml` → `200` on the default branch.
2. UI: satellite **Issues → New issue** no longer offers a blank issue — only the hub contact link.
3. The "Open in GitHub Copilot app" / template chooser shows exactly one community contact.

## 3. Phase 3 deliverable — constitution codification (byte-exact blocks)

### 3.1 AGENTS.md — insert as **§2.3.7**, AFTER §2.3.6 (Ephemeral Transit Pipeline, ends before `## 3. New Agent: Required Reading Path`):

```markdown
### 2.3.7 Zero-Issue Satellite Doctrine (#425)

`Supremeai-bd/supremeai-open` is the **sole canonical issue and task hub** for the federation (একক উন্মুক্ত হাব নীতি):

1. Every bug report, feature proposal, refactoring task, and bridge work order targeting ANY federation component is authored, ranked, claimed, and tracked on `supremeai-open`, tagged with its canonical `repo:<target>` label (13-label taxonomy = the `landing.yml` label arms).
2. Satellite repositories maintain a **zero-issue footprint**: `.github/ISSUE_TEMPLATE/config.yml` with `blank_issues_enabled: false` and a single contact link to this hub (byte-exact block: `docs/ZERO_ISSUE_SATELLITE_DOCTRINE_HANDOFF.md` §2). Maximum one static Architectural Blueprint issue (#1) per satellite.
3. Landed bridge work orders flip their upstream hub issue to `bridge:landed` and close it — **no orphan tracking issues** may be left on the private monorepo (intake zero-residue guarantee).
4. CI failures on any satellite or monorepo `main` report to this hub (`bridge:ci-failure` + `repo:<name>`) instead of opening isolated satellite issues.
```

### 3.2 ECOSYSTEM_MAP.md — append as **§6.3** at the end of §6 (after the "Reusable building blocks (cross-federation SSOT)…" paragraph that closes §6.2, i.e., end of file):

```markdown
### 6.3 Zero-Issue Satellite Doctrine (#425)

All federation issues live on **this repository** — one board, 13 `repo:<target>` labels, zero scattering. Satellites run `.github/ISSUE_TEMPLATE/config.yml` (`blank_issues_enabled: false` → hub contact link); landed work orders close their upstream hub issue as `bridge:landed` with no orphan monorepo issues. Full doctrine: `AGENTS.md` §2.3.7.
```

## 4. `repo:` label taxonomy cross-check (issue §2 vs landing.yml)

The 13 labels listed in #425 were verified against the `landing.yml` label arms (`repo:studio|api|core|command|skills|vscode|agents|browser|sdk|infra|mcp|archive|monorepo`) — **MATCH**. `repo:open` = the hub itself (no dispatch arm needed; the central monorepo append is unconditional).

⚠️ **Caveat:** `supremeai-archive` has a **label arm but no domain/path arm** — a work order targeting the archive satellite cannot be routed by touched files and MUST carry the `repo:archive` label. Worth remembering when the first archive-targeted issue appears.

## 5. Acceptance-criteria traceability

| #425 acceptance criterion | Coverage |
|---|---|
| Satellites have 0 open issues (or exactly 1 static blueprint) | §2 blocks new satellite issues at the UI level; existing stragglers: studio #1 (CORS bug — closes via the #408/#424 lane), studio #2 (bridge tracker, bot-managed) — operator closes any residue post-fix |
| Single dashboard for all 12+2 repositories | Already true for WOs; §3 codifies it permanently |
| Zero manual admin effort monitoring distributed boards | §2 prevents recurrence; Phase 2 drainage is the one-time cost (operator-side) |

## 6. Non-goals

- **No `.github/` writes through the bridge** (mechanically rejected).
- **No satellite hands-on** (11/12 private; studio changes ride the established WO→satellite lane only).
- **No Phase 2 drainage execution** (private board unreadable from here).
- **No Phase 4 dispatcher change** (loop file double-booked #378+#379, unknowable — same blocker as WO #417).
- **No CI-failure dispatch workflow design** (under-specified in #425; priority ordering is #374/#423 territory; mechanism belongs in a dedicated follow-up issue).
