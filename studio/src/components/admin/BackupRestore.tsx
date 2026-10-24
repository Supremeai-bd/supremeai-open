import { Card } from '../ui';
import { Database, RefreshCw, Download, Upload, Shield, Clock, HardDrive } from 'lucide-react';
import { useState, useEffect } from 'react';
import { apiClient } from '../../services/apiClient';

export interface Backup {
  id: string;
  timestamp: string;
  size: string;
  type: string;
  status: string;
  retention: string;
}

export function BackupRestore() {
  const [maintenanceMode, setMaintenanceMode] = useState(false);
  const [backups, setBackups] = useState<Backup[]>([]);

  const fetchBackups = async () => {
    try {
      const res = await apiClient.get<{ backups: Backup[] }>('/admin-api/backups');
      setBackups(res.backups || []);
    } catch (e: unknown) {
      console.error("Failed to fetch backups", e);
    }
  };

  useEffect(() => {
    fetchBackups();
  }, []);

  const triggerBackup = async () => {
    const tempId = `pending-${Date.now()}`;
    const newBackup = {
      id: tempId,
      timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19),
      size: '—',
      type: 'manual' as const,
      status: 'in_progress' as const,
      retention: 'permanent',
    };
    setBackups([newBackup, ...backups]);

    try {
      await apiClient.post<{ status: string; backup_path: string }>('/admin-api/backup');
      await fetchBackups(); // Refresh the list
    } catch (e: unknown) {
      setBackups(prev => prev.filter(b => b.id !== tempId));
      alert(`❌ Backup failed: ${e instanceof Error ? e.message : 'Unknown error'}`);
    }
  };

  return (
    <div className="flex-grow p-6 overflow-y-auto bg-[#030611]">
      <div className="flex items-center justify-between mb-6 pb-2 border-b border-[#00f3ff]/15">
        <h2 className="text-lg font-bold font-['Space_Grotesk'] tracking-widest text-[#00f3ff] uppercase">
          💾 Backup & System Maintenance
        </h2>
        <div className="flex gap-2">
          <button
            onClick={triggerBackup}
            className="flex items-center gap-2 px-3 py-1.5 rounded border border-[#00f3ff]/30 text-[#00f3ff] hover:bg-[#00f3ff]/10 text-[10px] font-bold font-mono uppercase transition-colors"
          >
            <Download size={10} /> Backup Now
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Card title="Total Backups">
          <div className="flex items-center gap-3">
            <Database size={20} className="text-[#00f3ff]" />
            <div>
              <div className="text-2xl font-bold text-white font-mono">{backups.length}</div>
              <div className="text-[10px] text-slate-400">Last 30 days</div>
            </div>
          </div>
        </Card>
        <Card title="Storage Used">
          <div className="flex items-center gap-3">
            <HardDrive size={20} className="text-purple-400" />
            <div>
              <div className="text-2xl font-bold text-white font-mono">9.2 GB</div>
              <div className="text-[10px] text-slate-400">of 100 GB</div>
            </div>
          </div>
        </Card>
        <Card title="Last Backup">
          <div className="flex items-center gap-3">
            <Clock size={20} className="text-emerald-400" />
            <div>
              <div className="text-sm font-bold text-white font-mono">Today 03:00</div>
              <div className="text-[10px] text-slate-400">Automatic</div>
            </div>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Backup History">
          <div className="flex flex-col gap-2">
            {backups.map(backup => (
              <div key={backup.id} className="flex items-center justify-between p-3 rounded-lg border border-slate-800 bg-slate-900/30">
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                    backup.status === 'completed' ? 'bg-emerald-950 text-emerald-400' :
                    backup.status === 'in_progress' ? 'bg-yellow-950 text-yellow-400 animate-pulse' :
                    'bg-red-950 text-red-400'
                  }`}>
                    {backup.status === 'in_progress' ? <RefreshCw size={14} className="animate-spin" /> : <Database size={14} />}
                  </div>
                  <div>
                    <div className="text-xs font-bold text-white font-mono">{backup.timestamp}</div>
                    <div className="text-[10px] text-slate-400 font-mono flex items-center gap-2">
                      <span>{backup.size}</span>
                      <span>•</span>
                      <span>{backup.type}</span>
                      <span>•</span>
                      <span>{backup.retention}</span>
                    </div>
                  </div>
                </div>
                <div className="flex gap-2">
                  {backup.status === 'completed' && (
                    <button className="text-[10px] text-[#00f3ff] hover:text-cyan-300 font-mono flex items-center gap-1 px-2 py-1 rounded border border-[#00f3ff]/30">
                      <Upload size={10} /> Restore
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Maintenance Mode">
          <div className="flex flex-col gap-4">
            <div className="p-4 rounded-lg border border-slate-800 bg-slate-900/30">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Shield size={14} className={maintenanceMode ? 'text-yellow-400' : 'text-slate-400'} />
                  <span className="text-xs font-bold text-white">Maintenance Mode</span>
                </div>
                <button
                  onClick={() => setMaintenanceMode(!maintenanceMode)}
                  className={`w-10 h-5 rounded-full transition-colors ${maintenanceMode ? 'bg-yellow-500' : 'bg-slate-700'}`}
                >
                  <div className={`w-4 h-4 rounded-full bg-white transition-transform ${maintenanceMode ? 'translate-x-5' : 'translate-x-0.5'}`} />
                </button>
              </div>
              {maintenanceMode ? (
                <div className="text-[10px] text-yellow-400 font-mono">
                  ⚠️ System is in maintenance mode. Users will see a maintenance page.
                </div>
              ) : (
                <div className="text-[10px] text-slate-400 font-mono">
                  System is operational. Enable to show maintenance page to users.
                </div>
              )}
            </div>

            <div className="p-4 rounded-lg border border-slate-800 bg-slate-900/30">
              <div className="text-xs font-bold text-white mb-3">Quick Actions</div>
              <div className="flex flex-col gap-2">
                <button className="flex items-center gap-2 px-3 py-2 rounded border border-slate-800 text-slate-400 hover:text-white text-[10px] font-mono transition-colors">
                  <RefreshCw size={12} /> Flush Redis Cache
                </button>
                <button className="flex items-center gap-2 px-3 py-2 rounded border border-slate-800 text-slate-400 hover:text-white text-[10px] font-mono transition-colors">
                  <HardDrive size={12} /> Rebuild Search Index
                </button>
                <button className="flex items-center gap-2 px-3 py-2 rounded border border-slate-800 text-slate-400 hover:text-white text-[10px] font-mono transition-colors">
                  <Database size={12} /> Vacuum Database
                </button>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
