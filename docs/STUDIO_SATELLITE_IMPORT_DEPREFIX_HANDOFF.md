# Studio Satellite Import: Domain-Prefix De-Mapping Hand-Off

- **WO:** r2 of WO #408 (`bridge-20261017-studio-import-deprefix-r2`)
- **Author:** zai-autonomous-contributor
- **Date:** 2026-10-17
- **Lane:** pure-new-file doc hand-off (operator-owned private surface, per the established `#393 §3` / `CLAIM_LEASE_DROPPIN` pattern)

## 1. Defect (evidence-backed)

The satellite import of WO #408 (`fix(studio): CORS-rejection noise amplification + dead health telemetry`) produced **supremeai-studio#3 with payload paths imported literally**: `+1933/−0` across 7 files at `studio/**`.

That prefix is wrong **on the satellite**:

| Evidence | Finding |
|---|---|
| `git ls-tree origin/main` (supremeai-studio) | root layout: `package.json`, `src/**`, `e2e/`, `packages/` at repo root |
| `studio/` on satellite main | **ABSENT** (`git cat-file -e origin/main:studio` fails) |
| `.github/workflows/landing.yml` domain arm | `studio/*\|examples/dashboard-preview/*\|api-schemas/dashboard.*` → `Supremeai-bd/supremeai-studio` — the prefix is a **dispatch key evaluated on the monorepo**, not a satellite filesystem path |
| supremeai-studio#3 three-dot diff | 7 files under `studio/**`, all full additions (`+1933/−0`) |

**Impact if merged as-is:** a phantom duplicate tree lands next to the real root files. The satellite's Vercel deployment and CI build from the repo **root**, so the actual CORS-rejection fixes (`src/services/apiClient.ts`, `src/utils/api.ts`, `src/components/auth/ServiceHealthBar.tsx`) would **never execute** — studio#1 would stay broken while the board shows the WO delivered. It also contradicts the anti-bloat doctrine (AGENTS.md §2.3.6, landed via PR #419): +1933 dead lines, and the satellite→monorepo upstream sync could echo the phantom tree back into the monorepo.

**Content fidelity is NOT in question.** All 7 files are sha256-identical across (a) the satellite PR branch `bridge-land/bridge-20261016-studio-cors-resilience-r1`, (b) the monorepo branch `bridge/bridge-20261016-studio-cors-resilience-r1`, and (c) the author's satellite-local branch `d250a13`. The import is byte-faithful — **only the path prefix is wrong.**

## 2. Intended delta (what the satellite PR should show)

Strip the `studio/` prefix → satellite-root-relative paths:

| Monorepo path (payload) | Satellite path (correct import) |
|---|---|
| `studio/package.json` | `package.json` |
| `studio/src/services/apiClient.ts` | `src/services/apiClient.ts` |
| `studio/src/services/apiClient.test.ts` | `src/services/apiClient.test.ts` |
| `studio/src/utils/api.ts` | `src/utils/api.ts` |
| `studio/src/utils/api.test.ts` | `src/utils/api.test.ts` |
| `studio/src/components/auth/ServiceHealthBar.tsx` | `src/components/auth/ServiceHealthBar.tsx` |
| `studio/src/components/auth/ServiceHealthBar.test.ts` | `src/components/auth/ServiceHealthBar.test.ts` |

True delta: **7 files, `+188/−1`** (branch `d250a13`). The satellite main tip is `1001b1a` and its net content is byte-identical to the WO's base `88fc6e4` (commit `f225e71` "Reapply" was reverted by `1001b1a`), so the delta is a clean drop-in on current main.

## 3. Importer fix spec (private bridge-intake — operator-owned)

**Rule:** when a work order's target repository resolves through the domain-routing arms, the satellite import must **de-map the matched domain prefix** from each file path before creating the satellite PR branch.

