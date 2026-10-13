export type Capability =
  | "health"
  | "logs"
  | "metrics"
  | "deploy"
  | "restart"
  | "rollback"
  | "env_vars"
  | "secrets"
  | "notify"
  | "ai_inference"
  | "storage"
  | "auth";

/**
 * Defines standard required capabilities for certain MCP operations.
 */
export const CAPABILITY_REQUIREMENTS = {
  getHealth: ["health"] as Capability[],
  getLogs: ["logs"] as Capability[],
  deploy: ["deploy"] as Capability[],
  restart: ["restart"] as Capability[],
  getMetrics: ["metrics"] as Capability[],
};
