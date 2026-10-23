import React from 'react';
import { Link } from 'react-router-dom';
import { FileText, History, Menu, Search, Sparkles, WandSparkles, Wrench, X, Zap } from 'lucide-react';
import { UnifiedChatBubble } from '../components/chat/UnifiedChatBubble';
import { brandFrom, brandTooltip, TIER_CLASS, type Brand } from '../lib/brandLabel';

// ROOT-CAUSE RESTYLE (Refs #878 / bridge-20261023-frontend-guestchat-cosmic):
// বাংলা মন্তব্য: গেস্ট চ্যাট আগে legacy slate/cyan প্যালেট ব্যবহার করত ও নিজের
// ফর্কড বাবল রেন্ডার করত — অন্য ট��যাবগুলোর Cosmic ডিজাইনের সাথে মিলত না।
// এখন Cosmic aurora green/purple প্যালেট + শেয়ারড UnifiedChatBubble
// (Refs #861) ব্যবহার করা হচ্ছে; চ্যাট লজিক / webhook-only ম্যান্ডেট অপরিবর্তিত।

export const publicLinks = [
  // ROOT-CAUSE FIX (guest nav misdirection, 2026-10-23): 'Chat' pointed at '/'
  // (the landing page) and Models/Features/Pricing/Docs pointed at duplicate
  // GuestChat alias pages — every nav item dumped guests into the same chat.
  // Chat now targets /chat; the duplicate alias links are removed from the nav
  // (their routes remain for direct URLs / backward compatibility).
  { to: '/chat', label: 'Chat' },
  { to: '/about', label: 'About' },
];

export const capabilityItems = [
  { title: 'History', text: 'Save and revisit conversations', icon: History, href: '/login' },
  { title: 'Files', text: 'Bring your own context', icon: FileText, href: '/login' },
  { title: 'Tools', text: 'Connect actions and workflows', icon: Wrench, href: '/login' },
  { title: 'Runs', text: 'Turn ideas into repeatable work', icon: Zap, href: '/login' },
  { title: 'Workspace', text: 'Keep projects and context together', icon: Sparkles, href: '/login' },
];

export function CapabilityStrip({ onProtected }: { onProtected: (feature: string) => void }) {
  // Issue #1460: protected capability chips used to navigate straight to
  // /login (or /register), destroying the guest's in-progress chat. They now
  // raise an in-page auth prompt instead — no navigation, state intact.
  return <nav className="relative z-10 mx-auto flex w-full max-w-7xl gap-2 overflow-x-auto px-4 pt-24 sm:px-8" aria-label="SupremeAI capabilities">
    <Link to="/chat" className="shrink-0 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs font-medium text-emerald-300">Chat</Link>
    {capabilityItems.map(({ title, icon: Icon }) => <button key={title} type="button" onClick={() => onProtected(title)} className="flex shrink-0 items-center gap-2 rounded-full border border-white/10 bg-white/[0.02] px-3 py-2 text-xs text-slate-500 transition hover:border-purple-500/40 hover:text-slate-200"><Icon size={13} aria-hidden="true" />{title}</button>)}
  </nav>;
}

export function AuthPromptModal({ feature, onClose }: { feature: string; onClose: () => void }) {
  // Issue #1460: "Sign in to access [Feature]" without navigating away.
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label={`Sign in to access ${feature}`} onClick={onClose}>
    <div className="w-full max-w-sm rounded-3xl border border-white/10 bg-[var(--surface-glass,rgba(15,23,42,0.9))] p-7 shadow-2xl" onClick={(event) => event.stopPropagation()}>
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-lg font-medium text-slate-100">Sign in to access {feature.toLowerCase()}</h2>
        <button type="button" onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-slate-200"><X size={16} /></button>
      </div>
      <p className="mt-3 text-sm leading-6 text-slate-500">Your conversation stays right here — create an account or sign in when you are ready, and this page will keep your state.</p>
      <div className="mt-6 flex flex-col gap-2">
        <Link to="/login" className="rounded-full bg-gradient-to-r from-emerald-500 to-purple-600 px-4 py-2.5 text-center text-sm font-semibold text-white shadow-md shadow-emerald-500/20 transition hover:opacity-95">Sign in</Link>
        <Link to="/register" className="rounded-full border border-white/15 px-4 py-2.5 text-center text-sm font-medium text-slate-200 transition hover:border-purple-400/40">Create account</Link>
      </div>
    </div>
  </div>;
}

