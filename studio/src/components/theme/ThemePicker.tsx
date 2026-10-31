import React from 'react';
import { Check, Palette } from 'lucide-react';
import { useTheme } from '../../contexts/useTheme';
import { THEME_META, THEME_ORDER } from '../../contexts/ThemeConstants';
import type { Theme } from '../../contexts/ThemeConstants';

const THEME_SWATCHES: Record<Theme, string> = {
  dark: 'linear-gradient(135deg, #101827 0%, #62d7b2 100%)',
  light: 'linear-gradient(135deg, #ffffff 0%, #38a3d9 100%)',
  synthwave: 'linear-gradient(135deg, #170d2d 0%, #ff4fd8 52%, #725cff 100%)',
  cyberpunk: 'linear-gradient(135deg, #071316 0%, #f5e642 48%, #ff6b35 100%)',
  minimal: 'linear-gradient(135deg, #f7f7f2 0%, #a7b3ac 100%)',
  sunset: 'linear-gradient(135deg, #1c0e0b 0%, #fb923c 52%, #e11d48 100%)',
  matrix: 'linear-gradient(135deg, #020a02 0%, #10b981 52%, #a7f3d0 100%)',
  emerald: 'linear-gradient(135deg, #061512 0%, #2dd4bf 52%, #7dd3fc 100%)',
};

export const ThemePicker: React.FC = () => {
  const { theme, setTheme } = useTheme();

  return (
    <details className="relative z-[var(--z-index-overlay)]">
      <summary
        className="flex cursor-pointer list-none items-center gap-2 rounded-full border border-[var(--sa-border)] bg-[var(--sa-surface)]/80 px-3 py-2 text-xs font-semibold text-[var(--sa-ink-muted)] shadow-[var(--sa-shadow-sm)] transition hover:border-[var(--sa-primary)] hover:text-[var(--sa-ink)] [&::-webkit-details-marker]:hidden"
        aria-label={`Theme: ${THEME_META[theme].label}`}
        title="Choose workspace theme"
      >
        <Palette size={14} aria-hidden="true" />
        <span className="hidden md:inline">{THEME_META[theme].label}</span>
      </summary>
      <div className="absolute right-0 top-11 w-72 rounded-2xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-3 shadow-[var(--sa-shadow-md)] backdrop-blur-xl">
        <div className="mb-3 flex items-center justify-between px-1">
          <div>
            <p className="sa-eyebrow">Workspace appearance</p>
            <p className="mt-1 text-xs text-[var(--sa-ink-muted)]">Choose a visual mode for chat and tools.</p>
          </div>
          <Palette size={16} className="text-[var(--sa-primary)]" aria-hidden="true" />
        </div>
        <div className="grid grid-cols-2 gap-2" role="menu" aria-label="Available themes">
          {THEME_ORDER.map((option) => {
            const selected = option === theme;
            return (
              <button
                key={option}
                type="button"
                role="menuitemradio"
                aria-checked={selected}
                onClick={(event) => {
                  setTheme(option);
                  const details = event.currentTarget.closest('details');
                  if (details) details.open = false;
                }}
                className={`group flex items-center gap-2 rounded-xl border px-2.5 py-2 text-left text-xs transition ${selected ? 'border-[var(--sa-primary)] bg-[var(--sa-primary-soft)] text-[var(--sa-ink)]' : 'border-[var(--sa-border)] text-[var(--sa-ink-muted)] hover:border-[var(--sa-primary)] hover:bg-[var(--sa-surface-muted)] hover:text-[var(--sa-ink)]'}`}
              >
                <span
                  className="size-7 shrink-0 rounded-lg border border-white/15 shadow-inner"
                  style={{ background: THEME_SWATCHES[option] }}
                  aria-hidden="true"
                />
                <span className="min-w-0 flex-1 truncate">{THEME_META[option].label}</span>
                {selected && <Check size={14} className="shrink-0 text-[var(--sa-primary)]" aria-hidden="true" />}
              </button>
            );
          })}
        </div>
      </div>
    </details>
  );
};
