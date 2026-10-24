import React, { type Dispatch, type SetStateAction } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Clock, X } from 'lucide-react';

import type { HistoryEntry } from './types';

// ════════════════════════════════════════════════════════════════════
// HISTORY PANEL (modal overlay)
// Extracted verbatim from the CrownJewelBrowser render tree.
// ════════════════════════════════════════════════════════════════════

interface HistoryPanelProps {
  show: boolean;
  setShowHistory: Dispatch<SetStateAction<boolean>>;
  history: HistoryEntry[];
  navigateTo: (url: string) => void;
}

export const HistoryPanel: React.FC<HistoryPanelProps> = ({
  show,
  setShowHistory,
  history,
  navigateTo,
}) => {
  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="absolute inset-0 bg-black/60 backdrop-blur-sm z-20 flex items-start justify-center pt-20"
          onClick={() => setShowHistory(false)}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
            className="bg-[#161b22] border border-cyan-500/30 rounded-xl shadow-2xl w-[500px] max-h-[400px] overflow-hidden"
          >
            <div className="p-4 border-b border-slate-700 flex items-center justify-between">
              <h3 className="font-bold text-white flex items-center gap-2">
                <Clock size={16} className="text-cyan-400" />
                History
              </h3>
              <button onClick={() => setShowHistory(false)}>
                <X size={14} className="text-slate-400" />
              </button>
            </div>
            <div className="overflow-y-auto max-h-[320px] p-2">
              {history.length === 0 ? (
                <div className="text-center text-slate-500 py-8">No history yet</div>
              ) : (
                [...history].reverse().map((entry, i) => (
                  <button
                    key={i}
                    onClick={() => { navigateTo(entry.url); setShowHistory(false); }}
                    className="w-full text-left px-3 py-2 hover:bg-slate-800 rounded flex items-center justify-between"
                  >
                    <div>
                      <div className="text-sm text-white">{entry.title || entry.url}</div>
                      <div className="text-[10px] text-slate-500 truncate max-w-[300px]">{entry.url}</div>
                    </div>
                    <div className="text-[10px] text-slate-500">
                      {new Date(entry.timestamp).toLocaleTimeString()}
                    </div>
                  </button>
                ))
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
