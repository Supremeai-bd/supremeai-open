import React, { useEffect, useState } from 'react';
import { Activity, Server, Database, CheckCircle, Terminal, DollarSign, Users, Settings, Zap, Cloud, Eye, ShieldAlert, FileText, GitMerge, GitBranch, Save, Clock, Network } from 'lucide-react';
import { fetchJavaWorkerHealth } from '../../../services/api/microserviceMonitor';
import type { JavaWorkerHealth } from '../../../services/api/microserviceMonitor';
import { useAdminStore } from '../../../store/adminStore';
import type { AdminSubTab } from '../../../types';
import { getApiBaseUrl } from '../../../utils/api';
import { getRawToken } from '../../../services/apiClient';
import { createSecureEventSource } from '../../../lib/secureSse';
// বাংলা মন্তব্য: জাভা ওয়ার্কার মেট্রিক্স ও কুইক নেভিগেশন প্যানেল — সব থিমের সাথে সামঞ্জস্যপূর্ণ
export const ServiceHealthMetrics: React.FC = () => {
  const [metrics, setMetrics] = useState<JavaWorkerHealth | null>(null);
  const setAdminSubTab = useAdminStore(state => state.setAdminSubTab);

  useEffect(() => {
    const loadMetrics = async () => {
      const data = await fetchJavaWorkerHealth();
      setMetrics(data);
    };
    loadMetrics();

    const backendUrl = getApiBaseUrl();
    const token = getRawToken();
    const sse = createSecureEventSource(`${backendUrl}/api/dashboard/stream`, token, {
      onMessage: (e) => {
        if (e.type === 'metrics_events') {
          loadMetrics();
        }
      }
    });

    return () => sse.close();
  }, []);

  // বাংলা মন্তব্য: ১৮টি অ্যাডমিন ট্যাবের জন্য নেভিগেশন বাটন
  const navButtons: { id: AdminSubTab; label: string; icon: React.ReactNode; color: string }[] = [
    { id: 'command-center', label: 'Central ORC', icon: <Server size={14} />, color: 'text-[var(--text-main)]' },
    { id: 'sandbox', label: 'Sandbox', icon: <Terminal size={14} />, color: 'text-[var(--text-secondary)]' },
    { id: 'logs', label: 'Logs', icon: <Activity size={14} />, color: 'text-blue-500' },
    { id: 'costs', label: 'Costs', icon: <DollarSign size={14} />, color: 'text-green-500' },
    { id: 'health', label: 'Health', icon: <CheckCircle size={14} />, color: 'text-emerald-500' },
    { id: 'users', label: 'Users', icon: <Users size={14} />, color: 'text-purple-500' },
    { id: 'config', label: 'Config', icon: <Settings size={14} />, color: 'text-[var(--text-secondary)]' },
    { id: 'model-router', label: 'Router', icon: <Network size={14} />, color: 'text-indigo-500' },
    { id: 'skills', label: 'Skills', icon: <Zap size={14} />, color: 'text-yellow-500' },
    { id: 'memory', label: 'Memory', icon: <Database size={14} />, color: 'text-cyan-500' },
    { id: 'cloud', label: 'Cloud', icon: <Cloud size={14} />, color: 'text-sky-500' },
    { id: 'observability', label: 'Observe', icon: <Eye size={14} />, color: 'text-teal-500' },
    { id: 'threats', label: 'Threats', icon: <ShieldAlert size={14} />, color: 'text-red-500' },
    { id: 'rules', label: 'Rules', icon: <FileText size={14} />, color: 'text-orange-500' },
    { id: 'cicd', label: 'CI/CD', icon: <GitMerge size={14} />, color: 'text-pink-500' },
    { id: 'github', label: 'GitHub', icon: <GitBranch size={14} />, color: 'text-slate-400' },
    { id: 'backups', label: 'Backups', icon: <Save size={14} />, color: 'text-lime-500' },
    { id: 'rate-limits', label: 'Limits', icon: <Clock size={14} />, color: 'text-rose-500' }
  ];

  if (!metrics) return <div className="text-[var(--text-secondary)] p-2 text-xs font-mono">Loading Worker Metrics...</div>;

  return (
    <div className="bg-[var(--bg-panel)] border border-[var(--border-accent)] rounded-xl p-3 shadow-lg relative overflow-hidden group backdrop-blur-xl w-80 transition-all duration-500">

      {/* Java Metrics Section (Compact) */}
      <div className="flex items-center justify-between mb-2 relative z-10 border-b border-[var(--border-accent)] pb-2 transition-colors duration-500">
        <h3 className="text-xs font-bold text-[var(--accent-primary)] flex items-center gap-1.5 uppercase tracking-wider font-mono">
          <Server size={12} className="animate-pulse" />
          Java Background Worker
        </h3>
        <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold tracking-widest uppercase ${metrics.status === 'HEALTHY' ? 'bg-green-500/20 text-[var(--accent-secondary)] border border-green-500/50' : 'bg-red-500/20 text-[var(--danger)] border border-red-500/50'}`}>
          {metrics.status}
        </span>
      </div>

      <div className="grid grid-cols-4 gap-1.5 relative z-10 mb-3">
        {[
          { label: 'CPU', value: `${metrics.cpuLoadPercentage}%` },
          { label: 'Mem', value: `${metrics.memoryUsageMb}M` },
          { label: 'Tasks', value: `${metrics.activeTasks}` },
          { label: 'Done', value: `${metrics.totalTasksProcessed}` }
        ].map((item) => (
          <div key={item.label} className="bg-[var(--bg-cell)] rounded p-1.5 border border-[var(--border-accent)] flex flex-col items-center justify-center transition-colors duration-500">
            <div className="text-[8px] text-[var(--text-secondary)] uppercase font-bold tracking-wider mb-0.5">{item.label}</div>
            <div className="text-xs font-mono text-[var(--text-main)]">{item.value}</div>
          </div>
        ))}
      </div>

      {/* Quick Navigation Section — বাটন গুলো নির্দিষ্ট ট্যাবে নেভিগেট করবে */}
      <div className="relative z-10 border-t border-[var(--border-accent)] pt-2 transition-colors duration-500">
        <div className="text-[9px] text-[var(--accent-primary)] uppercase font-bold tracking-widest mb-2 px-1">Quick Navigate</div>
        <div className="grid grid-cols-3 gap-1.5">
          {navButtons.map((btn) => (
            <button
              key={btn.id}
              onClick={() => setAdminSubTab(btn.id)}
              className="flex items-center gap-1.5 bg-[var(--bg-cell)] hover:bg-[var(--border-accent)] border border-transparent hover:border-[var(--border-accent)] rounded p-1.5 transition-all active:scale-95 group/btn cursor-pointer"
              title={btn.label}
            >
              <div className={`${btn.color} group-hover/btn:scale-110 transition-transform`}>{btn.icon}</div>
              <span className="text-[9px] font-medium text-[var(--text-secondary)] group-hover/btn:text-[var(--text-main)] truncate">{btn.label}</span>
            </button>
          ))}
        </div>
      </div>

    </div>
  );
};
