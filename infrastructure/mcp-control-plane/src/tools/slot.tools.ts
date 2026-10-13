import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import {
  approveSlot,
  provisionSlot,
  reinstateSlot,
  revokeSlot,
  rotateSlotCredential,
  slotIdFor,
  suspendSlot,
  slotStoreMaxStalenessMs,
  getSlot as getSlotRecord,
} from "../policy/slot-verification.js";
import { clientCredentialId, isRegistryNetworkBacked, lastStoreVerificationAt, listSlotClients } from "../policy/client-registry.js";
import { readSlotAudit } from "../policy/slot-audit.js";
import type { UserRole } from "../policy/auth.context.js";
import { requireScope } from "./client.tools.js";

/**
 * Verified Slot Architecture tools (#48) — the dashboard/management plane.
 *
 * Slots are pre-provisioned, credential-bound identities (`slot_<name>` in
 * the operational registry). Lifecycle: provision (pending) → approve
 * (active) → suspend / reinstate / rotate → revoke.
 *
 * Guardrails encoded here:
 *  • No auto-elevation — a provisioned slot stays `pending` until approved.
 *  • Slot-per-instance — one credential per independent agent instance.
 *  • Rotation/revocation take effect on the immediate-next authorization
 *    check (see policy/slot-verification.ts assertSlotAuthorization).
 */

