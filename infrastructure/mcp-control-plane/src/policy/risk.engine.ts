import { POLICY_SCHEMA } from "./policy.schema.generated.js";

/**
 * 🇧🇩 Risk Engine — schema-driven (SSoT: config/mcp_policy_schema.json) #2429
 *
 * বাংলা মন্তব্য:
 * আগে এই ফাইলে হাতে-লেখা provider→risk টেবিল ছিল — Python mirror-এর
 * (backend/core/mcp_policy.py) সাথে আলাদাভাবে maintain হতো, ফলে drift
 * তৈরি হয়েছিল (Python-এর agent_tools/memory/mcp_tools/mesh এই দিকে
 * ছিল না)। এখন উভয় ইঞ্জিন একই canonical schema থেকে **generated**
 * snapshot (policy.schema.generated.ts — scripts/ci/generate_mcp_policy.py)
 * পড়ে। এক জায়গায় নীতি বদলালে generator চালালেই দুই দিকে প্রতিফলিত হয়।
 *
 * Constitution Compliance:
 *   - Law #4 (SSoT): policy একবারই define — schema-তে
 *   - Law #19 (Observable): SCHEMA_HASH দিয়ে চলমান সংস্করণ শনাক্তযোগ্য
 */

export type RiskLevel = "R0" | "R1" | "R2" | "R3" | "R4" | "R5" | "R6";

export interface ActionContext {
  provider: string; // e.g., 'render', 'supabase', 'system'
  action: string;   // e.g., 'summary', 'restart', 'deploy', 'delete_db'
}

const RISK_LEVELS = new Set<string>(Object.keys(POLICY_SCHEMA.decisionMatrix));

function isRiskLevel(value: string): value is RiskLevel {
  return RISK_LEVELS.has(value);
}

export class RiskEngine {
  /**
   * Evaluates the risk level of a specific action (schema-driven).
   */
  public evaluate(context: ActionContext): RiskLevel {
    const { provider, action } = context;

    // ১. Read-only shortcut: system/health provider বা read-only keyword action।
    if (
      POLICY_SCHEMA.readOnlyProviders.includes(provider) ||
      POLICY_SCHEMA.readOnlyKeywords.some((keyword) => action.includes(keyword))
    ) {
      return "R0";
    }

    // ২. Provider-specific টেবিল (schema-generated)।
    const rules = POLICY_SCHEMA.providers[provider];
    if (rules) {
      const actionRisk = rules.actions[action];
      if (typeof actionRisk === "string" && isRiskLevel(actionRisk)) {
        return actionRisk;
      }
      // ৩. Provider-specific default (যেমন memory → R0) — না থাকলে গ্লোবাল default।
      if (typeof rules.default === "string" && isRiskLevel(rules.default)) {
        return rules.default;
      }
    }

    // ৪. গ্লোবাল default (unknown provider-ও এখানে পড়ে; fail-closed R3)।
    const fallback = POLICY_SCHEMA.defaultRisk;
    return isRiskLevel(fallback) ? fallback : "R3";
  }

  /** বর্তমান embedded schema snapshot-এর পরিচয় (observability)। */
  public schemaInfo(): { version: string; hash: string; providers: string[]; tools: number } {
    return {
      version: POLICY_SCHEMA.schemaVersion,
      hash: POLICY_SCHEMA.schemaHash,
      providers: Object.keys(POLICY_SCHEMA.providers),
      tools: Object.keys(POLICY_SCHEMA.toolProviderAction).length,
    };
  }
}

export const globalRiskEngine = new RiskEngine();
