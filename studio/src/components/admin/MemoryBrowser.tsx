/* eslint-disable @typescript-eslint/no-explicit-any */
import { useQuery } from '@tanstack/react-query';
import { Card, Badge, Skeleton } from '../ui';
import { Search, MessageSquare, Clock, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { apiClient } from '../../services/apiClient';

// #1823 (conversation-history split-brain): MemoryBrowser now reads the SAME
// source of truth the chat flow writes — ai_memory (pgvector) — via the
// /api/v1/conversations read-projection. The retired Firestore-backed
// /api/memory/conversations endpoint surfaced phantom empty histories.
interface ConversationSummary {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

interface TurnMessage {
  role: string;
  content: string;
  created_at?: string | null;
}

export function MemoryBrowser() {
  const { data: conversations, isLoading } = useQuery({
    queryKey: ['conversations'],
    queryFn: () => apiClient.get<any[]>('/api/v1/conversations/'),
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedConv, setSelectedConv] = useState<ConversationSummary | null>(null);
  const [messages, setMessages] = useState<TurnMessage[] | null>(null);
  const [messagesLoading, setMessagesLoading] = useState(false);

  // Fetch the selected session's turns from the same projection (detail view).
  useEffect(() => {
    if (!selectedConv) return;
    let cancelled = false;
    setMessagesLoading(true);
    setMessages(null);
    apiClient
      .get<TurnMessage[]>(`/api/v1/conversations/${encodeURIComponent(selectedConv.id)}/messages`)
      .then((rows) => {
        if (!cancelled) setMessages(Array.isArray(rows) ? rows : []);
      })
      .catch(() => {
        if (!cancelled) setMessages([]);
      })
      .finally(() => {
        if (!cancelled) setMessagesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedConv]);

  const filtered = (Array.isArray(conversations) ? conversations : [])?.filter((c: ConversationSummary) =>
    (c.title ?? '').toLowerCase().includes(searchQuery.toLowerCase())
  ) || [];

  return (
    <div className="flex-grow p-6 overflow-y-auto bg-[#030611]">
      <div className="flex items-center justify-between mb-6 pb-2 border-b border-[#00f3ff]/15">
        <h2 className="text-lg font-bold font-['Space_Grotesk'] tracking-widest text-[#00f3ff] uppercase">
          🧠 Memory & Knowledge
        </h2>
        <Badge variant="purple">RAG ENABLED</Badge>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-1">
          <div className="flex gap-2 mb-4">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-2 text-slate-400" />
              <input
                type="text"
                placeholder="Search conversations..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="w-full bg-[#06080b] border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-white outline-none focus:border-[#00f3ff] font-mono"
              />
            </div>
          </div>

          <div className="flex flex-col gap-2 max-h-[60vh] overflow-y-auto">
            {isLoading ? (
              <><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-full" /></>
            ) : filtered.length === 0 ? (
              <div className="text-xs text-slate-400 font-mono p-4 text-center">No conversations found.</div>
            ) : (
              filtered.map((conv: ConversationSummary) => (
                <button
                  key={conv.id}
                  onClick={() => setSelectedConv(conv)}
                  className={`text-left p-3 rounded-lg border transition-all ${
                    selectedConv?.id === conv.id
                      ? 'border-[#00f3ff]/50 bg-[#00f3ff]/10'
                      : 'border-slate-800 bg-slate-900/30 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-bold text-white font-mono truncate">{conv.title || conv.id}</span>
                    <span className="text-[9px] text-slate-400 font-mono shrink-0 ml-2">{conv.updated_at}</span>
                  </div>
                  <div className="text-[10px] text-slate-400 font-mono">{conv.message_count} exchange(s)</div>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="xl:col-span-2">
          {selectedConv ? (
            <Card title={`Session: ${selectedConv.title || selectedConv.id}`}>
              <div className="text-[10px] text-slate-400 mb-3 font-mono flex items-center gap-3">
                <span className="flex items-center gap-1"><Clock size={10} /> {selectedConv.updated_at}</span>
                <span className="flex items-center gap-1"><MessageSquare size={10} /> {selectedConv.message_count} turns</span>
              </div>
              {messagesLoading ? (
                <div className="flex flex-col gap-3">
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                </div>
              ) : (messages?.length ?? 0) === 0 ? (
                <div className="text-xs text-slate-400 font-mono p-4 text-center">No messages stored for this session.</div>
              ) : (
                <div className="flex flex-col gap-3">
                  {messages!.map((m, i) => (
                    <div key={i} className={`p-3 rounded-lg border text-xs font-mono ${
                      m.role === 'user' ? 'border-[#00f3ff]/30 bg-[#00f3ff]/5 text-white' : 'border-slate-800 bg-slate-900/30 text-slate-400'
                    }`}>
                      <div className="text-[9px] text-slate-400 mb-1 uppercase">{m.role}</div>
                      {m.content}
                    </div>
                  ))}
                </div>
              )}
              <div className="flex justify-between items-center mt-4 pt-3 border-t border-slate-800">
                <div className="text-[10px] text-slate-400">Session: <span className="text-emerald-400 font-mono">{selectedConv.id}</span></div>
                <div className="flex gap-2">
                  <button className="text-[10px] text-slate-400 hover:text-white font-mono">Export</button>
                  <button className="text-[10px] text-red-400 hover:text-red-300 font-mono flex items-center gap-1"><Trash2 size={10} /> Purge</button>
                </div>
              </div>
            </Card>
          ) : (
            <div className="h-full flex items-center justify-center p-8 border border-dashed border-slate-800 rounded-xl">
              <div className="text-center">
                <MessageSquare size={32} className="mx-auto text-slate-700 mb-3" />
                <div className="text-xs text-slate-400 font-mono">Select a conversation to view details</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
