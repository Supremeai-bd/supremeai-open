import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  X,
  MessageSquare,
  FileText,
  Loader2,
  ArrowUpRight,
  Sparkles,
} from 'lucide-react';
import { apiClient } from '../../services/apiClient';

// ─── Types ───────────────────────────────────────────────────────────────

interface ChatSearchDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

type MatchType = 'title' | 'message';

interface SearchResult {
  conversation_id: string;
  conversation_title: string;
  message_id: string;
  snippet: string;
  match_type: MatchType;
  relevance_score: number;
  highlighted?: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────

// SECURITY FIX (audit V-2 / S-3): The previous implementation passed user-
// provided text directly to dangerouslySetInnerHTML without escaping. Two fixes:
// 1. highlightMatch now escapes HTML in the text first, then wraps matches in
//    <mark> — so injected HTML in message content is rendered as literal text.
// 2. result.highlighted (from backend) is stripped of all tags except <mark>
//    before rendering to prevent stored XSS via backend response.

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}

function highlightMatch(text: string, query: string): string {
  // Escape HTML first, then apply highlighting to the safe string.
  const safeText = escapeHtml(text);
  if (!query) return safeText;
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`(${escaped})`, 'gi');
  return safeText.replace(
    regex,
    '<mark class="bg-amber-200 dark:bg-amber-500/30 text-amber-900 dark:text-amber-200 rounded px-0.5">$1</mark>'
  );
}

/** Allow only <mark> tags from backend-provided highlighted strings. */
function sanitizeHighlighted(html: string): string {
  // Strip every HTML tag except <mark> and </mark>.
  return html.replace(/<(?!\/?mark\b)[^>]+>/gi, '');
}


function formatScore(score: number): string {
  return `${Math.round(score * 100)}%`;
}

function getMatchTypeBadge(type: MatchType): { label: string; className: string } {
  if (type === 'title') {
    return {
      label: 'Title',
      className:
        'bg-sky-100 dark:bg-sky-500/10 text-sky-700 dark:text-sky-400 border-sky-200 dark:border-sky-500/25',
    };
  }
  return {
    label: 'Message',
    className:
      'bg-violet-100 dark:bg-violet-500/10 text-violet-700 dark:text-violet-400 border-violet-200 dark:border-violet-500/25',
  };
}

// ─── Sub-components ──────────────────────────────────────────────────────

