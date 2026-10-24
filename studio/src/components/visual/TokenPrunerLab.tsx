/**
 * studio/src/components/visual/TokenPrunerLab.tsx — Interactive TF-IDF lab (Way 11).
 *
 * বাংলা: "try it live" প্যাটার্নের exemplar — Way 2-এর TF-IDF tool pruner-এর
 * ব্রাউজার সিমুলেটর। ইউজার কোয়েরি লিখে দেখে কোন টুল স্কিমা থাকবে, কত টোকেন
 * বাঁচল — সম্পূর্ণ ক্লায়েন্ট-সাইড, কোনো API কল নেই।
 *
 * Reuses the same algorithm contract as gateway/tool_pruner.py + mcp
 * semantic_router.ts (TF × IDF cosine), simplified for the demo corpus.
 */

import { useMemo, useState } from 'react';

interface DemoTool {
  name: string;
  description: string;
  /** Rough token cost of the tool's JSON schema in a prompt. */
  schemaTokens: number;
}

const DEMO_TOOLS: DemoTool[] = [
  { name: 'github.list_prs', description: 'List open pull requests in a repository', schemaTokens: 180 },
  { name: 'github.get_failed_logs', description: 'Fetch failed CI run logs', schemaTokens: 140 },
  { name: 'bridge.work_queue', description: 'List open bridge work-order issues', schemaTokens: 210 },
  { name: 'redis.read_key', description: 'Read a key value from Redis', schemaTokens: 90 },
  { name: 'system_health', description: 'Fleet health snapshot for all services', schemaTokens: 120 },
  { name: 'render_get_logs', description: 'Fetch service logs from Render', schemaTokens: 110 },
  { name: 'memory_read_graph', description: 'Read the agent memory graph', schemaTokens: 160 },
  { name: 'docs_fetch', description: 'Fetch documentation pages', schemaTokens: 80 },
];

const WORD_RE = /[a-z0-9_]{2,}/g;
const STOP = new Set(['the', 'a', 'an', 'and', 'or', 'to', 'of', 'in', 'on', 'for', 'with', 'this', 'that', 'it', 'is', 'are', 'get', 'list', 'set', 'all']);

function tokenize(text: string): string[] {
  return (text.toLowerCase().match(WORD_RE) ?? []).filter((t) => !STOP.has(t));
}

function scoreCorpus(query: string, tools: DemoTool[]) {
  const qTokens = tokenize(query);
  if (!qTokens.length) return tools.map((t) => ({ ...t, score: 0 }));

  const df = new Map<string, number>();
  const toolTokens = tools.map((t) => {
    const toks = tokenize(`${t.name.replace(/[._-]/g, ' ')} ${t.description}`);
    for (const w of toks) df.set(w, (df.get(w) ?? 0) + 1);
    return toks;
  });
  const idf = (w: string) => Math.log((1 + tools.length) / (1 + (df.get(w) ?? 0))) + 1;

  const qTf = new Map<string, number>();
  for (const w of qTokens) qTf.set(w, (qTf.get(w) ?? 0) + 1);

  return tools.map((tool, i) => {
    let score = 0;
    for (const [w, tf] of qTf) {
      const freq = toolTokens[i].filter((x) => x === w).length;
      if (freq > 0) score += (1 + Math.log(tf)) * idf(w);
    }
    return { ...tool, score: score / Math.sqrt(qTokens.length) };
  });
}

export default function TokenPrunerLab() {
  const [query, setQuery] = useState('why did the ci run fail? show me the logs');
  const [threshold, setThreshold] = useState(0.3);

  const scored = useMemo(() => {
    const rows = scoreCorpus(query, DEMO_TOOLS);
    const max = Math.max(...rows.map((r) => r.score), 1e-9);
    return rows
      .map((r) => ({ ...r, norm: r.score / max }))
      .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
  }, [query]);

  const kept = scored.filter((r) => r.norm >= threshold);
  const dropped = scored.filter((r) => r.norm < threshold);
  const totalTokens = DEMO_TOOLS.reduce((a, t) => a + t.schemaTokens, 0);
  const keptTokens = kept.reduce((a, t) => a + t.schemaTokens, 0);
  const savedPct = totalTokens ? Math.round((100 * (totalTokens - keptTokens)) / totalTokens) : 0;

  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.02] p-4 md:p-6" aria-label="TF-IDF pruner lab">
      <header className="mb-4">
        <h3 className="text-sm font-medium text-white">Token Pruner Lab · <span className="text-white/50">live TF-IDF simulator</span></h3>
        <p className="mt-1 text-xs text-white/50">
          Same algorithm as the gateway tool pruner (Way 2) — try a query, watch the schema payload shrink.
        </p>
      </header>

      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Ask a query…"
        className="w-full rounded-lg border border-white/15 bg-black/40 px-3 py-2 font-mono text-sm text-white/90 outline-none focus:border-emerald-400/50"
      />

      <label className="mt-4 block text-xs text-white/50">
        Keep threshold: <span className="font-mono text-white/80">{threshold.toFixed(2)}</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
          className="mt-1 w-full accent-emerald-400"
        />
      </label>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <ul className="space-y-1.5">
          {scored.map((r) => (
            <li
              key={r.name}
              className={`flex items-center justify-between rounded border px-3 py-1.5 font-mono text-xs ${
                r.norm >= threshold
                  ? 'border-emerald-400/30 bg-emerald-400/5 text-emerald-100'
                  : 'border-white/10 text-white/35 line-through'
              }`}
            >
              <span>{r.name}</span>
              <span>{r.norm.toFixed(2)}</span>
            </li>
          ))}
        </ul>
        <div className="rounded-lg border border-indigo-400/30 bg-indigo-400/5 p-4">
          <div className="font-mono text-xs text-indigo-200/70">schema payload</div>
          <div className="mt-2 font-mono text-2xl text-white">{savedPct}% saved</div>
          <div className="mt-1 font-mono text-xs text-white/50">
            {keptTokens} / {totalTokens} tokens kept · {kept.length} tools kept, {dropped.length} pruned
          </div>
          <div className="mt-3 h-2 w-full overflow-hidden rounded bg-white/10">
            <div
              className="h-full bg-gradient-to-r from-emerald-400 to-indigo-400 transition-all"
              style={{ width: `${100 - savedPct}%` }}
            />
          </div>
        </div>
      </div>

      <p className="mt-4 text-[10px] text-white/35">
        Demo corpus only — production pruning runs in gateway/tool_pruner.py with the full registry.
      </p>
    </section>
  );
}
