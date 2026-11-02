# Evidence: #5191 — supremeai-vscode release pipeline fails `npm ci` (lockfile desync)

**Agent:** GLM Agent 26 (Job 486824) · **Date:** 2026-11-02 · **Mode:** evidence-only (remedy lives in satellite repo `Supremeai-bd/supremeai-vscode`, outside the supremeai-open agent envelope — no auto-close, verdict plane decides closure)

## Verified root cause (live reproduction on satellite main)

Satellite HEAD `0f859ef` (main, cloned 2026-11-02 ~03:38Z). Root `package.json` declares npm workspaces `['extension', 'desktop', 'mobile']` (name `supremeai-client-hub`). `desktop/package.json` declares `three ^0.187.0` and `@types/three ^0.187.0`, but the committed root `package-lock.json` contains **no entries for either package or their transitive closure**.

Live repro on the clone, verbatim:

```
$ npm ci
npm error code EUSAGE
npm error `npm ci` can only install packages when your package.json and
package-lock.json or npm-shrinkwrap.json are in sync.
npm error Missing: @types/three@0.187.0 from lock file
npm error Missing: three@0.187.0 from lock file
npm error Missing: @dimforge/rapier3d-compat@0.12.0 from lock file
npm error Missing: @tweenjs/tween.js@23.1.3 from lock file
npm error Missing: @types/stats.js@0.17.4 from lock file
npm error Missing: @types/webxr@0.5.24 from lock file
npm error Missing: fflate@0.8.3 from lock file
npm error Missing: meshoptimizer@1.1.1 from lock file
```

This matches the issue's package list exactly.

## How the desync was born (attribution)

Within visible history (shallow clone, depth 5), both `desktop/package.json` and `package-lock.json` were last touched by the **same** commit `3b5c9d9` (PR #4743, "Desktop user login", branch `bridge-20261101-vscode-user-login-r3`). That PR's title states it was **rebased on mirror main after two STALE_BASE rounds** — the lockfile shipped in that landing does not reflect the three.js deps the same landing added to the desktop manifest. Two structural observations:

1. The lockfile's `desktop` workspace entry lists `@tauri-apps/api, react, react-dom, react-markdown, remark-gfm` — no `three` / `@types/three`. The manifest and lock disagree on the same blob-pair.
2. Six of the eight missing packages (`@dimforge/rapier3d-compat`, `@tweenjs/tween.js`, `@types/stats.js`, `@types/webxr`, `fflate`, `meshoptimizer`) are the **dependency closure of `@types/three@0.187.0` itself** — they are declared nowhere in any workspace manifest, so nothing except a correct lockfile regen can restore them. (This is why the issue's mention of rapier3d looked puzzling: it is a transitive dep, not an undeclared direct one.)

## Verified fix (mechanical, deterministic)

```
$ npm install --package-lock-only     # exit 0, no hand-edited metadata
$ git diff --stat -- package-lock.json
 package-lock.json | 59 insertions(+), 1 deletion(-)
$ npm ci --dry-run                    # exit 0 — the exact gate that was red now passes
```

The diff is surgical: adds `three` + `@types/three` to the `desktop` workspace entry and inserts the six `@types/three` transitive entries with pinned versions/integrity hashes resolved from the registry. No other sections touched.

## Owner-lane action requested (single commit in supremeai-vscode)

1. On satellite main, run `npm install --package-lock-only` and commit the regenerated `package-lock.json` (mechanical patch; reproducible byte-for-byte against registry state).
2. Confirm a clean-runner `npm ci` plus the desktop typecheck/build and the release workflow go green.

## Root-cause fix (prevent recurrence — systemic, not just this row)

The failure class is "manifest and lockfile updated in different landing generations", enabled by rebase pipelines that can clobber one half of a manifest/lock pair. Prevention, in order of leverage:

- **CI gate on satellite repos:** add a job (or extend the existing satellite parity/sentinel gate in supremeai-open) that runs `npm ci --dry-run` on every change touching `**/package.json` or `**/package-lock.json`. It fails in seconds, before install, and catches this class deterministically. `.github/` is protected — owner lane must land it.
- **Bridge-side agent rule:** any landing that touches a `package.json` in a workspace repo MUST regenerate and co-land the lockfile in the same commit (same spirit as the Stale-Base Pin: a manifest without its lock is an incomplete landing).

## Evidence trail

- Claim: `work_claim` → `GRANT_NEW` at 2026-11-02T03:35:51Z (TTL 30min).
- Clone: `https://github.com/Supremeai-bd/supremeai-vscode` @ `0f859ef` (main).
- Repro + fix verification executed in sandbox 2026-11-02 03:40–03:50Z (node v24.22.1, npm 11.19.1).
- Issue-linked CI run (2026-11-01): `https://github.com/Supremeai-bd/supremeai-vscode/actions/runs/41278653710` (log payload no longer retrievable via API — live local repro on current main supersedes it as freshness proof).
