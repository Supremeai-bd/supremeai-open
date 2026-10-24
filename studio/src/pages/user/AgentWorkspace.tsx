import React, { useEffect, useRef, useState } from 'react';
import Editor from '@monaco-editor/react';
import type { Terminal } from 'xterm';
import type { FitAddon } from '@xterm/addon-fit';
import type { WebContainer } from '@webcontainer/api';
import 'xterm/css/xterm.css';
import { apiClient } from '../../services/apiClient';
import { BrowserPreview } from '../../components/customer/BrowserPreview';
import { Activity, Bot, ChevronRight, Eye, EyeOff, FileCode2, History, Maximize2, MessageSquare, PanelLeft, Play, Plus, Send, Settings2, TerminalSquare } from 'lucide-react';

interface Message { role: 'user' | 'agent'; content: string; source?: 'ai_api' | 'memory'; }
type Panel = 'chat' | 'terminal' | 'browser';

export const AgentWorkspace: React.FC = () => {
  const [prompt, setPrompt] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [generatedCode, setGeneratedCode] = useState('// SupremeAI Agent Ready.\n// Type a prompt to generate code...');
  const [isLoading, setIsLoading] = useState(false);
  const [isHealing, setIsHealing] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [panels, setPanels] = useState<Record<Panel, boolean>>({ chat: true, terminal: true, browser: true });
  const [agentPaused, setAgentPaused] = useState(false);
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<Terminal | null>(null);
  const webcontainerRef = useRef<WebContainer | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, isLoading]);

  useEffect(() => {
    let disposed = false;
    // FIX (P1, review 2026-09-12): the window 'resize' listener was registered
    // inside async init() and its cleanup function was DISCARDED by the caller —
    // the listener (closing over xterm/fit) leaked after unmount and re-fit on
    // disposed terminals. Track it in a ref-accessible variable and remove it in
    // the effect's real cleanup, with disposed-guards on every assignment.
    let resizeHandler: (() => void) | null = null;
    const init = async () => {
      if (!terminalRef.current || xtermRef.current) return;
      const { Terminal } = await import('xterm');
      const { FitAddon } = await import('@xterm/addon-fit');
      const term = new Terminal({ theme: { background: '#111318', foreground: '#cbd5e1', cursor: '#a7f3d0' }, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 12, cursorBlink: true });
      const fit = new FitAddon(); term.loadAddon(fit); term.open(terminalRef.current); fit.fit();
      if (disposed) { term.dispose(); return; }
      xtermRef.current = term; fitAddonRef.current = fit;
      term.writeln('SupremeAI agent runtime initializing...');
      term.writeln('Workspace ready. Waiting for commands.');
      if (window.crossOriginIsolated) {
        try {
          const { WebContainer } = await import('@webcontainer/api');
          const instance = await WebContainer.boot();
          if (!disposed) { webcontainerRef.current = instance; term.writeln('\r\n[system] WebContainer booted successfully.'); }
        } catch { term.writeln('\r\n[system] Browser sandbox could not start.'); }
      } else term.writeln('\r\n[system] Sandbox unavailable in this preview.');
      resizeHandler = () => { if (!disposed && xtermRef.current) fit.fit(); };
      window.addEventListener('resize', resizeHandler);
    };
    void init();
    return () => {
      disposed = true;
      if (resizeHandler) window.removeEventListener('resize', resizeHandler);
      xtermRef.current?.dispose(); xtermRef.current = null; void webcontainerRef.current?.teardown(); webcontainerRef.current = null;
    };
  }, []);

  const handleExecute = async () => {
    if (!prompt.trim() || isLoading || agentPaused) return;
    const trimmed = prompt.trim();
    const next = [...messages, { role: 'user' as const, content: prompt }]; setMessages(next); setPrompt(''); setIsLoading(true);
    // ফিক্স (ERR-A01 guard, defect register 2026-09-15): backend AgentTaskRequest enforces
    // prompt min_length=10 — fail fast in the UI with an actionable message instead of a deterministic 422.
    if (trimmed.length < 10) {
      setMessages([...next, { role: 'agent', content: 'Please add a bit more detail — the agent needs at least 10 characters to execute a task.', source: 'ai_api' }]);
      setIsLoading(false);
      return;
    }
    try {
      // ফিক্স (ERR-A01): backend AgentTaskRequest requires task_id — আগে { prompt, project_id }
      // পাঠানো হতো, তাই প্রতিটি execution 422 দিত। এখন সম্পূর্ণ contract অনুযায়ী payload।
      const data = (await apiClient.post<Record<string, unknown>>('/api/v1/agents/execute', { task_id: crypto.randomUUID(), prompt: trimmed, auto_execute: false }) || {}) as Record<string, unknown>;
      setMessages([...next, { role: 'agent', content: (data.result as string) || (data.message as string) || 'Agent completed the request.', source: 'ai_api' }]);
      if (typeof data.code === 'string') setGeneratedCode(data.code);
    } catch { setMessages([...next, { role: 'agent', content: 'Connection error to SupremeAI Backend.' }]); }
    finally { setIsLoading(false); }
  };

  const togglePanel = (panel: Panel) => setPanels(value => ({ ...value, [panel]: !value[panel] }));
  // ERR-G10 FIX (2026-09-16): runCode used to fake execution with a 700ms
  // setTimeout ("Evaluation queued.") without running anything. It now runs
  // the editor's code in the booted WebContainer for real and streams process
  // output into the terminal; when the sandbox is unavailable it says so
  // explicitly instead of pretending success.
  const runCode = async () => {
    if (isHealing) return;
    const term = xtermRef.current;
    const container = webcontainerRef.current;
    setIsHealing(true);
    try {
      if (!container || !term) {
        term?.writeln('\r\n[execution] NOT RUN: the browser code-execution sandbox (WebContainer) is unavailable in this preview — no evaluation was performed.');
        return;
      }
      term.writeln('\r\n[execution] Writing current file to the sandbox...');
      await container.fs.writeFile('/index.js', generatedCode);
      const proc = await container.spawn('jsh', ['-c', 'node index.js']);
      void proc.output.pipeTo(new WritableStream<string>({ write: data => term.write(data) }));
      const exit = await proc.exit;
      term.writeln(exit === 0 ? '\r\n[execution] Process finished (exit 0).' : `\r\n[execution] Process finished (exit ${exit}).`);
    } catch (error) {
      term?.writeln(`\r\n[execution] FAILED: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setIsHealing(false);
    }
  };

  return (
    <div className="flex min-h-0 w-full flex-1 overflow-hidden bg-[#0d0f12] text-slate-100">
      <aside className={`${historyOpen ? 'w-64' : 'w-14'} flex shrink-0 flex-col border-r border-white/[0.08] bg-[#111318] transition-[width] duration-300 max-md:absolute max-md:inset-y-0 max-md:left-0 max-md:z-30 max-md:shadow-2xl max-md:shadow-cyan-500/10`}>
        <div className="flex h-14 items-center justify-between border-b border-white/[0.08] px-3"><button className="rounded-lg p-2 text-slate-400 transition hover:bg-cyan-400/10 hover:text-cyan-200 hover:shadow-[0_0_16px_rgba(34,211,238,0.2)]" aria-label="Toggle session history" onClick={() => setHistoryOpen(!historyOpen)}>{historyOpen ? <PanelLeft size={17} /> : <ChevronRight size={17} />}</button>{historyOpen && <button className="rounded-lg p-2 text-slate-400 hover:bg-white/[0.06] hover:text-white" aria-label="New session"><Plus size={17} /></button>}</div>
        {historyOpen && <><div className="border-b border-white/[0.08] p-3"><button className="flex w-full items-center gap-2 rounded-lg bg-emerald-400 px-3 py-2 text-left text-xs font-semibold text-slate-950"><Plus size={14} /> New session</button></div><div className="flex-1 overflow-y-auto p-3"><div className="mb-3 flex items-center gap-2 px-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500"><History size={12} /> Session history</div><div className="rounded-lg border border-dashed border-white/[0.1] p-3 text-[11px] leading-relaxed text-slate-500">No sessions yet. Your completed agent runs will appear here.</div></div><div className="border-t border-white/[0.08] p-3"><button className="flex w-full items-center gap-2 rounded-lg p-2 text-xs text-slate-400 hover:bg-white/[0.06] hover:text-white"><Settings2 size={14} /> Workspace settings</button></div></>}
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-white/[0.08] px-4"><div className="flex items-center gap-3"><div className="flex size-8 items-center justify-center rounded-lg bg-emerald-400/15 text-emerald-300"><Bot size={18} /></div><div><div className="text-sm font-semibold">SupremeAI Agent</div><div className="flex items-center gap-1.5 text-[10px] text-slate-500"><span className={`size-1.5 rounded-full ${agentPaused ? 'bg-amber-400' : 'bg-emerald-400'}`} /> {agentPaused ? 'Paused · manual browser control enabled' : 'Ready'}</div></div></div><div className="flex items-center gap-1 rounded-lg border border-white/[0.08] bg-white/[0.03] p-1"><button onClick={() => setAgentPaused(value => !value)} className={`rounded-md px-2.5 py-1.5 text-[11px] font-medium transition ${agentPaused ? 'bg-amber-400/15 text-amber-200' : 'text-slate-400 hover:bg-white/[0.06] hover:text-white'}`} aria-pressed={agentPaused}>{agentPaused ? 'Resume agent' : 'Pause agent'}</button>{(['chat', 'terminal', 'browser'] as Panel[]).map(panel => <button key={panel} onClick={() => togglePanel(panel)} className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] capitalize transition-all ${panels[panel] ? 'bg-emerald-400/15 text-emerald-200 shadow-[0_0_14px_rgba(52,211,153,0.18)]' : 'text-slate-500 hover:bg-cyan-400/10 hover:text-cyan-200 hover:shadow-[0_0_14px_rgba(34,211,238,0.16)]'}`} aria-label={`${panels[panel] ? 'Hide' : 'Show'} ${panel}`} title={`${panels[panel] ? 'Hide' : 'Show'} ${panel}`}><span>{panel === 'chat' ? <MessageSquare size={13} /> : panel === 'terminal' ? <TerminalSquare size={13} /> : <Eye size={13} />}</span>{panel}</button>)}</div></header>

        <div className={`grid min-h-0 flex-1 gap-3 overflow-auto p-3 max-lg:flex max-lg:flex-col max-lg:overflow-y-auto ${Object.values(panels).filter(Boolean).length === 1 ? 'grid-cols-1' : Object.values(panels).filter(Boolean).length === 2 ? 'grid-cols-2 max-xl:grid-cols-1' : 'grid-cols-[minmax(240px,1fr)_minmax(320px,1.35fr)_minmax(280px,1fr)] max-2xl:grid-cols-[minmax(220px,0.9fr)_minmax(300px,1.2fr)_minmax(260px,0.9fr)] max-xl:grid-cols-[minmax(280px,1fr)_minmax(320px,1.15fr)]'}`}>
          {panels.chat && <section className="flex min-h-[320px] min-w-0 flex-col overflow-hidden rounded-xl border border-white/[0.08] bg-[#111318]"><div className="flex items-center justify-between border-b border-white/[0.08] px-4 py-3"><div className="flex items-center gap-2 text-xs font-semibold"><MessageSquare size={15} className="text-emerald-300" /> Agent chat</div><button onClick={() => togglePanel('chat')} className="text-slate-500 hover:text-white" aria-label="Hide chat"><EyeOff size={14} /></button></div><div className="flex-1 overflow-y-auto p-4"><div className="mb-5 rounded-lg border border-emerald-400/15 bg-emerald-400/[0.04] p-3 text-xs leading-relaxed text-slate-300"><span className="font-medium text-emerald-300">Agent plan</span><p className="mt-1">I’ll inspect the codebase, check for security issues, and report actionable findings.</p></div><div className="flex flex-col gap-3">{messages.map((msg, index) => <div key={index} className={`max-w-[92%] rounded-lg p-3 text-xs leading-relaxed ${msg.role === 'user' ? 'ml-auto bg-slate-700 text-white' : 'bg-white/[0.06] text-slate-300'}`}>{msg.content}</div>)}{isLoading && <div className="text-xs text-slate-500">Agent is thinking...</div>}<div ref={messagesEndRef} aria-hidden="true" /></div></div><div className="border-t border-white/[0.08] p-3"><textarea value={prompt} onChange={event => setPrompt(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); void handleExecute(); } }} placeholder="Ask the agent anything..." rows={3} className="w-full resize-none rounded-lg border border-white/[0.1] bg-[#0c0e11] p-3 text-xs text-white outline-none placeholder:text-slate-600 focus:border-emerald-400/50" /><div className="mt-2 flex items-center justify-between"><span className="text-[10px] text-slate-600">Enter to send · Shift+Enter for new line</span><button onClick={() => void handleExecute()} disabled={!prompt.trim() || isLoading} className="flex size-8 items-center justify-center rounded-lg bg-emerald-400 text-slate-950 transition hover:bg-emerald-300 disabled:opacity-40" aria-label="Send message"><Send size={14} /></button></div></div></section>}

          <section className="flex min-h-[420px] min-w-0 flex-col gap-3 overflow-hidden"><div className="flex min-h-[260px] flex-1 flex-col overflow-hidden rounded-xl border border-white/[0.08] bg-[#111318]"><div className="flex items-center justify-between border-b border-white/[0.08] px-4 py-3"><div className="flex items-center gap-2 text-xs font-semibold"><FileCode2 size={15} className="text-sky-300" /> Generated workspace <span className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-slate-500">index.js</span></div><button onClick={() => void runCode()} disabled={isHealing} className="flex items-center gap-1.5 rounded-md bg-emerald-400/15 px-2.5 py-1.5 text-[11px] font-medium text-emerald-300 hover:bg-emerald-400/25 disabled:opacity-40"><Play size={12} /> {isHealing ? 'Running...' : 'Run & evaluate'}</button></div><div className="min-h-0 flex-1"><Editor height="100%" theme="vs-dark" defaultLanguage="javascript" value={generatedCode} onChange={value => setGeneratedCode(value || '')} options={{ minimap: { enabled: false }, fontSize: 12, padding: { top: 14 } }} /></div></div>{panels.terminal && <div className="flex h-44 shrink-0 flex-col overflow-hidden rounded-xl border border-white/[0.08] bg-[#111318]"><div className="flex items-center justify-between border-b border-white/[0.08] px-4 py-2.5"><div className="flex items-center gap-2 text-xs font-semibold"><TerminalSquare size={14} className="text-amber-300" /> Terminal</div><button onClick={() => togglePanel('terminal')} className="text-slate-500 hover:text-white" aria-label="Hide terminal"><EyeOff size={14} /></button></div><div ref={terminalRef} className="min-h-0 flex-1 p-2" /></div>}</section>

          {panels.browser && <section className="flex min-h-[360px] min-w-0 flex-col overflow-hidden rounded-xl border border-white/[0.08] bg-[#111318] xl:flex"><div className="flex items-center justify-between border-b border-white/[0.08] px-4 py-3"><div className="flex items-center gap-2 text-xs font-semibold"><Activity size={15} className="text-cyan-300" /> Live browser</div><div className="flex items-center gap-2"><button className="text-slate-500 hover:text-white" aria-label="Maximize browser"><Maximize2 size={14} /></button><button onClick={() => togglePanel('browser')} className="text-slate-500 hover:text-white" aria-label="Hide browser"><EyeOff size={14} /></button></div></div><div className="min-h-0 flex-1 p-2"><BrowserPreview showDeviceToolbar={false} agentPaused={agentPaused} onAgentPauseToggle={() => setAgentPaused(value => !value)} /></div></section>}
        </div>
      </main>
    </div>
  );
};
