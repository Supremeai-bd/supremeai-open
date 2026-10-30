# Platform guardian receipt — render-api `supremeai-api` latest deploy build_failed (2026-10-31)

- **Agent:** GLM Agent 28 · Job 486832 · platform-guardian cycle 2026-10-31 01:54+08 · health_full_sweep 17:54Z
- **Verdict:** sweep 33 providers → 32 healthy, 0 incidents, **1 degraded: `render-api`** — `lastDeployStatus: build_failed`, container serving the PREVIOUS build. ~5h deployment drift, no registered outage.

**বাংলা:** প্ল্যাটফর্ম সুইপে `supremeai-api` (Render) পাওয়া গেছে degraded — সর্বশেষ auto-deploy-এর Docker build আজ ৫ বার ব্যর্থ (১৩:০২→১৬:২৩ UTC), কনটেইনার আগের ভালো build চালাচ্ছে, তাই সার্ভিস down নয় কিন্তু তার নিজের main থেকে পিছিয়ে (deployment-drift ক্লাস)। মূল কারণ: Dockerfile ধাপ #13 `/gateway` পাথ খোঁজে যা build context-এ নেই। ফিক্স স্যাটেলাইট রিপোর মালিক/admin লেনে — এজেন্ট এনভেলপের বাইরে।

## Mechanical evidence (live probes 17:54–17:56Z)

1. `health_full_sweep` → `render-api: degraded, latency 177ms, consecutiveFailures 0, impactedServices []`, evidence summary: *"Container running previous build, but latest deployment build_failed"*.
2. `render_service_health` (account `render-api`, service `supremeai-api`, id `srv-dbappass728c7396p580`) → `lastDeployStatus: "build_failed"`; **not quota**: `freeLimitRemaining 439.8 / 500`, `monthlyBuildMinutes 60.2`.
3. `render_get_logs` (level=error, 2026-10-30 window) → 15 error rows, **5 distinct failed build attempts**: 13:02:50, 14:10:06, 14:17:41, 15:44:34, 16:23:23 UTC — every auto-deploy since ~13:02Z re-fails. Exact error, identical each time:
   `#13 ERROR: failed to calculate checksum of ref …: "/gateway": not found` → `error: failed to solve: failed to compute cache key … "/gateway": not found` → `error: exit status 1`.
4. Service config: repo `https://github.com/Supremeai-bd/supremeai-api`, branch `main`, `autoDeploy: yes` (commit-triggered), docker env, `dockerfilePath: Dockerfile`, rootDir "".
5. Board scan (88 open rows, 17:56Z): **no existing row covers this** — no `render-api` / `supremeai-api` / build_failed receipt found (anti-stampede U4/U5 checked before filing).

## Root cause (from the build plane)

Docker build step **#13** computes a checksum over a `/gateway` path that is absent from the build context of `Supremeai-bd/supremeai-api@main` — the classic drift shapes: a `COPY gateway/ …` (or `WORKDIR /gateway` + COPY) whose source directory was renamed/moved in a recent commit, or a `.dockerignore`/rootDir change that excluded it. The exact line needs the satellite repo's tree, which is outside this open-repo agent envelope (boundary invariant: satellite code lives in its own mirror).

## Impact

- No outage: health checks pass against the stale container (`consecutiveFailures 0`); no downstream service registered as impacted.
- The failure class is **silent drift**: `autoDeploy: yes` means every new commit to `supremeai-api@main` re-fails and the live service keeps diverging from its main — the intended-code-vs-running-code gap grows with each push.

## Requested disposition (admin / satellite lane owns it)

1. In `Supremeai-bd/supremeai-api`, reconcile Dockerfile step #13 with the tree (restore/rename the `gateway` source path or fix the COPY/.dockerignore).
2. Push the fix and verify the next auto-deploy reaches `build_deployed` (or trigger a manual deploy) — a green deploy supersedes this receipt; close citing the deploy ID.
3. No autoclose from the agent side: the remedy lives in a satellite repo + admin service config (HITL), so closure belongs to the verdict/admin plane.

## Reflection Evidence

- **why:** the guardian sweep surfaced a degraded provider with zero registered impact — exactly the silent-drift shape a "no incidents" summary hides. Recording it as an actionable row (not walking past it) is invariant-8 discipline; a stale-build service that keeps failing on every push will drift indefinitely until someone reads the build log, and today's log read already identified the failing step and the missing path.
- **alternatives_rejected:** (a) patching `supremeai-api` via this bridge — boundary violation: satellite code never rides the open-repo plane, and the bridge targets supremeai-open only; (b) `action_render_deploy` trigger — redeploys the same broken commit and re-fails identically, and deploys are admin/HITL-owned; (c) worklog-only note — not durable, not queue-visible, nobody owns the disposition; (d) waiting for a scheduled re-probe — the drift is structural (config/repo mismatch), not transient, so it will not self-heal.
