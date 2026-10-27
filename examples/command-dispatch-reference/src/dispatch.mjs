/**
 * dispatch.mjs — omnichannel remote task injection handlers (issue #331).
 *
 * Zero-dependency reference implementation of:
 *   - webhook task ingestion  (POST body -> instruction envelope -> dispatch)
 *   - Telegram task ingestion (update -> /task command -> envelope candidate)
 *   - envelope validation against the REAL landed schema
 *     (api-schemas/instruction-envelope.schema.json, the deterministic
 *     5-section envelope, issue #30)
 *   - RBAC authorization against the REAL landed policy semantics
 *     (api-schemas/permissions.schema.json, issue #28) with the
 *     constitutional fail-closed defaults: anything not explicitly granted
 *     does not exist (defaults.unknown_action = deny).
 *
 * Acceptance criterion 3 (fail-closed): unverified sources, malformed JSON,
 * schema-invalid envelopes, unauthorized roles/chats and unknown actions are
 * ALL rejected with structured errors — nothing is partially processed.
 *
 * Stateless (AGENTS.md §2): createDispatcher() closes over injected config;
 * no module-level mutable state, no network calls (transport is the caller's).
 */

import { makeValidator } from "./schema_lite.mjs";

const SPECIALIST_ROLES = new Set([
  "coder", "auditor", "ci-fixer", "security-breaker", "browser-qa", "planner", "watcher",
]);

// 4-tier RBAC (permissions.schema.json RoleTier): the 7 specialist roles are
// operational renderings of the tier-2 "agent" rung.
const SPECIALIST_ROLE_TIER = 2;

/** Timing-weak but dependency-free secret comparison over equal-length hashes. */
function secretMatches(provided, expected) {
  if (typeof provided !== "string" || typeof expected !== "string") return false;
  if (provided.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < provided.length; i += 1) diff |= provided.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}

function deny(status, code, reason, extra = {}) {
  return { status, ok: false, accepted: false, error: { code, reason, ...extra } };
}

/**
 * Build the dispatcher. All configuration injected; nothing global.
 *
 * @param {object} opts
 * @param {object} opts.envelopeSchema  parsed instruction-envelope schema
 * @param {object} opts.permissionsPolicy parsed permissions policy (role_tiers,
 *        permission_scopes, defaults with unknown_action=deny)
 * @param {string} opts.webhookSecret  shared secret for the webhook route
 * @param {number[]} opts.authorizedChatIds  Telegram chats allowed to inject
 */
