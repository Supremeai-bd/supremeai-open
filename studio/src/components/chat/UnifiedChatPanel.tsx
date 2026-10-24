import React from 'react';
import { RotateCcw, Search, Sparkles, WandSparkles, Zap } from 'lucide-react';
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

export interface LiveAIOptions {
  conversationId?: string;
  history?: Array<{ role: 'user' | 'assistant'; text: string }>;
  /** Abort signal — lets the caller stop an in-flight generation (Stop button). */
  signal?: AbortSignal;
}

export async function callLiveAI(
  prompt: string,
  modelName: string,
  apiKey: string = '',
  onToken?: (token: string) => void,
  options?: LiveAIOptions,
): Promise<{ text: string; via?: string; brand?: Brand; conversationId?: string }> {
  const env = (import.meta as unknown as { env: Record<string, string> }).env || {};
  const webhookTarget = (env.VITE_STEALTH_WEBHOOK_URL || env.VITE_WEBHOOK_URL || '').replace(/\/$/, '');
  const apiTarget = (env.VITE_SUPREMEAI_API_URL || 'https://supremeai-api-ulw0.onrender.com').replace(/\/$/, '');
  const resolvedKey = apiKey || env.VITE_SUPREMEAI_API_KEY || (typeof localStorage !== 'undefined' ? (localStorage.getItem('supremeai_api_key') || 'guest') : 'guest');
  const modelId = modelName.toLowerCase().includes('reasoning') ? 'supremeai/openrouter' : (modelName.toLowerCase().includes('fast') ? 'supremeai/groq' : 'auto');

  const today = new Date().toISOString().split('T')[0];
  const systemPrompt = `You are SupremeAI. Today is ${today}. Your training data has a knowledge cutoff and may not reflect very recent events (elections, resignations, political changes, breaking news). For any time-sensitive factual question, provide what you know but explicitly state your knowledge may be outdated and recommend verifying with a current news source. Never assert outdated information as a current fact without this caveat.`;

  // Persistent conversation identifier across turns
  const convId = options?.conversationId
    || (typeof localStorage !== 'undefined' ? (localStorage.getItem('supremeai_conversation_id') || undefined) : undefined);

  // Carry forward up to 10 previous conversational turns for multi-turn coherence
  const historyMessages = (options?.history || [])
    .slice(-10)
    .filter((m) => m.text && m.text.trim())
    .map((m) => ({
      role: m.role,
      content: m.text,
    }));

  const messagesPayload = [
    { role: 'system', content: systemPrompt },
    ...historyMessages,
    { role: 'user', content: prompt },
  ];

  const body = JSON.stringify({
    model: modelId,
    messages: messagesPayload,
    // OWNER REQUEST (2026-10-24): request streaming — SSE-capable targets reply
    // token-by-token; non-stream webhooks ignore it and return a single JSON body.
    stream: true,
    ...(convId ? { conversation_id: convId } : {}),
  });

  // Oct-23 outage lesson: when every relay target failed, the guest only saw the
  // generic offline line while the gateway's 502 body carried the actual reason
  // (e.g. "STEALTH_WEBHOOK_URL host does not resolve"). Capture that detail and
  // surface it (truncated) so a config outage is self-explaining in chat.
  let relayDetail = '';

  const tryTarget = async (target: string): Promise<{ text: string; via?: string; brand?: Brand; conversationId?: string } | null> => {
    if (!target) return null;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);
    // STOP FEATURE (owner request 2026-10-24): the caller's abort signal is
    // chained into the fetch controller so Stop cancels the in-flight request.
    const external = options?.signal;
    const onExternalAbort = () => controller.abort();
    external?.addEventListener('abort', onExternalAbort);
    const detach = () => external?.removeEventListener('abort', onExternalAbort);
    try {
      // eslint-disable-next-line no-restricted-syntax
      const res = await fetch(`${target}/v1/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(resolvedKey ? { 'X-SupremeAI-Key': resolvedKey } : {}),
          ...(convId ? { 'X-Conversation-Id': convId } : {}),
        },
        body,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      detach();
      if (res.ok) {
        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('text/event-stream') && res.body) {
          // Streaming target: render tokens progressively as they arrive.
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let streamed = '';
          let pending = '';
          let brand: Brand | undefined;
          let responseConvId = convId;
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
                if (parsed?.conversation_id) responseConvId = String(parsed.conversation_id);
              } catch {
                streamed += payload;
                onToken?.(payload);
              }
            }
            if (done) break;
          }
          const clean = streamed.trim();
          if (clean && !clean.includes('[GEMINI Web Session Active]') && !clean.includes('health=100') && !clean.includes('[GROK Web Session Active]') && !clean.includes('[CHATGPT Web Session Active]') && !clean.includes('[PERPLEXITY Web Session Active]')) {
            return { text: clean, brand, via: brand?.label ?? 'stream', conversationId: responseConvId };
          }
          relayDetail = 'relay returned a non-chat or empty response';
        } else {
          // Non-stream target (webhook): one JSON body — the thinking stages cover the wait.
          const data = await res.json();
          const content = data?.choices?.[0]?.message?.content ?? data?.choices?.[0]?.delta?.content;
          if (content && typeof content === 'string' && !content.includes('[GEMINI Web Session Active]') && !content.includes('health=100') && !content.includes('[GROK Web Session Active]') && !content.includes('[CHATGPT Web Session Active]') && !content.includes('[PERPLEXITY Web Session Active]')) {
            const brand = brandFrom(data);
            const responseConvId = data?.conversation_id ? String(data.conversation_id) : convId;
            return { text: content.trim(), brand, via: brand.label, conversationId: responseConvId };
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
      detach();
      // Abort from the Stop button must not fall through to the next relay
      // target or the offline message — it is rethrown to the caller instead.
      if (external?.aborted) throw err;
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
  /** Initial input text (e.g. from ?intent= URL query param). */
  initialInput?: string;
  /** Optional callback when input changes. */
  onInputChange?: (value: string) => void;
  /** Optional callback when code block is previewed. */
  onPreview?: (code: string) => void;
  /** Optional custom styling classes. */
  className?: string;
  /**
   * Layout fit. 'page' (default) = standalone page surface with a
   * viewport-based min-height (guest chat page). 'fill' = fill the parent
   * flex container exactly — no viewport-height guessing; used by AI Studio
   * and the chat-first dashboard so the panel auto-adjusts to any screen
   * size instead of a hardcoded dvh offset (owner-reported sizing issues).
   */
  fit?: 'page' | 'fill';
  /**
   * Resume a saved conversation: loads its locally-persisted messages so the
   * chat continues with full context (history rail links use this).
   */
  initialConversationId?: string;
}

// CONVERSATION HISTORY (owner request 2026-10-24, parity with mainstream AI
// web apps): every conversation's messages are persisted locally keyed by the
// same conversation_id the backend receives — so a history entry can be
// reopened with full context even before a server-side history endpoint exists.
const HISTORY_KEY = 'supremeai_chat_history_v1';

function loadStoredConversation(id: string): Array<{ role: 'user' | 'assistant'; text: string }> {
  if (typeof localStorage === 'undefined') return [];
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const store = JSON.parse(raw) as Record<string, { messages: Array<{ role: 'user' | 'assistant'; text: string }>; updatedAt: number }>;
    const entry = store[id];
    return Array.isArray(entry?.messages) ? entry.messages : [];
  } catch {
    return [];
  }
}

function saveStoredConversation(id: string, messages: Array<{ role: 'user' | 'assistant'; text: string }>) {
  if (typeof localStorage === 'undefined' || messages.length === 0) return;
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    const store = raw ? (JSON.parse(raw) as Record<string, { messages: unknown[]; updatedAt: number }>) : {};
    store[id] = { messages, updatedAt: Date.now() };
    // Keep the 30 most recent conversations — bounded, no unbounded growth.
    const ids = Object.keys(store).sort((a, b) => (store[a].updatedAt ?? 0) - (store[b].updatedAt ?? 0));
    while (ids.length > 30) delete store[ids.shift() as string];
    localStorage.setItem(HISTORY_KEY, JSON.stringify(store));
  } catch { /* storage full or unavailable — history is best-effort */ }
}

/** Metadata of locally-persisted conversations for history sidebars. */
export interface StoredConversationMeta {
  id: string;
  title: string;
  updatedAt: number;
}

/** List persisted conversations (newest first) for history sidebars. */
export function listStoredConversations(): StoredConversationMeta[] {
  if (typeof localStorage === 'undefined') return [];
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const store = JSON.parse(raw) as Record<string, { messages?: Array<{ role: string; text: string }>; updatedAt: number }>;
    return Object.entries(store)
      .map(([id, entry]) => ({
        id,
        title: (entry.messages?.find((m) => m.role === 'user')?.text ?? 'Untitled conversation').slice(0, 60),
        updatedAt: entry.updatedAt ?? 0,
      }))
      .filter((meta) => meta.updatedAt > 0)
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, 30);
  } catch {
    return [];
  }
}

export function UnifiedChatPanel({
  extraHeader,
  extraActions,
  showStarter = true,
  initialInput,
  onInputChange,
  onPreview,
  className = '',
  fit = 'page',
  initialConversationId,
}: UnifiedChatPanelProps) {
  const [messages, setMessages] = React.useState<{ role: 'user' | 'assistant'; text: string; via?: string; brand?: Brand }[]>(() =>
    initialConversationId ? loadStoredConversation(initialConversationId) : [],
  );
  const [input, setInput] = React.useState(initialInput || '');
  const [model, setModel] = React.useState(chatModels[0]?.name ?? 'Supreme Auto');
  const [apiKey] = React.useState(typeof localStorage !== 'undefined' ? (localStorage.getItem('supremeai_api_key') || '') : '');
  const [busy, setBusy] = React.useState(false);
  const [awaitingFirst, setAwaitingFirst] = React.useState(false);
  const [conversationId, setConversationId] = React.useState<string>(() => {
    if (initialConversationId) {
      if (typeof localStorage !== 'undefined') {
        try { localStorage.setItem('supremeai_conversation_id', initialConversationId); } catch { /* ignore */ }
      }
      return initialConversationId;
    }
    if (typeof localStorage !== 'undefined') {
      const stored = localStorage.getItem('supremeai_conversation_id');
      if (stored) return stored;
    }
    const initialId = `conv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    if (typeof localStorage !== 'undefined') {
      try { localStorage.setItem('supremeai_conversation_id', initialId); } catch { /* ignore */ }
    }
    return initialId;
  });
  const listRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => { listRef.current?.scrollTo(0, listRef.current.scrollHeight); }, [messages]);

  // Persist the running conversation so the history rail can reopen it with
  // full context (best-effort, bounded to 30 conversations).
  React.useEffect(() => {
    if (conversationId && messages.length > 0) saveStoredConversation(conversationId, messages);
  }, [conversationId, messages]);

  // STOP FEATURE (owner request 2026-10-24): in-flight generations can be
  // cancelled — the controller aborts the fetch and the empty assistant
  // placeholder is removed instead of showing a fake fallback reply.
  const abortRef = React.useRef<AbortController | null>(null);
  const stopRequestedRef = React.useRef(false);
  const handleStop = () => {
    stopRequestedRef.current = true;
    abortRef.current?.abort();
  };

  React.useEffect(() => {
    if (initialInput !== undefined && initialInput !== '') {
      setInput(initialInput);
    }
  }, [initialInput]);

  const handleInputChange = (val: string) => {
    setInput(val);
    onInputChange?.(val);
  };

  const handleNewChat = () => {
    const nextId = `conv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setConversationId(nextId);
    if (typeof localStorage !== 'undefined') {
      try { localStorage.setItem('supremeai_conversation_id', nextId); } catch { /* ignore */ }
    }
    setMessages([]);
    setInput('');
  };

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    onInputChange?.('');
    setMessages((m) => [...m, { role: 'user', text }, { role: 'assistant', text: '' }]);
    setBusy(true);
    setAwaitingFirst(true);
    const controller = new AbortController();
    abortRef.current = controller;
    stopRequestedRef.current = false;
    const dropEmptyPlaceholder = () => {
      setMessages((m) => {
        const last = m[m.length - 1];
        return last && last.role === 'assistant' && !last.text ? m.slice(0, -1) : m;
      });
    };
    try {
      if (apiKey) { try { localStorage.setItem('supremeai_api_key', apiKey); } catch (e) { void e; } }
      let activeConvId = conversationId;
      if (!activeConvId) {
        activeConvId = `conv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        setConversationId(activeConvId);
        try { localStorage.setItem('supremeai_conversation_id', activeConvId); } catch { /* ignore */ }
      }
      // Streaming path: tokens render live into the assistant placeholder and
      // the thinking stages stop at the first token; non-stream webhooks keep
      // the staged indicator until the full reply lands in one piece.
      const reply = await callLiveAI(
        text,
        model,
        apiKey,
        (token) => {
          setAwaitingFirst(false);
          setMessages((m) => {
            const next = [...m];
            const last = next[next.length - 1];
            if (last && last.role === 'assistant') next[next.length - 1] = { ...last, text: last.text + token };
            return next;
          });
        },
        {
          conversationId: activeConvId,
          history: messages,
          signal: controller.signal,
        },
      );
      if (reply.conversationId && reply.conversationId !== activeConvId) {
        setConversationId(reply.conversationId);
        try { localStorage.setItem('supremeai_conversation_id', reply.conversationId); } catch { /* ignore */ }
      }
      setAwaitingFirst(false);
      if (stopRequestedRef.current) {
        dropEmptyPlaceholder();
        return;
      }
      setMessages((m) => [...m.slice(0, -1), { role: 'assistant', text: reply.text, via: reply.via, brand: reply.brand }]);
    } catch {
      setAwaitingFirst(false);
      if (stopRequestedRef.current) {
        dropEmptyPlaceholder();
        return;
      }
      setMessages((m) => {
        const last = m[m.length - 1];
        if (last && last.role === 'assistant' && !last.text) {
          return [...m.slice(0, -1), { role: 'assistant', text: responseFor(text), via: 'fallback' }];
        }
        return m;
      });
    } finally {
      abortRef.current = null;
      stopRequestedRef.current = false;
      setBusy(false);
    }
  }

  return <section className={`mx-auto flex w-full ${fit === 'fill' ? 'h-full min-h-0' : 'min-h-[calc(100dvh-13rem)] max-w-3xl flex-1'} flex-col gap-3 rounded-2xl border border-white/10 bg-[var(--surface-glass,rgba(15,23,42,0.6))] p-4 shadow-[var(--glow-accent,0_0_24px_rgba(168,85,247,0.15))] backdrop-blur-md ${className}`}>
    <div className="flex items-center gap-2">
      <select value={model} onChange={(e) => setModel(e.target.value)} className="flex-1 rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-purple-400/50">
        {chatModels.map((m) => <option key={m.name} value={m.name}>{m.name} — {m.detail}</option>)}
      </select>
      {messages.length > 0 && (
        <button
          type="button"
          onClick={handleNewChat}
          className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-slate-900/80 px-2.5 py-2 text-xs font-medium text-slate-300 transition hover:border-purple-400/40 hover:bg-slate-800 hover:text-white"
          title="Start a new conversation"
        >
          <RotateCcw size={13} className="text-slate-400" />
          <span>New</span>
        </button>
      )}
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
              <button key={label} type="button" onClick={() => handleInputChange(prompt)} className="group flex items-start gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-4 text-left transition hover:border-purple-500/40 hover:bg-purple-500/5 hover:shadow-[var(--glow-accent,0_0_24px_rgba(168,85,247,0.15))]">
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
        <UnifiedChatBubble text={m.text} sender={m.role === 'user' ? 'user' : 'system'} onPreview={onPreview} />
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
      <textarea
        value={input}
        onChange={(e) => handleInputChange(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
        rows={2}
        placeholder="Ask SupremeAI…"
        aria-label="Message SupremeAI"
        data-testid="chat-input"
        className="flex-1 resize-none rounded-xl border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-purple-400/50"
      />
      <button
        type="button"
        onClick={send}
        disabled={busy || !input.trim()}
        aria-label="Send message"
        data-testid="send-message-button"
        className="rounded-xl bg-gradient-to-r from-emerald-500 to-purple-600 px-4 py-2 text-sm font-semibold text-white shadow-md shadow-emerald-500/20 transition hover:opacity-95 disabled:opacity-50"
      >
        Send
      </button>
      {busy && (
        <button
          type="button"
          onClick={handleStop}
          aria-label="Stop generating"
          data-testid="stop-button"
          className="rounded-xl border border-white/10 bg-slate-900/80 px-3 py-2 text-sm font-medium text-slate-300 transition hover:border-red-400/40 hover:text-white"
        >
          Stop
        </button>
      )}
      {extraActions}
    </div>
  </section>;
}

export default UnifiedChatPanel;
