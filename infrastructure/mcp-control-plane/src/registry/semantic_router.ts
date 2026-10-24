/**
 * infrastructure/mcp-control-plane/src/registry/semantic_router.ts
 *
 * Semantic tool router (Infinity plan Way 3 — MCPlex pattern).
 *
 * বাংলা: MCP টুল স্কিমার উপর TF-IDF সেমান্টিক রাউটার — query-র সাথে
 * প্রাসঙ্গিক টুল বাছাই + অপ্রাসঙ্গিক টুল স্কিমা prune করে টোকেন বাঁচায়
 * (Infinity-রেফারেন্স: 70-90% token save)। কোনো এক্সটার্নাল ডিপ নেই।
 *
 * Design:
 * - Corpus = tool descriptors (name + description + tags). Index built once,
 *   refreshed explicitly (cheap; registry churn is rare).
 * - `route(query, topK)` returns ranked ToolRouteMatch[] with a 0..1 score.
 * - `pruneForQuery(query, toolSchemas, keepThreshold)` filters the *schema
 *   payload* handed to a model so only plausibly-relevant tools are sent.
 * - Deterministic (pure functions), constant-time token compare stays the
 *   caller's responsibility (security.py / compare_digest — unchanged).
 *
 * No external dependency: runs in Node 18+ and Cloudflare Workers alike.
 */

export interface ToolDescriptor {
  /** Stable tool id, e.g. 'github.list_prs' */
  name: string;
  /** Human description (already sanitized upstream — no secrets expected). */
  description?: string;
  /** Optional tags/capabilities that strengthen matching. */
  tags?: string[];
  /** Optional logical group used for audit logging. */
  group?: string;
}

export interface ToolRouteMatch {
  name: string;
  score: number; // 0..1 cosine over TF-IDF vectors
  matchedTerms: string[];
  group?: string;
}

interface TokenizedTool {
  name: string;
  group?: string;
  tokens: Map<string, number>; // term -> raw tf
  norm: number; // vector norm under final idf weights
}

const WORD_RE = /[a-z0-9_]{2,}/g;

const STOP = new Set([
  'the', 'a', 'an', 'and', 'or', 'to', 'of', 'in', 'on', 'for', 'with', 'this',
  'that', 'it', 'is', 'are', 'be', 'as', 'at', 'by', 'from', 'list', 'get',
  'set', 'all', 'any', 'new', 'use', 'using', 'tool',
]);

function tokenize(text: string): string[] {
  return (text.toLowerCase().match(WORD_RE) ?? []).filter((t) => !STOP.has(t));
}

export class SemanticToolRouter {
  private tools: TokenizedTool[] = [];
  private idf = new Map<string, number>();

  constructor(tools: ToolDescriptor[] = []) {
    this.reindex(tools);
  }

  /** (Re)build the inverted index. Call after registry churn. */
  reindex(tools: ToolDescriptor[]): void {
    const tokenized: TokenizedTool[] = tools.map((t) => {
      const tokens = new Map<string, number>();
      const bump = (w: string) => tokens.set(w, (tokens.get(w) ?? 0) + 1);
      // Tool name split on separators so 'github.list_prs' matches 'prs' too.
      for (const w of tokenize(t.name.replace(/[._\-/]/g, ' '))) bump(w);
      if (t.description) for (const w of tokenize(t.description)) bump(w);
      for (const tag of t.tags ?? []) for (const w of tokenize(tag)) bump(w);
      return { name: t.name, group: t.group, tokens, norm: 0 };
    });

    const df = new Map<string, number>();
    for (const t of tokenized) for (const w of t.tokens.keys()) df.set(w, (df.get(w) ?? 0) + 1);

    const n = Math.max(tokenized.length, 1);
    const idf = new Map<string, number>();
    for (const [w, c] of df) idf.set(w, Math.log((1 + n) / (1 + c)) + 1);

    // Precompute per-tool vector norms under the final idf weights.
    for (const t of tokenized) {
      let sq = 0;
      for (const [w, tf] of t.tokens) {
        sq += Math.pow((1 + Math.log(tf)) * (idf.get(w) ?? 1), 2);
      }
      t.norm = Math.sqrt(sq);
    }

    this.tools = tokenized;
    this.idf = idf;
  }

  get size(): number {
    return this.tools.length;
  }

  /** Rank tools for a natural-language query. */
  route(query: string, topK = 5): ToolRouteMatch[] {
    const qTokens = tokenize(query);
    if (!qTokens.length || !this.tools.length) return [];

    const qTf = new Map<string, number>();
    for (const w of qTokens) qTf.set(w, (qTf.get(w) ?? 0) + 1);

    let qSq = 0;
    const qWeights = new Map<string, number>();
    for (const [w, tf] of qTf) {
      const weight = (1 + Math.log(tf)) * (this.idf.get(w) ?? 1);
      qWeights.set(w, weight);
      qSq += weight * weight;
    }
    const qNorm = Math.sqrt(qSq);
    if (qNorm === 0) return [];

    const scored: ToolRouteMatch[] = [];
    for (const tool of this.tools) {
      if (tool.norm === 0) continue;
      let dot = 0;
      const matched: string[] = [];
      for (const [w, qw] of qWeights) {
        const tf = tool.tokens.get(w);
        if (tf === undefined) continue;
        const tw = (1 + Math.log(tf)) * (this.idf.get(w) ?? 1);
        dot += qw * tw;
        matched.push(w);
      }
      if (dot <= 0) continue;
      const cosine = dot / (qNorm * tool.norm);
      scored.push({
        name: tool.name,
        score: Math.max(0, Math.min(1, cosine)),
        matchedTerms: matched,
        group: tool.group,
      });
    }

    scored.sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
    return scored.slice(0, Math.max(1, topK));
  }

  /**
   * Prune full tool schemas down to those relevant to the query.
   * Returns the subset plus an audit hint (what was dropped and why).
   * `threshold` default 0.05 keeps anything with a non-trivial cosine.
   */
  pruneForQuery<S extends { name: string }>(
    query: string,
    schemas: S[],
    threshold = 0.05,
  ): { kept: S[]; dropped: string[]; matches: ToolRouteMatch[] } {
    const matches = this.route(query, this.tools.length || 1);
    const keep = new Map(matches.map((m) => [m.name, m.score] as const));
    const kept: S[] = [];
    const dropped: string[] = [];
    for (const schema of schemas) {
      const score = keep.get(schema.name) ?? 0;
      if (score >= threshold) kept.push(schema);
      else dropped.push(schema.name);
    }
    return { kept, dropped, matches };
  }
}

export default SemanticToolRouter;
