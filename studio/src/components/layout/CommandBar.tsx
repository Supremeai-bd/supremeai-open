// apps/studio-client/src/components/layout/CommandBar.tsx
// Universal Command Palette (Ctrl+K / Cmd+K)
// বাংলা মন্তব্য: ইউনিভার্সাল কমান্ড প্যালেট — দ্রুত অ্যাকশন, মডেল সুইচিং এবং পেজ ন্যাভিগেশনের জন্য।
// Raycast-style Inspector Drawer + Keyboard Navigation (↑/↓/Enter).

import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Command, X, ArrowRight, CornerDownLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { getCommandsForPortal, getCurrentPortal } from '../../config/commandRegistry';
import type { CommandDefinition } from '../../config/commandRegistry';

interface CommandItem {
  id: string;
  title: string;
  category: string;
  icon: React.ElementType;
  shortcut?: string;
  route?: string;
  action: () => void;
}

interface CommandBarProps {
  isOpen?: boolean;
  onClose?: () => void;
}

/** বাংলা মন্তব্য: registry definition → runtime item (navigate/action wiring) */
function materializeCommands(
  definitions: CommandDefinition[],
  navigate: (path: string) => void,
  onClose: () => void,
): CommandItem[] {
  return definitions.map((def) => ({
    id: def.id,
    title: def.title,
    category: def.category,
    icon: def.icon,
    shortcut: def.shortcut,
    route: def.route,
    action: () => {
      if (def.route) {
        navigate(def.route);
      }
      def.action?.();
      onClose();
    },
  }));
}

