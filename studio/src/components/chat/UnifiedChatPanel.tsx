import React from 'react';
import { Search, Sparkles, WandSparkles, Zap } from 'lucide-react';
import { UnifiedChatBubble } from './UnifiedChatBubble';
import { brandFrom, brandTooltip, TIER_CLASS, type Brand } from '../../lib/brandLabel';

// UNIFIED CHAT (Phase 1, 2026-10-24): the chat core (engine + panel UI) was
// extracted from src/pages/PublicPages.tsx so guest, user and admin
// dashboards share ONE implementation. Guests get the plain panel; user and
// admin dashboards render the same panel and pass extraHeader/extraActions
// for their additional options. Marketing model names, webhook-only relay
// mandate, streaming behavior and the staged thinking indicator are
// unchanged — this is a pure move, not a behavior change.

export const chatIntents = [
  { label: 'Research', prompt: 'Help me research a topic and organize the key findings.', icon: Search },
  { label: 'Write', prompt: 'Help me write a clear, useful first draft.', icon: WandSparkles },
  { label: 'Build', prompt: 'Help me turn an idea into a practical build plan.', icon: Zap },
  { label: 'Analyze', prompt: 'Help me analyze this problem and decide what to do next.', icon: Sparkles },
];

export const chatModels = [
  { name: 'Supreme Auto', detail: 'Best balance for everyday work', tag: 'Recommended' },
  { name: 'Reasoning Pro', detail: 'Deep analysis and complex planning', tag: 'Reasoning' },
  { name: 'Fast Chat', detail: 'Quick answers and brainstorming', tag: 'Fast' },
];
type Message = { role: 'user' | 'assistant'; text: string };
// OWNER NOTE (2026-10-24): the "high demand" message is an intentional marketing
// strategy (upsell toward sign-in / paid plan) — restored per owner decision.
export function responseFor(input: string) { return 'SupremeAI is experiencing high demand right now, so our servers are busy. Please try again in a moment. Want faster, priority responses and full access to files, tools, and history? Sign in or subscribe to a paid plan for high-priority queue access.'; }

