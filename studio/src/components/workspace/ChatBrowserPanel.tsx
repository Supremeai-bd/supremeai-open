import React, { useState } from 'react';
import { Send, Terminal, AlertTriangle, Wrench } from 'lucide-react';
import type { BrowserController } from '../browser/useBrowserController';

export interface ConsoleErrorAlert {
  id?: string;
  message: string;
  source?: string;
}

export interface ChatBrowserPanelProps {
  controller?: BrowserController;
  onNavigate?: (url: string) => void;
  inspectTag?: string | null;
  onClearInspect?: () => void;
  consoleErrors?: ConsoleErrorAlert[];
  onFixError?: (err: ConsoleErrorAlert) => void;
  className?: string;
}

interface Msg { role: 'user' | 'assistant'; text: string }

function parseNavCommand(input: string): string | null {
  const t = input.trim();
  const m1 = t.match(/^\/?navigate\s+(.+)$/i);
  if (m1) return m1[1].trim();
  const m2 = t.match(/agent:navigate\(([^)]+)\)/i);
  if (m2) return m2[1].trim().replace(/^['"]|['"]$/g, '');
  const m3 = t.match(/^go to\s+(.+)$/i);
  if (m3) return m3[1].trim();
  return null;
}

export const ChatBrowserPanel: React.FC<ChatBrowserPanelProps> = (props) => {
  const [messages, setMessages] = useState<Msg[]>([
    { role: 'assistant', text: 'Hi, I am Jerbez. I can navigate, inspect, and fix errors. Try "/navigate supremeai.dev".' },
  ]);
  const [input, setInput] = useState('');

  const doNavigate = (url: string) => {
    if (props.controller) props.controller.navigate(url);
    props.onNavigate?.(url);
  };

  const send = () => {
    const text = input.trim();
    if (!text) return;
    const nav = parseNavCommand(text);
    if (nav) {
      setMessages((m) => [...m, { role: 'user', text }, { role: 'assistant', text: `Navigating to ${nav}...` }]);
      doNavigate(nav);
      setInput('');
      return;
    }
    const finalText = props.inspectTag ? `${props.inspectTag}\n${text}` : text;
    setMessages((m) => [...m, { role: 'user', text: finalText }, { role: 'assistant', text: 'Working on it...' }]);
    setInput('');
  };

  return (
    <div className={`flex flex-col h-full bg-[#0d1117] ${props.className ?? ''}`}>
      <div className="flex-1 overflow-auto p-3 space-y-3">
        {messages.map((m, i) => (
          <div key={i} className={`text-sm ${m.role === 'user' ? 'text-cyan-200' : 'text-slate-200'}`}>
            <span className="font-semibold mr-1">{m.role === 'user' ? 'You' : 'Jerbez'}:</span>
            <span className="whitespace-pre-wrap">{m.text}</span>
          </div>
        ))}
        {(props.consoleErrors ?? []).length > 0 && (
          <div className="space-y-2">
            {(props.consoleErrors ?? []).map((err, i) => (
              <div key={i} className="flex items-center gap-2 p-2 bg-red-900/30 border border-red-700 rounded text-xs text-red-200">
                <AlertTriangle size={14} />
                <span className="flex-1 truncate">{err.message}</span>
                <button
                  onClick={() => props.onFixError?.(err)}
                  className="flex items-center gap-1 px-2 py-1 bg-red-600 hover:bg-red-500 rounded text-white"
                >
                  <Wrench size={12} /> Fix with AI
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="border-t border-slate-700 p-3">
        {props.inspectTag && (
          <div className="mb-2 inline-flex items-center gap-2 text-xs bg-cyan-900/40 border border-cyan-700 rounded px-2 py-1 text-cyan-200">
            <Terminal size={12} />
            {props.inspectTag}
            <button onClick={props.onClearInspect} className="ml-1 text-cyan-400 hover:text-white">x</button>
          </div>
        )}
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
            className="flex-1 bg-[#161b22] border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 outline-none"
            placeholder="Ask Jerbez or type /navigate <url>"
          />
          <button onClick={send} className="px-3 py-2 bg-cyan-600 hover:bg-cyan-500 rounded-lg text-white">
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatBrowserPanel;