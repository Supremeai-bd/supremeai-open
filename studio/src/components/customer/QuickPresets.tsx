import { useState } from 'react';

interface Preset {
  id: string;
  title: string;
  description: string;
  prompt: string;
  category: 'code' | 'translate' | 'write' | 'debug' | 'explain' | 'data';
}

const PRESETS: Preset[] = [
  // Code category
  { id: 'code-py', title: 'Python Algorithm', description: 'Generate a Python binary search algorithm', prompt: 'Write a Python binary search algorithm with O(log n) complexity', category: 'code' },
  { id: 'code-js', title: 'JS Function', description: 'Generate a JavaScript utility function', prompt: 'Write a JavaScript function to debounce a callback with configurable delay', category: 'code' },
  { id: 'code-react', title: 'React Component', description: 'Generate a React hook or component', prompt: 'Write a React custom hook called useLocalStorage for persisting state to localStorage', category: 'code' },

  // Translate category
  { id: 'trans-bn', title: '→ বাংলা', description: 'Translate English to Bengali', prompt: "Translate the following to Bengali: 'Welcome to SupremeAI Studio'", category: 'translate' },
  { id: 'trans-es', title: '→ Español', description: 'Translate English to Spanish', prompt: "Translate the following to Spanish: 'Welcome to SupremeAI Studio'", category: 'translate' },

  // Write category
  { id: 'write-email', title: 'Marketing Email', description: 'Draft a startup marketing email', prompt: 'Write a professional marketing email for an AI-powered SaaS startup launch', category: 'write' },
  { id: 'write-blog', title: 'Blog Post', description: 'Outline a technical blog post', prompt: 'Write an outline for a blog post about building scalable AI microservices', category: 'write' },

  // Debug category
  { id: 'debug-err', title: 'Error Explainer', description: 'Debug an error message', prompt: 'Explain this error and suggest a fix: TypeError: Cannot read property map of undefined', category: 'debug' },

  // Explain category
  { id: 'explain-code', title: 'Code Explainer', description: 'Explain any code snippet', prompt: 'Explain how the JavaScript event loop works with a simple code example', category: 'explain' },
];

interface QuickPresetsProps {
  onSelectPreset: (prompt: string) => void;
}

const CATEGORY_LABELS: Record<string, { icon: string; label: string; bnLabel: string }> = {
  code: { icon: '💻', label: 'Code', bnLabel: 'কোড' },
  translate: { icon: '🌐', label: 'Translate', bnLabel: 'অনুবাদ' },
  write: { icon: '✍️', label: 'Write', bnLabel: 'লেখা' },
  debug: { icon: '🐛', label: 'Debug', bnLabel: 'ডিবাগ' },
  explain: { icon: '📖', label: 'Explain', bnLabel: 'ব্যাখ্যা' },
  data: { icon: '📊', label: 'Data', bnLabel: 'ডেটা' },
};

export function QuickPresets({ onSelectPreset }: QuickPresetsProps) {
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  const categories = [...new Set(PRESETS.map(p => p.category))];

  const filteredPresets = PRESETS.filter(p => {
    const matchesSearch = search === '' ||
      p.title.toLowerCase().includes(search.toLowerCase()) ||
      p.description.toLowerCase().includes(search.toLowerCase()) ||
      p.prompt.toLowerCase().includes(search.toLowerCase());
    const matchesCategory = activeCategory === null || p.category === activeCategory;
    return matchesSearch && matchesCategory;
  });

  return (
    <div className="w-72 flex-shrink-0 bg-[#08090d]/60 backdrop-blur-lg border-r border-[rgba(138,92,246,0.15)] flex flex-col p-4 z-10">
      <div className="text-[11px] uppercase tracking-[2px] text-[#bc13fe] font-semibold mb-3">
        Quick Presets • দ্রুত প্রিসেট
      </div>

      {/* Search input */}
      <div className="mb-3">
        <input
          type="text"
          placeholder="Search presets... সার্চ করুন..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full bg-[#0c0d13] border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white placeholder-slate-500 outline-none focus:border-[#bc13fe]/50 transition-colors"
        />
      </div>

      {/* Category filter chips */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        <button
          onClick={() => setActiveCategory(null)}
          className={`text-[10px] px-2 py-1 rounded-full border transition-all ${
            activeCategory === null
              ? 'bg-[#bc13fe]/20 border-[#bc13fe]/50 text-[#bc13fe]'
              : 'border-slate-700 text-slate-400 hover:text-white'
          }`}
        >
          All
        </button>
        {categories.map(cat => {
          const info = CATEGORY_LABELS[cat];
          return (
            <button
              key={cat}
              onClick={() => setActiveCategory(activeCategory === cat ? null : cat)}
              className={`text-[10px] px-2 py-1 rounded-full border transition-all ${
                activeCategory === cat
                  ? 'bg-[#bc13fe]/20 border-[#bc13fe]/50 text-[#bc13fe]'
                  : 'border-slate-700 text-slate-400 hover:text-white'
              }`}
            >
              {info?.icon} {info?.label}
            </button>
          );
        })}
      </div>

      {/* Preset cards */}
      <div className="flex-grow overflow-y-auto flex flex-col gap-2">
        {filteredPresets.length === 0 ? (
          <div className="text-xs text-slate-500 text-center py-6">
            No presets match your search.
          </div>
        ) : (
          filteredPresets.map(preset => {
            const catInfo = CATEGORY_LABELS[preset.category];
            return (
              <div
                key={preset.id}
                onClick={() => onSelectPreset(preset.prompt)}
                className="bg-white/[0.02] border border-white/[0.04] rounded-lg p-2.5 text-xs cursor-pointer hover:border-[#bc13fe]/30 hover:bg-[#bc13fe]/5 transition-all duration-300"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px]">{catInfo?.icon || '📌'}</span>
                  <strong className="text-[#f8f9fa] block">{preset.title}</strong>
                </div>
                <span className="text-slate-400 text-[10px] block ml-5">{preset.description}</span>
              </div>
            );
          })
        )}
      </div>

      <div className="mt-4 p-3 bg-[#bc13fe]/5 border border-[#bc13fe]/20 rounded-lg flex items-center gap-3">
        <span className="w-2.5 h-2.5 rounded-full bg-[#bc13fe] animate-pulse"></span>
        <span className="text-xs font-semibold text-slate-300">Operator Core Ready</span>
      </div>
    </div>
  );
}

