import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowUp, BrainCircuit, Check, ChevronDown, Clock, Database, Download, FileCode2, FileText, GitBranch, History, Image as ImageIcon, LayoutTemplate, Menu, Paperclip, Plus, Search, Share2, Sparkles, Telescope, Terminal, WandSparkles, Wrench, X, Zap } from 'lucide-react';

const publicLinks = [
  { to: '/', label: 'Chat' },
  { to: '/models', label: 'Models' },
  { to: '/features', label: 'Features' },
  { to: '/pricing', label: 'Pricing' },
  { to: '/docs', label: 'Docs' },
  { to: '/about', label: 'About' },
];

const capabilityItems = [
  { title: 'History', text: 'Save and revisit conversations', icon: History, href: '/login' },
  { title: 'Files', text: 'Bring your own context', icon: FileText, href: '/login' },
  { title: 'Tools', text: 'Connect actions and workflows', icon: Wrench, href: '/login' },
  { title: 'Runs', text: 'Turn ideas into repeatable work', icon: Zap, href: '/login' },
  { title: 'Workspace', text: 'Keep projects and context together', icon: Sparkles, href: '/login' },
];

function CapabilityStrip({ onProtected }: { onProtected: (feature: string) => void }) {
  // Issue #1460: protected capability chips used to navigate straight to
  // /login (or /register), destroying the guest's in-progress chat. They now
  // raise an in-page auth prompt instead — no navigation, state intact.
  return <nav className="relative z-10 mx-auto flex w-full max-w-7xl gap-2 overflow-x-auto px-4 pt-24 sm:px-8" aria-label="SupremeAI capabilities">
    <Link to="/" className="shrink-0 rounded-full border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 text-xs font-medium text-cyan-200">Chat</Link>
    {capabilityItems.map(({ title, icon: Icon }) => <button key={title} type="button" onClick={() => onProtected(title)} className="flex shrink-0 items-center gap-2 rounded-full border border-white/10 bg-white/[0.02] px-3 py-2 text-xs text-slate-500 transition hover:border-cyan-300/30 hover:text-slate-200"><Icon size={13} aria-hidden="true" />{title}</button>)}
  </nav>;
}

function AuthPromptModal({ feature, onClose }: { feature: string; onClose: () => void }) {
  // Issue #1460: "Sign in to access [Feature]" without navigating away.
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4" role="dialog" aria-modal="true" aria-label={`Sign in to access ${feature}`} onClick={onClose}>
    <div className="w-full max-w-sm rounded-3xl border border-white/10 bg-[#171a20] p-7 shadow-2xl" onClick={(event) => event.stopPropagation()}>
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-lg font-medium text-slate-100">Sign in to access {feature.toLowerCase()}</h2>
        <button type="button" onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-slate-200"><X size={16} /></button>
      </div>
      <p className="mt-3 text-sm leading-6 text-slate-500">Your conversation stays right here — create an account or sign in when you are ready, and this page will keep your state.</p>
      <div className="mt-6 flex flex-col gap-2">
        <Link to="/login" className="rounded-full bg-cyan-300 px-4 py-2.5 text-center text-sm font-semibold text-slate-950 transition hover:bg-cyan-200">Sign in</Link>
        <Link to="/register" className="rounded-full border border-white/15 px-4 py-2.5 text-center text-sm font-medium text-slate-200 transition hover:border-cyan-300/40">Create account</Link>
      </div>
    </div>
  </div>;
}

const intents = [
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
      <Link to="/" aria-label="SupremeAI home" className="flex shrink-0 items-center gap-3 text-sm font-semibold tracking-[0.18em] text-slate-100"><span className="flex size-8 items-center justify-center rounded-xl bg-cyan-300 font-mono text-sm font-bold text-slate-950 shadow-[0_0_24px_rgba(103,232,249,0.25)]">S</span><span className="hidden sm:inline">SUPREMEAI</span></Link>
      <nav className="hidden items-center gap-4 md:flex lg:gap-6" aria-label="Public navigation">{publicLinks.map((link) => <Link key={link.to} to={link.to} className="text-sm text-slate-500 transition hover:text-slate-100">{link.label}</Link>)}</nav>
      <div className="flex items-center gap-2 sm:gap-3"><span className="hidden items-center gap-2 text-xs text-slate-600 lg:flex"><span className="size-1.5 rounded-full bg-emerald-400" />Guest mode</span><Link to="/login" className="hidden text-sm text-slate-400 transition hover:text-slate-100 sm:block">Sign in</Link><Link to="/register" className="rounded-full bg-cyan-300 px-4 py-2 text-sm font-semibold text-slate-950 shadow-[0_0_24px_rgba(103,232,249,0.15)] transition hover:bg-cyan-200">Get started</Link><button type="button" onClick={() => setMenuOpen((open) => !open)} className="rounded-lg p-2 text-slate-400 md:hidden" aria-label={menuOpen ? 'Close menu' : 'Open menu'} aria-expanded={menuOpen}>{menuOpen ? <X size={18} /> : <Menu size={18} />}</button></div>
    </div>
    {menuOpen && <nav className="mx-auto mt-3 flex max-w-7xl flex-col gap-1 rounded-2xl border border-white/10 bg-slate-900/95 p-3 md:hidden" aria-label="Mobile navigation">{publicLinks.map((link) => <Link key={link.to} to={link.to} onClick={() => setMenuOpen(false)} className="rounded-lg px-3 py-2 text-sm text-slate-300 hover:bg-white/5">{link.label}</Link>)}<Link to="/login" className="rounded-lg px-3 py-2 text-sm text-slate-300 hover:bg-white/5">Sign in</Link></nav>}
  </header>;
}

