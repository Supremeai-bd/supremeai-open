import React from 'react';
import { CheckCircle2, AlertCircle, XCircle, Info, X } from 'lucide-react';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Toast Stack
// বাংলা মন্তব্য: সাকসেস/এরর/সিকিউরিটি টোস্ট নোটিফিকেশন
// ═══════════════════════════════════════════════════════════════════════════

export type ToastType = 'success' | 'error' | 'warning' | 'info' | 'security';

export interface ToastItem {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
}

interface ToastStackProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}

const TOAST_STYLES: Record<ToastType, { icon: React.ReactNode; border: string; text: string }> = {
  success: { icon: <CheckCircle2 size={16} className="text-[#10b981]" />, border: 'border-[#10b981]/30', text: 'text-[#10b981]' },
  error: { icon: <XCircle size={16} className="text-[#ef4444]" />, border: 'border-[#ef4444]/30', text: 'text-[#ef4444]' },
  warning: { icon: <AlertCircle size={16} className="text-[#f59e0b]" />, border: 'border-[#f59e0b]/30', text: 'text-[#f59e0b]' },
  info: { icon: <Info size={16} className="text-[#00f3ff]" />, border: 'border-[#00f3ff]/30', text: 'text-[#00f3ff]' },
  security: { icon: <AlertCircle size={16} className="text-[#bc13fe]" />, border: 'border-[#bc13fe]/30', text: 'text-[#bc13fe]' },
};

export function ToastStack({ toasts, onDismiss }: ToastStackProps) {
  return (
    <div className="fixed bottom-20 right-4 z-50 space-y-2 w-80">
      {toasts.map((toast) => {
        const style = TOAST_STYLES[toast.type];
        return (
          <div
            key={toast.id}
            className={`flex items-start gap-3 p-3 rounded-xl border ${style.border} bg-[var(--sa-bg-1)] shadow-lg animate-slide-in`}
          >
            <div className="mt-0.5">{style.icon}</div>
            <div className="flex-1">
              <p className={`text-xs font-mono font-bold ${style.text}`}>{toast.title}</p>
              {toast.message && <p className="text-[10px] font-mono text-[var(--sa-text-1)] mt-0.5">{toast.message}</p>}
            </div>
            <button onClick={() => onDismiss(toast.id)} className="text-[var(--sa-text-2)] hover:text-[var(--sa-text-0)]">
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