export function createDispatcher(opts) {
  const {
    envelopeSchema, permissionsPolicy, webhookSecret, authorizedChatIds,
  } = opts ?? {};
  if (!envelopeSchema) throw new TypeError("envelopeSchema is required (fail-closed)");
  if (!permissionsPolicy) throw new TypeError("permissionsPolicy is required (fail-closed)");
  if (typeof webhookSecret !== "string" || webhookSecret.length < 8) {
    throw new TypeError("webhookSecret must be a string of length >= 8 (fail-closed)");
  }
  if (!Array.isArray(authorizedChatIds) || authorizedChatIds.length === 0) {
    throw new TypeError("authorizedChatIds must be a non-empty array (fail-closed: default-deny)");
  }
  const validateEnvelope = makeValidator(envelopeSchema);
  const policy = permissionsPolicy;
  if (policy?.defaults?.unknown_action !== "deny") {
    throw new TypeError("policy.defaults.unknown_action must be 'deny' (constitutional fail-closed)");
  }

  /** RBAC: deny-by-default (acceptance criterion 3).
   *
   * Order (all fail-closed): unknown scope/action -> deny; specialist roles
   * are pinned to their agent_sub_roles allowed-scope list -> deny when the
   * scope is not granted to that sub-role; tier check against min_role_tier;
   * MFA demand when the scope requires it (defaults.unverified_mfa=deny).
   */
  function authorize(actorRole, scopeId, action, { mfaToken = null } = {}) {
    const scope = (policy.permission_scopes || []).find((s) => s.scope_id === scopeId);
    if (!scope) return { allowed: false, reason: `unknown scope '${scopeId}' — deny by default` };
    if (!scope.actions.includes(action)) {
      return { allowed: false, reason: `action '${action}' not granted on '${scopeId}' — deny by default` };
    }
    const subRole = (policy.agent_sub_roles || []).find((s) => s.sub_role === actorRole);
    if (SPECIALIST_ROLES.has(actorRole)) {
      if (!subRole) {
        return { allowed: false, reason: `role '${actorRole}' has no agent_sub_roles grant — deny by default` };
      }
      if (!(subRole.allowed_permission_scope_ids || []).includes(scopeId)) {
        return {
          allowed: false,
          reason: `sub-role '${actorRole}' is not granted scope '${scopeId}' — deny by default`,
        };
      }
    }
    let tier;
    if (subRole) {
      tier = SPECIALIST_ROLE_TIER; // sub-roles are operational renderings of the agent rung
    } else {
      const rung = (policy.role_tiers || []).find((r) => r.name === actorRole);
      tier = rung ? rung.tier : 0;
    }
    if (tier < scope.min_role_tier) {
      return { allowed: false, reason: `role '${actorRole}' (tier ${tier}) below min_role_tier ${scope.min_role_tier}` };
    }
    if (scope.requires_mfa && !mfaToken) {
      return { allowed: false, reason: `scope '${scopeId}' requires MFA — no token presented (defaults.unverified_mfa=deny)` };
    }
    return { allowed: true, reason: `granted via '${scopeId}' (${subRole ? `sub-role ${actorRole}, ` : ""}tier ${tier})` };
  }

  /** Shared envelope gate: validate + authorize, fully structured rejections. */
  function ingestEnvelope(rawBody, actorRole, { mfaToken = null, source = "webhook" } = {}) {
    let payload;
    try {
      payload = JSON.parse(rawBody);
    } catch (exc) {
      return deny(422, "MALFORMED_JSON", `body is not valid JSON: ${exc.message}`, { source });
    }
    const errors = validateEnvelope(payload);
    if (errors.length > 0) {
      return deny(422, "ENVELOPE_INVALID",
        `payload violates api-schemas/instruction-envelope.schema.json (${errors.length} error(s))`,
        { source, errors: errors.slice(0, 10) });
    }
    const verdict = authorize(actorRole, "remote-task-injection", "inject", { mfaToken });
    if (!verdict.allowed) {
      return deny(403, "UNAUTHORIZED", verdict.reason, { source });
    }
    return {
      status: 202,
      ok: true,
      accepted: true,
      task_id: payload.target.task_id,
      issue: payload.target.issue,
      role: payload.section_1_role_contract.role,
      source,
    };
  }

  /** Webhook route (acceptance criterion 1): secret -> JSON -> schema -> RBAC. */
  function handleWebhook({ body, headers }) {
    const provided = headers?.["x-supreme-signature"];
    if (!secretMatches(provided, webhookSecret)) {
      return deny(403, "UNVERIFIED_SOURCE",
        "missing or invalid x-supreme-signature header — unverified triggers fail closed",
        { source: "webhook" });
    }
    return ingestEnvelope(body, "agent", { source: "webhook" });
  }

  /** Telegram route: authorized chat -> command parse -> envelope -> RBAC. */
  function handleTelegramUpdate(update) {
    const message = update?.message;
    const chatId = message?.chat?.id;
    if (!authorizedChatIds.includes(chatId)) {
      return deny(403, "UNAUTHORIZED_CHAT",
        `chat ${chatId ?? "(none)"} is not authorized — unverified triggers fail closed`,
        { source: "telegram" });
    }
    const text = typeof message?.text === "string" ? message.text.trim() : "";
    if (!text.startsWith("/task")) {
      return deny(422, "NOT_A_TASK_COMMAND", "only /task commands are accepted", { source: "telegram" });
    }
    // Deterministic /task command grammar: /task <issue> <objective...>
    const rest = text.slice("/task".length).trim();
    const [issue, ...objectiveParts] = rest.split(/\s+/);
    if (!/^[1-9][0-9]{0,7}$/.test(issue ?? "") || objectiveParts.length === 0) {
      return deny(422, "MALFORMED_COMMAND",
        "usage: /task <issue> <objective> — deterministic grammar, nothing guessed",
        { source: "telegram" });
    }
    const objective = objectiveParts.join(" ");
    // Envelope built to the landed contract's EXACT shapes (issue #30):
    // section_2 requires objective + 3 non-empty lists; section_3 requires
    // >=1 citable policy + admin_gate; section_4 requires the pinned
    // contract_version + exactly 3 named tiers; section_5 requires the
    // closes_reference line + template carrying it.
    const envelope = {
      schema_version: "1.0",
      envelope_format: "instruction-envelope-v1",
      target: {
        task_id: `task-${issue}`,
        issue,
        repository: "Supremeai-bd/supremeai",
        task_type: "IMPLEMENT",
        group: "agent-orchestration",
        priority: "P2",
      },
      section_1_role_contract: {
        role: "coder",
        role_description: "Implementation specialist dispatched from Telegram",
        operating_constraints: [
          "Autonomous execution inside declared scope only; no confirmation prompts.",
          `Objective from Telegram chat ${chatId}: ${objective}`,
        ],
        stop_conditions: ["Security boundary hit", "Out of declared scope"],
      },
      section_2_task_scope: {
        objective,
        touching_files: ["scripts/agents/"],
        forbidden_paths: [".env*", "secrets/**", "credentials/**", "vault/**"],
        acceptance_criteria: [`Objective satisfied: ${objective}`, "Zero unhandled crashes"],
      },
      section_3_governing_rules: {
        policies: [
          {
            id: "smallest-safe-change",
            statement:
              "Implement the smallest safe change strictly inside the declared Touching Files.",
            source: "AGENTS.md",
          },
        ],
        admin_gate: { required: false, status: "NOT_REQUIRED" },
      },
      section_4_verification: {
        contract_version: "agent-loop-contract/1",
        tiers: [
          {
            tier: 1,
            name: "reflection_check",
            command: "git diff --stat",
            expectation: "Diff limited to the declared Touching Files.",
          },
          {
            tier: 2,
            name: "boot_smoke_test",
            command: "python -c 'import scripts.agents.continuous_agent_loop'",
            expectation: "Loop module imports cleanly from the repository root.",
          },
          {
            tier: 3,
            name: "test_suite",
            command: "python -m pytest tests/ -q",
            expectation: "Full offline test suite passes.",
          },
        ],
        required_evidence: ["verification tier output", "diff check"],
      },
      section_5_submission: {
        pathway: "bridge_submit_patch",
        base_branch: "main",
        branch_convention: "^(feat|fix|docs|chore|test|refactor|perf|bridge|contributor)/<slug>",
        pr_title_prefix: "feat(open):",
        issue_reference_required: true,
        closes_reference: `Closes #${issue}`,
        pr_body_template: `## Summary\nTelegram-dispatched task for issue #${issue}: ${objective}.\n\nCloses #${issue}\n`,
      },
    };
    return ingestEnvelope(JSON.stringify(envelope), "coder", { source: "telegram" });
  }

  return { handleWebhook, handleTelegramUpdate, ingestEnvelope, authorize };
}
