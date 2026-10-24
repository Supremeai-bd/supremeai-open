import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';

interface HITLModalProps {
  pendingAction: { platform: string; content: string; context: Record<string, unknown> } | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function HITLModal({ pendingAction, onConfirm, onCancel }: HITLModalProps) {
  return (
    <AnimatePresence>
      {pendingAction && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="w-full max-w-md overflow-hidden bg-slate-900 border border-slate-700/50 rounded-2xl shadow-2xl shadow-indigo-500/10"
          >
            <div className="p-6">
              <div className="flex items-center gap-4 mb-6">
                <div className="flex items-center justify-center w-12 h-12 rounded-full bg-indigo-500/10 text-indigo-400">
                  <AlertTriangle className="w-6 h-6" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-white">Action Confirmation</h2>
                  <p className="text-sm text-slate-400">Human-in-the-Loop Intercept</p>
                </div>
              </div>

              <div className="p-4 mb-6 space-y-3 rounded-lg bg-slate-950/50 border border-slate-800">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium uppercase tracking-wider text-slate-500">Target</span>
                  <span className="text-sm font-semibold text-slate-200 capitalize">{pendingAction.platform}</span>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-xs font-medium uppercase tracking-wider text-slate-500">Payload snippet</span>
                  <p className="text-sm text-slate-300 font-mono truncate opacity-80">
                    {pendingAction.content || 'No content provided'}
                  </p>
                </div>
              </div>

              <p className="text-sm text-slate-400 mb-6">
                Are you sure you want to execute this action? The AI requires your explicit authorization to proceed.
              </p>

              <div className="flex gap-3">
                <button
                  onClick={onCancel}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 rounded-xl transition-colors"
                >
                  <XCircle className="w-4 h-4" />
                  Reject
                </button>
                <button
                  onClick={onConfirm}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-500 rounded-xl shadow-lg shadow-indigo-500/20 transition-all hover:shadow-indigo-500/40"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  Proceed
                </button>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
