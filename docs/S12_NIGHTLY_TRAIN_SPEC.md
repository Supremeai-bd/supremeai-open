# S12 — Hub-and-Spoke Nightly Consolidation Engine

Implements **#492** — `plan(infra): [nightly-train]` Hub-and-Spoke
consolidation with **MCP Tower Boundary Isolation**.

## 1. Deliverables

| File | Kind | Purpose |
|---|---|---|
| `scripts/tower/nightly_train_reference.py` | new | Deterministic reference: 11-satellite registry, MCP Tower boundary gate (monorepo unreachable), nightly cron contract (`0 0 * * *` UTC), heavy-suite daytime exclusivity, fail-closed head ingest, parity verification with isolated-commit P0 incidents, `nightly-YYYYMMDD` tag contract, Phase 1-4 order gate, telemetry heartbeat to the public embassy + Studio. |
| `tests/test_s12_nightly_train.py` | new | 18 offline contract tests (dual-mode), incl. CLI exit-code smoke. |
| This document | new | Spec + out-of-lane wiring appendices (tower tool manifest; private monorepo workflow). |

## 2. Boundary Isolation (criteria 1 & 2)

`assert_tower_target()` fails closed: `Supremeai-bd/supremeai` (any case,
bare or org-qualified) raises `TowerBoundaryViolation` — the proprietary
monorepo hosting `supremeai-core` and the credential vaults stays outside
every MCP tool's operational scope. The 11 canonical satellites
(`open`, `studio`, `browser`, `command`, `skills`, `vscode`, `agents`,
`api`, `infra`, `sdk`, `core`) resolve normally; anything else is
rejected. The `core` satellite is distinct from the monorepo and remains
routable (documented distinction, tested).

## 3. Nightly Train Lifecycle (criteria 3-5)

Cron contract: exactly `0 0 * * *` in UTC (`validate_cron` — deviations,
wrong tz, wildcarded hours all rejected).

| Phase | Contract | Enforcement |
|---|---|---|
| 1 · INGRESS | read latest stable SHAs of all 11 satellites, merge into staging | `ingest_heads()` — all 11 present, unique, 40-hex, else `TrainError` |
| 2 · HEAVY_VERIFY | full internal battery: integration, e2e gateway, migrations, fallback probes, cross-boundary contracts | `is_heavy_suite()` / `assert_suite_allowed()` — heavy suites raise in daytime lanes; the train lane passes |
| 3 · LANDING | atomic squash-merge + `nightly-YYYYMMDD` tag + parity records | `ConsolidationRun.tag` (strict `YYYYMMDD`), `verify_parity()` — DRIFT/MISSING become isolated-commit `P0-critical` incidents |
| 4 · TELEMETRY | heartbeat broadcast to `Supremeai-bd/supremeai-open` + Studio dashboard | `build_heartbeat()` — `parity: 100%` or `REGRESSION` with incident list; broadcast targets fixed |

`assert_train_order()` — the four phases run in order, no skips.

## 4. Appendix A — tower tool manifest (out-of-lane repo, spec hunk)

`Supremeai-bd/supremeai` (private) tool registry applies the equivalent
of:

```typescript
// mcp-control-plane tool surface hardening (issue #492 criteria 1-2)
const TOWER_ROUTABLE_REPOS = [
  "Supremeai-bd/supremeai-open", "Supremeai-bd/supremeai-studio",
  "Supremeai-bd/supremeai-browser", "Supremeai-bd/supremeai-command",
  "Supremeai-bd/supremeai-skills", "Supremeai-bd/supremeai-vscode",
  "Supremeai-bd/supremeai-agents", "Supremeai-bd/supremeai-api",
  "Supremeai-bd/supremeai-infra", "Supremeai-bd/supremeai-sdk",
  "Supremeai-bd/supremeai-core",
]; // NOTE: "Supremeai-bd/supremeai" (monolith) deliberately ABSENT.
export function routeTarget(repo: string): string {
  if (repo.toLowerCase() === "supremeai-bd/supremeai")
    throw new Error("TOWER_BOUNDARY_VIOLATION: monorepo is outside MCP scope (#492)");
  if (!TOWER_ROUTABLE_REPOS.includes(repo))
    throw new Error(`TOWER_BOUNDARY_VIOLATION: ${repo} is not a canonical satellite`);
  return repo;
}
```

## 5. Appendix B — private monorepo workflow skeleton (out-of-lane repo)

`Supremeai-bd/supremeai` `.github/workflows/nightly_train.yml` skeleton
(criteria 3-4; protected path — maintainer applies):

```yaml
on:
  schedule:
    - cron: "0 0 * * *"   # 00:00 UTC nightly — exactly the contract
jobs:
  nightly-train:
    runs-on: [self-hosted, heavy]
    steps:
      - name: Phase 1 — ingest 11 satellite heads
        run: python3 scripts/train/ingest_heads.py --manifest staging.json
      - name: Phase 2 — heavy verification (exclusive to this train)
        run: python3 scripts/train/run_heavy_battery.py --lane nightly_train
      - name: Phase 3 — atomic landing + tag
        run: python3 scripts/train/land_and_tag.py   # nightly-YYYYMMDD
      - name: Phase 4 — telemetry heartbeat
        run: python3 scripts/train/broadcast_heartbeat.py
```

Daytime satellite workflows are expected to keep suites light
(`assert_suite_allowed(suite, lane)` guards the contract server-side).

## 6. Test evidence

18 offline tests green in dual mode (`python3 -m unittest
test_s12_nightly_train -v` / `pytest -q`), `--self-test` green. Coverage:
boundary (monorepo blocked case-insensitively, `core` satellite allowed,
unknown repos blocked), cron exactness, heavy-suite lane gating, ingest
fail-closed matrix (missing/duplicate/unknown/malformed SHA), parity
happy/drift/missing with P0 incident isolation, tag strictness, phase
order, heartbeat clean/regression payloads, CLI exit codes (ALLOW 0 /
BLOCK 2).
