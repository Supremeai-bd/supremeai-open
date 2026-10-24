import React from 'react';
import { cn } from '../../utils/cn';
import { SpotlightCard } from './SpotlightCard';

export interface StatCardProps {
  label: string;
  value: React.ReactNode;
  icon?: React.ReactNode;
  hint?: string;
  delta?: string;
  deltaTone?: 'positive' | 'negative' | 'neutral';
  sparklineData?: number[];
  spotlightColor?: 'cyan' | 'purple' | 'neutral';
  className?: string;
}

export function StatCard({
  label,
  value,
  icon,
  hint,
  delta,
  deltaTone = 'neutral',
  sparklineData = [10, 15, 8, 22, 18, 26, 32],
  spotlightColor = 'cyan',
  className,
}: StatCardProps) {
  const deltaClass =
    deltaTone === 'positive'
      ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
      : deltaTone === 'negative'
        ? 'text-rose-400 bg-rose-500/10 border-rose-500/20'
        : 'text-slate-400 bg-slate-500/10 border-slate-500/20';

  // Compute SVG Sparkline Path
  const max = Math.max(...sparklineData, 1);
  const min = Math.min(...sparklineData, 0);
  const range = max - min || 1;
  const width = 80;
  const height = 24;

  const points = sparklineData
    .map((d, i) => {
      const x = (i / (sparklineData.length - 1 || 1)) * width;
      const y = height - ((d - min) / range) * (height - 4) - 2;
      return `${x},${y}`;
    })
    .join(' ');

  const strokeColor =
    deltaTone === 'positive'
      ? '#22c55e'
      : deltaTone === 'negative'
        ? '#ef4444'
        : spotlightColor === 'purple'
          ? '#a855f7'
          : '#00f3ff';

  return (
    <SpotlightCard
      spotlightColor={spotlightColor}
      title={hint}
      className={cn('p-5 shadow-[0_0_20px_rgba(0,0,0,0.4)]', className)}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400">
          {label}
        </span>
        {icon && <span className="text-lg text-slate-400">{icon}</span>}
      </div>

      <div className="flex items-end justify-between gap-2 mt-1">
        <div>
          <p className="text-2xl font-bold tracking-tight tabular-nums text-white">{value}</p>
          {delta && (
            <span
              className={cn(
                'inline-flex items-center gap-1 mt-1.5 px-2 py-0.5 text-[11px] font-semibold rounded-full border',
                deltaClass,
              )}
            >
              {delta}
            </span>
          )}
        </div>

        {/* Micro Sparkline Wave */}
        {sparklineData.length > 1 && (
          <div className="flex-shrink-0 opacity-80 transition-opacity hover:opacity-100">
            <svg
              width={width}
              height={height}
              className="overflow-visible"
              aria-label="Metric Sparkline Trend"
              data-testid="stat-sparkline"
            >
              <polyline
                fill="none"
                stroke={strokeColor}
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                points={points}
              />
            </svg>
          </div>
        )}
      </div>
    </SpotlightCard>
  );
}

export default StatCard;
