import React, { useState } from 'react';

export const MainLayout = ({ children }: { children: React.ReactNode }) => {
  const [isProMode, setIsProMode] = useState(false);

  return (
    <div className="h-screen bg-slate-950 text-white flex flex-col">
      {/* Top Header */}
      <header className="p-4 border-b border-white/10 flex justify-between items-center bg-black/50 backdrop-blur-sm z-10">
        <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
          SupremeAI
        </h1>
        <button
          onClick={() => setIsProMode(!isProMode)}
          className="text-xs bg-white/5 px-4 py-1.5 rounded-full border border-white/10 hover:bg-white/10 transition-all duration-300 ease-in-out font-medium"
        >
          {isProMode ? "Switch to Simple View" : "Developer Mode"}
        </button>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 flex overflow-hidden relative">
        {/* Chat Panel */}
        <div
          className={`h-full transition-all duration-500 ease-in-out ${
            isProMode ? 'w-1/3 border-r border-white/10' : 'w-full max-w-4xl mx-auto'
          }`}
        >
          {children}
        </div>

        {/* Pro Mode: Browser & Terminal (Glassmorphism) */}
        {isProMode && (
          <aside className="w-2/3 bg-white/[0.02] backdrop-blur-[12px] p-4 flex flex-col gap-4 animate-in fade-in slide-in-from-right-8 duration-500">
            {/* Browser View */}
            <div className="flex-1 bg-black/40 rounded-xl border border-white/10 overflow-hidden shadow-2xl flex flex-col">
              <div className="h-8 border-b border-white/10 bg-black/60 flex items-center px-4 gap-2">
                <div className="flex gap-1.5">
                  <div className="w-3 h-3 rounded-full bg-red-500/80"></div>
                  <div className="w-3 h-3 rounded-full bg-yellow-500/80"></div>
                  <div className="w-3 h-3 rounded-full bg-green-500/80"></div>
                </div>
                <div className="mx-auto text-[10px] text-gray-500 font-mono">Browser Preview</div>
              </div>
              <div className="flex-1 flex items-center justify-center text-gray-600 font-mono text-sm">
                Live Browser Feed...
              </div>
            </div>

            {/* Terminal Output */}
            <div className="h-1/3 bg-black/60 rounded-xl border border-white/10 p-3 font-mono text-xs shadow-2xl overflow-hidden flex flex-col">
              <div className="text-gray-500 mb-2 border-b border-white/5 pb-1">~/supremeai-core</div>
              <div className="flex-1 overflow-y-auto text-green-400/80 space-y-1">
                <div>$ tail -f core_system.log</div>
                <div>[INFO] System initialized.</div>
                <div>[INFO] Waiting for agent commands...</div>
              </div>
            </div>
          </aside>
        )}
      </main>
    </div>
  );
};