export async function registerSlotTools(server: McpServer): Promise<void> {
  server.tool(
    "slot.provision",
    "Provision a NEW credential-bound slot (Verified Slot Architecture #48). Returns the slot credential ONCE — store it securely. The slot starts 'pending' and authenticates nothing until slot.approve runs (no auto-elevation).",
    {
      name: z.string().min(1).max(64).regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/, "slot name must match ^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$"),
      role: z.enum(["viewer", "restricted_viewer", "repo_viewer", "agent", "admin", "supremeadmin"]).optional().describe("Slot role (default: viewer)"),
      tenantId: z.string().optional().describe("Tenant ID (tenant admin)"),
      adminToken: z.string().optional().describe("Tenant admin token"),
    },
    async (args) => {
      const { scope, error } = requireScope(args);
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      const tenantId = scope === "*" ? (args.tenantId ?? "tenant_default") : scope;
      try {
        const { slot, credential } = provisionSlot({ name: args.name, role: (args.role ?? "viewer") as UserRole, tenantId });
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              message: "Slot provisioned (status: pending). Approve it with slot.approve, then connect with the credential.",
              slot,
              credential,
              connection: {
                streamableHttp: { url: "/mcp?client=" + encodeURIComponent(args.name), headers: { "x-mcp-slot-token": credential } },
                sse: { url: `/agents/${encodeURIComponent(args.name)}/sse`, headers: { "x-mcp-slot-token": credential } },
              },
              warning: "The credential is shown ONLY ONCE. The URL alone is never authentication — without this credential the slot URL falls back to read-only viewer.",
            }, null, 2),
          }],
        };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "slot.approve",
    "Approve a pending slot so its credential can authenticate. Administrator action — there is no auto-elevation.",
    {
      name: z.string().describe("Slot name or full slot id"),
      tenantId: z.string().optional(),
      adminToken: z.string().optional(),
    },
    async (args) => {
      const { scope, error } = requireScope(args);
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      const slot = approveSlot(resolveSlotId(args.name), scope);
      if (!slot) return { isError: true, content: [{ type: "text", text: `Slot not found or not pending: ${args.name}` }] };      return { content: [{ type: "text", text: JSON.stringify({ message: "Slot approved — its credential now authenticates", slot }, null, 2) }] };
    }
  );

  server.tool(
    "slot.suspend",
    "Suspend a slot IMMEDIATELY (fail-closed). Access terminates on the immediate-next authorization check — no client reconnect required.",
    {
      name: z.string().describe("Slot name or full slot id"),
      reason: z.string().optional().describe("Why the slot is suspended (audit context)"),
      tenantId: z.string().optional(),
      adminToken: z.string().optional(),
    },
    async (args) => {
      const { scope, error } = requireScope(args);
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      const slot = suspendSlot(resolveSlotId(args.name), args.reason, scope);
      if (!slot) return { isError: true, content: [{ type: "text", text: `Slot not found or already revoked: ${args.name}` }] };
      return { content: [{ type: "text", text: JSON.stringify({ message: "Slot suspended — effective on the immediate-next authorization check", slot }, null, 2) }] };
    }
  );

  server.tool(
    "slot.reinstate",
    "Reinstate a suspended slot (returns it to active).",
    {
      name: z.string().describe("Slot name or full slot id"),
      tenantId: z.string().optional(),
      adminToken: z.string().optional(),
    },
    async (args) => {
      const { scope, error } = requireScope(args);
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      const slot = reinstateSlot(resolveSlotId(args.name), scope);
      if (!slot) return { isError: true, content: [{ type: "text", text: `Slot not found or not suspended: ${args.name}` }] };
      return { content: [{ type: "text", text: JSON.stringify({ message: "Slot reinstated", slot }, null, 2) }] };
    }
  );

  server.tool(
    "slot.rotate_credential",
    "Rotate a slot credential. The OLD credential is invalidated immediately — the new one is returned exactly once.",
    {
      name: z.string().describe("Slot name or full slot id"),
      tenantId: z.string().optional(),
      adminToken: z.string().optional(),
    },
    async (args) => {
      const { scope, error } = requireScope(args);
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      const result = rotateSlotCredential(resolveSlotId(args.name), scope);
      if (!result) return { isError: true, content: [{ type: "text", text: `Slot not found or not active: ${args.name}` }] };
      return { content: [{ type: "text", text: JSON.stringify({ message: "Credential rotated — the previous credential is dead from now on", slot: result.slot, credential: result.credential }, null, 2) }] };
    }
  );

  server.tool(
    "slot.revoke",
    "Revoke a slot permanently (terminal state — use slot.suspend for reversible revocation).",
    {
      name: z.string().describe("Slot name or full slot id"),
      tenantId: z.string().optional(),
      adminToken: z.string().optional(),
    },
    async (args) => {
      const { scope, error } = requireScope(args);
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      const ok = revokeSlot(resolveSlotId(args.name), scope);
      return { content: [{ type: "text", text: ok ? `Slot ${args.name} revoked.` : `Slot not found: ${args.name}` }] };
    }
  );

  server.tool(
    "slot.status",
    "Live slot state: role, status, credential fingerprint, store-verification freshness (fail-closed diagnostics).",
    {
      name: z.string().describe("Slot name or full slot id"),
    },
    async (args) => {
      const id = resolveSlotId(args.name);
      const slot = getSlotRecord(id);
      if (!slot) return { isError: true, content: [{ type: "text", text: `Slot not found: ${args.name}` }] };
      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            slot,
            credentialId: clientCredentialId(id),
            store: {
              networkBacked: isRegistryNetworkBacked(),
              lastVerifiedAtMs: lastStoreVerificationAt(),
              maxStalenessMs: slotStoreMaxStalenessMs(),
            },
          }, null, 2),
        }],
      };
    }
  );

  server.tool(
    "slot.list",
    "List provisioned slots (tenant-scoped) with live registry state — credential FINGERPRINTS only, never raw credentials. Consumed by the dashboard and scripts/operations/tower_db_bridge.py (sync-slots).",
    {
      tenantId: z.string().optional(),
      adminToken: z.string().optional(),
    },
    async (args) => {
      const { scope, error } = requireScope(args);
      if (error) return { isError: true, content: [{ type: "text", text: error }] };
      const slots = listSlotClients(scope).map((slot) => ({
        slot_id: slot.id,
        slot_name: slot.name,
        tenant_id: slot.tenantId,
        role: slot.role,
        status: slot.status,
        credential_id: clientCredentialId(slot.id),
        suspended_reason: slot.suspendedReason,
        provisioned_at: slot.createdAt,
        rotated_at: slot.rotatedAt,
      }));
      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            scope,
            count: slots.length,
            slots,
            note: "credential_id is a 12-hex fingerprint of the sha256 digest — raw credentials are never exposed.",
          }, null, 2),
        }],
      };
    }
  );

  server.tool(
    "slot.audit_trail",
    "Read the immutable slot audit trail (who, with which credential fingerprint and role, ran or attempted what, when). Admin only.",
    {
      name: z.string().optional().describe("Filter by slot name/id"),
      limit: z.number().int().min(1).max(500).optional().describe("Max events (newest last)"),
    },
    async (args) => {
      const slotId = args.name ? resolveSlotId(args.name) : undefined;
      const events = readSlotAudit({ slotId, limit: args.limit });
      return {
        content: [{
          type: "text",
          text: JSON.stringify({ count: events.length, slotId: slotId ?? null, events }, null, 2),
        }],
      };
    }
  );
}

/** Accepts `name` or full `slot_<name>` / `named_<name>` ids. */
function resolveSlotId(nameOrId: string): string {
  const trimmed = nameOrId.trim();
  if (trimmed.startsWith("slot_") || trimmed.startsWith("named_")) return trimmed;
  return slotIdFor(trimmed);
}
