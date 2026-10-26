/**
 * studio/src/pages/DevToolsPage.tsx — Free developer tools suite (Infinity plan Way 4).
 *
 * বাংলা: Infinity-র ১৩+ ফ্রি ডেভ টুলের প্যাটার্নে SupremeAI-র প্রথম ব্যাচ —
 * JSONForge (format/validate), SchemaForge (JSON-LD schema), CostForge
 * (API cost calculator)। সব ব্রাউজার-নেটিভ, সাইন-আপ ছাড়া, কোনো ব্যাকএন্ড কল নেই।
 *
 * Self-contained: no new dependencies (React only), Tailwind + existing tokens
 * (emerald/purple/indigo, glass surfaces). Zero data leaves the browser.
 *
 * Route (public, INTEGRATION.diff provided):
 *   <Route path="/tools" element={<PublicPageShell><DevToolsPage /></PublicPageShell>} />
 */

import { useMemo, useState } from 'react';

type ToolId = 'jsonforge' | 'schemaforge' | 'costforge';

interface ToolDef {
  id: ToolId;
  name: string;
  tagline: string;
  badge: string;
}

const TOOLS: ToolDef[] = [
  { id: 'jsonforge', name: 'JSONForge', tagline: 'Format, validate & inspect JSON', badge: 'FREE' },
  { id: 'schemaforge', name: 'SchemaForge', tagline: 'Generate JSON-LD schema from JSON', badge: 'FREE' },
  { id: 'costforge', name: 'CostForge', tagline: 'LLM API cost calculator', badge: 'FREE' },
];

const BADGE_STYLES: Record<string, string> = {
  FREE: 'border border-emerald-400/40 bg-emerald-400/10 text-emerald-300',
};

