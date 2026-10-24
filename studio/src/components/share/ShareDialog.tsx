import { useState, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X,
  Link2,
  Copy,
  Check,
  Eye,
  Globe,
  Lock,
  Loader2,
  Clock,
} from 'lucide-react';
import { apiClient } from '../../services/apiClient';
import { globalShowToastRef } from '../../contexts/ToastContext';

// ─── Types ───────────────────────────────────────────────────────────────

interface ShareDialogProps {
  conversationId: string;
  isOpen: boolean;
  onClose: () => void;
}

type ExpiryOption = '7d' | '30d' | '90d' | 'never';

interface ShareResponse {
  share_url: string;
  share_id: string;
  view_count: number;
  expires_at: string | null;
  is_public: boolean;
}

interface ExpiryConfig {
  value: ExpiryOption;
  label: string;
  description: string;
}

// ─── Constants ───────────────────────────────────────────────────────────

const EXPIRY_OPTIONS: ExpiryConfig[] = [
  { value: '7d', label: '7 days', description: 'Link expires in a week' },
  { value: '30d', label: '30 days', description: 'Link expires in a month' },
  { value: '90d', label: '90 days', description: 'Link expires in 3 months' },
  { value: 'never', label: 'Never', description: 'Link does not expire' },
];

// ─── Component ───────────────────────────────────────────────────────────

export function ShareDialog({ conversationId, isOpen, onClose }: ShareDialogProps) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [isPublic, setIsPublic] = useState(true);
  const [expiry, setExpiry] = useState<ExpiryOption>('30d');
  const [shareData, setShareData] = useState<ShareResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset state when dialog closes
  useEffect(() => {
    if (!isOpen) {
      // Keep shareData so user can still see link if they reopen quickly
      setError(null);
    }
  }, [isOpen]);

  const handleGenerateLink = useCallback(async () => {
    if (!conversationId) return;

    setIsGenerating(true);
    setError(null);

    try {
      const response = await apiClient.post<ShareResponse>(
        '/api/share/generate',
        {
          conversation_id: conversationId,
          is_public: isPublic,
          expires_in: expiry,
        }
      );

      setShareData(response);
      globalShowToastRef.current('success', 'Share link generated successfully!');
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Failed to generate share link';
      setError(message);
      globalShowToastRef.current('error', message);
    } finally {
      setIsGenerating(false);
    }
  }, [conversationId, isPublic, expiry]);

  const handleCopyLink = useCallback(async () => {
    if (!shareData?.share_url) return;

    try {
      await navigator.clipboard.writeText(shareData.share_url);
      setCopied(true);
      globalShowToastRef.current('success', 'Link copied to clipboard!');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for browsers without clipboard API
      const textarea = document.createElement('textarea');
      textarea.value = shareData.share_url;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [shareData]);

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) {
        onClose();
      }
    },
    [onClose]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    },
    [onClose]
  );

  const formattedExpiry = shareData?.expires_at
    ? new Date(shareData.expires_at).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : 'Never';

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
          onClick={handleBackdropClick}
          onKeyDown={handleKeyDown}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 16 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="w-full max-w-lg overflow-hidden bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/50 rounded-2xl shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700/50">
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                  <Link2 className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
                    Share Conversation
                  </h2>
                  <p className="text-sm text-slate-500 dark:text-slate-400">
                    Generate a link others can view
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="flex items-center justify-center w-8 h-8 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                aria-label="Close dialog"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Body */}
            <div className="px-6 py-5 space-y-6">
              {/* Visibility Toggle */}
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-3">
                  Visibility
                </label>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => setIsPublic(true)}
                    className={
                      `flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl border-2 text-sm font-medium transition-all ${
                        isPublic
                          ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400'
                          : 'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-600'
                      }`
                    }
                  >
                    <Globe className="w-4 h-4" />
                    Public
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsPublic(false)}
                    className={
                      `flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl border-2 text-sm font-medium transition-all ${
                        !isPublic
                          ? 'border-amber-500 bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400'
                          : 'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-600'
                      }`
                    }
                  >
                    <Lock className="w-4 h-4" />
                    Private
                  </button>
                </div>
                <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
                  {isPublic
                    ? 'Anyone with the link can view this conversation'
                    : 'Only people with the link and access can view'}
                </p>
              </div>

              {/* Expiry Selector */}
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-3">
                  <Clock className="w-4 h-4 inline-block mr-1.5 -mt-0.5" />
                  Expiration
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {EXPIRY_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setExpiry(option.value)}
                      className={
                        `flex flex-col items-start px-4 py-3 rounded-xl border-2 text-left transition-all ${
                          expiry === option.value
                            ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-500/10'
                            : 'border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600'
                        }`
                      }
                    >
                      <span
                        className={`text-sm font-medium ${
                          expiry === option.value
                            ? 'text-emerald-700 dark:text-emerald-400'
                            : 'text-slate-700 dark:text-slate-300'
                        }`}
                      >
                        {option.label}
                      </span>
                      <span className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                        {option.description}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Error State */}
              {error && (
                <div className="px-4 py-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20">
                  <p className="text-sm text-red-600 dark:text-red-400">
                    {error}
                  </p>
                </div>
              )}

              {/* Share URL Display */}
              {shareData && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-3"
                >
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
                    Share Link
                  </label>
                  <div className="flex gap-2">
                    <div className="flex-1 flex items-center px-4 py-2.5 rounded-xl bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                      <Link2 className="w-4 h-4 mr-2 text-slate-400 dark:text-slate-500 flex-shrink-0" />
                      <input
                        type="text"
                        readOnly
                        value={shareData.share_url}
                        className="flex-1 text-sm bg-transparent text-slate-700 dark:text-slate-300 outline-none truncate font-mono"
                        onFocus={(e) => e.target.select()}
                      />
                    </div>
                    <button
                      type="button"
                      onClick={handleCopyLink}
                      className={
                        `flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                          copied
                            ? 'bg-emerald-500 text-white'
                            : 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 hover:bg-slate-800 dark:hover:bg-slate-200'
                        }`
                      }
                    >
                      {copied ? (
                        <>
                          <Check className="w-4 h-4" />
                          <span className="hidden sm:inline">Copied!</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-4 h-4" />
                          <span className="hidden sm:inline">Copy</span>
                        </>
                      )}
                    </button>
                  </div>

                  {/* Stats Row */}
                  <div className="flex items-center gap-4 pt-2">
                    <div className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
                      <Eye className="w-4 h-4" />
                      <span>
                        {shareData.view_count}
                        {shareData.view_count === 1 ? ' view' : ' views'}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
                      <Clock className="w-4 h-4" />
                      <span>Expires {formattedExpiry}</span>
                    </div>
                    <div
                      className={`ml-auto inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                        shareData.is_public
                          ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400'
                          : 'bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400'
                      }`
                    }
                    >
                      {shareData.is_public ? (
                        <Globe className="w-3 h-3" />
                      ) : (
                        <Lock className="w-3 h-3" />
                      )}
                      {shareData.is_public ? 'Public' : 'Private'}
                    </div>
                  </div>
                </motion.div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-200 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-800/50">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2.5 text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleGenerateLink}
                disabled={isGenerating}
                className="flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl shadow-lg shadow-emerald-500/20 transition-all"
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Generating...
                  </>
                ) : shareData ? (
                  <>
                    <Link2 className="w-4 h-4" />
                    Regenerate Link
                  </>
                ) : (
                  <>
                    <Link2 className="w-4 h-4" />
                    Generate Share Link
                  </>
                )}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
