// lease.mjs — least-privilege capability leases (issue #332 AC3).
//
// Grants are checked against the permissions SSOT exactly like the landed
// command-dispatch reference (deny-by-default chain):
//   1. unknown tool            -> deny
//   2. tool scope not in the
//      agent sub-role pinning  -> deny
//   3. scope min_role_tier
//      above the agent tier    -> deny
//   4. scope requires_mfa and
//      MFA unverified          -> deny (defaults.unverified_mfa)
//   5. unknown scope id        -> deny (defaults.unknown_action analog)
// A grant is a frozen, EXPIRING capability token; execute() re-checks it at
// call time (a lease outliving its TTL authorizes nothing).

export class LeaseDenied extends Error {
  constructor(code, reason) {
    super(`${code}: ${reason}`);
    this.name = "LeaseDenied";
    this.code = code;
    this.reason = reason;
  }
}

const SCOPE_EXEC_ACTIONS = new Set(["execute", "read"]); // read scopes alone never authorize execution

export class LeaseAuthority {
  /**
   * @param {object} policy permissions fixture (role_tiers, agent_sub_roles,
   *                        permission_scopes, defaults)
   * @param {() => number} [clock] wall-clock seconds (injectable for tests)
   */
  constructor(policy, clock = () => Date.now() / 1000) {
    if (policy === null || typeof policy !== "object") {
      throw new LeaseDenied("config_invalid", "permissions policy object required");
    }
    if (policy.defaults && policy.defaults.unverified_mfa !== "deny") {
      // The deny-by-default posture is the whole point — refuse to run
      // against a policy that softened it.
      throw new LeaseDenied("config_invalid", "defaults.unverified_mfa must be 'deny' (fail-closed)");
    }
    this.#policy = policy;
    this.#clock = clock;
  }

  #policy;
  #clock;

  #subRole(name) {
    return (this.#policy.agent_sub_roles || []).find((s) => s.sub_role === name);
  }

  #scope(scopeId) {
    return (this.#policy.permission_scopes || []).find((s) => s.scope_id === scopeId);
  }

  /**
   * Grant a lease for one tool of one installed manifest.
   * @returns {object} frozen lease {tool, granted_scopes, expires_at}
   */
  grant({ sub_role, role_tier, mfa_verified = false, manifest, tool_name, ttl_s = 300 }) {
    const sub = this.#subRole(sub_role);
    if (!sub) {
      throw new LeaseDenied("unknown_sub_role", `sub_role '${sub_role}' is not in the policy`);
    }
    if (!Number.isInteger(role_tier) || role_tier < 1 || role_tier > 4) {
      throw new LeaseDenied("bad_tier", "role_tier must be an integer 1..4");
    }
    const tool = (manifest.tools || []).find((t) => t.name === tool_name);
    if (!tool) {
      // Unknown tool = the #1 SSRF-style escalation attempt. Deny BEFORE any
      // wire activity (fail closed).
      throw new LeaseDenied("unknown_tool", `tool '${tool_name}' is not declared by skill '${manifest.name}'`);
    }
    const allowed = new Set(sub.allowed_permission_scope_ids || []);
    for (const scopeId of tool.required_scopes) {
      const scope = this.#scope(scopeId);
      if (!scope) {
        throw new LeaseDenied("unknown_scope", `scope '${scopeId}' not in policy`);
      }
      if (!allowed.has(scopeId)) {
        throw new LeaseDenied("scope_not_pinned",
          `sub_role '${sub_role}' does not pin scope '${scopeId}' (deny-by-default)`);
      }
      if (scope.min_role_tier > role_tier) {
        throw new LeaseDenied("tier_too_low",
          `scope '${scopeId}' requires tier >= ${scope.min_role_tier}, agent has ${role_tier}`);
      }
      if (scope.requires_mfa && !mfa_verified) {
        throw new LeaseDenied("mfa_required", `scope '${scopeId}' requires verified MFA`);
      }
    }
    if (!Number.isInteger(ttl_s) || ttl_s <= 0 || ttl_s > 3600) {
      throw new LeaseDenied("bad_ttl", "ttl_s must be an integer in (0, 3600]");
    }
    return Object.freeze({
      tool: tool_name,
      skill: manifest.name,
      granted_scopes: Object.freeze([...tool.required_scopes]),
      expires_at: Math.floor(this.#clock()) + ttl_s,
    });
  }

  /**
   * Re-check a lease at EXECUTION time (AC3).
   * @returns {{ok: true}} or throws LeaseDenied
   */
  check(lease, toolName, manifest) {
    if (lease === null || typeof lease !== "object") {
      throw new LeaseDenied("no_lease", "a granted lease is required before execution");
    }
    const now = Math.floor(this.#clock());
    if (now >= lease.expires_at) {
      throw new LeaseDenied("lease_expired", `lease expired at ${lease.expires_at} (now ${now})`);
    }
    if (lease.tool !== toolName) {
      throw new LeaseDenied("tool_mismatch", `lease covers '${lease.tool}', not '${toolName}'`);
    }
    const tool = (manifest.tools || []).find((t) => t.name === toolName);
    if (!tool) {
      throw new LeaseDenied("unknown_tool", `tool '${toolName}' not in installed manifest`);
    }
    for (const scopeId of tool.required_scopes) {
      if (!lease.granted_scopes.includes(scopeId)) {
        throw new LeaseDenied("scope_escalation",
          `tool now requires '${scopeId}' which the lease does not grant`);
      }
    }
    return { ok: true };
  }
}

export { SCOPE_EXEC_ACTIONS };
