/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useState, useEffect } from 'react';
import { X, Rocket, CheckCircle2, Loader2, AlertCircle, Shield, GitBranch } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../../services/apiClient';
import { useDashboardStore } from '../../../store/dashboardStore';

export interface DeploymentTarget {
  region: 'us-central1' | 'us-east1' | 'eu-west1';
  service: string;
}

export interface DeployRequest {
  target: DeploymentTarget;
}

export interface DeploymentStatus {
  status: 'pending' | 'running' | 'success' | 'failed';
  message: string;
  build_id?: string;
  url?: string;
  started_at?: number;
  finished_at?: number;
}

interface DeploymentModalProps {
  initialLogs?: Array<{ status: string; message: string }>;
}

const DeploymentModal: React.FC<DeploymentModalProps> = ({
  initialLogs = []
}) => {
  const isDeploymentModalOpen = useDashboardStore((s) => s.isDeploymentModalOpen);
  const setDeploymentModal = useDashboardStore((s) => s.setDeploymentModal);

  const [target, setTarget] = useState<DeploymentTarget['region']>('us-central1');
  const [logs, setLogs] = useState<Array<{ status: string; message: string; branch?: string; created_at?: number }>>(initialLogs);
  const [deploymentStatus, setDeploymentStatus] = useState<DeploymentStatus | null>(null);

  // পোস্ট-ডিপ্লয় লগ লোড করার জন্য CI রিপোর্ট হুক ব্যবহার করা হচ্ছে
  const { data: ciLogs } = useQuery({
    queryKey: ['deployment-logs'],
    queryFn: () => apiClient.get('/admin-api/ci-logs?limit=10'),
    refetchInterval: (query: any) => query.state.error ? false : 15000,
    enabled: isDeploymentModalOpen,
  });

  // ডিপ্লয় মিউটেশন - ডিপ্লয়মেন্ট লাইফসাইকেল ম্যানেজ করার জন্য
  const deployMutation = useMutation({
    mutationFn: () =>
      apiClient.post<{ message: string }>('/admin-api/deploy', {
        target: { region: target, service: 'supremeai-api' },
      }),
    onSuccess: async (data) => {
      const buildId = data.message?.match(/build\/([a-zA-Z0-9_-]+)/)?.[1];
      setLogs((prev) => [...prev, { status: 'INFO', message: data.message }]);
      setDeploymentStatus({ status: 'running', message: 'Deployment started...', build_id: buildId });
    },
    onError: (err) => {
      setDeploymentStatus({ status: 'failed', message: err instanceof Error ? err.message : 'Deployment failed' });
      setLogs((prev) => [...prev, { status: 'ERROR', message: 'Deployment failed' }]);
    },
  });

  // ডিপ্লয় স্ট্যাটাস পোলিং
  useEffect(() => {
    if (!isDeploymentModalOpen) return;
    let failureCount = 0;
    const interval = setInterval(async () => {
      if (!deploymentStatus || deploymentStatus.status !== 'running') return;
      try {
        const statusRes = await apiClient.get<DeploymentStatus>(`/admin-api/deploy-status/${deploymentStatus.build_id}`);
        setDeploymentStatus({
          ...statusRes,
          url: statusRes.url || deploymentStatus.url,
        });
        failureCount = 0; // reset on success
      } catch (err) {
        failureCount += 1;
        console.warn(`[Deployment] Polling failed (${failureCount}/5):`, err);
        if (failureCount >= 5) {
          setDeploymentStatus({
            status: 'failed',
            message: 'Deployment status could not be retrieved. Connection lost.'
          });
          setLogs((prev) => [...prev, { status: 'ERROR', message: 'Deployment status checking failed. Polling stopped.' }]);
          clearInterval(interval);
        }
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [isDeploymentModalOpen, deploymentStatus]);

  // CI লগগুলো প্রসেস করে ডিসপ্লেবল লগে রূপান্তরকারী
  useEffect(() => {
    if (!ciLogs) return;

    // বাংলা মন্তব্য: set-state-in-effect ফিক্স — লগ প্রসেসিং async ফাংশনের ভেতরে করা হয়েছে
    const processCILogs = async () => {
      const resolved = (Array.isArray(ciLogs) ? ciLogs : []).map((log: { status?: string; message?: string; commit_message?: string; branch?: string; created_at?: number }) => ({
        status: log.status || 'INFO',
        message: log.message || log.commit_message || 'Pipeline event',
        branch: log.branch,
        created_at: log.created_at,
      }));
      setLogs((prev) => (prev.length ? [...prev, ...resolved] : resolved));
    };

    processCILogs();
  }, [ciLogs]);

  const queryClient = useQueryClient();

  useEffect(() => {
    if (isDeploymentModalOpen && !deploymentStatus) {
      if (ciLogs && Array.isArray(ciLogs) && ciLogs.length > 0) {
        // বাংলা মন্তব্য: set-state-in-effect ফিক্স — ডিপ্লয়মেন্ট স্ট্যাটাস সেট করা async ফাংশনের ভেতরে করা হয়েছে
        const initDeploymentStatus = async () => {
          const latest = ciLogs[0];
          const mapped = { status: latest.status || 'INFO', message: latest.message || latest.commit_message || 'Pipeline event' };
          setDeploymentStatus({
            status: mapped.status === 'success' ? 'success' : mapped.status === 'failed' ? 'failed' : 'running',
            message: mapped.message,
            url: mapped.status === 'success' ? 'https://supremeai-api-565236080752.us-central1.run.app' : undefined,
          });
        };

        initDeploymentStatus();
      }
    }
  }, [isDeploymentModalOpen, ciLogs, deploymentStatus]);

  const handleDeploy = () => {
    setLogs([]);
    setDeploymentStatus(null);
    deployMutation.mutate();
  };

  const handleClose = () => {
    setDeploymentModal(false);
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'success':
        return 'text-[#00ff66]';
      case 'failed':
        return 'text-[#ff0055]';
      case 'running':
        return 'text-[#ffaa00]';
      default:
        return 'text-slate-400';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success':
        return <CheckCircle2 size={14} className="text-[#00ff66]" />;
      case 'failed':
        return <AlertCircle size={14} className="text-[#ff0055]" />;
      case 'running':
        return <Loader2 size={14} className="animate-spin text-[#ffaa00]" />;
      default:
        return <Shield size={14} className="text-slate-400" />;
    }
  };

  return (
    <AnimatePresence>
      {isDeploymentModalOpen && (
        <motion.div
          initial={{ opacity: 0, backdropFilter: 'blur(0px)' }}
          animate={{ opacity: 1, backdropFilter: 'blur(8px)' }}
          exit={{ opacity: 0, backdropFilter: 'blur(0px)' }}
          transition={{ duration: 0.3 }}
          className="fixed inset-0 bg-slate-950/80 z-[999] flex items-center justify-center"
        >
          <motion.div
            initial={{ scale: 0.95, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.95, y: 20 }}
            transition={{ type: 'spring', damping: 20, stiffness: 100 }}
            className="w-[500px] max-h-[85vh] sci-fi-glass-panel rounded-2xl p-6 flex flex-col shadow-[0_0_40px_rgba(0,243,255,0.15)]"
          >
            <div className="flex items-center justify-between border-b border-[rgba(0,243,255,0.25)] pb-4 mb-4">
              <div className="flex items-center gap-3">
                <Rocket size={18} className="text-[#00f3ff]" />
                <h3 className="text-base font-mono font-bold text-white uppercase tracking-widest">
                  One-Click Deploy
                </h3>
              </div>
              <button
                onClick={handleClose}
                className="text-[#00f3ff] hover:text-white bg-[#00f3ff]/10 hover:bg-[#00f3ff]/30 p-1.5 rounded-lg transition-colors border border-[#00f3ff]/30"
              >
                <X size={18} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-4">
              <div className="sci-fi-glass rounded-lg p-4 space-y-3">
                <label className="text-[10px] font-mono text-[#00f3ff] uppercase tracking-widest block mb-2">
                  select target region
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {(['us-central1', 'us-east1', 'eu-west1'] as const).map((region) => (
                    <button
                      key={region}
                      onClick={() => setTarget(region)}
                      className={`py-2 px-3 rounded-md text-xs font-mono font-bold uppercase transition-all ${
                        target === region
                          ? 'bg-[#00f3ff]/20 text-[#00f3ff] border border-[#00f3ff] shadow-[0_0_10px_rgba(0,243,255,0.3)]'
                          : 'bg-slate-900/50 text-slate-400 border border-slate-700 hover:border-slate-500'
                      }`}
                    >
                      {region.replace('us-', 'US-').replace('eu-', 'EU-')}
                    </button>
                  ))}
                </div>
              </div>

              <div className="sci-fi-glass rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <GitBranch size={12} className="text-[#00f3ff]" />
                  <span className="text-[10px] font-mono text-[#00f3ff] uppercase tracking-widest">Deployment Logs</span>
                </div>
                <div className="space-y-2 max-h-48 overflow-y-auto font-mono text-[11px]">
                  {logs.length === 0 ? (
                    <div className="text-slate-400 text-[10px] italic">
                      Waiting for deployment to start...
                    </div>
                  ) : (
                    logs.map((log, idx) => (
                      <div key={idx} className="flex items-start gap-2">
                        {getStatusIcon(log.status)}
                        <div className="flex-1">
                          <span className={getStatusColor(log.status)}>[{log.status}]</span>{' '}
                          <span className="text-slate-300">{log.message}</span>
                          {log.branch && (
                            <span className="text-slate-400 ml-2">({log.branch})</span>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {deploymentStatus && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`sci-fi-glass rounded-lg p-4 border ${
                    deploymentStatus.status === 'success'
                      ? 'border-[#00ff66]/40'
                      : deploymentStatus.status === 'failed'
                      ? 'border-[#ff0055]/40'
                      : 'border-[#ffaa00]/40'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    {deploymentStatus.status === 'success' ? (
                      <CheckCircle2 size={14} className="text-[#00ff66]" />
                    ) : deploymentStatus.status === 'failed' ? (
                      <AlertCircle size={14} className="text-[#ff0055]" />
                    ) : (
                      <Loader2 size={14} className="animate-spin text-[#ffaa00]" />
                    )}
                    <span className={`text-xs font-mono font-bold uppercase tracking-widest ${getStatusColor(deploymentStatus.status)}`}>
                      {deploymentStatus.status}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-300 font-mono">{deploymentStatus.message}</p>
                  {deploymentStatus.url && (
                    <a
                      href={deploymentStatus.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[#00f3ff] hover:text-white text-[11px] font-mono underline mt-2 inline-block"
                    >
                      {deploymentStatus.url}
                    </a>
                  )}
                </motion.div>
              )}
            </div>

            <div className="mt-4 pt-4 border-t border-[rgba(0,243,255,0.2)] flex gap-3">
              <button
                onClick={handleClose}
                className="flex-1 bg-slate-900/50 hover:bg-slate-800/50 text-slate-400 hover:text-white font-mono font-bold py-2.5 rounded-lg transition-colors border border-slate-700 uppercase tracking-widest text-xs"
              >
                Close
              </button>
              <button
                onClick={handleDeploy}
                disabled={deployMutation.isPending || (deploymentStatus?.status === 'running')}
                className="flex-1 bg-[#00f3ff]/20 hover:bg-[#00f3ff]/40 text-[#00f3ff] hover:text-white font-mono font-bold py-2.5 rounded-lg transition-colors border border-[#00f3ff] shadow-[0_0_15px_rgba(0,243,255,0.3)] hover:shadow-[0_0_25px_rgba(0,243,255,0.6)] uppercase tracking-widest text-xs disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {deployMutation.isPending ? (
                  <span className="flex items-center justify-center gap-2">
                    <Loader2 size={12} className="animate-spin" />
                    Deploying...
                  </span>
                ) : (
                  <span className="flex items-center justify-center gap-2">
                    <Rocket size={12} />
                    Deploy Now
                  </span>
                )}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default DeploymentModal;

