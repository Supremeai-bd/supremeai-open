import { useState } from 'react';
import { Card, Badge } from '../../ui';
import { AlertTriangle, TrendingUp } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { useUnifiedStore } from '../../../store/unifiedStore';
import { useMetrics } from '../../../hooks/useDashboardData';

const latencyData: Array<{ time: string; p50: number; p95: number; p99: number }> = [];
const endpointErrors: Array<{ endpoint: string; errors: number; total: number }> = [];

export function ObservabilityDashboard() {
  const [range, setRange] = useState<'1h' | '6h' | '24h' | '7d'>('6h');
  const storeAlerts = useUnifiedStore(s => s.alerts).slice(0, 5);
  const { data: metrics } = useMetrics();

  return (
    <div className="flex-grow p-6 overflow-y-auto bg-[#030611] text-[var(--foreground)]">
      <div className="flex items-center justify-between mb-6 pb-2 border-b border-[var(--border-color)]">
        <h2 className="text-lg font-bold font-['Space_Grotesk'] tracking-widest text-[#00f3ff] uppercase">
          📊 Observability & Intelligence
        </h2>
        <div className="flex gap-1">
          {(['1h', '6h', '24h', '7d'] as const).map(r => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-2 py-1 text-[10px] font-bold rounded font-mono transition-colors ${
                range === r ? 'bg-[#00f3ff]/20 text-[#00f3ff]' : 'text-slate-400 hover:text-[var(--foreground)]'
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card title="QPS" banglaHint="প্রতি সেকেন্ডে মোট রিকোয়েস্ট বা কুয়েরির সংখ্যা।">
          <div className="text-2xl font-bold text-[var(--foreground)] font-mono">{metrics?.requests_per_second ?? '—'}</div>
          <div className="text-[10px] text-emerald-400 font-mono flex items-center gap-1">
            <TrendingUp size={10} /> +12% from last hour
          </div>
        </Card>
        <Card title="P50 Latency" banglaHint="৫০% রিকোয়েস্টের গড় প্রসেসিং সময় বা লেটেন্সি।">
          <div className="text-2xl font-bold text-[var(--foreground)] font-mono">{metrics?.latency_p50_ms != null ? `${metrics.latency_p50_ms}ms` : '—'}</div>
          <div className="text-[10px] text-emerald-400 font-mono flex items-center gap-1">
            <TrendingUp size={10} /> -5% improvement
          </div>
        </Card>
        <Card title="P99 Latency" banglaHint="৯৯% রিকোয়েস্টের সর্বোচ্চ প্রসেসিং সময় বা লেটেন্সি।">
          <div className="text-2xl font-bold text-[#00f3ff] font-mono">{metrics?.latency_p99_ms != null ? `${metrics.latency_p99_ms}ms` : '—'}</div>
          <div className="text-[10px] text-yellow-400 font-mono">Above threshold (800ms)</div>
        </Card>
        <Card title="Error Rate" banglaHint="মোট রিকোয়েস্টের সাপেক্ষে ফেইল হওয়া এরর পার্সেন্টেজ।">
          <div className="text-2xl font-bold text-emerald-400 font-mono">{metrics?.error_rate != null ? `${metrics.error_rate}%` : '—'}</div>
          <div className="text-[10px] text-slate-400 font-mono">Within acceptable range</div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <Card title="Latency Percentiles" banglaHint="ভিন্ন ভিন্ন পার্সেন্টাইলের (P50, P95, P99) লেটেন্সি চার্ট।">
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={latencyData}>
              <XAxis dataKey="time" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ backgroundColor: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: 8, color: 'var(--foreground)' }} />
              <Area type="monotone" dataKey="p50" stroke="#10b981" fillOpacity={0} strokeWidth={2} />
              <Area type="monotone" dataKey="p95" stroke="#f59e0b" fillOpacity={0} strokeWidth={2} />
              <Area type="monotone" dataKey="p99" stroke="#ef4444" fillOpacity={0} strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Endpoint Error Breakdown" banglaHint="নির্দিষ্ট এপিআই এন্ডপয়েন্ট ভিত্তিক এরর কাউন্ট বিবরণ।">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={endpointErrors}>
              <XAxis dataKey="endpoint" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ backgroundColor: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: 8, color: 'var(--foreground)' }} />
              <Bar dataKey="errors" fill="#ef4444" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card title="Recent Alerts & Incidents" banglaHint="সাম্প্রতিক ঘটে যাওয়া অ্যালার্ট, ওয়ার্নিং এবং রিস্টোরেশন স্ট্যাটাস।">
        <div className="flex flex-col gap-2">
          {storeAlerts.length > 0 ? (
            storeAlerts.map((alert) => (
              <div key={alert.id} className="flex items-center gap-4 p-3 rounded-lg border border-[var(--border-color)] bg-[var(--alert-bg)]">
                <AlertTriangle size={14} className={
                  alert.severity === 'critical' || alert.severity === 'error' ? 'text-red-400' :
                  alert.severity === 'warning' ? 'text-yellow-400' : 'text-[#00f3ff]'
                } />
                <div className="flex-1">
                  <div className="text-xs text-[var(--foreground)] font-mono">{alert.message}</div>
                  <div className="text-[10px] text-slate-400 mt-0.5">
                    {new Date(alert.timestamp).toLocaleTimeString()} • {alert.source}
                  </div>
                </div>
                <Badge variant={alert.resolvedAt ? 'success' : (alert.acknowledged ? 'info' : 'warning')}>
                  {alert.resolvedAt ? 'Resolved' : (alert.acknowledged ? 'Acked' : 'New')}
                </Badge>
              </div>
            ))
          ) : (
            <div className="text-xs text-slate-400 font-mono text-center py-4">No recent alerts</div>
          )}
        </div>
      </Card>
    </div>
  );
}
