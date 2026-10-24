// Bangla comment: AI "চিন্তা করছে" অ্যানিমেশন — গ্লোয়িং বর্ডার ও টাইপিং ডটস
export function TypingIndicator() {
  return (
    <div className="flex flex-col gap-1 self-start items-start max-w-[85%]">
      <div className="flex items-center gap-2 px-4 py-2.5 rounded-2xl bg-[#0a0c14]/85 border border-[#bc13fe]/18 text-slate-200 text-xs backdrop-blur-md shadow-[0_0_14px_rgba(188,19,254,0.12)] animate-pulse-glow">
        <span className="flex gap-1 items-center">
          <span className="w-1.5 h-1.5 rounded-full bg-[#00f3ff] animate-bounce" style={{ animationDelay: '0ms' }}></span>
          <span className="w-1.5 h-1.5 rounded-full bg-[#bc13fe] animate-bounce" style={{ animationDelay: '150ms' }}></span>
          <span className="w-1.5 h-1.5 rounded-full bg-[#00f3ff] animate-bounce" style={{ animationDelay: '300ms' }}></span>
        </span>
        <span className="text-[10px] font-mono text-slate-400 ml-1">SupremeAI is thinking…</span>
      </div>
    </div>
  );
}