// ------------------------------------------------------------------ JSONForge
function JsonForge() {
  const [raw, setRaw] = useState('{"hello": "supremeai","items": [1, 2, 3]}');
  const [indent, setIndent] = useState(2);

  const result = useMemo(() => {
    if (!raw.trim()) return { ok: true as const, text: '', error: '' };
    try {
      const parsed: unknown = JSON.parse(raw);
      return { ok: true as const, text: JSON.stringify(parsed, null, indent), error: '' };
    } catch (e) {
      return { ok: false as const, text: '', error: e instanceof Error ? e.message : 'Invalid JSON' };
    }
  }, [raw, indent]);

  const stats = useMemo(() => {
    try {
      const parsed = JSON.parse(raw) as unknown;
      const count = (v: unknown): number => {
        if (Array.isArray(v)) return v.reduce<number>((a, x) => a + count(x), 1);
        if (v && typeof v === 'object') {
          return Object.values(v as Record<string, unknown>).reduce<number>((a, x) => a + count(x), 1);
        }
        return 1;
      };
      return { nodes: count(parsed), bytes: new Blob([raw]).size };
    } catch {
      return null;
    }
  }, [raw]);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 text-xs text-white/60">
        <label className="flex items-center gap-2">
          Indent
          <select
            className="rounded border border-white/15 bg-black/40 px-2 py-1 text-white/80"
            value={indent}
            onChange={(e) => setIndent(Number(e.target.value))}
          >
            <option value={2}>2</option>
            <option value={4}>4</option>
          </select>
        </label>
        {stats && (
          <span className="font-mono">
            {stats.nodes} nodes · {stats.bytes} bytes
          </span>
        )}
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <textarea
          className="h-64 w-full resize-none rounded-lg border border-white/15 bg-black/40 p-3 font-mono text-sm text-white/90 outline-none focus:border-emerald-400/50"
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          spellCheck={false}
          aria-label="JSON input"
        />
        <pre
          className={`h-64 w-full overflow-auto rounded-lg border p-3 font-mono text-sm ${
            result.ok
              ? 'border-emerald-400/30 bg-emerald-400/5 text-emerald-100/90'
              : 'border-red-400/40 bg-red-400/5 text-red-200'
          }`}
        >
          {result.ok ? result.text || '—' : `✗ ${result.error}`}
        </pre>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- SchemaForge
function SchemaForge() {
  const [raw, setRaw] = useState('{"product": {"name": "SupremeAI", "price": 0}}');

  const schema = useMemo(() => {
    const infer = (v: unknown): Record<string, unknown> => {
      if (v === null) return { type: 'null' };
      if (Array.isArray(v)) {
        return { type: 'array', items: v.length ? infer(v[0]) : {} };
      }
      if (typeof v === 'object') {
        const props: Record<string, unknown> = {};
        for (const [k, val] of Object.entries(v as Record<string, unknown>)) props[k] = infer(val);
        return { type: 'object', properties: props };
      }
      if (typeof v === 'number') return { type: Number.isInteger(v) ? 'integer' : 'number' };
      if (typeof v === 'boolean') return { type: 'boolean' };
      return { type: 'string' };
    };
    try {
      const parsed = JSON.parse(raw) as unknown;
      return {
        ok: true as const,
        text: JSON.stringify(
          { '@context': 'https://schema.org', '@type': 'Thing', ...infer(parsed) },
          null,
          2,
        ),
        error: '',
      };
    } catch (e) {
      return { ok: false as const, text: '', error: e instanceof Error ? e.message : 'Invalid JSON' };
    }
  }, [raw]);

  return (
    <div className="space-y-3">
      <p className="text-xs text-white/60">
        Paste JSON → get a JSON-LD (schema.org) skeleton. Pure client-side inference.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        <textarea
          className="h-64 w-full resize-none rounded-lg border border-white/15 bg-black/40 p-3 font-mono text-sm text-white/90 outline-none focus:border-purple-400/50"
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          spellCheck={false}
          aria-label="JSON source"
        />
        <pre
          className={`h-64 w-full overflow-auto rounded-lg border p-3 font-mono text-sm ${
            schema.ok
              ? 'border-purple-400/30 bg-purple-400/5 text-purple-100/90'
              : 'border-red-400/40 bg-red-400/5 text-red-200'
          }`}
        >
          {schema.ok ? schema.text || '—' : `✗ ${schema.error}`}
        </pre>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ CostForge
function CostForge() {
  const [inputTokens, setInputTokens] = useState(100000);
  const [outputTokens, setOutputTokens] = useState(50000);
  const [inPrice, setInPrice] = useState(0.5); // $ / 1M input tokens
  const [outPrice, setOutPrice] = useState(1.5); // $ / 1M output tokens

  const inputCost = (inputTokens / 1_000_000) * inPrice;
  const outputCost = (outputTokens / 1_000_000) * outPrice;
  const total = inputCost + outputCost;

  const fmt = (n: number) => (n < 0.01 && n > 0 ? `<$0.01` : `$${n.toFixed(4).replace(/\.?0+$/, '')}`);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        {(
          [
            ['Input tokens', inputTokens, setInputTokens, inPrice, setInPrice],
            ['Output tokens', outputTokens, setOutputTokens, outPrice, setOutPrice],
          ] as const
        ).map(([label, tokens, setTokens, price, setPrice]) => (
          <div key={label} className="rounded-lg border border-white/10 bg-black/30 p-4">
            <div className="mb-2 text-sm text-white/70">{label}</div>
            <input
              type="number"
              min={0}
              className="w-full rounded border border-white/15 bg-black/40 px-2 py-1 font-mono text-sm text-white/90"
              value={tokens}
              onChange={(e) => setTokens(Math.max(0, Number(e.target.value) || 0))}
            />
            <label className="mt-3 block text-xs text-white/50">
              Price ($ per 1M tokens)
              <input
                type="number"
                min={0}
                step="0.01"
                className="mt-1 w-full rounded border border-white/15 bg-black/40 px-2 py-1 font-mono text-sm text-white/90"
                value={price}
                onChange={(e) => setPrice(Math.max(0, Number(e.target.value) || 0))}
              />
            </label>
          </div>
        ))}
      </div>
      <div className="rounded-lg border border-indigo-400/30 bg-indigo-400/5 p-4 font-mono text-sm text-indigo-100">
        <div>input: {fmt(inputCost)}</div>
        <div>output: {fmt(outputCost)}</div>
        <div className="mt-2 text-lg font-semibold text-white">total: {fmt(total)}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------- page
export default function DevToolsPage() {
  const [active, setActive] = useState<ToolId>('jsonforge');

  return (
    <div className="mx-auto max-w-dash px-4 py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-white">Free Developer Tools</h1>
        <p className="mt-2 text-sm text-white/60">
          Browser-native, zero sign-up, zero telemetry. Inspired by the Infinity dev-tools pattern —
          built SupremeAI-first.
        </p>
      </header>

      <nav className="mb-6 flex flex-wrap gap-2" aria-label="Tool selector">
        {TOOLS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setActive(t.id)}
            className={`group rounded-lg border px-4 py-2 text-left transition ${
              active === t.id
                ? 'border-emerald-400/50 bg-emerald-400/10'
                : 'border-white/10 bg-white/[0.03] hover:border-white/25'
            }`}
            aria-pressed={active === t.id}
          >
            <span className="flex items-center gap-2 text-sm font-medium text-white">
              {t.name}
              <span className={`rounded border px-1.5 py-0.5 text-[10px] ${BADGE_STYLES[t.badge]}`}>
                {t.badge}
              </span>
            </span>
            <span className="block text-xs text-white/50">{t.tagline}</span>
          </button>
        ))}
      </nav>

      <section className="rounded-xl border border-white/10 bg-white/[0.02] p-4 shadow-2xl md:p-6">
        {active === 'jsonforge' && <JsonForge />}
        {active === 'schemaforge' && <SchemaForge />}
        {active === 'costforge' && <CostForge />}
      </section>

      <p className="mt-6 text-xs text-white/40">
        All processing happens in your browser. Nothing is uploaded, stored, or logged.
      </p>
    </div>
  );
}

export { DevToolsPage };

