// apps/studio-client/src/components/dashboard/LivingActionDock.tsx
// বাংলা মন্তব্য: real dnd-kit droppable targets per enabled integration — status visuals driven purely by the nodeStatus prop
import { useDroppable } from '@dnd-kit/core';
import { AnimatePresence, motion, type Variants } from 'framer-motion';
import { GitBranch, Hash, FileText, CheckCircle2, AlertTriangle, Loader2 } from 'lucide-react';
import type { IntegrationMeta } from '../../hooks/useWorkspaceSettings';
import type { DockActionResult } from '../../hooks/useDynamicDock';

interface LivingActionDockProps {
  enabledIntegrations: IntegrationMeta[];
  nodeStatus: Record<string, DockActionResult>;
}

const ICON_MAP: Record<IntegrationMeta['icon'], React.ComponentType<{ size?: number; className?: string }>> = {
  Github: GitBranch,
  Slack: Hash,
  FileText,
};

// বাংলা মন্তব্য: প্রতিটি স্ট্যাটাসের জন্য variant — dnd-kit-এর isOver স্টেট এর সাথে conflict না করার জন্য বর্ডার/রিং আলাদা রাখা হয়েছে
const nodeVariants: Variants = {
  idle: {
    scale: [1, 1.035, 1],
    opacity: [0.82, 1, 0.82],
    boxShadow: '0 0 0 0 rgba(99,102,241,0)',
    transition: { duration: 3.2, repeat: Infinity, ease: 'easeInOut' },
  },
  pending: {
    scale: [1, 1.09, 1],
    boxShadow: [
      '0 0 0 0 rgba(99,102,241,0.55)',
      '0 0 0 10px rgba(99,102,241,0)',
      '0 0 0 0 rgba(99,102,241,0)',
    ],
    transition: { duration: 0.65, repeat: Infinity, ease: 'easeOut' },
  },
  success: {
    scale: [1, 1.18, 1],
    backgroundColor: ['rgba(16,185,129,0.05)', 'rgba(16,185,129,0.35)', 'rgba(16,185,129,0.08)'],
    boxShadow: ['0 0 0 0 rgba(16,185,129,0)', '0 0 24px 4px rgba(16,185,129,0.6)', '0 0 0 0 rgba(16,185,129,0)'],
    transition: { duration: 0.55, ease: 'easeOut' },
  },
  error: {
    x: [0, -7, 7, -6, 6, -3, 3, 0],
    backgroundColor: ['rgba(244,63,94,0.05)', 'rgba(244,63,94,0.3)', 'rgba(244,63,94,0.08)'],
    boxShadow: ['0 0 0 0 rgba(244,63,94,0)', '0 0 20px 3px rgba(244,63,94,0.55)', '0 0 0 0 rgba(244,63,94,0)'],
    transition: { duration: 0.5, ease: 'easeInOut' },
  },
};

const overlayVariants: Variants = {
  initial: { opacity: 0, scale: 0.4 },
  animate: { opacity: 1, scale: 1, transition: { type: 'spring', stiffness: 500, damping: 24 } },
  exit: { opacity: 0, scale: 0.4, transition: { duration: 0.15 } },
};

const dockVariants: Variants = {
  hidden: { opacity: 0, y: 24, scale: 0.96 },
  visible: { opacity: 1, y: 0, scale: 1, transition: { type: 'spring', stiffness: 260, damping: 26 } },
  exit: { opacity: 0, y: 24, scale: 0.96, transition: { duration: 0.15 } },
};

function DockNode({ integration, status }: { integration: IntegrationMeta; status: DockActionResult }) {
  // বাংলা মন্তব্য: dnd-kit droppable target — id === platform, যা useDynamicDock.handleDragEnd এর over.id এর সাথে মেলে
  const { isOver, setNodeRef } = useDroppable({ id: integration.id });
  const Icon = ICON_MAP[integration.icon];

  return (
    <div className="flex flex-col items-center gap-1.5">
      <motion.div
        ref={setNodeRef}
        variants={nodeVariants}
        animate={status.status}
        className={`relative w-16 h-16 rounded-2xl border flex items-center justify-center transition-colors duration-200 ${
          isOver ? 'border-indigo-400 bg-indigo-500/15' : 'border-white/10 bg-white/[0.04]'
        }`}
      >
        <Icon size={22} className="text-slate-200" />

        <AnimatePresence>
          {status.status === 'pending' && (
            <motion.div
              key="pending"
              variants={overlayVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              className="absolute -top-1.5 -right-1.5 bg-indigo-500 rounded-full p-1"
            >
              <Loader2 size={11} className="text-white animate-spin" />
            </motion.div>
          )}
          {status.status === 'success' && (
            <motion.div
              key="success"
              variants={overlayVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              className="absolute -top-1.5 -right-1.5 bg-emerald-500 rounded-full p-1"
            >
              <CheckCircle2 size={11} className="text-white" />
            </motion.div>
          )}
          {status.status === 'error' && (
            <motion.div
              key="error"
              variants={overlayVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              className="absolute -top-1.5 -right-1.5 bg-rose-500 rounded-full p-1"
            >
              <AlertTriangle size={11} className="text-white" />
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      <span className="text-[10px] font-medium text-slate-400">{integration.label}</span>

      <AnimatePresence>
        {status.message && (status.status === 'error' || status.status === 'success') && (
          <motion.span
            key={status.message}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className={`text-[9px] text-center max-w-[80px] leading-tight ${
              status.status === 'error' ? 'text-rose-400' : 'text-emerald-400'
            }`}
          >
            {status.message}
          </motion.span>
        )}
      </AnimatePresence>
    </div>
  );
}

// বাংলা মন্তব্য: enter/exit AnimatePresence প্যারেন্ট (LivingDashboardShell) থেকে কন্ট্রোল হয় — এই কম্পোনেন্ট সবসময় একটাই root motion.div রেন্ডার করে
export function LivingActionDock({ enabledIntegrations, nodeStatus }: LivingActionDockProps) {
  return (
    <motion.div
      variants={dockVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      data-testid="living-action-dock"
      className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-end gap-6 px-6 py-4 rounded-2xl border border-white/10 bg-[var(--supremeai-color-bg-elevated-dark)]/90 backdrop-blur-xl shadow-2xl shadow-black/40"
    >
      {enabledIntegrations.map((integration) => (
        <DockNode
          key={integration.id}
          integration={integration}
          status={nodeStatus[integration.id] ?? { status: 'idle', message: '' }}
        />
      ))}
    </motion.div>
  );
}
