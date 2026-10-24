import React from 'react';
import { type LucideIcon, Sparkles } from 'lucide-react';
import { SpotlightCard } from './SpotlightCard';

export interface EmptyStateProps {
  icon?: LucideIcon | React.ElementType;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  secondaryActionLabel?: string;
  onSecondaryAction?: () => void;
  className?: string;
  spotlightColor?: 'cyan' | 'purple' | 'neutral';
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon = Sparkles,
  title,
  description,
  actionLabel,
  onAction,
  secondaryActionLabel,
  onSecondaryAction,
  className = '',
  spotlightColor = 'cyan',
}) => {
  return (
    <SpotlightCard
      spotlightColor={spotlightColor}
      className={`p-8 text-center flex flex-col items-center justify-center rounded-2xl ${className}`}
      data-testid="empty-state"
    >
      <div className="relative mb-4">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-cyan-500/20 to-purple-500/20 border border-white/10 flex items-center justify-center shadow-[0_0_20px_rgba(0,243,255,0.15)]">
          <Icon className="w-6 h-6 text-cyan-400" />
        </div>
      </div>

      <h3 className="text-base font-bold text-slate-100">{title}</h3>
      <p className="text-xs text-slate-400 max-w-sm mt-1 mb-6 leading-relaxed">
        {description}
      </p>

      {(actionLabel || secondaryActionLabel) && (
        <div className="flex flex-wrap items-center justify-center gap-3">
          {actionLabel && (
            <button
              onClick={onAction}
              className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 text-white text-xs font-semibold rounded-xl shadow-[0_0_15px_rgba(0,243,255,0.3)] transition-all hover:scale-105 active:scale-95"
            >
              {actionLabel}
            </button>
          )}
          {secondaryActionLabel && (
            <button
              onClick={onSecondaryAction}
              className="px-4 py-2 bg-slate-800/80 hover:bg-slate-800 text-slate-300 hover:text-white text-xs font-medium rounded-xl border border-white/10 transition-colors"
            >
              {secondaryActionLabel}
            </button>
          )}
        </div>
      )}
    </SpotlightCard>
  );
};

export default EmptyState;
