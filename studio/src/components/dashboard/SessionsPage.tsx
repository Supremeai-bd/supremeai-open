// বাংলা মন্তব্য: Devin-স্টাইল হোম — নতুন সেশন কম্পোজার ও সেশন তালিকা; ব্যাকএন্ড /task/execute দিয়ে AI রেসপন্স আনা হয়
import { useState, useEffect } from 'react';
import { Send, Trash2, CircleDot, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { getAethelResponse } from '../../services/chatService';
import {
  type DashboardSession,
  loadSessions,
  createSession,
  upsertSession,
  deleteSession,
} from './sessionStore';

interface SessionsPageProps {
  onOpenSession: (id: string) => void;
}

const statusIcon = (status: DashboardSession['status']) => {
  if (status === 'running') return <CircleDot size={14} className="text-blue-400 animate-pulse" />;
  if (status === 'finished') return <CheckCircle2 size={14} className="text-emerald-400" />;
  return <XCircle size={14} className="text-rose-400" />;
};

export function SessionsPage({ onOpenSession }: SessionsPageProps) {
  const [sessions, setSessions] = useState<DashboardSession[]>([]);
  const [prompt, setPrompt] = useState('');
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    // বাংলা মন্তব্য: loadSessions() এখন async — ব্যাকএন্ড API কল করে
    loadSessions().then(setSessions);
  }, []);

  // বাংলা মন্তব্য: নতুন সেশন শুরু — প্রম্পট থেকে সেশন তৈরি করে ব্যাকএন্ডে টাস্ক পাঠানো হয়
  const handleStartSession = async () => {
    if (!prompt.trim() || starting) return;
    setStarting(true);
    const session = createSession(prompt.trim());
    const updated = await upsertSession(session);
    setSessions(updated);
    setPrompt('');
    onOpenSession(session.id);

    // বাংলা মন্তব্য: রেসপন্স আসার পর ব্যাকএন্ড থেকে সর্বশেষ সেশন পড়ে তার উপর মেসেজ যোগ করা হয়,
    // যাতে ডিটেইল পেজে পাঠানো ফলো-আপ মেসেজ হারিয়ে না যায় (race condition প্রতিরোধ)
    let completed: DashboardSession;
    try {
      const responseText = await getAethelResponse(session.title, [
        { role: 'user', content: session.messages[0].text },
      ]);
      const allSessions = await loadSessions();
      const latest = allSessions.find((s) => s.id === session.id) || session;
      completed = {
        ...latest,
        status: 'finished',
        messages: [
          ...latest.messages,
          {
            id: Date.now(),
            sender: 'SupremeAI',
            text: responseText,
            timestamp: new Date().toLocaleTimeString(),
          },
        ],
      };
    } catch (error) {
      const allSessions = await loadSessions();
      const latest = allSessions.find((s) => s.id === session.id) || session;
      completed = {
        ...latest,
        status: 'error',
        messages: [
          ...latest.messages,
          {
            id: Date.now(),
            sender: 'SupremeAI',
            text: `AI backend error: ${error instanceof Error ? error.message : 'Unable to process task.'}`,
            timestamp: new Date().toLocaleTimeString(),
          },
        ],
      };
    }
    const finalSessions = await upsertSession(completed);
    setSessions(finalSessions);
    setStarting(false);
  };

  const handleDelete = async (id: string) => {
    const remaining = await deleteSession(id);
    setSessions(remaining);
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-10">
      <h1 className="text-2xl font-semibold text-white text-center mb-6">
        What do you want to build today?
      </h1>

      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3 mb-10 focus-within:border-blue-500/50 transition-colors">
        <textarea
          data-testid="session-composer"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleStartSession();
            }
          }}
          placeholder="Give SupremeAI a task to work on..."
          rows={3}
          className="w-full bg-transparent text-sm text-white placeholder-slate-500 outline-none resize-none"
        />
        <div className="flex justify-end">
          <button
            data-testid="start-session-btn"
            onClick={handleStartSession}
            disabled={!prompt.trim() || starting}
            className="flex items-center gap-2 px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-400 text-white text-xs font-medium transition-colors"
          >
            <Send size={12} />
            {starting ? 'Starting…' : 'Start Session'}
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-medium text-slate-300">Recent sessions</h2>
        <span className="text-xs text-slate-400">{sessions.length} total</span>
      </div>

      {sessions.length === 0 ? (
        <p className="text-sm text-slate-400 text-center py-10">
          No sessions yet. Start your first task above.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {sessions.map((session) => (
            <li
              key={session.id}
              data-testid="session-row"
              className="group flex items-center gap-3 p-3 rounded-lg border border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.05] cursor-pointer transition-colors"
              onClick={() => onOpenSession(session.id)}
            >
              {statusIcon(session.status)}
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white truncate">{session.title}</p>
                <p className="text-[11px] text-slate-400 flex items-center gap-1">
                  <Clock size={10} />
                  {new Date(session.updated_at).toLocaleString()}
                </p>
              </div>
              <button
                aria-label="Delete session"
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete(session.id);
                }}
                className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-rose-400 transition-all"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
