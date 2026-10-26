# 🌉 Bridge Work Order — [P0] Studio CI green: fix the two admin-gate typecheck errors breaking the Verify & Build lane

Addresses the `handoff:coder` CI-failure orders on `Supremeai-bd/supremeai-studio` main
(#1417 and the sibling orders for runs 40385534200 / 40382764270 / 40382763769 — one shared
root cause). Failures started with the "Admin gate: server-verified code-only entry" commits
(19:00Z) and every sync since: runs die in 22–57 s at the Typecheck step, so the deploy job is
skipped and the Cloudflare Pages production build has been stale since 2026-10-26 ~19:00Z.

## The two errors (exact, from the failing run page)
1. `src/pages/admin/AdminShell.tsx(359,7): error TS17001: JSX elements cannot have multiple
   attributes with the same name.` — the `<AdminConsole>` JSX lists the four login props
   (`adminOtp`, `setAdminOtp`, `rememberBrowser`, `setRememberBrowser`) TWICE (first batch
   right after `handleAdminLogin`, second batch after `setNewUserPerms`). The gate rework
   pasted the login-prop group into the already-updated prop list.
2. `src/components/admin/AdminConsole.tsx(59,…): Property 'handleAdminLogout' is missing in
   type …` — the gate rework added a required `handleAdminLogout: () => void` to
   `AuthenticatedViewProps` (used as `onLogout`, AdminAuthenticated.tsx line 44/82), but
   `AdminConsoleProps` was not extended and AdminShell does not pass it, so the
   `<AuthenticatedView {...props} />` spread fails the typecheck.

## The fix (3 small edits, 2 files, public + satellite byte-identical bases)
- **studio/src/pages/admin/AdminShell.tsx**: remove the duplicated 4-prop block (keep the
  first occurrence); pass `handleAdminLogout={handleAdminLogout}` into `<AdminConsole>`
  (the value is already in scope from `useAdminStore()`).
- **studio/src/components/admin/AdminConsole.tsx**: add the required
  `handleAdminLogout: () => void;` to `AdminConsoleProps` (comment documents why).
- Logout keeps working end-to-end: AdminShell (store) → AdminConsole (props) →
  AuthenticatedView (`onLogout`, DB-backed trusted-device revocation). Making the prop
  optional was rejected — it would silently break the logout the gate just added.

## Verification (real, local, reproducible)
- tsc 5.9.3 parse-level check: BEFORE — original AdminShell.tsx reproduces
  `error TS17001 … (359,7)` exactly as CI; AFTER — no TS17001 (grep clean on both files).
- Diff bases re-fetched from the public tip at submission time; the public studio mirror and
  the satellite files are byte-identical (SHA-verified for AdminShell.tsx).
- Downstream steps (lint/vitest/build) untouched by these edits — no imports, exports,
  runtime paths or CSS classes change; only a duplicated JSX attribute removal and one
  required prop threaded through.

## Labels
`bridge:queued` `P0-critical` `area:ci` `repo:studio` `handoff:coder`