function ResultItem({
  result,
  query,
  onClick,
}: {
  result: SearchResult;
  query: string;
  onClick: (conversationId: string) => void;
}) {
  const badge = getMatchTypeBadge(result.match_type);

  return (
    <button
      type="button"
      onClick={() => onClick(result.conversation_id)}
      className="w-full text-left px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors group"
    >
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500 flex-shrink-0 mt-0.5">
          {result.match_type === 'title' ? (
            <FileText className="w-4 h-4" />
          ) : (
            <MessageSquare className="w-4 h-4" />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Conversation title + match type badge */}
          <div className="flex items-center gap-2 mb-1">
            <h4 className="text-sm font-semibold text-slate-800 dark:text-white truncate">
              {result.conversation_title}
            </h4>
            <span
              className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-semibold rounded border ${badge.className}`}
            >
              {badge.label}
            </span>
          </div>

          {/* Snippet with highlighted match */}
          {result.match_type === 'message' && (
            <p
              className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2 leading-relaxed"
              dangerouslySetInnerHTML={{
                __html: result.highlighted
                  // SECURITY FIX (audit S-3): sanitize backend HTML — allow only <mark>.
                  ? sanitizeHighlighted(result.highlighted)
                  : highlightMatch(result.snippet, query),
              }}
            />
          )}

          {/* Relevance score + arrow */}
          <div className="flex items-center gap-2 mt-1.5">
            <span className="text-[10px] font-mono text-slate-400 dark:text-slate-500">
              Relevance: {formatScore(result.relevance_score)}
            </span>
            <ArrowUpRight className="w-3 h-3 text-slate-300 dark:text-slate-600 opacity-0 group-hover:opacity-100 transition-opacity ml-auto" />
          </div>
        </div>
      </div>
    </button>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────

export function ChatSearchDialog({ isOpen, onClose }: ChatSearchDialogProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Focus input when dialog opens
  useEffect(() => {
    if (isOpen) {
      // Small delay to allow animation to start
      const timer = setTimeout(() => {
        inputRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    } else {
      setQuery('');
      setResults([]);
      setHasSearched(false);
      setError(null);
    }
  }, [isOpen]);

  // Perform search with debounce
  const performSearch = useCallback(async (searchQuery: string) => {
    const trimmed = searchQuery.trim();
    if (!trimmed) {
      setResults([]);
      setHasSearched(false);
      setIsSearching(false);
      return;
    }

    setIsSearching(true);
    setError(null);

    try {
      const response = await apiClient.get<SearchResult[]>(
        `/api/chat/search/?q=${encodeURIComponent(trimmed)}`
      );
      setResults(Array.isArray(response) ? response : []);
    } catch {
      setError('Search failed. Please try again.');
      setResults([]);
    } finally {
      setIsSearching(false);
      setHasSearched(true);
    }
  }, []);

  // Debounced search effect
  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    if (!query.trim()) {
      setResults([]);
      setHasSearched(false);
      setIsSearching(false);
      return;
    }

    setIsSearching(true);
    debounceRef.current = setTimeout(() => {
      performSearch(query);
    }, 300);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [query, performSearch]);

  // Keyboard shortcut (Escape to close)
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    },
    [onClose]
  );

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) {
        onClose();
      }
    },
    [onClose]
  );

  const handleResultClick = useCallback(
    (conversationId: string) => {
      // Dispatch a navigation event that the parent can listen to
      window.dispatchEvent(
        new CustomEvent('supremeai-navigate-to-conversation', {
          detail: conversationId,
        })
      );
      onClose();
    },
    [onClose]
  );

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] px-4 bg-black/50 backdrop-blur-sm"
          onClick={handleBackdropClick}
          onKeyDown={handleKeyDown}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -12 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="w-full max-w-xl overflow-hidden bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/50 rounded-2xl shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Search Input Header */}
            <div className="flex items-center gap-3 px-5 py-4 border-b border-slate-200 dark:border-slate-700/50">
              <Search className="w-5 h-5 text-slate-400 dark:text-slate-500 flex-shrink-0" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search all conversations..."
                className="flex-1 text-base bg-transparent text-slate-800 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 outline-none"
                autoComplete="off"
                spellCheck={false}
              />
              {/* Keyboard shortcut hint or clear button */}
              <div className="flex items-center gap-2">
                {query && (
                  <button
                    type="button"
                    onClick={() => setQuery('')}
                    className="p-1 rounded-md text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                    aria-label="Clear search"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
                {!query && (
                  <kbd className="hidden sm:inline-flex items-center px-2 py-1 text-xs font-mono text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                    ESC
                  </kbd>
                )}
              </div>
            </div>

            {/* Results Area */}
            <div className="max-h-[50vh] overflow-y-auto custom-scrollbar">
              {/* Initial state */}
              {!query.trim() && (
                <div className="flex flex-col items-center gap-3 py-12 px-6">
                  <Sparkles className="w-10 h-10 text-slate-200 dark:text-slate-700" />
                  <p className="text-sm text-slate-400 dark:text-slate-500 text-center">
                    Type to search across all your conversations
                  </p>
                </div>
              )}

              {/* Loading state */}
              {isSearching && (
                <div className="flex items-center justify-center gap-2 py-8">
                  <Loader2 className="w-5 h-5 animate-spin text-violet-500" />
                  <span className="text-sm text-slate-400 dark:text-slate-500">
                    Searching...
                  </span>
                </div>
              )}

              {/* Error state */}
              {error && !isSearching && (
                <div className="px-5 py-4">
                  <p className="text-sm text-red-500 dark:text-red-400 text-center">
                    {error}
                  </p>
                </div>
              )}

              {/* No results */}
              {hasSearched && !isSearching && !error && results.length === 0 && (
                <div className="flex flex-col items-center gap-3 py-12 px-6">
                  <Search className="w-10 h-10 text-slate-200 dark:text-slate-700" />
                  <p className="text-sm text-slate-500 dark:text-slate-400 text-center font-medium">
                    No results found
                  </p>
                  <p className="text-xs text-slate-400 dark:text-slate-500 text-center max-w-xs">
                    Try different keywords or check your spelling. Search works across all conversation titles and messages.
                  </p>
                </div>
              )}

              {/* Results list */}
              {results.length > 0 && (
                <>
                  {/* Result count */}
                  <div className="flex items-center justify-between px-5 py-2.5 border-b border-slate-100 dark:border-slate-800">
                    <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                      {results.length} {results.length === 1 ? 'result' : 'results'}
                    </span>
                  </div>

                  {/* Result items */}
                  <div className="divide-y divide-slate-100 dark:divide-slate-800">
                    {results.map((result) => (
                      <ResultItem
                        key={`${result.conversation_id}-${result.message_id}`}
                        result={result}
                        query={query}
                        onClick={handleResultClick}
                      />
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* Footer with hints */}
            <div className="flex items-center justify-between px-5 py-2.5 border-t border-slate-200 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-800/30">
              <div className="flex items-center gap-4 text-[10px] text-slate-400 dark:text-slate-500">
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 rounded text-[9px] font-mono">↵</kbd>
                  open
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 rounded text-[9px] font-mono">esc</kbd>
                  close
                </span>
              </div>
              <span className="text-[10px] text-slate-400 dark:text-slate-500">
                ⌘K to search
              </span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
