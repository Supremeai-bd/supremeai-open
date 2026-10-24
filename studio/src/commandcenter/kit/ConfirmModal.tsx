import type { ReactNode } from 'react';
import { X, AlertTriangle } from 'lucide-react';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Confirm Modal
// বাংলা মন্তব্য: ডেস্ট্রাক্টিভ অ্যাকশন কনফার্মেশন মোডাল
// ═══════════════════════════════════════════════════════════════════════════

interface ConfirmModalProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  children?: ReactNode;
}

export function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = 'নিশ্চিত করুন',
  cancelLabel = 'বাতিল',
  danger,
  loading,
  onConfirm,
  onCancel,
  children,
}: ConfirmModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-6 shadow-2xl">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            {danger && <AlertTriangle size={20} className="text-[#ef4444]" />}
            <h3 className="text-sm font-mono font-bold text-[var(--sa-text-0)]">{title}</h3>
          </div>
          <button onClick={onCancel} className="text-[var(--sa-text-1)] hover:text-[var(--sa-text-0)]">
            <X size={16} />
          </button>
        </div>
        <p className="text-xs font-mono text-[var(--sa-text-1)] mb-4">{message}</p>
        {children}
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 rounded-lg border border-[var(--sa-line)] text-xs font-mono text-[var(--sa-text-1)] hover:border-[var(--sa-text-1)] disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`px-4 py-2 rounded-lg text-xs font-mono font-bold disabled:opacity-50 ${
              danger
                ? 'bg-[#ef4444]/20 text-[#ef4444] border border-[#ef4444]/40 hover:bg-[#ef4444]/30'
                : 'bg-[#00f3ff]/20 text-[#00f3ff] border border-[#00f3ff]/40 hover:bg-[#00f3ff]/30'
            }`}
          >
            {loading ? 'প্রসেসিং...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
