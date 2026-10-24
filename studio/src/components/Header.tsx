export function Header() {
  const hostname = window.location.hostname;
  const isAdminDomain = hostname.includes('admin');

  return (
    <div className="h-14 flex-shrink-0 bg-[var(--card-bg)] backdrop-blur-md border-b border-[var(--border-color)] flex items-center justify-between px-6 z-20">
      <div className="flex items-center gap-3">
        <span className="text-2xl drop-shadow-[0_0_10px_#00f3ff]">🔱</span>
        <span className="font-bold tracking-widest text-lg font-['Space_Grotesk'] text-[var(--foreground)]">
          SUPREME<span className="text-[#00f3ff]">AI</span>
        </span>
        <span className="hidden sm:inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-cyan-950/50 text-[#00f3ff] border border-cyan-800/40">
          <span className="w-1.5 h-1.5 rounded-full bg-[#00f3ff] animate-pulse"></span>
          NEURAL LINK ACTIVE
        </span>
      </div>

      {/* Global tab switch */}
      <div className="flex bg-[var(--sidebar-bg)] rounded-lg p-1 border border-[var(--border-color)]">
        <span className={`px-4 py-1.5 text-xs font-semibold rounded-md ${isAdminDomain ? 'bg-[#bc13fe]/20 text-[#bc13fe] border border-[#bc13fe]/30' : 'bg-[#00f3ff]/20 text-[#00f3ff] border border-[#00f3ff]/30'}`}>
          {isAdminDomain ? 'God Control Center' : 'Operator Studio'}
        </span>
      </div>

      <div className="text-xs text-slate-400 font-mono hidden md:block">
        v2.0 (FastAPI Core)
      </div>
    </div>
  );
}
