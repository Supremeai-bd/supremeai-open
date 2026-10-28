# Ghost-tower vault master-key hazard — R57 option A agent-slice landed, platform runbook (report-only brief)

**Lane:** R57 (#2262, ecosystem-scout, Job 478520 04:25Z cycle, verdict `adapt`) — adopted in part this cycle. **Numbering note:** the ticket originally filed as R56 (20:29Z); the slot registered first for #2265 (a8bb80f/PR #2267, 20:42Z) — re-slotted to R57 by drift pass 18 per the pass-4 free-pool doctrine (adoption ≠ allocation; the issue number is the stable identifier). **Scope:** land the one agent-executable slice of the recommended option (the blueprint env declaration), carry the platform runbook for the rest, and register the lane same-cycle. Nothing here duplicates the deploy-lane RCA (`docs/bridge/bridge-20261028-deploy-lane-rca.md`, recommended-fix #2 second clause) — it operationalizes it.

## The hazard (structurally confirmed, dated receipts)

- Deploy-lane RCA boot log: render-primary `[VAULT] Generated new Master Key at /root/.supremeai_vault/vault.key` (01:02:53Z) — flagged "data-plane hazard: anything encrypted under the previous key becomes unreadable after redeploy".
- **Structural confirmation (this cycle's grep):** `browser/ghost_tower/credential_vault.py:25` sets `VAULT_DIR = Path(os.path.expanduser(r"~\.supremeai_vault"))` — the vault lives in the home dir, while the service's only persistent disk mounts at `/data/profile` (browser/render.yaml). The vault path is therefore **ephemeral on every redeploy**, successful or not — invisible to the deploy lane by construction, and the #2225 retry storm fired it repeatedly.
- The in-code fix chain already exists: `get_or_create_master_key()` (:32-48) resolves **env-first** (`CREDENTIAL_MASTER_KEY`), then keyfile, then generates a fresh Fernet key — the live failure mode. Repo-wide wiring of the env var: **exactly one occurrence, its own read site** (tracked grep + code_search, single hit) — nothing in any deployment plane sets it.

## What landed (option A agent-slice, this PR)

`browser/render.yaml` now declares `CREDENTIAL_MASTER_KEY` with `sync: false` on the `supremeai-browser` service (the ghost-tower host). Semantics, verified against the code path:

- **No-op until the secret exists:** `sync: false` means the value comes from the dashboard/Infisical; until the platform lane stores it, the env var is unset at boot, `os.getenv` returns empty, and resolution falls through to the keyfile/generate branch — byte-for-byte today's behavior. **Unset = rollback.**
- **Last-regeneration property:** once the platform lane stores the secret and it syncs, env-first wins on every boot; the next key generation is the last one, and vault material becomes stable across every future swap. This composes with R55's landed health gate: health checks now gate *whether* a new instance takes over; the master key env makes *what that instance can decrypt* stable.

## Platform runbook (option A remainder — zero code)

1. Generate one Fernet key offline on any machine with the `cryptography` package: call `Fernet.generate_key()` (the same constructor the vault itself uses at credential_vault.py:42) and print it — one line, no arguments, no file I/O.
2. Store it as an Infisical secret (fleet convention: `infisical_bootstrap.py` runs on every service boot; `browser/ghost_tower/sync_cookies_to_infisical.py` already carries ghost-tower material to Infisical by design; `scripts/ops/security/auto_repair_cloudflare_vault.py` writes secrets as an ops routine).
3. Map the secret to `CREDENTIAL_MASTER_KEY` on render-primary (dashboard env or Infisical mapping) — the blueprint declaration from this PR is the wiring placeholder.
4. **Time it to a redeploy:** the mapping takes effect on the next boot; anything encrypted under the current ephemeral key is lost at that swap by design (it would be lost at the next redeploy anyway) — so do the mapping as part of a planned redeploy, not before one.
5. Rollback: unset the env var (falls back to per-boot generation — the old, hazardous but known behavior).

## Rejected / deferred (per the scout's routing)

- **B — Render persistent disk for the vault:** heavier (disk cost, mount coupling, single-AZ constraints); persistence-via-env is the fleet convention (ticket opt-B).
- **C — rotation/KMS hardening:** deferred; sibling `core/security/secure_credential_store.py` already models both (`RotatingFernet` multi-key decrypt :49-75, `KMS_KEY_NAME` :193) and is the template if the ghost vault is ever unified post-wave-3.9 (ticket opt-C).
- **D — wait for #2225:** rejected outright — the deploy-storm **is** the exposure window; every retry and every success regenerates keys (ticket opt-D).

## Residual honesty notes

- `sync: false` semantics on blueprint-sync'd services: Render creates the env var in the dashboard without a value; if the platform lane never stores the secret, behavior is unchanged (env-first branch simply never fires). Whether the dashboard requires an explicit no-op save is a Render-UI detail — the mapping is idempotent either way.
- **Latent oddity (observation only, not fixed here):** `r"~\.supremeai_vault"` at credential_vault.py:25 is a raw Windows-flavored path string; on Linux it expands to a directory literally named `\.supremeai_vault` (backslash is a valid filename char). Harmless-but-consistent today (same path every boot, so keyfile resolution within one instance's life works); a candidate 1-line cleanup for any future code-touch of this file — noted so nobody mistakes it for the hazard.
- Quota impact of one more Infisical secret: honestly unverified (scout's flag, unchanged).
