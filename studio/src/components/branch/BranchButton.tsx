import { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { GitBranch, Loader2 } from 'lucide-react';
import { apiClient } from '../../services/apiClient';
import { globalShowToastRef } from '../../contexts/ToastContext';

// ─── Types ───────────────────────────────────────────────────────────────

interface BranchButtonProps {
  conversationId: string;
  messageId: string;
  onBranchCreated: (newConvId: string) => void;
}

interface BranchResponse {
  new_conversation_id: string;
  title: string;
}

// ─── Component ───────────────────────────────────────────────────────────

export default function BranchButton({ conversationId, messageId, onBranchCreated }: BranchButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [branchTitle, setBranchTitle] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleClickOutside = useCallback((event: MouseEvent) => {
    if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
      setIsOpen(false);
      setBranchTitle('');
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      // Focus the input when opening
      setTimeout(() => inputRef.current?.focus(), 50);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, handleClickOutside]);

  const handleBranch = useCallback(async () => {
    if (isCreating) return;

    setIsCreating(true);
    try {
      const response = await apiClient.post<BranchResponse>(
        `/api/conversations/${conversationId}/branch`,
        {
          message_id: messageId,
          title: branchTitle.trim() || undefined,
        }
      );

      onBranchCreated(response.new_conversation_id);
      globalShowToastRef.current('success', 'Branch created successfully!');
      setIsOpen(false);
      setBranchTitle('');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to create branch';
      globalShowToastRef.current('error', message);
    } finally {
      setIsCreating(false);
    }
  }, [conversationId, messageId, branchTitle, isCreating, onBranchCreated]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleBranch();
    }
    if (e.key === 'Escape') {
      setIsOpen(false);
      setBranchTitle('');
    }
  }, [handleBranch]);

  return (
    <div className="relative inline-flex" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        disabled={isCreating}
        className={
          'group flex items-center justify-center w-8 h-8 rounded-lg transition-all ' +
          'text-slate-400 hover:text-violet-500 ' +
          'hover:bg-violet-50 dark:hover:bg-violet-500/10 ' +
          'opacity-0 group-hover/parent:opacity-100 ' +
          'focus-within:opacity-100 hover:opacity-100 ' +
          'disabled:opacity-50 disabled:cursor-not-allowed'
        }
        aria-label="Branch from this message"
        title="Branch from here"
      >
        {isCreating ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <GitBranch className="w-4 h-4" />
        )}
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.95 }}
            transition={{ duration: 0.12, ease: 'easeOut' }}
            className={
              'absolute left-1/2 -translate-x-1/2 bottom-full mb-2 w-72 ' +
              'bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/50 ' +
              'rounded-xl shadow-xl shadow-slate-900/10 dark:shadow-slate-950/40 ' +
              'overflow-hidden z-50'
            }
          >
            {/* Arrow */}
            <div className="flex justify-center">
              <div className="w-2.5 h-2.5 bg-white dark:bg-slate-900 border-r border-b border-slate-200 dark:border-slate-700/50 rotate-45 -mb-1.5 translate-y-1" />
            </div>

            <div className="p-3 space-y-3">
              <div className="flex items-center gap-2 mb-2">
                <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-violet-100 dark:bg-violet-500/10 text-violet-600 dark:text-violet-400">
                  <GitBranch className="w-4 h-4" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900 dark:text-white">
                    Branch from here
                  </p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Create a new conversation from this point
                  </p>
                </div>
              </div>

              <input
                ref={inputRef}
                type="text"
                placeholder="Branch title (optional)"
                value={branchTitle}
                onChange={(e) => setBranchTitle(e.target.value)}
                onKeyDown={handleKeyDown}
                className={
                  'w-full px-3 py-2 text-sm rounded-lg border transition-colors ' +
                  'bg-slate-50 dark:bg-slate-800 border-slate-200 dark:border-slate-700 ' +
                  'text-slate-900 dark:text-white placeholder:text-slate-400 ' +
                  'focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500'
                }
              />

              <button
                type="button"
                onClick={handleBranch}
                disabled={isCreating}
                className={
                  'w-full flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-all ' +
                  'text-white bg-violet-600 hover:bg-violet-500 ' +
                  'shadow-lg shadow-violet-500/20 ' +
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                }
              >
                {isCreating ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Creating branch...
                  </>
                ) : (
                  <>
                    <GitBranch className="w-4 h-4" />
                    Branch
                  </>
                )}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
