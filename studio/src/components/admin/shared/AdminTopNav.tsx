import React from 'react';
import { Bell, User } from 'lucide-react';

interface AdminTopNavProps {
  operatorName?: string;
  uptime?: string;
  userName?: string;
  onLogout?: () => void;
}

// বাংলা মন্তব্য: সুপ্রিমএআই ড্যাশবোর্ডের জন্য ওপরের নেভিগেশন বার (Admin Top Navigation Bar)
// এটি রেফারেন্স ইমেজ অনুযায়ী তৈরি করা হয়েছে এবং এতে লোগো, অপারেটর নেম, সিস্টেম অনলাইন ইন্ডিকেটর ও ইউজার প্রোফাইল শো করা হচ্ছে।
export const AdminTopNav: React.FC<AdminTopNavProps> = ({
  operatorName = 'UNASSIGNED',
  uptime = 'STATUS UNKNOWN',
  userName = 'OPERATOR',
  onLogout
}) => {
  return (
    <header className="flex h-16 select-none items-center justify-between border-b border-[var(--sa-border)] bg-[var(--sa-surface)] px-4 font-mono text-[var(--sa-ink)] sm:px-6">
      {/* বাম পাশ: লোগো ও অর্কেস্ট্রেশন প্ল্যাটফর্ম টেক্সট */}
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          {/* গ্লোয়িং সুপ্রিমএআই লোগো */}
          <div className="flex size-7 items-center justify-center rounded-lg bg-[var(--sa-primary)] text-xs font-black text-white shadow-[0_0_18px_rgba(34,211,238,0.35)]">
            S
          </div>
          <span className="font-sans text-lg font-semibold tracking-tight text-[var(--sa-ink)]">
            Supreme<span className="text-[var(--sa-primary)]">AI</span>
          </span>
        </div>
        <div className="hidden h-6 w-px bg-[var(--sa-border)] md:block" />
        <span className="hidden font-sans text-xs uppercase tracking-[0.15em] text-[var(--sa-ink-muted)] md:inline">
          Orchestration Platform
        </span>
      </div>

      {/* মাঝের অংশ: এআই অপারেটর ও সিস্টেম স্ট্যাটাস */}
      <div className="hidden lg:flex items-center gap-4 text-xs">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-slate-900/60 border border-slate-800 text-slate-400">
          <span>AI OPERATOR:</span>
          <span className="text-[#00f3ff] font-bold">{operatorName}</span>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-emerald-950/30 border border-emerald-500/30 text-emerald-400 font-bold shadow-[0_0_10px_rgba(16,185,129,0.1)]">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
          <span>SYSTEM ONLINE • {uptime}</span>
        </div>
      </div>

      {/* ডান পাশ: নোটিফিকেশন বেল, ইউজার ইনফো ও লগআউট বাটন */}
      <div className="flex items-center gap-4">
        {/* নোটিফিকেশন বেল */}
        <button className="relative p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-900/50 transition-all border border-transparent hover:border-slate-800">
          <Bell size={18} />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-rose-500 shadow-[0_0_8px_#f43f5e]" />
        </button>

        <div className="w-[1px] h-6 bg-slate-800" />

        {/* ইউজার কার্ড */}
        <div className="flex items-center gap-3 pl-1">
          <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center overflow-hidden">
            <User size={16} className="text-slate-300" />
          </div>
          <div className="hidden sm:block text-left font-sans">
            <div className="text-xs font-bold text-slate-200 tracking-wide">{userName}</div>
          </div>
        </div>

        {onLogout && (
          <button
            onClick={onLogout}
            className="text-[10px] font-bold text-rose-400 hover:text-rose-300 px-2 py-1 rounded border border-rose-500/20 hover:border-rose-500/40 bg-rose-500/5 hover:bg-rose-500/10 transition-all"
          >
            EXIT
          </button>
        )}
      </div>
    </header>
  );
};
