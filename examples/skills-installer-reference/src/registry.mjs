// registry.mjs — capability registry (issue #332 AC1).
//
// Loads a marketplace of skill manifests FAIL-CLOSED: every manifest is
// validated at construction (manifest.mjs contract); one invalid manifest
// rejects the WHOLE load — a poisoned marketplace entry can never be half-
// installed. Discovery and install are pure functions over the frozen index.

import { validateManifest } from "./manifest.mjs";

export class RegistryError extends Error {
  constructor(message) {
    super(message);
    this.name = "RegistryError";
  }
}

export class CapabilityRegistry {
  /**
   * @param {object} permissionsPolicy parsed permissions fixture (needs permission_scopes)
   * @param {object[]} rawManifests marketplace manifests
   */
  constructor(permissionsPolicy, rawManifests) {
    if (permissionsPolicy === null || typeof permissionsPolicy !== "object") {
      throw new RegistryError("permissions policy object required (fail-closed)");
    }
    const scopes = permissionsPolicy.permission_scopes;
    if (!Array.isArray(scopes) || scopes.length === 0) {
      throw new RegistryError("permissions policy must carry a non-empty permission_scopes list");
    }
    this.#scopeIds = new Set(scopes.map((s) => s.scope_id).filter(Boolean));
    if (this.#scopeIds.size !== scopes.length) {
      throw new RegistryError("duplicate scope_id in permissions policy (fail-closed)");
    }
    if (!Array.isArray(rawManifests) || rawManifests.length === 0) {
      throw new RegistryError("marketplace manifests must be a non-empty array");
    }
    const index = new Map();
    for (const raw of rawManifests) {
      let manifest;
      try {
        manifest = validateManifest(raw, this.#scopeIds);
      } catch (err) {
        // Uniform fail-closed surface: a poisoned marketplace entry rejects
        // the WHOLE load, with the underlying reason preserved.
        throw new RegistryError(`manifest load rejected: ${err.message}`);
      }
      if (index.has(manifest.name)) {
        throw new RegistryError(`duplicate skill name '${manifest.name}' in marketplace`);
      }
      index.set(manifest.name, manifest);
    }
    this.#index = index;
  }

  #scopeIds;
  #index;

  /** All installed skill names (deterministic order). */
  listNames() {
    return [...this.#index.keys()].sort();
  }

  /**
   * Discovery (AC1): skills whose tools require the queried scope.
   * @param {{scope_id?: string, action?: "read"|"execute"}} query
   */
  discover(query = {}) {
    if (query.scope_id !== undefined && !this.#scopeIds.has(query.scope_id)) {
      // Unknown scope in a DISCOVERY QUERY is a caller bug — honest empty
      // result would hide it; the fail-closed posture reports it.
      throw new RegistryError(`query.scope_id '${query.scope_id}' is not in the permissions SSOT`);
    }
    const results = [];
    for (const manifest of this.#index.values()) {
      const matched = manifest.tools.filter((tool) => {
        const scopeOk = query.scope_id === undefined || tool.required_scopes.includes(query.scope_id);
        const cap = manifest.capabilities.find((c) => c.scope_id === query.scope_id);
        const actionOk = query.action === undefined || (cap && cap.actions.includes(query.action));
        return scopeOk && actionOk;
      });
      if (matched.length > 0) {
        results.push(Object.freeze({
          name: manifest.name,
          version: manifest.version,
          description: manifest.description,
          entry: manifest.entry,
          matching_tools: matched.map((t) => t.name),
        }));
      }
    }
    return results.sort((a, b) => (a.name < b.name ? -1 : 1));
  }

  /**
   * Install (AC1): return the validated manifest as an immutable handle.
   * Installation is pure validation + freeze — nothing executes here.
   */
  install(name) {
    const manifest = this.#index.get(name);
    if (manifest === undefined) {
      throw new RegistryError(`skill '${name}' not found in registry (fail-closed)`);
    }
    return manifest;
  }
}