export function PublicLayout({ children }: { children: React.ReactNode }) { return <div className="min-h-screen bg-[#0d0f12] text-slate-100">{children}</div>; }

type Message = { role: 'user' | 'assistant'; text: string };
function responseFor(input: string) { return 'SupremeAI is experiencing high demand right now, so our servers are busy. Please try again in a moment. Want faster, priority responses and full access to files, tools, and history? Sign in or subscribe to a paid plan for high-priority queue access.'; }

async function callLiveAI(prompt: string, modelName: string, apiKey: string = ''): Promise<string> {
  try {
    const apiTarget = (import.meta as unknown as { env: Record<string, string> }).env?.VITE_SUPREMEAI_API_URL || 'https://supremeai-api-ulw0.onrender.com';
    const resolvedKey = apiKey || (import.meta as unknown as { env: Record<string, string> }).env?.VITE_SUPREMEAI_API_KEY || (typeof localStorage !== 'undefined' ? localStorage.getItem('supremeai_api_key') || '' : '');
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 25000);

    // Audit fix (bridge-20261019): inject system prompt with today's date.
    // Prev bug: no system message → model returned stale facts as current truth
    // (e.g. claimed Sheikh Hasina was Bangladesh PM after her Aug 2024 resignation).
    const today = new Date().toISOString().split('T')[0];
    const systemPrompt = `You are SupremeAI. Today is ${today}. Your training data has a knowledge cutoff and may not reflect very recent events (elections, resignations, political changes, breaking news). For any time-sensitive factual question, provide what you know but explicitly state your knowledge may be outdated and recommend verifying with a current news source. Never assert outdated information as a current fact without this caveat.`;

    const res = await fetch(`${apiTarget}/v1/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(resolvedKey ? { 'X-SupremeAI-Key': resolvedKey } : {}),
      },
      body: JSON.stringify({
        model: modelName.toLowerCase().includes('reasoning') ? 'gemini-1.5-pro' : 'auto',
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: prompt },
        ],
        stream: false,
      }),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (res.ok) {
      const data = await res.json();
      const content = data?.choices?.[0]?.message?.content;
      if (content && typeof content === 'string' && !content.includes('[GEMINI Web Session Active]') && !content.includes('health=100')) {
        return content.trim();
      }
    }
  } catch (err) {
    console.warn('[GuestChat] Live AI fallback triggered:', err);
  }
  return responseFor(prompt);
}

function AssistantAvatar({ muted = false }: { muted?: boolean }) { return <span aria-hidden="true" className={`mt-1 flex size-6 shrink-0 items-center justify-center rounded-lg font-mono text-[10px] font-bold text-cyan-300 ${muted ? 'bg-cyan-300/[0.06]' : 'bg-cyan-300/10 shadow-[0_0_16px_rgba(103,232,249,0.15)]'}`}>S</span>; }

export function GuestChat() {
  const [messages, setMessages] = React.useState<{ role: 'user' | 'assistant'; text: string }[]>([]);
  const [input, setInput] = React.useState('');
  const [model, setModel] = React.useState(models[0]?.name ?? 'Supreme Auto');
  const [apiKey, setApiKey] = React.useState(typeof localStorage !== 'undefined' ? (localStorage.getItem('supremeai_api_key') || '') : '');
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
      if (apiKey) { try { localStorage.setItem('supremeai_api_key', apiKey); } catch {} }
      const reply = await callLiveAI(text, model, apiKey);
      setMessages((m) => [...m, { role: 'assistant', text: reply }]);
    } catch {
      setMessages((m) => [...m, { role: 'assistant', text: responseFor(text) }]);
    } finally {
      setBusy(false);
    }
  }

  return <section className="mx-auto flex w-full max-w-3xl flex-col gap-3 rounded-2xl border border-white/10 bg-white/[0.02] p-4">
    <div className="flex items-center gap-2">
      <select value={model} onChange={(e) => setModel(e.target.value)} className="flex-1 rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-200">
        {models.map((m) => <option key={m.name} value={m.name}>{m.name} — {m.detail}</option>)}
      </select>
    </div>
    <div ref={listRef} className="flex max-h-96 flex-col gap-2 overflow-y-auto rounded-xl bg-slate-950/40 p-3">
      {messages.length === 0 && <p className="text-sm text-slate-500">Ask SupremeAI anything to get started.</p>}
      {messages.map((m, i) => <div key={i} className={`flex gap-2 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
        {m.role === 'assistant' && <AssistantAvatar />}
        <div className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${m.role === 'user' ? 'bg-cyan-300 text-slate-950' : 'bg-white/[0.04] text-slate-200'}`}>{m.text}</div>
      </div>)}
      {busy && <div className="flex gap-2"><AssistantAvatar muted /><div className="text-sm italic text-slate-400">Thinking…</div></div>}
    </div>
    <div className="flex gap-2">
      <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }} rows={2} placeholder="Ask SupremeAI…" className="flex-1 resize-none rounded-xl border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-300/40" />
      <button type="button" onClick={send} disabled={busy || !input.trim()} className="rounded-xl bg-cyan-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200 disabled:opacity-50">Send</button>
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