// manifest.mjs — skill package manifest validation (issue #332 AC1).
//
// Fail-closed: a manifest is either FULLY valid against this contract or it
// is rejected wholesale. Unknown keys, unknown scope ids, host-bearing URLs,
// and path traversal are all rejected at load time — a drifted manifest can
// never reach the installer.
//
// Manifests carry NO hostnames: the entry is a tower-relative path and the
// agent supplies the base URL at connect time (no SSRF-by-manifest).

const MANIFEST_VERSION = "skill-manifest/1";
const NAME_RE = /^[a-z][a-z0-9-]{2,31}$/;
const VERSION_RE = /^\d+\.\d+\.\d+$/;
const PATH_RE = /^\/[a-z0-9/_.-]*$/;
const TOOL_RE = /^[a-z][a-z0-9_-]{1,63}$/;

export class ManifestError extends Error {
  constructor(message) {
    super(message);
    this.name = "ManifestError";
  }
}

function requireString(value, field, max) {
  if (typeof value !== "string" || value.length === 0 || value.length > max) {
    throw new ManifestError(`${field}: non-empty string <= ${max} chars required`);
  }
}

/**
 * Validate one skill manifest against the strict contract.
 * @param {object} raw candidate manifest
 * @param {Set<string>} knownScopeIds scope-id SSOT from the permissions policy
 * @returns {object} frozen, validated manifest
 */
export function validateManifest(raw, knownScopeIds) {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    throw new ManifestError("manifest must be a JSON object");
  }
  const allowed = ["manifest_version", "name", "version", "description", "capabilities", "entry", "tools"];
  for (const key of Object.keys(raw)) {
    if (!allowed.includes(key)) {
      throw new ManifestError(`unknown manifest key '${key}' (fail-closed)`);
    }
  }
  if (raw.manifest_version !== MANIFEST_VERSION) {
    throw new ManifestError(`manifest_version must be exactly '${MANIFEST_VERSION}'`);
  }
  requireString(raw.name, "name", 32);
  if (!NAME_RE.test(raw.name)) throw new ManifestError("name: kebab-case, 3-32 chars, starts with a letter");
  requireString(raw.version, "version", 16);
  if (!VERSION_RE.test(raw.version)) throw new ManifestError("version: semver MAJOR.MINOR.PATCH required");
  requireString(raw.description, "description", 280);

  if (!Array.isArray(raw.capabilities) || raw.capabilities.length === 0) {
    throw new ManifestError("capabilities: non-empty array required");
  }
  for (const cap of raw.capabilities) {
    if (cap === null || typeof cap !== "object" || Array.isArray(cap)) {
      throw new ManifestError("capabilities entries must be objects");
    }
    for (const key of Object.keys(cap)) {
      if (!["scope_id", "actions"].includes(key)) {
        throw new ManifestError(`unknown capability key '${key}'`);
      }
    }
    if (!knownScopeIds.has(cap.scope_id)) {
      throw new ManifestError(`capability scope_id '${cap.scope_id}' is not in the permissions SSOT (fail-closed)`);
    }
    if (!Array.isArray(cap.actions) || cap.actions.length === 0 ||
        !cap.actions.every((a) => a === "read" || a === "execute")) {
      throw new ManifestError(`capability '${cap.scope_id}': actions must be a non-empty subset of ['read','execute']`);
    }
  }

  if (raw.entry === null || typeof raw.entry !== "object") {
    throw new ManifestError("entry: object required");
  }
  for (const key of Object.keys(raw.entry)) {
    if (!["transport", "path"].includes(key)) {
      throw new ManifestError(`unknown entry key '${key}'`);
    }
  }
  if (raw.entry.transport !== "sse" && raw.entry.transport !== "streamable-http") {
    throw new ManifestError("entry.transport must be 'sse' or 'streamable-http' (MCP standards only)");
  }
  requireString(raw.entry.path, "entry.path", 128);
  if (!PATH_RE.test(raw.entry.path) || raw.entry.path.includes("..")) {
    throw new ManifestError("entry.path: tower-relative path only (no hosts, no scheme, no traversal)");
  }

  if (!Array.isArray(raw.tools) || raw.tools.length === 0) {
    throw new ManifestError("tools: non-empty array required");
  }
  const seen = new Set();
  for (const tool of raw.tools) {
    if (tool === null || typeof tool !== "object" || Array.isArray(tool)) {
      throw new ManifestError("tools entries must be objects");
    }
    for (const key of Object.keys(tool)) {
      if (!["name", "description", "required_scopes"].includes(key)) {
        throw new ManifestError(`unknown tool key '${key}'`);
      }
    }
    requireString(tool.name, "tool.name", 64);
    if (!TOOL_RE.test(tool.name)) throw new ManifestError(`tool name '${tool.name}' invalid`);
    if (seen.has(tool.name)) throw new ManifestError(`duplicate tool name '${tool.name}'`);
    seen.add(tool.name);
    requireString(tool.description, `tool ${tool.name} description`, 280);
    if (!Array.isArray(tool.required_scopes) || tool.required_scopes.length === 0) {
      throw new ManifestError(`tool ${tool.name}: required_scopes non-empty array required`);
    }
    for (const sid of tool.required_scopes) {
      if (!knownScopeIds.has(sid)) {
        throw new ManifestError(`tool ${tool.name}: required scope '${sid}' not in permissions SSOT (fail-closed)`);
      }
    }
  }

  return Object.freeze({
    manifest_version: raw.manifest_version,
    name: raw.name,
    version: raw.version,
    description: raw.description,
    capabilities: Object.freeze(raw.capabilities.map((c) => Object.freeze({ ...c }))),
    entry: Object.freeze({ ...raw.entry }),
    tools: Object.freeze(raw.tools.map((t) => Object.freeze({ ...t, required_scopes: Object.freeze([...t.required_scopes]) }))),
  });
}
