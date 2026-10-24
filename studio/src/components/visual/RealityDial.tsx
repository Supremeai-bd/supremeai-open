/**
 * studio/src/components/visual/RealityDial.tsx — 4-level reality dial widget (Way 11).
 *
 * বাংলা: Infinity SPINE-এর 4-level reality dial-এর studio উইজেট — gateway
 * telemetry-র "rigidity level" দেখায় (L1 সবচেয়ে শিথিল, L4 সবচেয়ে কঠোর)।
 * Live data না থাকলে 'unknown' স্টেট — কখনো ভুয়া green নয় (honest observability)।
 *
 * Self-contained presentational component. Data contract (prop only):
 *   level: 1..4 | null   (null = unknown — renders muted, never fake-green)
 */

import { useMemo, useState, useEffect } from 'react';

export interface RealityDialProps {
  /** Current gateway reality-dial level, or null when unknown/unreachable. */
  level: number | null;
  /** Optional last-updated epoch ms for the freshness stamp. */
  updatedAt?: number | null;
  /** Compact mode for dashboard tiles. */
  compact?: boolean;
}

const LEVELS = [
  { n: 1, label: 'L1 · Advisory', hint: 'Observations only — nothing stripped', color: 'emerald' },
  { n: 2, label: 'L2 · Guarded', hint: 'Unearned apologies stripped', color: 'emerald' },
  { n: 3, label: 'L3 · Assertive', hint: 'Capitulation pivots rewritten mid-stream', color: 'purple' },
  { n: 4, label: 'L4 · Absolute', hint: 'Strictest invariants, zero accommodation', color: 'indigo' },
] as const;

const RING: Record<string, string> = {
  emerald: 'border-emerald-400/50 bg-emerald-400/10 text-emerald-200',
  purple: 'border-purple-400/50 bg-purple-400/10 text-purple-200',
  indigo: 'border-indigo-400/50 bg-indigo-400/10 text-indigo-200',
};

export default function RealityDial({ level, updatedAt, compact = false }: RealityDialProps) {
  const known = typeof level === 'number' && level >= 1 && level <= 4;
  const active = useMemo(() => LEVELS.find((l) => l.n === level), [level]);

  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    setNow(Date.now());
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [updatedAt]);

  const freshness = useMemo(() => {
    if (!updatedAt) return null;
    const ageS = Math.max(0, Math.round((now - updatedAt) / 1000));
    return ageS < 5 ? 'live' : `${ageS}s ago`;
  }, [updatedAt, now]);

  return (
    <section
      className={`rounded-xl border border-white/10 bg-white/[0.02] p-4 ${compact ? 'max-w-xs' : ''}`}
      aria-label="Reality dial"
      data-testid="reality-dial"
    >
      <header className="mb-3 flex items-baseline justify-between">
        <h3 className="text-xs font-medium uppercase tracking-wider text-white/50">Reality Dial</h3>
        <span className={`font-mono text-[10px] ${freshness === 'live' ? 'text-emerald-300' : 'text-white/40'}`}>
          {freshness ?? 'no data'}
        </span>
      </header>

      {!known ? (
        <p className="font-mono text-sm text-white/40">status: unknown — dial level not reported</p>
      ) : (
        <div className="space-y-2">
          <div className={`inline-block rounded-lg border px-3 py-1 font-mono text-sm ${RING[active!.color]}`}>
            {active!.label}
          </div>
          <ul className="mt-2 space-y-1">
            {LEVELS.map((l) => (
              <li
                key={l.n}
                className={`flex items-center gap-2 text-xs ${
                  l.n === level ? 'text-white' : 'text-white/35'
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    l.n === level ? 'bg-emerald-400' : 'bg-white/15'
                  }`}
                  aria-hidden
                />
                <span className="font-mono">L{l.n}</span>
                <span>{l.hint}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
