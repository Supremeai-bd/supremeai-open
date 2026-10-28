# Fleet Contract Probe — D4 contract-gated deploy health (bridge 2026-10-28)

**Lane**: platform-guardian / coder (standing directive, unclaimed lane)
**Lineage**: #1819 → #1835/#1836 → **#1874** (D2/D3/D4 directives) → #1930 (D3 sentinel) → **this artifact (D4 instrument)**
**Probe window**: 2026-10-28T04:06Z–04:17Z (tower handshake + zero-credential live probes)
**Anti-stampede scan** (04:08Z, 20 open WOs): #1933 `status:claimed` (auto-lander race, superseded by #1950); #1897 unclaimed but its RCA is queued as #1905 by another agent (hands-off); #1912 is an admin-runbook — a validated +6-line `.github/workflows/pipeline.yml` diff that per the #1643/#1769 protected-path rule lands as a single admin commit, not an agent PR; #1934 is a completed guardian report, not a task. No open, unclaimed, agent-landable P0/P1/P2 in agent lanes this cycle → executed the remaining directive from my own merged #1874 artifact (D4), the same unclaimed-lane precedent as #1930 (D3).

## Why D4 is still open — fresh evidence this cycle

#1874 documented the polarity: after the #1819 swap window closed and the gateway edge served the fixed contract (10/10), provider snapshots kept reporting the stale failure. This cycle the same polarity repeated on a different service set, captured live:

| tower system_health (04:06Z) | live edge probe (04:10–04:17Z) | verdict |
|---|---|---|
| render-primary `update_failed` — "Container running previous build" | `/health` → 200, full contract shape, **`uptime_seconds=9614` ⇒ container started ≈01:30Z** (fresh), `checks` all healthy | **FALSE_NEGATIVE_HEALTH** |
| render-worker `update_failed` | `/health` → 200, `status:"ok"`, `runner_version` pinned shape | **FALSE_NEGATIVE_HEALTH** |
| render-mcp `update_failed` | `/health` → 200, coherent aggregation body `services:{healthy:30,degraded:3,total:33}` | **FALSE_NEGATIVE_HEALTH** |
| render-api `live` | `/healthz` → 200, 5-field liveness, zero redaction-class markers | ALIGNED |
| render-scraper `live` | `/health` → 200, posture fields noted (see Observations) | ALIGNED |

Two structural facts make deployStatus-only health untrustworthy, now with a standing instrument:

1. **`update_failed` outlives its incident.** Primary's fresh container (~01:30Z) serves a healthy contract while the record still says the deploy failed — the record answers "did the platform's last deploy attempt finish", not "is the edge serving". Both primary and tower kept the stale flag at 04:06Z–04:17Z.
2. **Two vocabularies share the word "degraded".** Tower `/health` returns HTTP 200 with body `status:"degraded"` (downstream aggregation contract), while provider `deployStatus:"degraded"` means a failed deploy attempt. A consumer that joins them naively mis-triages. The probe pins tower by SHAPE (`services.{healthy,degraded,total}` required) and surfaces body-status separately (`CONTRACT_OK_BODY_DEGRADED`), never as drift.

## The instrument: `scripts/ci/fleet_contract_probe.py` (stdlib-only, zero-credential)

- **Fleet table**: the 5-node SSOT vocabulary of `gateway/service/app.py` `/api/health-aggregation` (`api, scraper, tower, primary, worker`; env overrides `RENDER_{ID}_URL`); URLs live-verified 04:10Z. Deep gateway probing stays in `boundary_contract_sentinel.py` (12 probes) — this module is the fleet-wide shallow health-surface contract, complement not duplicate.
- **Per-node pins**: required keys (+ nested `services.{healthy,degraded,total}` for tower), per-node body-status vocabulary (**worker answers `"ok"`, not `"healthy"` — pinning one global word would false-positive a healthy node**, the wolf-proof lesson from #1874), forbidden redaction-class markers on the `api` public surface (`stealth_dns`, `stealth_priority1`, `infisical`, fix-hint vocabulary — the #1902/#1908 class now guarded fleet-side).
- **Extra non-forbidden fields are NOTES, never drift** — fleet services legitimately evolve health payloads; a sentinel that cries wolf gets ignored.
- **Sentry polarity join** (`--sentry-json` from tower `system_health`): `ALIGNED` / `FALSE_NEGATIVE_HEALTH` (edge OK, sentry degraded — informational, never fails a gate) / `SILENT_REGRESSION` (edge drift, sentry live — the deadly #1819 class) / `CONFIRMED_INCIDENT` / `UNPROBEABLE`.
- **Exit contract**: `0` report-only or self-test, `1` only under `--strict` (ops lane), `2` all-unreachable honest skip — a network failure is never reported as pass. Self-test is hermetic: local fixture servers, **8/8 verdicts, miss=0, fp=0**, honest-skip proof, polarity-join proof.
- **Wiring**: `run_all_guards.py` GUARDS +1 (22/22 stable); `tests/test_fleet_contract_probe.py` 6/6 (offline, dual-mode); `scripts/ops/_INDEX.md` regenerated (512 scripts, check OK).

## Observations (report-only, no ask)

- **Scraper posture surface**: `/health` publishes `infisical_configured: true`, `total_cookies: 7`, `cookies_loaded`, `max_concurrency: 3` — boolean/count operational posture, no secrets, but it is the only fleet node advertising tooling posture on an unauthenticated surface. Recorded as an observation for the scraper service's owners (different repo); the probe deliberately does NOT classify it as drift (cross-fleet vocabulary is per-node).
- **Redis ledger watch-item** (carried from the 09:05 cycle): primary chain `softThresholdHit=true` at 480k/500k, cooldown to 2026-11-01; `cache_status` this cycle returns only the semantic-cache config (qdrant/gemini, hitThreshold 0.93) — the rate-limit ledger is not externally visible, so this stays an ops-lane watch item, and no `action_redis_*` mutation is touched by an agent.
- **CI board**: #1933's failure run (1932/merge) is moot — #1932 was superseded by #1950 (fresh rebase-equivalent cut, landed `498031b`); the issue now only needs its `status:claimed` holder (or a maintainer) to close on the landed supersession.

## Verdict

D4 is now an executable standing check, not a documentation ask: the fleet's "is it deployed correctly" question is answered by live contract probes joined against sentry records, with the polarity class that twice produced false-negative health (01:09Z primary/worker/render-api trio per #1874; 04:06–04:17Z primary/worker/mcp-tower trio per this cycle) mechanically named per node. Fleet verdict at probe time: **5/5 nodes on-contract**; 3 nodes `FALSE_NEGATIVE_HEALTH` (sentry lag only, zero edge drift).
