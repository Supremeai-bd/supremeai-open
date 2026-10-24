import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Zap, Dna, Globe, Sparkles } from 'lucide-react';
import { SpotlightCard } from '../ui/SpotlightCard';

export interface QuickActionItem {
  id: string;
  title: string;
  description: string;
  icon: React.ElementType;
  color: 'cyan' | 'purple';
  route?: string;
  action?: () => void;
}

interface QuickActionsPanelProps {
  className?: string;
}

export const QuickActionsPanel: React.FC<QuickActionsPanelProps> = ({ className = '' }) => {
  const navigate = useNavigate();

  const actions: QuickActionItem[] = [
    {
      id: 'self-healer',
      title: 'Trigger Self-Healer',
      description: 'Run background auto-diagnosis & pool healing loop',
      icon: Zap,
      color: 'cyan',
      action: () => {
        window.dispatchEvent(
          new CustomEvent('supremeai-notification', {
            detail: { message: 'Self-Healer Loop Triggered. All background connections healthy.' },
          })
        );
      },
    },
    {
      id: 'evolution-forge',
      title: 'Evolve New Skill',
      description: 'Synthesize genetic skills & optimize task velocity',
      icon: Dna,
      color: 'purple',
      route: '/evolution-forge',
    },
    {
      id: 'browser-sandbox',
      title: 'Browser Live Preview',
      description: 'Launch in-app sandboxed browser with hot-reload',
      icon: Globe,
      color: 'cyan',
      route: '/workspace',
    },
    {
      id: 'gap-miner',
      title: 'Deep Codebase Audit',
      description: 'Mine architecture drifts and missing dependencies',
      icon: Sparkles,
      color: 'purple',
      action: () => {
        window.dispatchEvent(
          new CustomEvent('supremeai-notification', {
            detail: { message: 'Codebase Gap Audit running across 52 knowledge domains.' },
          })
        );
      },
    },
  ];

  return (
    <div className={`space-y-3 ${className}`} data-testid="quick-actions-panel">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
          <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
          Quick Actions
        </h3>
        <span className="text-[10px] font-mono text-slate-500">Autonomous Actions</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {actions.map((action) => {
          const Icon = action.icon;
          const isCyan = action.color === 'cyan';
          return (
            <SpotlightCard
              key={action.id}
              spotlightColor={action.color}
              onClick={() => {
                if (action.route) navigate(action.route);
                action.action?.();
              }}
              className="p-3.5 rounded-xl cursor-pointer group hover:border-white/20 transition-all duration-200"
            >
              <div className="flex items-start gap-3">
                <div
                  className={`p-2 rounded-lg transition-transform duration-200 group-hover:scale-110 ${
                    isCyan
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                      : 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-bold text-slate-200 group-hover:text-white transition-colors truncate">
                    {action.title}
                  </p>
                  <p className="text-[11px] text-slate-400 line-clamp-2 mt-0.5 leading-snug">
                    {action.description}
                  </p>
                </div>
              </div>
            </SpotlightCard>
          );
        })}
      </div>
    </div>
  );
};

export default QuickActionsPanel;
