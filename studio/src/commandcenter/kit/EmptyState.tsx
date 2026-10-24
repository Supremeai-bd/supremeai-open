import { AlertTriangle } from 'lucide-react';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Empty/Degraded State
// বাংলা মন্তব্য: API DOWN হলে UI কখনো ফাঁকা থাকবে না — degraded state দেখাবে
// ═══════════════════════════════════════════════════════════════════════════

interface EmptyStateProps {
  title?: string;
  message?: string;
  loading?: boolean;
  onRetry?: () => void;
}

export function EmptyState({
  title = 'ডেটা লোড হচ্ছে না',
  message = 'সার্ভার থেকে ডেটা পাওয়া যাচ্ছে না। কিছুক্ষণ পর আবার চেষ্টা করুন।',
  loading,
  onRetry,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center p-8 rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] min-h-[160px]">
      {loading ? (
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#00f3ff]/30 border-t-[#00f3ff]" />
      ) : (
        <AlertTriangle size={28} className="text-[#f59e0b] mb-3 opacity-80" />
      )}
      <p className="text-sm font-mono text-[var(--sa-text-0)] mb-1">{title}</p>
      <p className="text-xs font-mono text-[var(--sa-text-1)] text-center max-w-[280px]">{message}</p>
      {onRetry && !loading && (
        <button
          onClick={onRetry}
          className="mt-4 px-4 py-1.5 rounded-lg border border-[#00f3ff]/30 text-[#00f3ff] text-xs font-mono hover:bg-[#00f3ff]/10 transition-colors"
        >
          আবার চেষ্টা করুন · RETRY
        </button>
      )}
    </div>
  );
}
