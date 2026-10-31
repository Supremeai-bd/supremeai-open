# SupremeAI Desktop Admin Console

The desktop Admin console is a read-only workspace in the existing desktop application. Platform owners see the service health map and tenant usage overview. Tenant administrators see only the tenant assigned to their account, its configured limits, and its recorded UTC daily usage. This first release intentionally has no create, edit, delete, billing, or account-management actions.

## Provision a tenant administrator

Tenant access is derived from Supabase Auth **app metadata**, which must be assigned by a trusted platform operator. In Supabase Auth, set the user's `app_metadata` to:

```json
{
  "role": "tenant_admin",
  "tenant_id": "<tenant id from tenant_limits>"
}
```

The `tenant_id` must exactly match a row in `tenant_limits`. The current table schema has no `is_active` column; row existence plus server-managed `app_metadata` is the grant. To deprovision access, remove the role/tenant assignment in Supabase Auth; deleting the tenant row also blocks dashboard reads immediately. Tenant sessions last one hour. Do not place the assignment in user-editable `user_metadata`; the sign-in endpoint ignores that field. The desktop never submits a tenant ID, and the tenant dashboard endpoint uses only the verified, signed claim.

## Server configuration

The Gateway service needs access to the following secrets through its existing environment/Infisical configuration:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY` (or the existing `SUPABASE_KEY`) for password authentication with Supabase Auth
- `SUPABASE_SERVICE_ROLE_KEY` for server-side, read-only tenant queries; this key must never be shipped to the desktop
- `SUPREMEAI_JWT_SECRET`, shared with the primary API so Gateway-issued tenant-admin tokens can be validated there

The existing platform-owner sign-in continues to use the Gateway's configured admin email/password and TOTP policy. The owner email must be in the Gateway's existing admin allowlist. Owner tenant overview reads are separately restricted to a valid `admin` token whose email is allowlisted.

## Sign in

Open **Admin console** from the desktop sidebar. Select **Platform owner** or **Tenant administrator**, then use the corresponding existing SupremeAI credentials. Owner accounts follow the existing TOTP step-up flow. Tenant-admin sessions expire after one hour; owner sessions follow the existing Gateway policy. The native desktop stores access tokens only in process memory and clears them on sign-out or when closing the console; tokens are not written to localStorage or disk.

If tenant data is unavailable, check that the tenant row exists and that the Gateway has the required Supabase service-role secret. Accounts that require an additional Supabase MFA challenge are denied by this initial flow rather than being issued a session without completing MFA; support for completing that challenge must be added before using such accounts here. The owner service-health card is read from the primary API's existing `/admin-api/health-map` endpoint. Tenant usage is the recorded daily total from `tenant_usage`; the display uses UTC day boundaries and may not include transient Redis counters.
