import React, { type Dispatch, type SetStateAction } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';

import type { ConsoleMessage } from './types';

// ════════════════════════════════════════════════════════════════════
// DEVTOOLS PANEL (bottom console)
// Extracted verbatim from the CrownJewelBrowser render tree.
// ════════════════════════════════════════════════════════════════════

interface DevToolsPanelProps {
  show: boolean;
  setShowDevToolsPanel: Dispatch<SetStateAction<boolean>>;
  clearConsole: () => void;
  consoleMessages: ConsoleMessage[];
}

export const DevToolsPanel: React.FC<DevToolsPanelProps> = ({
  show,
  setShowDevToolsPanel,
  clearConsole,
  consoleMessages,
}) => {
  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 200, opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          className="bg-[#1c2128] border-t border-slate-700 flex flex-col overflow-hidden"
        >
          {/* DevTools Header */}
          <div className="flex items-center justify-between px-3 py-1 bg-[#161b22] border-b border-slate-700">
            <div className="flex items-center gap-3">
              {['Console', 'Network', 'Elements'].map(tab => (
                <button key={tab} className="text-[10px] text-slate-400 hover:text-white px-2 py-0.5">
                  {tab}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <button onClick={clearConsole} className="text-[10px] text-slate-400 hover:text-white">
                Clear
              </button>
              <button onClick={() => setShowDevToolsPanel(false)}>
                <X size={10} className="text-slate-400" />
              </button>
            </div>
          </div>

          {/* Console Output */}
          <div className="flex-1 overflow-y-auto p-2 font-mono text-[11px] space-y-0.5">
            {consoleMessages.length === 0 ? (
              <div className="text-slate-500 text-center py-4">Console is empty</div>
            ) : (
              consoleMessages.map((msg, i) => (
                <div
                  key={i}
                  className={`${
                    msg.type === 'error' ? 'text-red-400' :
                    msg.type === 'warn' ? 'text-yellow-400' :
                    msg.type === 'info' ? 'text-blue-400' :
                    'text-slate-300'
                  }`}
                >
                  <span className="text-slate-500 mr-2">[{new Date(msg.timestamp).toLocaleTimeString()}]</span>
                  {msg.content}
                </div>
              ))
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
