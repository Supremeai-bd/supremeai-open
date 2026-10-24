// apps/studio-client/src/components/dashboard/LiveSimulator.tsx
// বাংলা মন্তব্য: Magic Window — SVG Transformation Map, Chat node → Integration nodes, DAG health nodeStatus থেকে সরাসরি রেন্ডার হয়
import { motion, AnimatePresence, type Variants } from 'framer-motion';
import { AlertCircle } from 'lucide-react';
import type { IntegrationMeta } from '../../hooks/useWorkspaceSettings';
import type { DockActionResult, DockNodeStatus } from '../../hooks/useDynamicDock';

interface LiveSimulatorProps {
  // বাংলা মন্তব্য: aggregate status — Chat নোডের নিজস্ব পালস ড্রাইভ করে
  state: DockNodeStatus;
  nodeStatus: Record<string, DockActionResult>;
  enabledIntegrations: IntegrationMeta[];
}

const NODE_COLORS: Record<DockNodeStatus, { fill: string; glow: string; stroke: string }> = {
  idle: { fill: '#334155', glow: 'rgba(51,65,85,0)', stroke: '#475569' },
  pending: { fill: '#4338ca', glow: 'rgba(99,102,241,0.55)', stroke: '#818cf8' },
  success: { fill: '#059669', glow: 'rgba(16,185,129,0.65)', stroke: '#34d399' },
  error: { fill: '#be123c', glow: 'rgba(244,63,94,0.6)', stroke: '#fb7185' },
};

const chatPulse: Variants = {
  idle: { scale: [1, 1.04, 1], transition: { duration: 2.6, repeat: Infinity, ease: 'easeInOut' } },
  pending: { scale: [1, 1.1, 1], transition: { duration: 0.8, repeat: Infinity, ease: 'easeOut' } },
  success: { scale: [1, 1.06, 1], transition: { duration: 0.6 } },
  error: { scale: [1, 1.06, 1], transition: { duration: 0.6 } },
};

const LAYOUT = { width: 320, height: 340, chatX: 46, chatY: 170, nodeX: 262 };

function layoutY(index: number, total: number): number {
  if (total <= 1) return LAYOUT.chatY;
  const span = 240;
  const start = LAYOUT.chatY - span / 2;
  return start + (span / (total - 1)) * index;
}

export function LiveSimulator({ state, nodeStatus, enabledIntegrations }: LiveSimulatorProps) {
  const errorLogs = Object.entries(nodeStatus || {})
    .filter(([_, info]) => info.status === 'error')
    .map(([platform, info]) => ({ platform, message: info.message }));

  // বাংলা মন্তব্য: কোনো ইন্টিগ্রেশন enabled না থাকলে dummy নোড বসানো হয় না — খালি স্টেট সরাসরি জানানো হয়
  const integrations = enabledIntegrations || [];
  if (integrations.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-xs text-slate-500 px-6 text-center">
        No integrations enabled — turn one on in Sidebar → Integrations to see the transformation map.
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col w-full h-full p-4 overflow-hidden">
      <div className="flex-1 flex items-center justify-center relative min-h-[220px]">
      <svg
        viewBox={`0 0 ${LAYOUT.width} ${LAYOUT.height}`}
        className="w-full h-full max-h-[420px]"
        role="img"
        aria-label="Live orchestrator transformation map"
      >
        {integrations.map((integration, i) => {
          const status = nodeStatus[integration.id]?.status ?? 'idle';
          const y = layoutY(i, integrations.length);
          const colors = NODE_COLORS[status];
          const path = `M ${LAYOUT.chatX + 20} ${LAYOUT.chatY} C ${LAYOUT.chatX + 120} ${LAYOUT.chatY}, ${LAYOUT.nodeX - 100} ${y}, ${LAYOUT.nodeX - 20} ${y}`;

          return (
            <g key={integration.id}>
              {/* বাংলা মন্তব্য: pending হলে dash-flow অ্যানিমেশন — data physically চলছে এমন অনুভূতি দেয় */}
              <motion.path
                d={path}
                fill="none"
                stroke={colors.stroke}
                strokeWidth={status === 'idle' ? 1 : 2}
                strokeLinecap="round"
                strokeDasharray={status === 'pending' ? '6 6' : undefined}
                initial={false}
                animate={
                  status === 'pending'
                    ? { strokeDashoffset: [0, -24], opacity: 1 }
                    : { strokeDashoffset: 0, opacity: status === 'idle' ? 0.35 : 0.9 }
                }
                transition={
                  status === 'pending'
                    ? { duration: 0.9, repeat: Infinity, ease: 'linear' }
                    : { duration: 0.3 }
                }
              />

              <motion.circle
                cx={LAYOUT.nodeX}
                cy={y}
                r={16}
                fill={colors.fill}
                stroke={colors.stroke}
                strokeWidth={1.5}
                initial={false}
                animate={{
                  r: status === 'success' ? [16, 20, 16] : 16,
                  filter: `drop-shadow(0 0 ${status === 'idle' ? 0 : 8}px ${colors.glow})`,
                }}
                transition={{ duration: 0.5, ease: 'easeOut' }}
              />
              <text x={LAYOUT.nodeX} y={y + 30} textAnchor="middle" className="fill-slate-400" fontSize={9}>
                {integration.label}
              </text>
            </g>
          );
        })}

        {/* Chat node — root of the DAG visualization */}
        <motion.circle
          cx={LAYOUT.chatX}
          cy={LAYOUT.chatY}
          r={20}
          fill="#1e293b"
          stroke={NODE_COLORS[state].stroke}
          strokeWidth={2}
          variants={chatPulse}
          animate={state}
        />
        <text x={LAYOUT.chatX} y={LAYOUT.chatY + 36} textAnchor="middle" className="fill-slate-300 font-medium" fontSize={10}>
          Chat
        </text>
      </svg>
      </div>

      <AnimatePresence>
        {errorLogs.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0, marginTop: 0 }}
            animate={{ opacity: 1, height: 'auto', marginTop: 16 }}
            exit={{ opacity: 0, height: 0, marginTop: 0 }}
            className="w-full shrink-0"
          >
            <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl flex flex-col gap-2">
              <div className="flex items-center gap-2 text-rose-400 mb-1">
                <AlertCircle className="w-4 h-4" />
                <span className="font-semibold text-xs tracking-wide uppercase">Incident Dashboard</span>
              </div>
              <div className="max-h-28 overflow-y-auto space-y-1.5 pr-1 custom-scrollbar">
                {errorLogs.map((log) => (
                  <div key={log.platform} className="bg-slate-900/60 p-2 rounded-lg border border-rose-500/10">
                    <span className="text-rose-400 font-medium capitalize text-[11px] block mb-0.5">{log.platform} Incident</span>
                    <span className="text-slate-300 font-mono text-[10px] break-all leading-tight">{log.message}</span>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