- Strip the **longest matching** domain-arm prefix — prefixes are not all one component: `studio/`, `api/`, `gateway/`, `core/`, `command/`, `skills/`, `vscode/`, `agents/`, `runner/`, `browser/`, `sandbox/`, `sdk/`, `deployments/`, `infra/` are single-component, but `infrastructure/mcp-control-plane/` and `examples/dashboard-preview/` are **two-component**.
- The same de-map applies when resolution came from the `repo:<name>` **label channel** (`repo:studio` → supremeai-studio): strip the domain prefix that the label's arm pattern denotes (`studio/`).
- Files already satellite-root-relative (no domain prefix matched) pass through unchanged.
- File-alias arms (`api-schemas/dashboard.*` → studio, `api-schemas/gateway.*` → api, `examples/sdk-*` → sdk, `handlers/telegram*` → command, …) are **file-name aliases**, not directory prefixes; they need an explicit per-alias target-path table rather than a mechanical strip. Out of scope here — no live WO rides one yet. Record before the first such WO.

## 4. Disposition of the open phantom PR (supremeai-studio#3)

1. **Close without merging.** No satellite-side cleanup is needed — nothing on satellite main has changed (PR branch is bot-owned, never merged).
2. **Regenerate the satellite PR** from the existing monorepo branch `bridge/bridge-20261016-studio-cors-resilience-r1` with the de-map of §3 applied (or equivalently, apply the 7 mapped files of §2 directly — content is sha256-verified identical, see §6). The regenerated PR will show the true `+188/−1` delta.
3. No re-submission from the author is required for the content; this hand-off only unblocks the path mapping.

## 5. Post-merge verification (satellite)

- `pnpm install && pnpm vitest run src/services/apiClient.test.ts src/utils/api.test.ts src/components/auth/` → targeted **48/48**. Key contracts: CORS `TypeError` → exactly **1** fetch call (was 4); constructed timeout + 503 still retry to `MAX_ATTEMPTS=4` (cold-start contract #1679 intact); `publicHealthRefetchInterval` error=60000 / else=20000, never 0.
- Full-suite parity: failure set == pre-existing main baseline (10 undeclared-devDep transform failures + 2 cache.manager #2510); 573 passed. Typecheck parity: 12 == 12 pre-existing, 0 in touched files.
- Vercel deploy of `supremeai-studio-live`: console shows **no repeated CORS-origin-policy error storms** (deterministic `TypeError` fires once per re-fire, not 4×); the health chip recovers on 60 s backoff once the backend origin allowlist (private supremeai#205) lands.

## 6. sha256 manifest (content identity, satellite-root-relative names)

```
1f1956b03e2563aeef2a8faa7e0ececa3dca3cc56a1d3c3b75f3ed44e16edaa9  package.json
c25d2fc27cbdc27e177ae7b39afb21b3dd7fc2d9bdb34ae3c4fdbb2b1e2e586e  src/services/apiClient.ts
ce65a7d3cb2b84eb13d2f3540cbbdb08f38055cc2f9379d410261f44e9b4b4a3  src/services/apiClient.test.ts
b83dc0300af47a243f51957621f1824ff4d907af9e76f504f77139bf55dc28ab  src/utils/api.ts
8cda10358f8be50527e7311b58927d2af835b289779698e7905702c8fff745b6  src/utils/api.test.ts
637d9d07dfb30bd4255100f3bb4fb5a1bd62ceeaaf8a5bbb88fb0c6556a31cf5  src/components/auth/ServiceHealthBar.tsx
066f82ac9891d4d03c6dac325b20efc5fbe30f3946bfdbcfa8a4f5be1c7078b4  src/components/auth/ServiceHealthBar.test.ts
```

## 7. Non-goals

- **No change to `landing.yml` routing arms** — the `studio/` prefix is correct *as the monorepo dispatch key*; only the satellite import step needs the de-map.
- **No satellite-side workaround** (repo history reverted a hardcoded-backend-URL change within minutes — satellite main is hands-off except the true delta of §2).
- No redesign of the #419 event-driven auto-prune job (deltas recorded on WO #420 for signal-driven follow-up only).
