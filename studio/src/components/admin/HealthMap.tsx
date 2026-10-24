/* eslint-disable @typescript-eslint/no-explicit-any */
interface HealthMapProps {
  healthMap: any;
}

export function HealthMap({ healthMap }: HealthMapProps) {
  const providers = [
    {
      id: "gcp",
      name: "Google Cloud Platform",
      status: "ACTIVE",
      latency: healthMap?.gcp?.latency ?? "—",
      region: healthMap?.gcp?.region ?? "—",
      endpoint: "https://gcp.supremeai.dev/health",
      colorClass: "bg-emerald-950 text-emerald-400 border-emerald-900/60",
      statusDot: "bg-emerald-400",
      uptime: "—"
    },
    {
      id: "railway",
      name: "Railway Host",
      status: "ACTIVE",
      latency: healthMap?.railway?.latency ?? "—",
      region: healthMap?.railway?.region ?? "—",
      endpoint: "https://railway.supremeai.dev/health",
      colorClass: "bg-emerald-950 text-emerald-400 border-emerald-900/60",
      statusDot: "bg-emerald-400",
      uptime: "—"
    },
    {
      id: "render",
      name: "Render Deploy",
      status: healthMap?.render?.status ?? "UNKNOWN",
      latency: healthMap?.render?.latency ?? "—",
      region: healthMap?.render?.region ?? "—",
      endpoint: "https://render.supremeai.dev/health",
      colorClass: "bg-yellow-950/80 text-yellow-400 border-yellow-900/60",
      statusDot: "bg-yellow-400",
      uptime: "—"
    },
    {
      id: "cloudflare",
      name: "Cloudflare Edge",
      status: healthMap?.cloudflare?.status ?? "UNKNOWN",
      latency: healthMap?.cloudflare?.latency ?? "—",
      region: healthMap?.cloudflare?.region ?? "—",
      endpoint: "https://cf.supremeai.dev/health",
      colorClass: "bg-emerald-950 text-emerald-400 border-emerald-900/60",
      statusDot: "bg-emerald-400",
      uptime: "—"
    }
  ];

  return (
    <div className="flex-grow bg-[#030611] p-6 overflow-y-auto font-sans">
      <div className="flex items-center justify-between mb-6 pb-2 border-b border-slate-800">
        <h3 className="text-sm font-bold text-slate-200 tracking-wider font-mono">📡 SYSTEM HEALTH MAP</h3>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
          <span className="text-[10px] text-emerald-400 font-mono">{healthMap?.overall_status ?? 'STATUS UNKNOWN'}</span>
        </div>
      </div>

      {/* Health Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-[#090a0f] border border-slate-900 rounded-xl p-4 flex flex-col">
          <span className="text-[10px] text-slate-400 font-mono uppercase">Overall Uptime</span>
          <span className="text-xl font-bold text-white mt-1 font-mono">{healthMap?.overall_uptime ?? '—'}</span>
        </div>
        <div className="bg-[#090a0f] border border-slate-900 rounded-xl p-4 flex flex-col">
          <span className="text-[10px] text-slate-400 font-mono uppercase">Edge Latency</span>
          <span className="text-xl font-bold text-[#00f3ff] mt-1 font-mono">{healthMap?.edge_latency ?? '—'}</span>
        </div>
        <div className="bg-[#090a0f] border border-slate-900 rounded-xl p-4 flex flex-col">
          <span className="text-[10px] text-slate-400 font-mono uppercase">Active Clusters</span>
          <span className="text-xl font-bold text-white mt-1 font-mono">{healthMap?.active_clusters ?? '—'}</span>
        </div>
        <div className="bg-[#090a0f] border border-slate-900 rounded-xl p-4 flex flex-col">
          <span className="text-[10px] text-slate-400 font-mono uppercase">Error Rate (24h)</span>
          <span className="text-xl font-bold text-[#00ff66] mt-1 font-mono">{healthMap?.error_rate_24h ?? '—'}</span>
        </div>
      </div>

      {/* Providers Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {providers.map(prov => (
          <div key={prov.id} className="bg-[#0c0d12]/80 border border-slate-900 rounded-xl p-5 flex flex-col gap-4">
            <div className="flex justify-between items-center">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${prov.statusDot} ${prov.status === 'ACTIVE' && 'animate-pulse'}`} />
                <span className="font-bold text-xs text-white tracking-wide font-mono">{prov.name}</span>
              </div>
              <span className={`px-2 py-0.5 text-[9px] font-bold rounded border ${prov.colorClass} font-mono`}>
                {prov.status}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-[11px] font-mono text-slate-400">
              <div>Region: <span className="text-slate-200">{prov.region}</span></div>
              <div>Latency: <span className="text-slate-200">{prov.latency}</span></div>
              <div>Uptime: <span className="text-[#00ff66]">{prov.uptime}</span></div>
              <div>Endpoint: <span className="text-slate-400 truncate block max-w-[150px]">{prov.endpoint}</span></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

