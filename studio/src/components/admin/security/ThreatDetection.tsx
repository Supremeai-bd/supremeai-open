import { Card, Badge } from '../../ui';
import { Shield, AlertTriangle, Eye, CheckCircle2, XCircle } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../../../services/apiClient';
import { adminTokenStore } from '../../../services/adminTokenStore';

const severityConfig: Record<string, { variant: 'danger' | 'warning' | 'info' | 'success'; icon: typeof Shield }> = {
  critical: { variant: 'danger', icon: AlertTriangle },
  high: { variant: 'danger', icon: Shield },
  medium: { variant: 'warning', icon: Eye },
  low: { variant: 'info', icon: Shield },
};

interface FindingItem {
  severity?: string;
  item?: string;
  title?: string;
  source?: string;
  timestamp?: string;
  message?: string;
  description?: string;
}

interface SecurityScanResponse {
  findings?: FindingItem[];
  total_findings?: number;
  status?: string;
  scan_time?: string;
}

export function ThreatDetection() {
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard', 'security-scan'],
    queryFn: () => apiClient.get<SecurityScanResponse>('/admin-api/security-scan'),
    enabled: !!adminTokenStore.getDecodedToken(),
    refetchInterval: 30_000,
  });

  const findings = Array.isArray(data?.findings) ? data.findings : [];
  const total = data?.total_findings ?? findings.length;
  const threats = findings
    .filter((f: FindingItem) => f.severity === 'critical' || f.severity === 'high' || f.severity === 'medium')
    .map((f: FindingItem, i: number) => ({
      id: i + 1,
      type: f.item ? String(f.item).replace(/_/g, ' ') : (f.title || 'Threat'),
      severity: f.severity,
      source: f.source || 'system',
      timestamp: f.timestamp || '',
      blocked: f.severity !== 'low',
      snippet: f.message || f.description || '',
    }));

  return (
    <div className="flex-grow p-6 overflow-y-auto bg-[#030611]">
      <div className="flex items-center justify-between mb-6 pb-2 border-b border-[#00f3ff]/15">
        <h2 className="text-lg font-bold font-['Space_Grotesk'] tracking-widest text-red-400 uppercase">
          🛡️ Security & Threat Center
        </h2>
        <div className="flex gap-2">
          <Badge variant="danger">{total} FINDINGS</Badge>
          <Badge variant={total === 0 ? 'success' : 'warning'}>{total === 0 ? 'SECURE' : 'MONITORED'}</Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Card title="Security Score" className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Shield size={20} className={total === 0 ? 'text-emerald-400' : 'text-amber-400'} />
            <div>
              <div className="text-xs text-slate-400">Overall Grade</div>
              <div className="text-2xl font-bold text-emerald-400 font-mono">{total === 0 ? 'A' : 'B-'}</div>
            </div>
          </div>
        </Card>
        <Card title="Detected Findings">
          <div className="text-2xl font-bold text-red-400 font-mono">{total}</div>
          <div className="text-[10px] text-slate-400">from live security scan</div>
        </Card>
        <Card title="Scan Status">
          <div className="text-2xl font-bold text-yellow-400 font-mono">{isLoading ? '...' : (data?.status || 'idle')}</div>
          <div className="text-[10px] text-slate-400">{data?.scan_time ? new Date(data.scan_time).toLocaleString() : 'auto every 30s'}</div>
        </Card>
      </div>

      <Card title="Recent Threat Events">
        <div className="flex flex-col gap-2">
          {isLoading && threats.length === 0 ? (
            <div className="text-center py-8 text-slate-500 font-mono text-xs">Scanning...</div>
          ) : threats.length === 0 ? (
            <div className="text-center py-8 text-slate-500 font-mono text-xs">No threats detected. System secure.</div>
          ) : (
            threats.map(t => {
            const config = severityConfig[t.severity ?? 'low'] || severityConfig.low;
            return (
              <div key={t.id} className="p-3 rounded-lg border border-slate-800 bg-slate-900/30 flex items-center gap-4">
                <config.icon size={14} className={`flex-shrink-0 ${
                  t.severity === 'critical' ? 'text-red-400' :
                  t.severity === 'high' ? 'text-red-400' :
                  t.severity === 'medium' ? 'text-yellow-400' : 'text-cyan-400'
                }`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-bold text-white font-mono">{t.type}</span>
                    <Badge variant={config.variant}>{(t.severity ?? 'low').toUpperCase()}</Badge>
                    {t.blocked ? <Badge variant="success"><CheckCircle2 size={10} /> BLOCKED</Badge> : <Badge variant="warning"><XCircle size={10} /> ALLOWED</Badge>}
                  </div>
                  <div className="text-[10px] text-slate-400 font-mono">
                    Source: {t.source} • {t.timestamp}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-1 truncate">"{t.snippet}"</div>
                </div>
                <button className="text-[10px] text-[#00f3ff] hover:text-cyan-300 font-mono px-2 py-1 rounded border border-[#00f3ff]/30">
                  Details
                </button>
              </div>
            );
          })
          )}
        </div>
      </Card>
    </div>
  );
}