export const CommandBar: React.FC<CommandBarProps> = ({ isOpen: controlledOpen, onClose }) => {
  const [internalOpen, setInternalOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const navigate = useNavigate();

  const isOpen = controlledOpen !== undefined ? controlledOpen : internalOpen;

  const handleClose = useCallback(() => {
    if (onClose) onClose();
    else setInternalOpen(false);
    setQuery('');
    setSelectedIndex(0);
  }, [onClose]);

  const commands: CommandItem[] = materializeCommands(
    getCommandsForPortal(getCurrentPortal()),
    navigate,
    handleClose,
  );

  const filteredCommands = commands.filter(
    (item) =>
      item.title.toLowerCase().includes(query.toLowerCase()) ||
      item.category.toLowerCase().includes(query.toLowerCase())
  );

  const selectedCommand = filteredCommands[selectedIndex] || filteredCommands[0];

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (controlledOpen === undefined) {
          setInternalOpen((prev) => !prev);
        } else if (isOpen) {
          handleClose();
        }
      }
      if (e.key === 'Escape' && isOpen) {
        handleClose();
      }
      if (!isOpen || filteredCommands.length === 0) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => (prev + 1) % filteredCommands.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) => (prev - 1 + filteredCommands.length) % filteredCommands.length);
      } else if (e.key === 'Enter' && selectedCommand) {
        e.preventDefault();
        selectedCommand.action();
      }
    };

    const handleOpenEvent = () => setInternalOpen(true);

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('supremeai-open-command-palette', handleOpenEvent);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('supremeai-open-command-palette', handleOpenEvent);
    };
  }, [isOpen, controlledOpen, handleClose, filteredCommands, selectedCommand]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-16 px-4 bg-slate-950/80 backdrop-blur-xl">
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: -12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -12 }}
            className="w-full max-w-3xl overflow-hidden rounded-2xl border border-white/10 bg-slate-900/95 shadow-[0_20px_60px_rgba(0,0,0,0.8)] backdrop-blur-2xl"
          >
            {/* Header / Search Input */}
            <div className="flex items-center border-b border-white/10 px-4 py-3.5 bg-slate-900/80">
              <Search className="mr-3 h-5 w-5 text-cyan-400" />
              <input
                type="text"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setSelectedIndex(0);
                }}
                placeholder="Type a command or search workspace... (↑/↓ to navigate, Enter to run)"
                className="flex-1 bg-transparent text-sm font-medium text-slate-100 placeholder-slate-500 focus:outline-none"
                autoFocus
              />
              <button
                onClick={handleClose}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Split View: Left List + Right Raycast Inspector Drawer */}
            <div className="grid grid-cols-1 md:grid-cols-5 min-h-[320px] max-h-[420px]">
              {/* Left Column: Command List */}
              <div className="md:col-span-3 overflow-y-auto p-2 border-r border-white/5 space-y-1">
                {filteredCommands.length === 0 ? (
                  <div className="p-8 text-center text-sm text-slate-500">
                    No commands found matching "{query}"
                  </div>
                ) : (
                  filteredCommands.map((item, index) => {
                    const Icon = item.icon;
                    const isSelected = index === selectedIndex;
                    return (
                      <button
                        key={item.id}
                        onClick={item.action}
                        onMouseEnter={() => setSelectedIndex(index)}
                        className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-left text-xs font-medium transition-all ${
                          isSelected
                            ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 shadow-[0_0_12px_rgba(0,243,255,0.2)]'
                            : 'text-slate-300 hover:bg-slate-800/60 border border-transparent'
                        }`}
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          <div
                            className={`rounded-lg p-1.5 ${
                              isSelected
                                ? 'bg-cyan-500/30 text-cyan-300'
                                : 'bg-slate-800 text-slate-400'
                            }`}
                          >
                            <Icon className="h-3.5 w-3.5" />
                          </div>
                          <span className="truncate">{item.title}</span>
                        </div>
                        {item.shortcut && (
                          <kbd className="ml-2 flex-shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[9px] font-mono text-slate-400 border border-slate-700">
                            {item.shortcut}
                          </kbd>
                        )}
                      </button>
                    );
                  })
                )}
              </div>

              {/* Right Column: Raycast Inspector Drawer */}
              <div className="hidden md:flex md:col-span-2 flex-col justify-between p-4 bg-slate-950/40 text-xs text-slate-400">
                {selectedCommand ? (
                  <div className="space-y-4">
                    <div>
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                        {selectedCommand.category}
                      </span>
                      <h4 className="text-sm font-bold text-slate-100 mt-2">
                        {selectedCommand.title}
                      </h4>
                      <p className="text-[11px] text-slate-400 mt-1">
                        {selectedCommand.route
                          ? `Navigate to destination route: ${selectedCommand.route}`
                          : 'Execute autonomous pipeline action.'}
                      </p>
                    </div>

                    <div className="p-2.5 rounded-xl bg-slate-900/80 border border-white/5 space-y-1.5 font-mono text-[11px]">
                      <div className="flex justify-between text-slate-400">
                        <span>Action Type:</span>
                        <span className="text-cyan-400">{selectedCommand.route ? 'Route Navigation' : 'Engine Action'}</span>
                      </div>
                      <div className="flex justify-between text-slate-400">
                        <span>Access Level:</span>
                        <span className="text-emerald-400">Authorized</span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-slate-500 text-center my-auto">Select a command to view details</div>
                )}

                {/* Quick Execute Hint */}
                {selectedCommand && (
                  <div className="pt-3 border-t border-white/5 flex items-center justify-between text-[10px] text-slate-500">
                    <span className="flex items-center gap-1">
                      Press <CornerDownLeft className="h-3 w-3 text-cyan-400" /> to run
                    </span>
                    <ArrowRight className="h-3 w-3 text-slate-600" />
                  </div>
                )}
              </div>
            </div>

            {/* Footer Bar */}
            <div className="flex items-center justify-between border-t border-white/10 px-4 py-2 bg-slate-950/80 text-[11px] text-slate-500 font-mono">
              <span className="flex items-center gap-1.5">
                <Command className="h-3 w-3 text-cyan-400" /> SupremeAI Command Registry
              </span>
              <div className="flex items-center gap-3">
                <span>↑↓ Navigate</span>
                <span>↵ Select</span>
                <span>ESC Close</span>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default CommandBar;
