# AUDIT — 2026-10-16 post-#280 webhook bridge channel is dead in production (unsigned POST → live-verified HTTP 401; event shape rejected by the tower's own intake contract)

> **id:** audit-2026-10-16-bridge-webhook-contract
> **title:** landing.yml streams bridge orders to the production tower unsigned (401) with an event name and payload shape the tower's intake does not accept — three independent rejection layers, failures soft-silenced
> **document_role:** audit
> **status:** active
> **canonical:** true
> **owner:** agent-orchestration (Auditor role, AGENT_RULES.md §3)
> **last_verified:** 2026-10-16
> **related_docs:** [INGRESS_SECURITY_POLICY.md](INGRESS_SECURITY_POLICY.md) · [AUDIT_2026-10-16-stale-base-guard-frozen-base-sha.md](AUDIT_2026-10-16-stale-base-guard-frozen-base-sha.md) · [AUDIT_2026-10-16-account-chain-dangling-ref.md](AUDIT_2026-10-16-account-chain-dangling-ref.md)
> **source_issue:** filed via bridge (this document's own Work Order)

> **Auditor:** external autonomous contributor agent (zero-credential Pathway 1, AGENTS.md §2.1).
> **Method:** fresh-surface audit of the just-landed #280 transition (main `9e604a8`): the new
> webhook streaming step was checked against the tower's own public-mirror contract
> (`webhook_signature.ts`, `bridge_intake.ts`, `normalizer.ts`), then the production endpoint
> was probed live. Severity **P2** (the transition's default delivery channel is
> non-functional and its failure mode is silent; the repository-dispatch fallback works only
> when `BRIDGE_DISPATCH_TOKEN` is configured — unverifiable anonymously),
> **agent-orchestration** group.

## Finding — P2 · agent-orchestration · three independent rejection layers + soft-silenced failure

The "Stream landed patch reference via Webhook / Bridge Intake" step (landing.yml, landed by
#280) posts to `BRIDGE_WEBHOOK_URL` (default: the production tower
`https://supremeai-mcp-tower.onrender.com/webhooks/github`) with headers
`Content-Type`, `User-Agent`, `X-GitHub-Event: bridge_order_queued` — **no signature** — and
a payload `{event_kind: "bridge.order.queued", source_repo, pr_number, …}`. Against the
tower's own public-mirror contract this request is rejected three independent ways:

1. **Signature (live-verified):** the tower requires `X-Hub-Signature-256` in production —
   `hasWebhookSignature()` (`src/lib/webhook_signature.ts`) fail-closes on missing secret or
   missing `sha256=` header, comparing the constant-time HMAC of the raw body. **Live probe
   2026-10-16:** `POST /webhooks/github` with the exact shape the workflow sends →
   `HTTP 401 {"error":"Invalid webhook signature"}`.
2. **Event name:** the intake's `decide()` (`src/events/bridge_intake.ts`) accepts only
   `issues`×{opened,reopened,labeled}, `pull_request`×{opened,reopened,synchronize},
   `issue_comment`×{created}; anything else → `unsupported event: bridge_order_queued.`
3. **Payload shape:** even before the type check, `decide()` requires
   `payload.repository.full_name` (the webhook sends `source_repo` instead) and a
   non-`[bot]` `sender.login` (absent) → `missing repository identity`.

The step's failure handling is soft by design (`|| true`) but **silent in effect**: the
webhook branch only echoes "Bridge Webhook returned HTTP 401" with no `::warning::`, and the
dispatch fallback (#2, correctly shaped `event_type`+`client_payload`) runs only when
`BRIDGE_DISPATCH_TOKEN` is set — if it is not, the run ends with the informational
"BRIDGE_DISPATCH_TOKEN not set; webhook delivery completed." and **no landed-patch reference
reaches the private intake at all**. Net: since #280 removed the issue-driven intake, the
public→private bridge sync's default path is structurally dead.

## Verified fix — carried diff for an authorized lane (`.github/` is bridge-protected)

Sign the POST and send a GitHub-shaped event the tower's existing intake accepts (validated
against the mirror's own code — see evidence), keeping the dispatch channel untouched:

```diff
--- a/.github/workflows/landing.yml
+++ b/.github/workflows/landing.yml
@@ -415,6 +415,7 @@
         env:
           BRIDGE_DISPATCH_TOKEN: ${{ secrets.BRIDGE_DISPATCH_TOKEN }}
           BRIDGE_WEBHOOK_URL: ${{ secrets.BRIDGE_WEBHOOK_URL || 'https://supremeai-mcp-tower.onrender.com/webhooks/github' }}
+          BRIDGE_WEBHOOK_SECRET: ${{ secrets.BRIDGE_WEBHOOK_SECRET }}
           PR_NUM: ${{ steps.check_scope.outputs.pr_num }}
```

```diff
--- a/.github/workflows/landing.yml (run block, webhook section)
@@
-          # 1. Stream directly to Webhook (MCP Tower / Bridge Ingress)
-          if [ -n "${BRIDGE_WEBHOOK_URL}" ]; then
-            echo "Streaming patch event to Webhook: ${BRIDGE_WEBHOOK_URL}..."
-            HTTP_WH=$(curl -s -o /tmp/webhook_resp.txt -w "%{http_code}" -X POST \
-              -H "Content-Type: application/json" \
-              -H "User-Agent: SupremeAI-Bridge-Webhook/1.0" \
-              -H "X-GitHub-Event: bridge_order_queued" \
-              "${BRIDGE_WEBHOOK_URL}" \
-              -d "${PAYLOAD}" || true)
-            echo "Bridge Webhook returned HTTP ${HTTP_WH}"
-          fi
+          # 1. Stream directly to Webhook (MCP Tower / Bridge Ingress).
+          #    Tower contract: production rejects unsigned POSTs (hasWebhookSignature,
+          #    src/lib/webhook_signature.ts — HMAC-SHA256 over the RAW body, "sha256=<hex>")
+          #    and the bridge intake accepts GitHub-shaped issues+labeled events only
+          #    (src/events/bridge_intake.ts decide(): repository.full_name + sender +
+          #    action ∈ WAKE sets). Sign the exact bytes POSTed; the bridge_order context
+          #    rides inside the payload for downstream visibility.
+          if [ -n "${BRIDGE_WEBHOOK_SECRET}" ]; then
+            export BRIDGE_ORDER_JSON="${PAYLOAD}"
+            WEBHOOK_BODY=$(python3 -c '
+          import json, os
+          order = json.loads(os.environ["BRIDGE_ORDER_JSON"])
+          body = {
+              "action": "labeled",
+              "repository": {"full_name": order.get("source_repo", "Supremeai-bd/supremeai-open")},
+              "sender": {"login": "supremeai-bridge"},
+              "issue": {"number": order.get("pr_number", 0),
+                        "title": "Bridge order for PR #%s: %s" % (order.get("pr_number", "?"), order.get("task_id", "")),
+                        "labels": [{"name": "bridge:queued"}]},
+              "label": {"name": "bridge:queued"},
+              "bridge_order": order,
+          }
+          print(json.dumps(body))
+          ')
+            SIG=$(printf '%s' "${WEBHOOK_BODY}" | openssl dgst -sha256 -hmac "${BRIDGE_WEBHOOK_SECRET}" | awk '{print $2}')
+            HTTP_WH=$(curl -s -o /tmp/webhook_resp.txt -w "%{http_code}" -X POST \
+              -H "Content-Type: application/json" \
+              -H "User-Agent: SupremeAI-Bridge-Webhook/1.0" \
+              -H "X-GitHub-Event: issues" \
+              -H "X-Hub-Signature-256: sha256=${SIG}" \
+              "${BRIDGE_WEBHOOK_URL}" \
+              -d "${WEBHOOK_BODY}" || true)
+            case "${HTTP_WH}" in
+              2*) echo "✅ Bridge Webhook accepted (HTTP ${HTTP_WH})." ;;
+              "") echo "::warning::Bridge Webhook unreachable — no HTTP status returned." ;;
+              *) echo "::warning::Bridge Webhook returned HTTP ${HTTP_WH} — tower did not accept the bridge order (check BRIDGE_WEBHOOK_SECRET/URL)." ;;
+            esac
+          else
+            echo "::warning::BRIDGE_WEBHOOK_SECRET not set — webhook streaming SKIPPED (production tower rejects unsigned webhooks with HTTP 401; live-verified 2026-10-16)."
+          fi
```

Admin alternative (equally valid, tower-side): add a dedicated signed bridge route/acceptance
to the tower and keep the workflow's custom event — but the workflow must still SIGN either
way (layer 1 is unconditional in production).

## Evidence record

| Check | Result |
|---|---|
| Live probe (unsigned POST, exact workflow shape) | `HTTP 401 {"error":"Invalid webhook signature"}` from `supremeai-mcp-tower.onrender.com/webhooks/github`, 2026-10-16 |
| Signature recipe cross-validation | openssl HMAC over exact POST bytes ↔ mirror's own `hasWebhookSignature()` → PASS; tampered-body negative control → rejected |
| Intake acceptance of proposed shape | mirror's `BridgeIntakeService.decide()` on `normalizeGitHubEvent("issues", proposed)` → `accept=true, reason=issue.labeled` |
| Dispatch channel (#2) body shape | cleared — correctly wrapped `event_type` + `client_payload` |
| `set -e` posture | cleared — webhook/dispatch are post-landing notify channels; soft-fail is the design; the carried diff upgrades silence to `::warning::` |
| Audit base | main `9e604a8` (#280 landed) |
