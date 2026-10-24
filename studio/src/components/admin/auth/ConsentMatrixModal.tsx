import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, CheckCircle2, XCircle, MessageSquare, Terminal } from 'lucide-react';
import '../admin-hud.css';

interface ConsentRequest {
  id: string;
  taskPurpose: string;
  riskLevel: 'Low' | 'High' | 'Critical';
  diffPreview?: string;
}

interface ConsentMatrixModalProps {
  isOpen: boolean;
  request: ConsentRequest | null;
  onApproveOnce: (id: string) => void;
  onApproveAlways: (id: string) => void;
  onRejectWithFeedback: (id: string, feedback: string) => void;
  onHardReject: (id: string) => void;
  onClose: () => void;
}

// বাংলা মন্তব্য: HITL (Human-in-the-Loop) কনসেন্ট ম্যাট্রিক্স মোডাল, যা ক্রিটিকাল টাস্ক অ্যাপ্রুভ করার জন্য ব্যবহার করা হবে।
export const ConsentMatrixModal: React.FC<ConsentMatrixModalProps> = ({
  isOpen,
  request,
  onApproveOnce,
  onApproveAlways,
  onRejectWithFeedback,
  onHardReject,
}) => {
  const [feedback, setFeedback] = useState('');
  const [showFeedbackInput, setShowFeedbackInput] = useState(false);

  if (!request) return null;

  const getRiskColor = (level: string) => {
    switch (level) {
      case 'Critical': return 'text-red-500 border-red-500/50 shadow-[0_0_15px_rgba(239,68,68,0.5)]';
      case 'High': return 'text-orange-500 border-orange-500/50 shadow-[0_0_15px_rgba(249,115,22,0.5)]';
      case 'Low': return 'text-[#00f3ff] border-[#00f3ff]/50 shadow-[0_0_15px_rgba(0,243,255,0.5)]';
      default: return 'text-[#00f3ff] border-[#00f3ff]/50';
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <motion.div
            data-testid="consent-matrix-modal"
            initial={{ scale: 0.9, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.9, opacity: 0, y: 20 }}
            className={`relative w-full max-w-2xl p-6 glass-panel rounded-2xl border ${getRiskColor(request.riskLevel)} bg-slate-900/80`}
          >
            {/* Header */}
            <div className="flex items-center gap-3 border-b border-white/10 pb-4 mb-4">
              <AlertTriangle className={`w-8 h-8 ${request.riskLevel === 'Critical' ? 'text-red-500 animate-pulse' : 'text-orange-500'}`} />
              <div>
                <h2 className="text-xl font-mono font-bold text-white tracking-wider uppercase">Authorization Required</h2>
                <p className="text-xs font-mono text-slate-400">System paused. Awaiting human validation.</p>
              </div>
              <div className="ml-auto flex items-center gap-2">
                <span className="text-xs font-mono text-slate-400 uppercase tracking-widest">Risk:</span>
                <span className={`text-xs font-bold font-mono px-2 py-1 rounded border ${getRiskColor(request.riskLevel)}`}>
                  {request.riskLevel}
                </span>
              </div>
            </div>

            {/* Content */}
            <div className="space-y-4 mb-6">
              <div>
                <h3 className="text-sm font-mono text-[#00f3ff] mb-1">Task Purpose:</h3>
                <p className="text-sm text-slate-300 bg-black/40 p-3 rounded border border-white/5">
                  {request.taskPurpose}
                </p>
              </div>

              {request.diffPreview && (
                <div>
                  <h3 className="text-sm font-mono text-[#00f3ff] mb-1 flex items-center gap-2">
                    <Terminal className="w-4 h-4" /> Code/Config Diff Preview:
                  </h3>
                  <pre className="text-xs text-slate-300 bg-[#0d1117] p-4 rounded border border-white/10 overflow-x-auto font-mono max-h-48">
                    <code>{request.diffPreview}</code>
                  </pre>
                </div>
              )}
            </div>

            {/* Feedback Input (Conditional) */}
            <AnimatePresence>
              {showFeedbackInput && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="mb-4 overflow-hidden"
                >
                  <textarea
                    className="w-full bg-black/50 border border-white/20 rounded p-3 text-sm text-white focus:outline-none focus:border-[#00f3ff] font-mono resize-none"
                    rows={3}
                    placeholder="Provide voice/text feedback for AI correction..."
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                  />
                  <div className="flex justify-end gap-2 mt-2">
                    <button
                      onClick={() => setShowFeedbackInput(false)}
                      className="px-3 py-1.5 text-xs font-mono text-slate-400 hover:text-white transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => onRejectWithFeedback(request.id, feedback)}
                      className="px-3 py-1.5 text-xs font-mono bg-[#00f3ff]/20 text-[#00f3ff] border border-[#00f3ff]/50 rounded hover:bg-[#00f3ff]/40 transition-colors"
                    >
                      Submit Feedback
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* 4 Decision Buttons */}
            {!showFeedbackInput && (
              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={() => onApproveOnce(request.id)}
                  className="flex items-center justify-center gap-2 py-3 px-4 rounded border border-green-500/50 text-green-400 hover:bg-green-500/20 transition-all font-mono text-sm glow-green"
                >
                  <CheckCircle2 className="w-4 h-4" /> Approve Once
                </button>
                <button
                  onClick={() => onApproveAlways(request.id)}
                  className="flex items-center justify-center gap-2 py-3 px-4 rounded border border-[#00f3ff]/50 text-[#00f3ff] hover:bg-[#00f3ff]/20 transition-all font-mono text-sm glow-cyan"
                >
                  <CheckCircle2 className="w-4 h-4" /> Approve Always (Save Rule)
                </button>
                <button
                  onClick={() => setShowFeedbackInput(true)}
                  className="flex items-center justify-center gap-2 py-3 px-4 rounded border border-orange-500/50 text-orange-400 hover:bg-orange-500/20 transition-all font-mono text-sm"
                >
                  <MessageSquare className="w-4 h-4" /> Reject with Feedback
                </button>
                <button
                  onClick={() => onHardReject(request.id)}
                  className="flex items-center justify-center gap-2 py-3 px-4 rounded border border-red-500/50 text-red-500 hover:bg-red-500/20 transition-all font-mono text-sm"
                >
                  <XCircle className="w-4 h-4" /> Hard Reject
                </button>
              </div>
            )}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};
