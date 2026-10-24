import { useEffect, useMemo, useRef, useState } from 'react';
import { Search, Command } from 'lucide-react';
import type { CommandModuleId } from '../data/types';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Command Palette (⌘K)
// বাংলা মন্তব্য: ফাজি সার্চ সব মডিউল, অ্যাকশন, টেন্যান্ট
// ═══════════════════════════════════════════════════════════════════════════

export interface PaletteItem {
  id: string;
  label: string;
  description?: string;
  group: string;
  module?: CommandModuleId;
  action?: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  items: PaletteItem[];
  onClose: () => void;
  onSelect: (item: PaletteItem) => void;
}

export function CommandPalette({ open, items, onClose, onSelect }: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    if (!q) return items;
    return items.filter(
      (item) =>
        item.label.toLowerCase().includes(q) ||
        item.description?.toLowerCase().includes(q) ||
        item.group.toLowerCase().includes(q)
    );
  }, [items, query]);

  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      }
      if (e.key === 'Enter' && filtered[selectedIndex]) {
        onSelect(filtered[selectedIndex]);
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [open, filtered, selectedIndex, onSelect, onClose]);

  if (!open) return null;

  const groups = filtered.reduce<Record<string, PaletteItem[]>>((acc, item) => {
    (acc[item.group] = acc[item.group] || []).push(item);
    return acc;
  }, {});

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] shadow-2xl overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--sa-line)]">
          <Search size={16} className="text-[#00f3ff]" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            placeholder="মডিউল, অ্যাকশন, টেন্যান্ট খুঁজুন..."
            className="flex-1 bg-transparent text-sm font-mono text-[var(--sa-text-0)] placeholder-[var(--sa-text-2)] focus:outline-none"
          />
          <span className="flex items-center gap-1 text-[9px] font-mono text-[var(--sa-text-2)]">
            <Command size={10} /> K
          </span>
        </div>
        <div className="max-h-80 overflow-y-auto py-2">
          {Object.entries(groups).map(([group, groupItems]) => (
            <div key={group}>
              <div className="px-4 py-1 text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)]">
                {group}
              </div>
              {groupItems.map((item, _idx) => {
                const globalIdx = filtered.indexOf(item);
                return (
                  <button
                    key={item.id}
                    onClick={() => onSelect(item)}
                    onMouseEnter={() => setSelectedIndex(globalIdx)}
                    className={`w-full px-4 py-2 flex items-center justify-between text-left ${
                      selectedIndex === globalIdx ? 'bg-[#00f3ff]/10' : ''
                    }`}
                  >
                    <div>
                      <p className="text-xs font-mono text-[var(--sa-text-0)]">{item.label}</p>
                      {item.description && (
                        <p className="text-[10px] font-mono text-[var(--sa-text-2)]">{item.description}</p>
                      )}
                    </div>
                    {item.module && (
                      <span className="text-[9px] font-mono uppercase text-[#00f3ff]/60">{item.module}</span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="px-4 py-6 text-center text-xs font-mono text-[var(--sa-text-2)]">
              কোনো ফলাফল নেই · NO RESULTS
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
