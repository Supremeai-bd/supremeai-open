# #1690 Verification receipt r1 — the gateway license mismatch is already remedied on live main by #3156; residuals are admin-lane

- **Task ID:** `bridge-20261030-1690-license-recovery-r1`
- **Lane:** report-only verification receipt (docs-only, zero code, zero protected paths, no closure requested)
- **Agent:** GLM Agent 08 (Job 486735), cycle 12:08Z–12:3xZ 2026-10-30, zero-credential probes
- **Claim:** work_claim GRANT_TAKEOVER 12:11:36Z, 30-min lease (prior claim Job 477792 expired 849m > 30m ttl, loop pre-verified); released after filing

## Why this receipt exists

The loop dispatched #1690 (`audit:finding`, P2) whose headline is a live license-contract contradiction: `gateway/LICENSE` shipped MIT while ECOSYSTEM_MAP §2.3 classes the `supremeai-api` domain Private · Proprietary. Before claiming, the U3 STALE-INCIDENT doctrine required re-verifying every evidence point against live main. Result: **the in-envelope remedy is already landed** — the receipt records the skip-with-evidence so solvers stop re-solving a fixed finding, and names the two genuinely-open residuals precisely.

## Evidence point 1 — gateway/LICENSE is now the proprietary notice (REMEDIED)

`git log -- gateway/LICENSE` attributes the current file to `2dd1dc3 2026-10-30 fix(federation): resolve cross-satellite regressions, async I/O, and ci guards (#3156)`. Live head of the file:

> Proprietary License — All Rights Reserved
> Copyright (c) 2026 SaifulHaque Niloy. All rights reserved.
> … No open-source license is granted. See ECOSYSTEM_MAP.md §2.3 for the licensing policy.

This is exactly resolution 2 of the issue ("replace gateway/LICENSE with the standard proprietary notice"), and the notice self-anchors to the licensing SSOT.

## Evidence point 2 — zero MIT license headers remain in the mirror (REMEDIED)

Tree sweep over `gateway/**` (326 files): zero `MIT License` strings, zero SPDX MIT identifiers. The only 8 files grepping "MIT" carry the substring inside `RATE_LIMIT` / `LIMIT` identifiers (test env keys, rate-limiter code in `gateway/service/app.py`, `gateway/service/redis_rate_limit.py`, etc.) — the false-positive class, listed here so the next sweep does not re-derive it.

## Evidence point 3 — SSOT side unchanged and consistent

ECOSYSTEM_MAP §2.3 live text: strict MIT set = `supremeai-open`, `supremeai-studio`, `supremeai-vscode`; `supremeai-api` sits under "Proprietary / All Rights Reserved … provider gateway". Routing table maps `gateway/**` → `Supremeai-bd/supremeai-api`. With evidence points 1–2, the contradiction the issue describes no longer exists on live main.

## Residual A — satellite repo settings (admin-lane, still open)

Live tower `github_repo_info` probe (12:1xZ): `Supremeai-bd/supremeai-api` → `license: unknown/no-license`, description = "SupremeAI Unified Provider Gateway — API-key plane, provider routing contract, config-driven fallback (plan v1.0 → v1.1)" — **no `[PRIVATE]` tag** (the `supremeai-core` convention). Repo settings are outside every agent envelope (zero-credential bridge cannot edit them). Suggested admin one-liner: prefix the description with `[PRIVATE]` and either add a LICENSE file to the satellite or consciously accept the no-license display.

## Residual B — contract-surface license ambiguity (new datum, same class, policy verdict)

`api-schemas/**` (20 contract files incl. `gateway.openapi.yaml`, the generated `gateway_models.py`, and fixtures) carries **no per-tree LICENSE**; under the repo-root MIT these files are currently MIT-effective, yet §2.3's strict MIT list names only open/studio/vscode and the issue's resolution 2 expects the contract surface to stay public. "Public in open" does not by itself answer whether the contract files are MIT-**granted** (copy/sublicense rights) or public-to-read under the proprietary notice. Choosing between those is an IP-policy decision, not a mechanical fix — flagged for the admin's verdict, deliberately untouched by this agent. If the verdict is "proprietary", the one-line remedy is the same standard notice as `gateway/LICENSE`, dropped as `api-schemas/LICENSE`.

## Disposition

No closure requested: the filer/admin owns #1690's verdict (close-as-remedied vs keep-open for the two residuals). Refs #1690. Refs #3156.

## Verification

- Zero-credential reads only: git log/tree greps on the public clone @ origin/main `f5ef0ab`; tower `github_repo_info` on the satellite. No writes anywhere; claim released after filing.
- `continuous_agent_loop --verify-only`: 8/8 PASS at cycle intake and pre-submit; `CONTRACT_VERSION=agent-loop-contract/1` final line.
- `radar_index_freshness_guard --check`: exit 0 pre-submit (docs-only receipt, issue-number citations only).

## Reflection

**Why:** the P2 row still reads as a live IP contradiction to every priority scan; one receipt converts it into "remedied by #3156 + two named residuals", which is the cheapest way to stop solver churn and give the admin a decision-ready summary instead of a re-audit.
**Alternatives rejected:** (a) re-fixing gateway/LICENSE — already the standard notice; a second license file would create a new contradiction, not fix one; (b) adding `api-schemas/LICENSE` unilaterally — an IP grant/withholding decision, admin-lane by nature (Residual B is flagged, not decided); (c) silently skipping — the U3 guard requires the skip be recorded with evidence.

## Rollback

git revert-safe: delete this single receipt file (pure docs addition).
