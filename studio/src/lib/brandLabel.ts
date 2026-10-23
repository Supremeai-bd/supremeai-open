// Refs brand badge plan: server decides the label, UI only displays it.
export type Brand = { channel: string; engine: string; tier: string; label: string };

const ENGINE_HINTS: [string, string][] = [
  ['gemini', 'ge'], ['grok', 'gr'], ['gpt', 'gp'], ['openai', 'gp'], ['claude', 'cl'],
  ['perplexity', 'px'], ['deepseek', 'ds'], ['llama', 'lm'], ['groq', 'lm'], ['mistral', 'mi'],
];

/** Read `data.supremeai` from a chat response; fall back to deriving from `data.model`. */
export function brandFrom(data: unknown): Brand {
  const d = (data ?? {}) as { supremeai?: Partial<Brand>; model?: string };
  const s = d.supremeai;
  if (s && s.label && s.channel && s.engine && s.tier) return s as Brand;
  const low = String(d.model ?? '').toLowerCase();
  const engine = ENGINE_HINTS.find(([k]) => low.includes(k))?.[1] ?? 'ge';
  return { channel: 'w', engine, tier: 'Turbo', label: `SupremeAI w.${engine} Turbo` };
}

export const TIER_CLASS: Record<string, string> = {
  Turbo: 'bg-cyan-500/15 text-cyan-300 border-cyan-400/30',
  Free: 'bg-slate-500/15 text-slate-300 border-slate-400/30',
  Pro: 'bg-purple-500/15 text-purple-300 border-purple-400/30',
  Ultra: 'bg-amber-500/15 text-amber-300 border-amber-400/30',
};

const ENGINE_NAMES: Record<string, string> = {
  ge: 'Gemini', gr: 'Grok', gp: 'ChatGPT', cl: 'Claude', px: 'Perplexity', ds: 'DeepSeek', lm: 'Llama', mi: 'Mistral',
};

export function brandTooltip(b: Brand): string {
  const ch = b.channel === 'a' ? 'API key' : 'Webhook relay';
  return `${ch} · ${ENGINE_NAMES[b.engine] ?? 'Unknown engine'} · ${b.tier}`;
}
