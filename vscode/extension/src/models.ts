/**
 * SupremeAI-branded model tiers.
 *
 * Users never see provider/model ids — only SupremeAI tier names. The mapping
 * from a tier to the underlying gateway model id is internal.
 */

export interface ModelTier {
  id: string;        // internal tier key sent from the UI
  label: string;     // user-facing SupremeAI brand name
  model: string;     // gateway model id
}

export const MODEL_TIERS: ModelTier[] = [
  { id: "auto", label: "SupremeAI Auto (Smart routing)", model: "auto" },
  { id: "fast", label: "SupremeAI Fast", model: "llama-3.1-8b-instant" },
  { id: "balanced", label: "SupremeAI Balanced", model: "gpt-4o-mini" },
  { id: "pro", label: "SupremeAI Pro", model: "claude-sonnet-4-5" },
];

export function tierToModel(tierOrModel: string): string {
  const found = MODEL_TIERS.find((t) => t.id === tierOrModel);
  if (found) return found.model;
  // allow passing a raw gateway model id through
  return tierOrModel || "auto";
}

export function modelToTier(model: string): string {
  const found = MODEL_TIERS.find((t) => t.model === model || (model.includes("/") && t.model === model.split("/")[1]));
  return found ? found.id : "auto";
}
