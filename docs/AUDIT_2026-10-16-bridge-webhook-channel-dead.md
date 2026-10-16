# Bridge Webhook Dispatch Channel — Dead on Arrival (PR #280 fallout)

- Author: zai-autonomous-contributor (Z.ai Code autonomous contributor agent)
- Task ID: `bridge-20261016-bridge-webhook-dead`
- Base: Supremeai-bd/supremeai-open main `9e604a8`
- Lane: zero-credential Pathway 1 (audit-doc WO; the primary fix surface `.github/workflows/landing.yml` is outside the external-agent write boundary, and the tower-side half alone cannot restore the channel — see "Why not patched in-task")
- Trigger: scout round 3 sweep of the PR #280 surface ("replace issue-driven auto-bridge with webhook and direct dispatch")

## Finding F-W1 (P1 — integration break): the primary bridge-dispatch webhook channel cannot deliver any event

The new landing.yml "Stream landed patch reference via Webhook / Bridge Intake (#107)" step POSTs to the tower's `/webhooks/github` endpoint, but the sender and receiver disagree in **three independent ways**; any one of them alone kills the channel.

### Break 1 — Authentication: sender never signs, receiver requires a signature

Receiver (`infrastructure/mcp-control-plane/src/index.ts`, webhook block, verified on 9e604a8):

```ts
const isGithub = url === "/webhooks/github";
const secret = isGithub ? env.githubWebhookSecret : env.cloudflareWebhookSecret;
if (env.nodeEnv === "production" && !hasWebhookSignature(req.headers[signatureHeader]?.toString(), body, secret ?? "")) {
  res.writeHead(401, ...); // "Invalid webhook signature"
}
```

`hasWebhookSignature` (src/lib/webhook_signature.ts) fail-closes on missing secret, missing header, or non-`sha256=` prefix.

Sender (`.github/workflows/landing.yml`, webhook POST block): the curl sends only `Content-Type`, `User-Agent: SupremeAI-Bridge-Webhook/1.0`, and `X-GitHub-Event: bridge_order_queued` — **no `X-Hub-Signature-256` header is ever computed or sent**, and the workflow has no `GITHUB_WEBHOOK_SECRET` to compute one with.

Outcome in production: **HTTP 401 on every post**. (If the tower runs with NODE_ENV unset the check is skipped — but then Break 2 drops the event instead. There is no environment in which this body reaches the bridge intake.)

### Break 2 — Event type: the intake whitelist has no `bridge_order_queued`

`infrastructure/mcp-control-plane/src/events/bridge_intake.ts`, `decide()`:

```ts
if (type === "issues" && WAKE_ISSUE_ACTIONS.has(action)) ...
if (type === "pull_request" && WAKE_PR_ACTIONS.has(action)) ...
if (type === "issue_comment" && WAKE_COMMENT_ACTIONS.has(action)) ...
return { accept: false, reason: `unsupported event: ${type}.${action}` };
```

The workflow's `X-GitHub-Event: bridge_order_queued` normalizes to `event.type = "bridge_order_queued"` → **dropped as `unsupported event: bridge_order_queued.undefined`**. Repo-wide census (`rg --hidden`): `bridge_order_queued` appears **only** in `.github/workflows/landing.yml` — zero consumers exist anywhere in the tower source; the payload's `event_kind` field also has zero references in tower src.

### Break 3 — Payload shape: repository-dispatch wrapper vs webhook expectations

The workflow builds `{"event_type": "bridge_order_queued", "client_payload": {...}}` — the GitHub *repository dispatch* envelope. The intake's accepted paths read GitHub *webhook* envelopes (`payload.action`, `payload.issue.number`, `payload.pull_request.number`). No code path unwraps `client_payload` for this route.

### Live impact (observable)

- The step treats every HTTP code as non-fatal (`echo "Bridge Webhook returned HTTP ${HTTP_WH}"` — no `::error::`), so the breakage is **silent by construction**.
- Every sync WO currently on the board (e.g. #269 pr268-sync, #254 pr253-sync, #249/#248, #235, …) was produced by the OLD issue-driven auto-bridge before 9e604a8 landed. **Zero sync WOs have been produced by the new channel since it went live.** The surviving path is the secondary `repository_dispatch → Supremeai-bd/supremeai` POST (Bearer token), which works only when `BRIDGE_DISPATCH_TOKEN` is configured; the tower's own webhook ingress receives nothing.

## Proposed minimal fixes (for the authorized lane)

1. landing.yml (blocked surface): compute `SIG="sha256=$(python3 -c 'import hmac,hashlib,os;print(hmac.new(os.environ["GITHUB_WEBHOOK_SECRET"].encode(), os.environ["PAYLOAD"].encode(), hashlib.sha256).hexdigest())')"` over the exact posted bytes and add `-H "X-Hub-Signature-256: ${SIG}"`; provision `GITHUB_WEBHOOK_SECRET` as a repo secret mirrored to the tower.
2. Tower side (bridgeable surface, offered for whoever lands 1): teach the intake to accept the bridge-order event — e.g. in `decide()` accept `type === "bridge_order_queued"` with `eventKey: bridge-order:${payload?.client_payload?.task_id ?? "?"}` (idempotency via the existing dedup TTL), or unwrap `client_payload` in the normalizer. The exact patch is intentionally NOT invented here in full (auth model is an admin decision — see below).
3. Operator check: confirm `BRIDGE_DISPATCH_TOKEN` is set on the public repo so the secondary channel carries bridge orders until 1+2 land (it is the only thing keeping private intake fed right now).

## ADMIN_DECISION requested (§6 — intent not presumed)

- Auth model for tower-bound bridge orders: GitHub HMAC (`GITHUB_WEBHOOK_SECRET`) vs a dedicated shared-secret header/token for a non-GitHub sender. The workflow's sender is not GitHub's webhook service (custom User-Agent, custom event name), so treating it as one is a design choice, not a bug fix.
- Whether the tower should also accept `bridge_order_queued` envelopes from the private-repo dispatch path for symmetry.

## Why not patched in-task (U2)

- `.github/` is a hard-blocked path for external-agent patches (tower rejects, stricter than admin-review) — Break 1's primary fix lives there.
- A tower-only patch (Breaks 2+3) is bridgeable but insufficient: in production the request 401s at Break 1 before the intake runs, so shipping the tower half alone would not restore the channel and would falsely imply resolution.
- Fix shape depends on the auth-model decision above → §6 no-presumption.

## U9 sweep report

similar found: 1 (F-W1) | fixed in-task: 0 | filed follow-up: 1 (this WO) | no-overlap: sibling WOs #266/#270/#271/#272/#273/#274/#278/#281 scopes checked — none touch landing.yml's webhook step or the tower webhook/intake path.

## References

- PR #280 / commit `9e604a8` (channel introduction) · PR #279 (design) · `docs/INGRESS_SECURITY_POLICY.md` (ingress governance) · `infrastructure/mcp-control-plane/src/events/bridge_intake.ts` (intake whitelist) · `src/lib/webhook_signature.ts` (fail-closed verifier)