export async function callLiveAI(prompt: string, modelName: string, apiKey: string = '', onToken?: (token: string) => void): Promise<{ text: string; via?: string; brand?: Brand }> {
  const env = (import.meta as unknown as { env: Record<string, string> }).env || {};
  const webhookTarget = (env.VITE_STEALTH_WEBHOOK_URL || env.VITE_WEBHOOK_URL || '').replace(/\/$/, '');
  const apiTarget = (env.VITE_SUPREMEAI_API_URL || 'https://supremeai-api-ulw0.onrender.com').replace(/\/$/, '');
  const resolvedKey = apiKey || env.VITE_SUPREMEAI_API_KEY || (typeof localStorage !== 'undefined' ? (localStorage.getItem('supremeai_api_key') || 'guest') : 'guest');
  const modelId = modelName.toLowerCase().includes('reasoning') ? 'supremeai/openrouter' : (modelName.toLowerCase().includes('fast') ? 'supremeai/groq' : 'auto');

  const today = new Date().toISOString().split('T')[0];
  const systemPrompt = `You are SupremeAI. Today is ${today}. Your training data has a knowledge cutoff and may not reflect very recent events (elections, resignations, political changes, breaking news). For any time-sensitive factual question, provide what you know but explicitly state your knowledge may be outdated and recommend verifying with a current news source. Never assert outdated information as a current fact without this caveat.`;

  const body = JSON.stringify({
    model: modelId,
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: prompt },
    ],
    // OWNER REQUEST (2026-10-24): request streaming — SSE-capable targets reply
    // token-by-token; non-stream webhooks ignore it and return a single JSON body.
    stream: true,
  });

  // Oct-23 outage lesson: when every relay target failed, the guest only saw the
  // generic offline line while the gateway's 502 body carried the actual reason
  // (e.g. "STEALTH_WEBHOOK_URL host does not resolve"). Capture that detail and
  // surface it (truncated) so a config outage is self-explaining in chat.
  let relayDetail = '';

  const tryTarget = async (target: string): Promise<{ text: string; via?: string; brand?: Brand } | null> => {
    if (!target) return null;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);
    try {
      // eslint-disable-next-line no-restricted-syntax
      const res = await fetch(`${target}/v1/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(resolvedKey ? { 'X-SupremeAI-Key': resolvedKey } : {}),
        },
        body,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      if (res.ok) {
        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('text/event-stream') && res.body) {
          // Streaming target: render tokens progressively as they arrive.
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let streamed = '';
          let pending = '';
          let brand: Brand | undefined;
          while (true) {
            const { done, value } = await reader.read();
            pending += decoder.decode(value ?? new Uint8Array(), { stream: !done });
            const lines = pending.split(/\r?\n/);
            pending = lines.pop() ?? '';
            for (const line of lines) {
              if (!line.startsWith('data:')) continue;
              const payload = line.slice(5).trim();
              if (!payload || payload === '[DONE]') continue;
              try {
                const parsed = JSON.parse(payload);
                const delta: string | undefined = parsed?.choices?.[0]?.delta?.content ?? parsed?.token ?? parsed?.delta;
                if (delta) { streamed += delta; onToken?.(delta); }
                const b = brandFrom(parsed);
                if (b) brand = brand ?? b;
              } catch {
                streamed += payload;
                onToken?.(payload);
              }
            }
            if (done) break;
          }
          const clean = streamed.trim();
          if (clean && !clean.includes('[GEMINI Web Session Active]') && !clean.includes('health=100') && !clean.includes('[GROK Web Session Active]') && !clean.includes('[CHATGPT Web Session Active]') && !clean.includes('[PERPLEXITY Web Session Active]')) {
            return { text: clean, brand, via: brand?.label ?? 'stream' };
          }
          relayDetail = 'relay returned a non-chat or empty response';
        } else {
          // Non-stream target (webhook): one JSON body — the thinking stages cover the wait.
          const data = await res.json();
          const content = data?.choices?.[0]?.message?.content ?? data?.choices?.[0]?.delta?.content;
          if (content && typeof content === 'string' && !content.includes('[GEMINI Web Session Active]') && !content.includes('health=100') && !content.includes('[GROK Web Session Active]') && !content.includes('[CHATGPT Web Session Active]') && !content.includes('[PERPLEXITY Web Session Active]')) {
            const brand = brandFrom(data);
            return { text: content.trim(), brand, via: brand.label };
          }
          relayDetail = 'relay returned a non-chat or empty response';
        }
      } else {
        try {
          const errData = await res.json();
          const detail = errData?.detail || errData?.error || errData?.reason;
          if (detail) {
            relayDetail = `HTTP ${res.status}: ${String(detail)}`;
            console.warn('[GuestChat] target http error:', target, res.status, detail);
          }
        } catch { /* non-JSON error body — keep generic detail */ }
      }
    } catch (err) {
      clearTimeout(timeoutId);
      relayDetail = 'network error (timeout, DNS or CORS)';
      console.warn('[GuestChat] target failed:', target, err);
    }
    return null;
  };

  // Priority 1: direct frontend webhookTarget (if configured)
  if (webhookTarget) {
    const webhookResult = await tryTarget(webhookTarget);
    if (webhookResult) return webhookResult;
  }

  // Priority 2: forward to gateway (which routes strictly to STEALTH_WEBHOOK_URL)
  if (apiTarget && apiTarget !== webhookTarget) {
    const gatewayWebhookResult = await tryTarget(apiTarget);
    if (gatewayWebhookResult) return gatewayWebhookResult;
  }

  /*
   * [COMMENTED OUT PER USER MANDATE: reply only webhook use korbe, API key & fallback 2tai remove/comment]
   *
   * // Priority 2: API (gateway API key squad)
   * for (let attempt = 0; attempt < 2; attempt++) { ... }
   *
   * // Priority 3: hardcoded fallback
   * return { text: responseFor(prompt), via: 'fallback' };
   */

  const offlineSuffix = relayDetail ? ` (${relayDetail.slice(0, 200)})` : '';
  return { text: `Webhook relay is currently offline or unreachable.${offlineSuffix}`, via: 'webhook-offline' };
}

// OWNER REQUEST (2026-10-24): the webhook-only relay takes a while to reply, so the
// wait is presented as a live "thinking" stage progression instead of dead air —
// the delay should feel like part of the experience, not a hang.
const THINKING_STAGES = [
  'Understanding your question…',
  'Routing across the SupremeAI mesh…',
  'Selecting the best model…',
  'Composing your answer…',
  'Almost there…',
];

export function ThinkingIndicator() {
  const [elapsed, setElapsed] = React.useState(0);
  const reduced = React.useMemo(() => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches, []);
  React.useEffect(() => {
    const timer = window.setInterval(() => setElapsed((seconds) => seconds + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const stage = THINKING_STAGES[Math.min(Math.floor(elapsed / 5), THINKING_STAGES.length - 1)];
  return (
    <div className="flex items-center gap-3 self-start rounded-xl border border-purple-500/20 bg-purple-950/20 px-3 py-2.5" role="status" aria-label="SupremeAI is thinking">
      <span className="relative flex size-4 items-center justify-center">
        {reduced ? null : <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-purple-500 opacity-30" />}
        <span className="relative inline-flex size-2 rounded-full bg-purple-400" />
      </span>
      <span className="text-sm text-purple-200">{stage}</span>
      <span className="font-mono text-[10px] text-slate-500">{elapsed}s</span>
    </div>
  );
}

export interface UnifiedChatPanelProps {
  /** Extra controls beside the model picker (user/admin dashboards). */
  extraHeader?: React.ReactNode;
  /** Extra controls beside the Send button (user/admin dashboards). */
  extraActions?: React.ReactNode;
  /** Hide the starter cards when a dashboard supplies its own intro. */
  showStarter?: boolean;
}

export function UnifiedChatPanel({ extraHeader, extraActions, showStarter = true }: UnifiedChatPanelProps) {
  const [messages, setMessages] = React.useState<{ role: 'user' | 'assistant'; text: string; via?: string; brand?: Brand }[]>([]);
  const [input, setInput] = React.useState('');
  const [model, setModel] = React.useState(chatModels[0]?.name ?? 'Supreme Auto');
  const [apiKey] = React.useState(typeof localStorage !== 'undefined' ? (localStorage.getItem('supremeai_api_key') || '') : '');
  const [busy, setBusy] = React.useState(false);
  const [awaitingFirst, setAwaitingFirst] = React.useState(false);
  const listRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => { listRef.current?.scrollTo(0, listRef.current.scrollHeight); }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', text }, { role: 'assistant', text: '' }]);
    setBusy(true);
    setAwaitingFirst(true);
    try {
      if (apiKey) { try { localStorage.setItem('supremeai_api_key', apiKey); } catch (e) { void e; } }
      // Streaming path: tokens render live into the assistant placeholder and
      // the thinking stages stop at the first token; non-stream webhooks keep
      // the staged indicator until the full reply lands in one piece.
      const reply = await callLiveAI(text, model, apiKey, (token) => {
        setAwaitingFirst(false);
        setMessages((m) => {
          const next = [...m];
          const last = next[next.length - 1];
          if (last && last.role === 'assistant') next[next.length - 1] = { ...last, text: last.text + token };
          return next;
        });
      });
      setAwaitingFirst(false);
      setMessages((m) => [...m.slice(0, -1), { role: 'assistant', text: reply.text, via: reply.via, brand: reply.brand }]);
    } catch {
      setAwaitingFirst(false);
      setMessages((m) => {
        const last = m[m.length - 1];
        if (last && last.role === 'assistant' && !last.text) {
          return [...m.slice(0, -1), { role: 'assistant', text: responseFor(text), via: 'fallback' }];
        }
        return m;
      });
    } finally {
      setBusy(false);
    }
  }

  return <section className="mx-auto flex min-h-[calc(100dvh-13rem)] w-full max-w-3xl flex-1 flex-col gap-3 rounded-2xl border border-white/10 bg-[var(--surface-glass,rgba(15,23,42,0.6))] p-4 shadow-[var(--glow-accent,0_0_24px_rgba(168,85,247,0.15))] backdrop-blur-md">
    <div className="flex items-center gap-2">
      <select value={model} onChange={(e) => setModel(e.target.value)} className="flex-1 rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-purple-400/50">
        {chatModels.map((m) => <option key={m.name} value={m.name}>{m.name} — {m.detail}</option>)}
      </select>
      {extraHeader}
    </div>
    <div ref={listRef} className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto rounded-xl bg-slate-950/40 p-3">
{messages.length === 0 && showStarter && (
        <div className="flex flex-1 flex-col items-center justify-center gap-6 py-8 text-center">
          {/* OWNER REQUEST (2026-10-24): fill the empty middle of the guest chat
              with an attractive starter surface and sink the composer toward the
              bottom of the viewport. Marketing model names (Supreme Auto /
              Reasoning Pro / Fast Chat) are intentionally unchanged. */}
          <div className="relative flex size-16 items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-tr from-emerald-400/20 via-indigo-500/20 to-purple-600/20 shadow-[var(--glow-accent,0_0_24px_rgba(168,85,247,0.25))]">
            <span className="bg-gradient-to-r from-emerald-400 to-purple-500 bg-clip-text text-2xl font-bold text-transparent">S</span>
          </div>
          <div>
            <h2 className="text-xl font-semibold text-slate-100 sm:text-2xl">How can SupremeAI help you today?</h2>
            <p className="mt-2 text-sm text-slate-500">Ask anything — or pick a starting point below.</p>
          </div>
          <div className="grid w-full max-w-xl grid-cols-1 gap-3 sm:grid-cols-2">
            {chatIntents.map(({ label, prompt, icon: Icon }) => (
              <button key={label} type="button" onClick={() => setInput(prompt)} className="group flex items-start gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-4 text-left transition hover:border-purple-500/40 hover:bg-purple-500/5 hover:shadow-[var(--glow-accent,0_0_24px_rgba(168,85,247,0.15))]">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-slate-900 text-emerald-300 group-hover:text-purple-300"><Icon size={15} /></span>
                <span>
                  <span className="block text-sm font-semibold text-slate-200">{label}</span>
                  <span className="mt-1 block text-xs leading-5 text-slate-500">{prompt}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
      {messages.map((m, i) => <div key={i} className={`flex flex-col ${m.role === 'user' ? 'items-end' : 'items-start'}`}>
        {/* Refs #861: shared Cosmic UnifiedChatBubble — আর কোনো ফর্কড legacy bubble নেই */}
        <UnifiedChatBubble text={m.text} sender={m.role === 'user' ? 'user' : 'system'} />
        {m.role === 'assistant' && (
          m.brand ? (
            <div
              className="mt-1 flex items-center gap-1 px-1 text-[11px]"
              title={brandTooltip(m.brand)}
            >
              <span className="font-semibold tracking-tight bg-gradient-to-r from-emerald-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent">
                SupremeAI{m.brand.tier}
              </span>
              <span className="font-mono text-[8px] text-slate-500/80 hover:text-slate-300 transition-colors select-all">
                ({m.brand.channel}.{m.brand.engine})
              </span>
            </div>
          ) : m.via ? (
            <span className="mt-1 px-1 text-[10px] font-mono text-slate-500">[{m.via}]</span>
          ) : null
        )}
      </div>)}
      {busy && awaitingFirst && <ThinkingIndicator />}
    </div>
    <div className="flex gap-2">
      <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }} rows={2} placeholder="Ask SupremeAI…" className="flex-1 resize-none rounded-xl border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-purple-400/50" />
      <button type="button" onClick={send} disabled={busy || !input.trim()} className="rounded-xl bg-gradient-to-r from-emerald-500 to-purple-600 px-4 py-2 text-sm font-semibold text-white shadow-md shadow-emerald-500/20 transition hover:opacity-95 disabled:opacity-50">Send</button>
      {extraActions}
    </div>
  </section>;
}

export default UnifiedChatPanel;