export const intents = [
  { label: 'Research', prompt: 'Help me research a topic and organize the key findings.', icon: Search },
  { label: 'Write', prompt: 'Help me write a clear, useful first draft.', icon: WandSparkles },
  { label: 'Build', prompt: 'Help me turn an idea into a practical build plan.', icon: Zap },
  { label: 'Analyze', prompt: 'Help me analyze this problem and decide what to do next.', icon: Sparkles },
];

const models = [
  { name: 'Supreme Auto', detail: 'Best balance for everyday work', tag: 'Recommended' },
  { name: 'Reasoning Pro', detail: 'Deep analysis and complex planning', tag: 'Reasoning' },
  { name: 'Fast Chat', detail: 'Quick answers and brainstorming', tag: 'Fast' },
];

export function PublicHeader() {
  const [menuOpen, setMenuOpen] = React.useState(false);
  return <header className="absolute inset-x-0 top-0 z-20 border-b border-white/[0.06] px-4 py-4 sm:px-8 sm:py-5">
    <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
      <Link to="/" aria-label="SupremeAI home" className="flex shrink-0 items-center gap-3 text-sm font-semibold tracking-[0.18em] text-slate-100"><span className="flex size-8 items-center justify-center rounded-xl bg-gradient-to-tr from-emerald-400 via-indigo-500 to-purple-600 font-mono text-sm font-bold text-white shadow-lg shadow-purple-500/20">S</span><span className="hidden sm:inline">SUPREMEAI</span></Link>
      <nav className="hidden items-center gap-4 md:flex lg:gap-6" aria-label="Public navigation">{publicLinks.map((link) => <Link key={link.to} to={link.to} className="text-sm text-slate-500 transition hover:text-slate-100">{link.label}</Link>)}</nav>
      <div className="flex items-center gap-2 sm:gap-3"><span className="hidden items-center gap-2 text-xs text-slate-600 lg:flex"><span className="size-1.5 rounded-full bg-emerald-400" />Guest mode</span><Link to="/login" className="hidden text-sm text-slate-400 transition hover:text-slate-100 sm:block">Sign in</Link><Link to="/register" className="rounded-full bg-gradient-to-r from-emerald-500 to-purple-600 px-4 py-2 text-sm font-semibold text-white shadow-md shadow-emerald-500/20 transition hover:opacity-95">Get started</Link><button type="button" onClick={() => setMenuOpen((open) => !open)} className="rounded-lg p-2 text-slate-400 md:hidden" aria-label={menuOpen ? 'Close menu' : 'Open menu'} aria-expanded={menuOpen}>{menuOpen ? <X size={18} /> : <Menu size={18} />}</button></div>
    </div>
    {menuOpen && <nav className="mx-auto mt-3 flex max-w-7xl flex-col gap-1 rounded-2xl border border-white/10 bg-slate-900/95 p-3 md:hidden" aria-label="Mobile navigation">{publicLinks.map((link) => <Link key={link.to} to={link.to} onClick={() => setMenuOpen(false)} className="rounded-lg px-3 py-2 text-sm text-slate-300 hover:bg-white/5">{link.label}</Link>)}<Link to="/login" className="rounded-lg px-3 py-2 text-sm text-slate-300 hover:bg-white/5">Sign in</Link></nav>}
  </header>;
}

export function PublicLayout({ children }: { children: React.ReactNode }) { return <div className="min-h-screen bg-slate-950 text-[var(--sa-ink,#f8fafc)]">{children}</div>; }

type Message = { role: 'user' | 'assistant'; text: string };
function responseFor(input: string) { return 'SupremeAI is experiencing high demand right now, so our servers are busy. Please try again in a moment. Want faster, priority responses and full access to files, tools, and history? Sign in or subscribe to a paid plan for high-priority queue access.'; }

