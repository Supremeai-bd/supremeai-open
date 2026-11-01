# SupremeAI Desktop Admin Console

The desktop console is currently **platform-owner-only and read-only**. It displays the existing service health map and tenant usage overview. There are no create, edit, delete, billing, account-management, shell, or arbitrary-command controls in the desktop client.

There are no tenant administrators provisioned for the current rollout. Tenant-admin sign-in is therefore disabled in both the desktop UI and the native Tauri command boundary. Keep it disabled until owner-controlled provisioning, a least-privilege permission matrix, revocation, and auditable server-side actions are implemented and tested.

## Owner sign-in and session handling

Open **Admin console** from the desktop sidebar and sign in with the platform owner's existing SupremeAI credentials. If Gateway policy requires TOTP, enter a fresh six-digit authenticator code. The desktop does not request or persist trusted-device tokens; access tokens are kept only in process memory and cleared on sign-out or when closing the console.

The owner email must be in the Gateway's configured admin allowlist. Owner tenant-overview reads are separately restricted to an `admin` token whose email is allowlisted. Desktop dashboard reads use the existing Gateway tenant-overview endpoint and primary API `/admin-api/health-map` endpoint.

## Required server configuration

The Gateway service needs the following secrets through its existing environment/Infisical configuration:

- `SUPREMEAI_JWT_SECRET` (or an approved existing secret alias), shared with the primary API. Deployed environments fail closed if no signing key is configured; the development fallback is available only when `ENV` explicitly identifies a local or test environment.
- `SUPABASE_URL`, `SUPABASE_ANON_KEY` (or `SUPABASE_KEY`), and `SUPABASE_SERVICE_ROLE_KEY` are used by the existing tenant-authentication/read path. The service-role key must never be shipped to the desktop.

## Tenant-admin enablement prerequisites

When tenant administrators are introduced, their grant must come only from trusted server-managed Supabase Auth `app_metadata`, never user-editable `user_metadata`. The tenant ID must match a real tenant record, and every endpoint must derive scope from the signed server-validated claim rather than a client-supplied tenant ID. Before enabling this role in the desktop, add owner-only provisioning/deprovisioning, explicit permissions per operation, MFA/step-up for sensitive actions, audit records, and tests for cross-tenant denial. The current UI and native command intentionally expose no tenant-admin login path.

## Safe-write prerequisites

Do not wire existing backend CRUD endpoints directly to desktop buttons. Before adding writes, each server endpoint must enforce role and tenant scope, require recent step-up authentication for sensitive actions, validate a bounded action schema, protect against replay, record an audit event, and return an outcome the UI can verify. The desktop should show a preview and require an explicit confirmation before dispatch. No arbitrary shell or command-execution facility is part of the admin console.

The displayed tenant usage is the recorded daily total from `tenant_usage`, uses UTC day boundaries, and may not include transient Redis counters. Missing telemetry must remain visibly unavailable rather than be presented as confirmed healthy or zero.
