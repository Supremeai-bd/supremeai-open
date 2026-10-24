
// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Gauge Ring (circular progress)
// বাংলা মন্তব্য: সার্কুলার গেজ — CPU/মেমোরি/স্বাস্থ্য শতাংশ দেখানোর জন্য
// ═══════════════════════════════════════════════════════════════════════════

interface GaugeRingProps {
    value: number; // 0-100
    size?: number;
    strokeWidth?: number;
    label?: string;
    sublabel?: string;
    tone?: 'cyan' | 'emerald' | 'amber' | 'rose' | 'violet';
}

const TONE_COLORS: Record<string, { stroke: string; glow: string; text: string }> = {
    cyan: { stroke: '#00f3ff', glow: 'drop-shadow(0 0 6px rgba(0,243,255,0.6))', text: 'text-[#00f3ff]' },
    emerald: { stroke: '#10b981', glow: 'drop-shadow(0 0 6px rgba(16,185,129,0.6))', text: 'text-[#10b981]' },
    amber: { stroke: '#f59e0b', glow: 'drop-shadow(0 0 6px rgba(245,158,11,0.6))', text: 'text-[#f59e0b]' },
    rose: { stroke: '#ef4444', glow: 'drop-shadow(0 0 6px rgba(239,68,68,0.6))', text: 'text-[#ef4444]' },
    violet: { stroke: '#bc13fe', glow: 'drop-shadow(0 0 6px rgba(188,19,254,0.6))', text: 'text-[#bc13fe]' },
};

export function GaugeRing({
    value,
    size = 80,
    strokeWidth = 6,
    label,
    sublabel,
    tone = 'cyan',
}: GaugeRingProps) {
    const clamped = Math.max(0, Math.min(100, value));
    const radius = (size - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (clamped / 100) * circumference;
    const t = TONE_COLORS[tone] || TONE_COLORS.cyan;

    return (
        <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
            <svg width={size} height={size} className="-rotate-90">
                {/* Track */}
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="none"
                    stroke="var(--sa-bg-3)"
                    strokeWidth={strokeWidth}
                />
                {/* Progress */}
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="none"
                    stroke={t.stroke}
                    strokeWidth={strokeWidth}
                    strokeLinecap="round"
                    strokeDasharray={circumference}
                    strokeDashoffset={offset}
                    style={{ filter: t.glow, transition: 'stroke-dashoffset 0.6s ease' }}
                />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className={`font-mono font-bold ${t.text}`} style={{ fontSize: size * 0.2 }}>
                    {Math.round(clamped)}%
                </span>
                {label && (
                    <span className="text-[8px] text-[var(--sa-text-2)] font-mono uppercase tracking-wider mt-0.5">
                        {label}
                    </span>
                )}
                {sublabel && (
                    <span className="text-[7px] text-[var(--sa-text-3)] font-mono">{sublabel}</span>
                )}
            </div>
        </div>
    );
}
