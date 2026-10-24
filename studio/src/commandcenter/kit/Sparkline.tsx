
// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Sparkline (pure SVG, no chart lib)
// বাংলা মন্তব্য: হালকা SVG স্পার্কলাইন — কোনো ভারী চার্ট লাইব্রেরি নেই
// ═══════════════════════════════════════════════════════════════════════════

interface SparklineProps {
    data: number[];
    width?: number;
    height?: number;
    color?: string; // বাংলা মন্তব্য: stroke-এর সংক্ষিপ্ত বিকল্প — মডিউলগুলো `color` পাঠায়
    stroke?: string;
    fill?: string;
    strokeWidth?: number;
}

export function Sparkline({
    data,
    width = 120,
    height = 32,
    color,
    stroke: strokeProp,
    fill = 'rgba(0,243,255,0.08)',
    strokeWidth = 1.5,
}: SparklineProps) {
    const stroke = strokeProp ?? color ?? 'var(--sa-cyan)';

    if (!data || data.length === 0) {
        return (
            <div className="w-full flex items-center justify-center text-[8px] text-[var(--sa-text-2)] font-mono">
                NO DATA
            </div>
        );
    }

    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const stepX = width / (data.length - 1 || 1);

    const points = data.map((v, i) => {
        const x = i * stepX;
        const y = height - ((v - min) / range) * (height - 4) - 2;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    });

    const polyline = points.join(' ');
    const area = `0,${height} ${polyline} ${width},${height}`;

    return (
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
            <polygon points={area} fill={fill} />
            <polyline
                points={polyline}
                fill="none"
                stroke={stroke}
                strokeWidth={strokeWidth}
                strokeLinejoin="round"
                strokeLinecap="round"
            />
        </svg>
    );
}
