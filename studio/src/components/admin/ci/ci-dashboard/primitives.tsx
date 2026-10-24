// ══════════════════════════════════════════════════════════════════════════════
// CI Dashboard — SUB-COMPONENTS (UI primitives)
// (extracted verbatim from CIDashboard.tsx — mechanical split, no behavior change)
// ══════════════════════════════════════════════════════════════════════════════

import type { ElementType, ReactNode } from 'react';
import { Wifi, WifiOff, Loader2, AlertCircle } from 'lucide-react';
import { COLORS, STATUS_CONFIG } from './constants';
import { getGradeColor } from './utils';
import type { ConnectionStatus } from './types';

export function Badge({ children, variant = 'default' }: { children: ReactNode; variant?: 'success' | 'warning' | 'failure' | 'default' }) {
  const variants = {
    success: 'bg-green-100 text-green-800 border-green-200',
    warning: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    failure: 'bg-red-100 text-red-800 border-red-200',
    default: 'bg-gray-100 text-gray-800 border-gray-200',
  };

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${variants[variant]}`}>
      {children}
    </span>
  );
}

export function ScoreCircle({ score, grade, size = 80 }: { score: number; grade: string; size?: number }) {
  const radius = (size - 8) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (score / 100) * circumference;
  const color = getGradeColor(grade);

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="transform -rotate-90">
        <circle cx={size/2} cy={size/2} r={radius} fill="none" stroke="#e5e7eb" strokeWidth="6" />
        <circle
          cx={size/2}
          cy={size/2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          className="transition-all duration-1000 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-bold" style={{ color }}>{score}</span>
        <span className="text-xs font-semibold" style={{ color }}>{grade}</span>
      </div>
    </div>
  );
}

export function AnimatedStatus({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.skipped;
  const Icon = config.icon;
  const isAnimating = status === 'in_progress';

  return (
    <div
      className={`p-2 rounded-lg ${config.bgColor}`}
      style={{ color: config.color }}
    >
      <Icon className={`w-5 h-5 ${isAnimating ? 'animate-spin' : ''}`} />
    </div>
  );
}

export function ProgressBar({ value, max = 100, color, showLabel = false }: { value: number; max?: number; color?: string; showLabel?: boolean }) {
  const percentage = Math.min((value / max) * 100, 100);
  const barColor = color || (percentage >= 90 ? COLORS.success : percentage >= 70 ? COLORS.warning : COLORS.failure);

  return (
    <div className="w-full">
      <div className="flex justify-between items-center mb-1">
        {showLabel && <span className="text-xs text-gray-600">{percentage.toFixed(0)}%</span>}
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500 ease-out"
          style={{ width: `${percentage}%`, backgroundColor: barColor }}
        />
      </div>
    </div>
  );
}

export function EmptyState({ message, icon: Icon }: { message: string; icon: ElementType }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-gray-500">
      <Icon className="w-12 h-12 mb-4 text-gray-300" />
      <p className="text-lg font-medium">{message}</p>
      <p className="text-sm mt-1">Check back soon or try refreshing</p>
    </div>
  );
}

// Connection status pill (was the inline `renderConnectionBadge()` helper in CIDashboard)
export function ConnectionBadge({ status }: { status: ConnectionStatus }) {
  const configs = {
    connected: { icon: Wifi, color: 'text-green-600', bg: 'bg-green-100', label: 'Live' },
    disconnected: { icon: WifiOff, color: 'text-gray-400', bg: 'bg-gray-100', label: 'Offline' },
    connecting: { icon: Loader2, color: 'text-blue-600', bg: 'bg-blue-100', label: 'Connecting...' },
    error: { icon: AlertCircle, color: 'text-red-600', bg: 'bg-red-100', label: 'Error' },
  };

  const config = configs[status];
  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${config.bg} ${config.color}`}>
      <Icon className={`w-3 h-3 ${status === 'connecting' ? 'animate-spin' : ''}`} />
      {config.label}
    </span>
  );
}
