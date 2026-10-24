import { useMemo } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { useMetrics } from '../../hooks/useDashboardData';
import { useDashboardStore } from '../../store/dashboardStore';

export function RealTimeMetricsPanel() {
  const { data: metrics, isLoading, dataUpdatedAt } = useMetrics(5000);
  const dashboardMode = useDashboardStore((s) => s.dashboardMode);
  const isSimple = dashboardMode === 'simple';

  // বাংলা মন্তব্য: Date.now() render-এ কল করা React purity নিয়ম ভঙ্গ করে।
  // react-query-এর dataUpdatedAt (stable timestamp) ব্যবহার করা হচ্ছে — এটি
  // ডেটা আপডেটের সময় পরিবর্তিত হয়, তাই গ্রাফের X-অক্ষ টাইমস্ট্যাম্প সঠিক থাকে।
  const now = dataUpdatedAt;

  const series = useMemo(() => {
    if (!metrics) return [];
    return [
      {
        id: 'rps',
        label: 'RPS',
        color: '#00f3ff',
        data: [
          { t: now, v: metrics.requests_per_second },
        ],
      },
      {
        id: 'p50',
        label: 'P50 (ms)',
        color: '#b5179e',
        data: [
          { t: now, v: metrics.latency_p50_ms },
        ],
      },
      {
        id: 'p95',
        label: 'P95 (ms)',
        color: '#ff9900',
        data: [
          { t: now, v: metrics.latency_p95_ms },
        ],
      },
      {
        id: 'err',
        label: 'Error Rate',
        color: '#ff003c',
        data: [
          { t: now, v: Number((metrics.error_rate || 0).toFixed(4)) },
        ],
      },
    ];
  }, [metrics, now]);

  if (isLoading) {
    return (
      <div className="rounded-xl border border-slate-900 bg-slate-950/60 p-5 shadow-[0_0_15px_rgba(0,0,0,0.3)]">
        <div className="text-[10px] font-mono text-slate-400 uppercase tracking-widest">
          Loading metrics...
        </div>
      </div>
    );
  }

  if (!metrics) {
    return (
      <div className="rounded-xl border border-slate-900 bg-slate-950/60 p-5 shadow-[0_0_15px_rgba(0,0,0,0.3)]">
        <div className="text-[10px] font-mono text-slate-400 uppercase tracking-widest">
          Metrics unavailable
        </div>
      </div>
    );
  }

  return (
    <div
      className={`rounded-xl border shadow-[0_0_15px_rgba(0,0,0,0.3)] ${
        isSimple
          ? 'border-slate-100 bg-white p-5'
          : 'border-slate-900 bg-slate-950/60 p-5'
      }`}
    >
      <div className="mb-4 flex items-center justify-between">
        <span
          className={`text-[10px] uppercase font-bold tracking-wider ${
            isSimple ? 'text-slate-900' : 'text-[#00f3ff]'
          }`}
        >
          Live Metrics
        </span>
        <span className="text-[9px] font-mono text-slate-400">
          {new Date(dataUpdatedAt).toLocaleTimeString()}
        </span>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {/* বাংলা মন্তব্য: backend এখন অনুপলব্ধ মেট্রিক null পাঠায় (false-assurance
            doctrine) — null-safe রেন্ডারিং বাধ্যতামূলক, নইলে .toLocaleString() ক্র্যাশ করে। */}
        <Kpi
          label="Requests/s"
          value={metrics.requests_per_second != null ? metrics.requests_per_second.toLocaleString() : '—'}
          accent="#00f3ff"
          isSimple={isSimple}
        />
        <Kpi
          label="Latency P50"
          value={metrics.latency_p50_ms != null ? `${metrics.latency_p50_ms} ms` : '—'}
          accent="#b5179e"
          isSimple={isSimple}
        />
        <Kpi
          label="Latency P95"
          value={metrics.latency_p95_ms != null ? `${metrics.latency_p95_ms} ms` : '—'}
          accent="#ff9900"
          isSimple={isSimple}
        />
        <Kpi
          label="Error Rate"
          value={metrics.error_rate != null ? `${metrics.error_rate.toFixed(4)}` : '—'}
          accent="#ff003c"
          isSimple={isSimple}
        />
      </div>

      <div className={`h-64 w-full ${isSimple ? 'bg-slate-50' : 'bg-black/20'} rounded-lg p-2`}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={mergeSeries(series)}
            margin={{ top: 5, right: 10, left: 0, bottom: 0 }}
          >
            <defs>
              {series.map((s) => (
                <linearGradient key={s.id} id={`grad-${s.id}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={s.color} stopOpacity={0.35} />
                  <stop offset="95%" stopColor={s.color} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke={isSimple ? '#e5e7eb' : '#0f172a'}
            />
            <XAxis
              dataKey="t"
              type="number"
              domain={['dataMin', 'dataMax']}
              tickFormatter={(ts) =>
                new Date(ts).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })
              }
              stroke={isSimple ? '#9ca3af' : '#1e293b'}
              tick={{ fontSize: 10, fontFamily: 'monospace' }}
              minTickGap={40}
            />
            <YAxis
              stroke={isSimple ? '#9ca3af' : '#1e293b'}
              tick={{ fontSize: 10, fontFamily: 'monospace' }}
              width={45}
            />
            <Tooltip
              contentStyle={{
                fontFamily: 'monospace',
                fontSize: 11,
                borderRadius: 8,
                border: '1px solid #334155',
                backgroundColor: isSimple ? '#ffffff' : '#0b0f19',
                color: isSimple ? '#0f172a' : '#e2e8f0',
              }}
              labelFormatter={(ts) =>
                new Date(ts as string | number).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })
              }
            />
            {series.map((s) => (
              <Area
                key={s.id}
                type="monotone"
                dataKey={`${s.id}.v`}
                stroke={s.color}
                strokeWidth={2}
                fill={`url(#grad-${s.id})`}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function Kpi({ label, value, accent, isSimple }: { label: string; value: string; accent: string; isSimple: boolean }) {
  return (
    <div
      className={`rounded-lg border p-3 ${
        isSimple ? 'border-slate-100 bg-slate-50' : 'border-slate-900 bg-black/20'
      }`}
    >
      <div className={`text-[9px] uppercase ${isSimple ? 'text-slate-400' : 'text-slate-400'}`}>
        {label}
      </div>
      <div className="mt-1 text-sm font-bold" style={{ color: isSimple ? '#0f172a' : accent }}>
        {value}
      </div>
    </div>
  );
}

interface SeriesItem {
  id: string;
  data: { t: number; v: number }[];
}

function mergeSeries(series: SeriesItem[]) {
  const map = new Map<number, Record<string, unknown>>();
  for (const s of series) {
    for (const pt of s.data) {
      const row = map.get(pt.t) || { t: pt.t };
      row[s.id] = { v: pt.v };
      map.set(pt.t, row);
    }
  }
  return Array.from(map.values()).sort((a, b) => (a.t as number) - (b.t as number));
}