async function callLiveAI(prompt: string, modelName: string, apiKey: string = ''): Promise<{ text: string; via?: string; brand?: Brand }> {
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
    stream: false,
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
        const data = await res.json();
        const content = data?.choices?.[0]?.message?.content;
        if (content && typeof content === 'string' && !content.includes('[GEMINI Web Session Active]') && !content.includes('health=100') && !content.includes('[GROK Web Session Active]') && !content.includes('[CHATGPT Web Session Active]') && !content.includes('[PERPLEXITY Web Session Active]')) {
          const brand = brandFrom(data);
          return { text: content.trim(), brand, via: brand.label };
        }
        relayDetail = 'relay returned a non-chat or empty response';
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

export function GuestChat() {
  const [messages, setMessages] = React.useState<{ role: 'user' | 'assistant'; text: string; via?: string; brand?: Brand }[]>([]);
  const [input, setInput] = React.useState('');
  const [model, setModel] = React.useState(models[0]?.name ?? 'Supreme Auto');
  const [apiKey] = React.useState(typeof localStorage !== 'undefined' ? (localStorage.getItem('supremeai_api_key') || '') : '');
  const [busy, setBusy] = React.useState(false);
  const listRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => { listRef.current?.scrollTo(0, listRef.current.scrollHeight); }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', text }]);
    setBusy(true);
    try {
      if (apiKey) { try { localStorage.setItem('supremeai_api_key', apiKey); } catch (e) { void e; } }
      const reply = await callLiveAI(text, model, apiKey);
      setMessages((m) => [...m, { role: 'assistant', text: reply.text, via: reply.via, brand: reply.brand }]);
    } catch {
      setMessages((m) => [...m, { role: 'assistant', text: responseFor(text), via: 'fallback' }]);
    } finally {
      setBusy(false);
    }
  }

  return <section className="mx-auto flex w-full max-w-3xl flex-col gap-3 rounded-2xl border border-white/10 bg-[var(--surface-glass,rgba(15,23,42,0.6))] p-4 shadow-[var(--glow-accent,0_0_24px_rgba(168,85,247,0.15))] backdrop-blur-md">
    <div className="flex items-center gap-2">
      <select value={model} onChange={(e) => setModel(e.target.value)} className="flex-1 rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-purple-400/50">
        {models.map((m) => <option key={m.name} value={m.name}>{m.name} — {m.detail}</option>)}
      </select>
    </div>
    <div ref={listRef} className="flex max-h-96 flex-col gap-3 overflow-y-auto rounded-xl bg-slate-950/40 p-3">
      {messages.length === 0 && <p className="text-sm text-slate-500">Ask SupremeAI anything to get started.</p>}
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
      {busy && <div className="flex items-center gap-1.5 px-1 py-1" aria-label="SupremeAI is thinking"><span className="size-1.5 animate-pulse rounded-full bg-purple-400" /><span className="size-1.5 animate-pulse rounded-full bg-purple-400 [animation-delay:150ms]" /><span className="size-1.5 animate-pulse rounded-full bg-purple-400 [animation-delay:300ms]" /></div>}
    </div>
    <div className="flex gap-2">
      <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }} rows={2} placeholder="Ask SupremeAI…" className="flex-1 resize-none rounded-xl border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-purple-400/50" />
      <button type="button" onClick={send} disabled={busy || !input.trim()} className="rounded-xl bg-gradient-to-r from-emerald-500 to-purple-600 px-4 py-2 text-sm font-semibold text-white shadow-md shadow-emerald-500/20 transition hover:opacity-95 disabled:opacity-50">Send</button>
    </div>
  </section>;
}


export const GuestChatPage = GuestChat;
export const ModelsPage = GuestChat;
export function PublicInfoPage(_props: { kind?: string }) { return <GuestChat />; }
export const PricingPage = GuestChat;
export const FeaturesPage = GuestChat;
export const DocsPage = GuestChat;
export const AboutPage = GuestChat;
export default GuestChat;
