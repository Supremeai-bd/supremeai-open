// বাংলা মন্তব্য: Devin-স্টাইল Usage পেজ — ব্যাকএন্ড /metrics/usage/ থেকে ইউসেজ মেট্রিক্স এনে recharts দিয়ে দেখানো হয়
import { useState, useEffect } from 'react';
import { Loader2, Activity } from 'lucide-react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import { apiClient } from '../../services/apiClient';

interface UsageMetric {
  date?: string;
  metric_date?: string;
  total_requests: number;
  total_tokens: number;
  unique_users: number;
  avg_latency_ms: number;
  error_rate: number;
}

export function UsagePage() {
  const [items, setItems] = useState<UsageMetric[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    apiClient
      .get<{ items: UsageMetric[] }>('/metrics/usage/?limit=30')
      .then((data) => setItems((data.items || []).slice().reverse()))
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load usage metrics'))
      .finally(() => setLoading(false));
  }, []);

  const totalRequests = items.reduce((acc, m) => acc + (m.total_requests || 0), 0);
  const totalTokens = items.reduce((acc, m) => acc + (m.total_tokens || 0), 0);
  const avgLatency = items.length
    ? Math.round(items.reduce((acc, m) => acc + (m.avg_latency_ms || 0), 0) / items.length)
    : 0;

  const chartData = items.map((m) => ({
    date: m.date || m.metric_date || '',
    requests: m.total_requests || 0,
    tokens: m.total_tokens || 0,
  }));

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <h1 className="text-lg font-semibold text-white mb-1">Usage</h1>
      <p className="text-xs text-slate-400 mb-6">
        Platform usage over the last 30 days. SupremeAI is free — no billing, ever.
      </p>

      {loading ? (
        <div className="flex justify-center py-16 text-slate-400">
          <Loader2 size={20} className="animate-spin" />
        </div>
      ) : error ? (
        <p className="text-xs text-rose-400">{error}</p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3 mb-6">
            <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
              <p className="text-xl font-semibold text-white">{totalRequests.toLocaleString()}</p>
              <p className="text-[11px] text-slate-400">Total requests</p>
            </div>
            <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
              <p className="text-xl font-semibold text-white">{totalTokens.toLocaleString()}</p>
              <p className="text-[11px] text-slate-400">Total tokens</p>
            </div>
            <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
              <p className="text-xl font-semibold text-white">{avgLatency} ms</p>
              <p className="text-[11px] text-slate-400">Avg latency</p>
            </div>
          </div>

          {chartData.length === 0 ? (
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-10 text-center">
              <Activity size={20} className="mx-auto text-slate-600 mb-2" />
              <p className="text-sm text-slate-400">No usage data recorded yet.</p>
            </div>
          ) : (
            <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4 h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="reqGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#64748b' }} />
                  <YAxis tick={{ fontSize: 10, fill: '#64748b' }} />
                  <Tooltip
                    contentStyle={{
                      background: '#0f172a',
                      border: '1px solid rgba(255,255,255,0.1)',
                      borderRadius: 8,
                      fontSize: 11,
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="requests"
                    stroke="#3b82f6"
                    fill="url(#reqGradient)"
                    strokeWidth={1.5}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </div>
  );
}
