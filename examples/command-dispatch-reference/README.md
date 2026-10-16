# Command Dispatch Reference — remote task injection handlers (#331)

Zero-dependency reference implementation of the omnichannel remote task
injection routes: **webhook** + **Telegram** ingestion that validate every
payload against the landed deterministic 5-section instruction envelope and
enforce fail-closed RBAC — unverified or unauthorized triggers never reach
dispatch.

## Contracts implemented (SSOT — no copies)

| Contract | Path |
|----------|------|
| Instruction envelope (5 sections) | [`api-schemas/instruction-envelope.schema.json`](../../api-schemas/instruction-envelope.schema.json) (issue #30) |
| Permissions / RBAC policy | [`api-schemas/permissions.schema.json`](../../api-schemas/permissions.schema.json) (issue #28), canonical instance: [`api-schemas/fixtures/permissions.fixture.json`](../../api-schemas/fixtures/permissions.fixture.json) |

- `src/schema_lite.mjs` — minimal Draft-2020-12 subset validator carrying
  EXACTLY the keyword set used by those contracts. Unknown schema keywords
  **fail closed** (the validator refuses to run), so contract drift can never
  silently weaken validation. `format` is annotation-only (Draft 2020-12).
- `src/dispatch.mjs` — `createDispatcher({ envelopeSchema, permissionsPolicy,
  webhookSecret, authorizedChatIds })`:
  - `handleWebhook({ body, headers })` — `x-supreme-signature` gate → JSON
    parse → envelope schema validation → RBAC → `202` structured acceptance.
  - `handleTelegramUpdate(update)` — authorized chat gate → deterministic
    `/task <issue> <objective>` grammar → envelope construction → same gate.
  - `authorize(role, scopeId, action)` — deny-by-default chain: unknown
    scope/action → deny; specialist sub-roles pinned to their
    `agent_sub_roles.allowed_permission_scope_ids` → deny when ungranted;
    tier < `min_role_tier` → deny; MFA-required scope without token → deny.

## Fail-closed posture (issue #331 acceptance criterion 3)

Every rejection is structured: `{ ok: false, error: { code, reason } }` —
`403 UNVERIFIED_SOURCE` (missing/wrong webhook secret), `403 UNAUTHORIZED_CHAT`
(unauthorized Telegram chat), `403 UNAUTHORIZED` (RBAC deny-by-default),
`422 MALFORMED_JSON`, `422 MALFORMED_COMMAND`, `422 ENVELOPE_INVALID` (with
per-error details). Nothing is partially processed: validation and
authorization complete BEFORE any acceptance.

## Run

```bash
npm run build   # node --check both modules
npm test        # 16 offline tests against the REAL landed contracts
```

The tests demonstrate both RBAC directions honestly: the **canonical**
permissions fixture (which does not yet grant a task-ingestion scope) **must
deny** every ingestion (deny-by-default), while a deployment-extended policy
granting `remote-task-injection` to the coder sub-role **may accept** — with
MFA-gated variants. Granting that scope for real deployments is an
ADMIN_DECISION, out of scope for this reference.
