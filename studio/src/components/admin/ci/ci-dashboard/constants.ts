// ══════════════════════════════════════════════════════════════════════════════
// CI Dashboard — COLOR CONSTANTS
// (extracted verbatim from CIDashboard.tsx — mechanical split, no behavior change)
// ══════════════════════════════════════════════════════════════════════════════

import type { ElementType } from 'react';
import {
  CheckCircle2,
  XCircle,
  Minus,
  Loader2,
} from 'lucide-react';

export const COLORS = {
  success: '#22c55e',
  successBg: '#f0fdf4',
  failure: '#ef4444',
  failureBg: '#fef2f2',
  warning: '#f59e0b',
  warningBg: '#fffbeb',
  skipped: '#94a3b8',
  skippedBg: '#f8fafc',
  primary: '#3b82f6',
  primaryBg: '#eff6ff',
  purple: '#8b5cf6',
  pink: '#ec4899',

  gradeColors: {
    'A+': '#22c55e', 'A': '#22c55e', 'A-': '#84cc16',
    'B+': '#84cc16', 'B': '#eab308', 'B-': '#eab308',
    'C+': '#f97316', 'C': '#f97316', 'C-': '#ef4444',
    'D': '#ef4444', 'F': '#dc2626',
  },
};

export const STATUS_CONFIG: Record<string, { icon: ElementType; color: string; bgColor: string; label: string }> = {
  success: { icon: CheckCircle2, color: COLORS.success, bgColor: COLORS.successBg, label: 'Passed' },
  failure: { icon: XCircle, color: COLORS.failure, bgColor: COLORS.failureBg, label: 'Failed' },
  cancelled: { icon: Minus, color: COLORS.skipped, bgColor: COLORS.skippedBg, label: 'Cancelled' },
  skipped: { icon: Minus, color: COLORS.skipped, bgColor: COLORS.skippedBg, label: 'Skipped' },
  in_progress: { icon: Loader2, color: COLORS.primary, bgColor: COLORS.primaryBg, label: 'Running' },
};
