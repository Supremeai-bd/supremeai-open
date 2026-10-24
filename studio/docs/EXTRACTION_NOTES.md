# Studio Extraction Notes (Phase 2, roadmap §14)

**বাংলা:** monolith-এর `frontend/` এখানে root-এ এসেছে — import রিফ্যাক্টর ছাড়াই (§17 নিয়ম: extract ও refactor একসাথে নয়)।

## What was extracted

| Source (monolith) | Destination here | Why |
|---|---|---|
| `frontend/*` | repo root | IS the Studio client (`supremeai-studio-client`) |
| `packages/design-tokens` | `packages/design-tokens` | workspace dep of frontend |
| `packages/ui-components` | `packages/ui-components` | workspace dep of frontend |
| `packages/shared-services` | `packages/shared-services` | workspace dep (🟡 review later per Phase 0) |
| `packages/core-infrastructure` | `packages/core-infrastructure` | workspace dep (🟡 review later per Phase 0) |
| `packages/shared-types` | `packages/shared-types` | workspace dep; canonical contracts also in `supremeai-sdk` |

## Verified preconditions (Phase 0 probes)

- `frontend/src` → direct backend imports: **0**
- workspace packages → monolith-path imports: **0**
- workspace deps resolve via `pnpm-workspace.yaml` (`packages/*`)

## Rules (roadmap §4.1)

Keep out of this repo: private orchestration prompts, internal policy evaluation,
production credentials, privileged MCP execution code, internal memory datasets.

## Future work

- Replace `@supremeai/shared-types` with `@supremeai/sdk` dependency when SDK publishes (Phase 1 → 2 bridge)
- Public quality bar (§20): tests green, dependency scan, a11y pass
