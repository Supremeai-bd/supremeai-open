import { useEffect, useMemo, useRef, useState } from 'react';
import { CornerDownLeft, Search } from 'lucide-react';
import { useCommandCenterStore } from '../state/useCommandCenterStore';
import { COMMAND_ITEMS } from './moduleIndex';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — ⌘K Command Palette
// বাংলা মন্তব্য: FIX(palette-dead) — আগে CommandBar-এর ⌘K বাটন শুধু
// isPaletteOpen=true সেট করত, কিন্তু state-টি কোনো UI consume করত না —
// অর্থাৎ বাটনটি চাক্ষুষভাবে no-op ছিল। এখন এই প্যালেট ওই state-কে কাজে
// লাগিয়ে ফাজি সার্চ + কিবোর্ড নেভিগেশনসহ প্রকৃত কমান্ড প্যালেট দেয়।
// ═══════════════════════════════════════════════════════════════════════════

export function CommandPalette() {
  const { isPaletteOpen, setPaletteOpen, setActiveModule } = useCommandCenterStore();
  const [query, setQuery] = useState('');
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Global ⌘K / Ctrl+K toggle — the badge in CommandBar promises this.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        const next = !useCommandCenterStore.getState().isPaletteOpen;
        useCommandCenterStore.getState().setPaletteOpen(next);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  // Focus + reset whenever the palette opens.
  useEffect(() => {
    if (isPaletteOpen) {
      setQuery('');
      setCursor(0);
      // Defer so the input exists before focus (modal mounts with open).
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [isPaletteOpen]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return COMMAND_ITEMS;
    return COMMAND_ITEMS.filter(
      (item) =>
        item.label.toLowerCase().includes(q) ||
        item.id.toLowerCase().includes(q) ||
        item.module.toLowerCase().includes(q),
    );
  }, [query]);

  if (!isPaletteOpen) return null;

  const activate = (index: number) => {
    const item = results[index];
    if (!item) return;
    setActiveModule(item.module);
    setPaletteOpen(false);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      setPaletteOpen(false);
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      setCursor((c) => Math.min(c + 1, results.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      activate(cursor);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-[14vh] backdrop-blur-sm"
      role="presentation"
      onClick={() => setPaletteOpen(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="কমান্ড প্যালেট"
        className="w-[min(560px,calc(100vw-2rem))] overflow-hidden rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-[var(--sa-line)] px-4 py-3">
          <Search size={14} className="text-[var(--sa-text-2)]" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setCursor(0);
            }}
            onKeyDown={onKeyDown}
            placeholder="মডিউল খুঁজুন…"
            aria-label="কমান্ড অনুসন্ধান"
            className="w-full bg-transparent font-mono text-sm text-[var(--sa-text-0)] outline-none placeholder:text-[var(--sa-text-2)]"
          />
          <kbd className="rounded border border-[var(--sa-line)] px-1.5 py-0.5 text-[9px] font-mono text-[var(--sa-text-2)]">
            ESC
          </kbd>
        </div>
        <ul className="max-h-72 overflow-y-auto py-1" role="listbox" aria-label="মডিউল তালিকা">
          {results.length === 0 && (
            <li className="px-4 py-6 text-center text-xs font-mono text-[var(--sa-text-2)]">
              কোনো মডিউল মেলেনি
            </li>
          )}
          {results.map((item, index) => (
            <li key={item.id} role="option" aria-selected={index === cursor}>
              <button
                type="button"
                onMouseEnter={() => setCursor(index)}
                onClick={() => activate(index)}
                className={`flex w-full items-center gap-3 px-4 py-2 text-left transition-colors ${
                  index === cursor
                    ? 'bg-[#00f3ff]/10 text-[var(--sa-text-0)]'
                    : 'text-[var(--sa-text-1)]'
                }`}
              >
                <item.icon size={13} className="text-[#00f3ff]" />
                <span className="flex-1 text-xs">{item.label}</span>
                <span className="text-[9px] font-mono uppercase text-[var(--sa-text-2)]">
                  {item.module}
                </span>
                {index === cursor && <CornerDownLeft size={11} className="text-[var(--sa-text-2)]" />}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
