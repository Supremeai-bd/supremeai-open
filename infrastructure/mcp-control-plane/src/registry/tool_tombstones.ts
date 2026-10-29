/**
 * MCP Tool Tombstones & Renaming Deprecation Redirection (#2640).
 *
 * Implements self-describing tool migration redirects for retired/renamed MCP tools.
 * When an external caller invokes a retired or renamed tool name, instead of a bare
 * `-32602 Tool not found` error, the registry returns a structured `tool_moved`
 * redirect specifying the canonical successor.
 */

export interface ToolTombstone {
  retiredName: string;
  canonicalName: string;
  deprecatedSince: string;
  reason?: string;
}

/**
 * Registry of known renamed/retired tools mapping old names to their canonical successors.
 */
export const TOOL_TOMBSTONES: Record<string, ToolTombstone> = {
  // Underscore -> Dotted canonicals
  "bridge_work_queue": {
    retiredName: "bridge_work_queue",
    canonicalName: "bridge.work_queue",
    deprecatedSince: "2026-10-29",
    reason: "Canonical naming scheme adopted dotted names for queue operations (#2454)",
  },
  "bridge_work_order": {
    retiredName: "bridge_work_order",
    canonicalName: "bridge.work_order",
    deprecatedSince: "2026-10-29",
    reason: "Canonical naming scheme adopted dotted names for work order operations (#2454)",
  },
  "github_create_issue": {
    retiredName: "github_create_issue",
    canonicalName: "github.create_issue",
    deprecatedSince: "2026-10-29",
    reason: "Unified github family registration under github.* canonicals",
  },
  "github_list_issues": {
    retiredName: "github_list_issues",
    canonicalName: "github.list_issues",
    deprecatedSince: "2026-10-29",
    reason: "Unified github family registration under github.* canonicals",
  },
  "github_list_prs": {
    retiredName: "github_list_prs",
    canonicalName: "github.list_prs",
    deprecatedSince: "2026-10-29",
    reason: "Unified github family registration under github.* canonicals",
  },

  // #2488 Guide-named dotted variants -> canonical underscore/dotted handlers
  "bridge.read_feedback": {
    retiredName: "bridge.read_feedback",
    canonicalName: "bridge_read_feedback",
    deprecatedSince: "2026-10-29",
    reason: "Operational bridge feedback reader handler",
  },
  "bridge.work.renew": {
    retiredName: "bridge.work.renew",
    canonicalName: "bridge_work_renew",
    deprecatedSince: "2026-10-29",
    reason: "Operational bridge lease renewal handler",
  },
  "bridge.work.release": {
    retiredName: "bridge.work.release",
    canonicalName: "bridge_work_release",
    deprecatedSince: "2026-10-29",
    reason: "Operational bridge lease release handler",
  },
  "work.claim": {
    retiredName: "work.claim",
    canonicalName: "work_claim",
    deprecatedSince: "2026-10-29",
    reason: "Operational atomic claim handler",
  },
};

export interface ToolMovedResponse {
  error: "tool_moved";
  message: string;
  retiredName: string;
  use: string;
  deprecatedSince: string;
  code: number;
}

/**
 * Checks whether a requested tool name is a tombstone and returns a structured redirect if so.
 */
export function resolveToolTombstone(toolName: string): ToolMovedResponse | null {
  const tombstone = TOOL_TOMBSTONES[toolName];
  if (!tombstone) {
    return null;
  }

  return {
    error: "tool_moved",
    code: -32602,
    message: `Tool '${toolName}' has moved to canonical name '${tombstone.canonicalName}'. Please update your call to use '${tombstone.canonicalName}'.`,
    retiredName: tombstone.retiredName,
    use: tombstone.canonicalName,
    deprecatedSince: tombstone.deprecatedSince,
  };
}

/**
 * Returns nearest match suggestion for an unknown tool name from registered names.
 */
export function suggestNearestTool(unknownName: string, registeredNames: Iterable<string>): string | null {
  const lowerUnknown = unknownName.toLowerCase().replace(/[-_.]/g, "");
  let bestMatch: string | null = null;
  let bestScore = 0;

  for (const name of registeredNames) {
    const lowerRegistered = name.toLowerCase().replace(/[-_.]/g, "");
    if (lowerRegistered === lowerUnknown) {
      return name;
    }
    if (lowerRegistered.includes(lowerUnknown) || lowerUnknown.includes(lowerRegistered)) {
      bestMatch = name;
      bestScore = 1;
    }
  }

  return bestMatch;
}

