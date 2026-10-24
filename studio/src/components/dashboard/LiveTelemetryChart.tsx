import React from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { SpotlightCard } from '../ui/SpotlightCard';

export interface TelemetryPoint {
  time: string;
  throughput: number;
  latency: number;
}

const DEFAULT_DATA: TelemetryPoint[] = [
  { time: '00:00', throughput: 45, latency: 120 },
  { time: '04:00', throughput: 82, latency: 95 },
  { time: '08:00', throughput: 140, latency: 42 },
  { time: '12:00', throughput: 195, latency: 38 },
  { time: '16:00', throughput: 230, latency: 45 },
  { time: '20:00', throughput: 180, latency: 50 },
  { time: '23:59', throughput: 210, latency: 36 },
];

interface LiveTelemetryChartProps {
  data?: TelemetryPoint[];
  className?: string;
}

export const LiveTelemetryChart: React.FC<LiveTelemetryChartProps> = ({
  data = DEFAULT_DATA,
  className = '',
}) => {
  return (
    <SpotlightCard
      spotlightColor="cyan"
      className={`p-5 rounded-2xl shadow-xl flex flex-col justify-between ${className}`}
      data-testid="live-telemetry-chart"
    >
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
            <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wider">
              Swarm Throughput & Engine Latency
            </h3>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Real-time inference metrics & distributed task velocity
          </p>
        </div>

        <div className="flex items-center gap-4 text-xs font-mono">
          <span className="flex items-center gap-1.5 text-cyan-400">
            <span className="w-2 h-2 rounded-full bg-cyan-400" />
            Throughput (Req/s)
          </span>
          <span className="flex items-center gap-1.5 text-purple-400">
            <span className="w-2 h-2 rounded-full bg-purple-400" />
            Latency (ms)
          </span>
        </div>
      </div>

      <div className="h-56 w-full min-h-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="cyanGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#00F3FF" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#00F3FF" stopOpacity={0.0} />
              </linearGradient>
              <linearGradient id="purpleGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#A855F7" stopOpacity={0.35} />
                <stop offset="95%" stopColor="#A855F7" stopOpacity={0.0} />
              </linearGradient>
            </defs>

            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
            <XAxis
              dataKey="time"
              stroke="#64748B"
              fontSize={11}
              tickLine={false}
              axisLine={false}
            />
            <YAxis stroke="#64748B" fontSize={11} tickLine={false} axisLine={false} />

            <Tooltip
              content={({ active, payload, label }) => {
                if (active && payload && payload.length) {
                  return (
                    <div className="rounded-xl border border-white/10 bg-slate-900/90 p-3 shadow-2xl backdrop-blur-xl text-xs font-mono">
                      <p className="text-slate-400 mb-1 font-semibold">{label}</p>
                      <p className="text-cyan-400 flex items-center justify-between gap-4">
                        <span>Throughput:</span>
                        <span className="font-bold">{payload[0]?.value} req/s</span>
                      </p>
                      <p className="text-purple-400 flex items-center justify-between gap-4 mt-0.5">
                        <span>Latency:</span>
                        <span className="font-bold">{payload[1]?.value} ms</span>
                      </p>
                    </div>
                  );
                }
                return null;
              }}
            />

            <Area
              type="monotone"
              dataKey="throughput"
              stroke="#00F3FF"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#cyanGradient)"
            />
            <Area
              type="monotone"
              dataKey="latency"
              stroke="#A855F7"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#purpleGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </SpotlightCard>
  );
};

export default LiveTelemetryChart;
