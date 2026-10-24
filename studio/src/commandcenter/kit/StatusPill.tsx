
// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Status Pill
// বাংলা মন্তব্য: লাইভ স্ট্যাটাস ইন্ডিকেটর — ব্লিঙ্কিং ডট + টেক্সট
// ═══════════════════════════════════════════════════════════════════════════

type StatusLevel = 'healthy' | 'active' | 'warning' | 'critical' | 'offline' | 'pending' | 'unknown';

interface StatusPillProps {
    status: StatusLevel | string;
    label?: string;
    pulse?: boolean;
    size?: 'sm' | 'md' | 'lg';
}

const STATUS_STYLES: Record<string, { dot: string; text: string; bg: string; border: string }> = {
    healthy: { dot: 'bg-[#10b981] shadow-[0_0_8px_#10b981]', text: 'text-[#10b981]', bg: 'bg-[#10b981]/10', border: 'border-[#10b981]/20' },
    active: { dot: 'bg-[#00f3ff] shadow-[0_0_8px_#00f3ff]', text: 'text-[#00f3ff]', bg: 'bg-[#00f3ff]/10', border: 'border-[#00f3ff]/20' },
    success: { dot: 'bg-[#10b981] shadow-[0_0_8px_#10b981]', text: 'text-[#10b981]', bg: 'bg-[#10b981]/10', border: 'border-[#10b981]/20' },
    warning: { dot: 'bg-[#f59e0b] shadow-[0_0_8px_#f59e0b]', text: 'text-[#f59e0b]', bg: 'bg-[#f59e0b]/10', border: 'border-[#f59e0b]/20' },
    critical: { dot: 'bg-[#ef4444] shadow-[0_0_8px_#ef4444]', text: 'text-[#ef4444]', bg: 'bg-[#ef4444]/10', border: 'border-[#ef4444]/20' },
    error: { dot: 'bg-[#ef4444] shadow-[0_0_8px_#ef4444]', text: 'text-[#ef4444]', bg: 'bg-[#ef4444]/10', border: 'border-[#ef4444]/20' },
    offline: { dot: 'bg-[#64748b]', text: 'text-[#64748b]', bg: 'bg-[#64748b]/10', border: 'border-[#64748b]/20' },
    pending: { dot: 'bg-[#6366f1] shadow-[0_0_8px_#6366f1]', text: 'text-[#6366f1]', bg: 'bg-[#6366f1]/10', border: 'border-[#6366f1]/20' },
    unknown: { dot: 'bg-[#64748b]', text: 'text-[#64748b]', bg: 'bg-[#64748b]/10', border: 'border-[#64748b]/20' },
};

const SIZE_CLASSES = {
    sm: { text: 'text-[9px]', dot: 'w-1.5 h-1.5', gap: 'gap-1', px: 'px-1.5', py: 'py-0.5' },
    md: { text: 'text-[10px]', dot: 'w-2 h-2', gap: 'gap-1.5', px: 'px-2', py: 'py-1' },
    lg: { text: 'text-xs', dot: 'w-2.5 h-2.5', gap: 'gap-2', px: 'px-3', py: 'py-1.5' },
};

export function StatusPill({ status, label, pulse = true, size = 'md' }: StatusPillProps) {
    const style = STATUS_STYLES[status] || STATUS_STYLES.unknown;
    const s = SIZE_CLASSES[size];

    return (
        <div className={`inline-flex items-center ${s.gap} ${s.px} ${s.py} rounded-full ${style.bg} ${style.border} border ${style.text} font-mono font-bold ${s.text} uppercase tracking-wider`}>
            <span className={`relative flex ${s.dot} ${style.dot} ${pulse ? 'animate-pulse' : ''}`}>
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${style.dot} opacity-75 ${pulse ? '' : 'hidden'}`} />
                <span className={`relative inline-flex rounded-full h-full w-full ${style.dot}`} />
            </span>
            {label || status}
        </div>
    );
}
