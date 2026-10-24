import { QuickPresets } from './QuickPresets';
import { ChatPanel } from './ChatPanel';
import { HomeFeed } from './HomeFeed';
import { useState, lazy, Suspense } from 'react';
import type { ChatMessage } from '../../types';

// বাংলা মন্তব্য: CodeEditor (Monaco) lazy load — ইনিশিয়াল বান্ডিল থেকে সরানো হয়েছে।
const CodeEditor = lazy(() => import('./CodeEditor').then(m => ({ default: m.CodeEditor })));

interface CustomerSupportEditorStudioProps {
  code: string;
  setCode: (code: string) => void;
  customerMessages: ChatMessage[];
  customerInput: string;
  setCustomerInput: (val: string) => void;
  loading: boolean;
  handleSendCustomer: () => void;
  theme: 'dark' | 'light';
  toggleTheme: () => void;
}

export function CustomerSupportEditorStudio({
  code,
  setCode,
  customerMessages,
  customerInput,
  setCustomerInput,
  loading,
  handleSendCustomer,
  theme,
  toggleTheme
}: CustomerSupportEditorStudioProps) {
  const [currentView, setCurrentView] = useState<'presets' | 'feed'>('presets');

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex-shrink-0 p-4 border-b border-[#00f3ff]/20 flex justify-between items-center">
        <h2 className="text-xl font-bold font-['Space_Grotesk'] tracking-widest uppercase">
          Operator Studio
        </h2>
        <div className="flex items-center gap-2">
          <button
            onClick={toggleTheme}
            className="text-xs font-bold text-[#00f3ff] hover:text-cyan-400 tracking-wider transition-colors"
          >
            {theme === 'dark' ? '🌙 Light Mode' : '☀️ Dark Mode'}
          </button>
        </div>
      </div>
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        {/* Tab bar for Quick Presets and Home Feed */}
        <div className="flex-shrink-0 lg:w-64 lg:flex-shrink-0 w-full mb-4 lg:mb-0 flex items-center space-x-2 border-b border-[#00f3ff]/20 pb-2">
          <button
            onClick={() => setCurrentView('presets')}
            className={`flex-1 px-3 py-2 text-xs font-semibold rounded font-mono transition-colors ${currentView === 'presets' ? 'bg-[#00f3ff]/20 text-[#00f3ff]' : 'text-slate-400 hover:text-white'}`}
          >
            Quick Presets
          </button>
          <button
            onClick={() => setCurrentView('feed')}
            className={`flex-1 px-3 py-2 text-xs font-semibold rounded font-mono transition-colors ${currentView === 'feed' ? 'bg-[#00f3ff]/20 text-[#00f3ff]' : 'text-slate-400 hover:text-white'}`}
          >
            Home Feed
          </button>
        </div>

        {/* Content area */}
        <div className="flex-1 flex flex-col gap-4">
          {currentView === 'presets' ? (
            <div className="w-full"><QuickPresets onSelectPreset={setCustomerInput} /></div>
          ) : (
            <HomeFeed />
          )}
          <div className="flex-1"><Suspense fallback={<div className="h-64 w-full animate-pulse rounded bg-zinc-800/40" />}><CodeEditor code={code} onChange={setCode} /></Suspense></div>
          <div className="flex-1">
            <ChatPanel
              messages={customerMessages}
              input={customerInput}
              onInputChange={setCustomerInput}
              onSend={handleSendCustomer}
              loading={loading}
              onSaveToProject={setCode}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
