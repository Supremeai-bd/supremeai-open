import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Eye,
  Calendar,
  ArrowRight,
  Sparkles,
  AlertTriangle,
  User,
  Bot,
} from 'lucide-react';
import { apiClient } from '../services/apiClient';

// ─── Types ───────────────────────────────────────────────────────────────

interface SharedConversationData {
  share_id: string;
  title: string;
  messages: {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: string;
  }[];
  view_count: number;
  created_at: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────

// SECURITY FIX (audit S-3 / V-1): The previous implementation escaped HTML
// first, then re-injected raw <strong>/<code> tags whose $1 capture groups were
// NOT re-escaped — creating a potential XSS bypass for mixed input.
// Correct order: (1) extract code spans to protect them, (2) escape all HTML in
// the remaining text, (3) restore code spans with their content escaped too,
// (4) apply bold/linebreak patterns to the already-escaped plain text.
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}

function formatMessageContent(content: string): string {
  // Step 1: Pull out inline code spans so their content is never treated as markup.
  const codeSlots: string[] = [];
  const withPlaceholders = content.replace(/`([^`]+)`/g, (_, inner) => {
    const escaped = escapeHtml(inner);
    const slot = `\x00CODE${codeSlots.length}\x00`;
    codeSlots.push(`<code class="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono">${escaped}</code>`);
    return slot;
  });

  // Step 2: HTML-escape everything that remains (including any AI-injected tags).
  const escaped = escapeHtml(withPlaceholders);

  // Step 3: Apply safe markdown patterns on the now-escaped string.
  const formatted = escaped
    // Bold — capture group is already HTML-escaped, safe to wrap.
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    // Line breaks
    .replace(/\n/g, '<br/>');

  // Step 4: Restore code spans (already escaped in step 1).
  return codeSlots.reduce(
    (str, html, i) => str.replace(`\x00CODE${i}\x00`, html),
    formatted
  );
}


function formatTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}

// ─── Skeleton ────────────────────────────────────────────────────────────

function SkeletonMessage({ align }: { align: 'left' | 'right' }) {
  return (
    <div className={'flex gap-3 ' + (align === 'right' ? 'flex-row-reverse' : '')}>
      <div className="w-8 h-8 rounded-full bg-slate-200 dark:bg-slate-700 animate-pulse flex-shrink-0" />
      <div className={'max-w-[75%] space-y-2 ' + (align === 'right' ? 'text-right' : '')}>
        <div className="h-4 w-24 rounded bg-slate-200 dark:bg-slate-700 animate-pulse mx-auto" style={{ width: '60px' }} />
        <div className="h-20 w-64 rounded-2xl bg-slate-200 dark:bg-slate-700 animate-pulse" />
      </div>
    </div>
  );
}

function SkeletonPage() {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <div className="max-w-3xl mx-auto px-4 py-8">
        {/* Header skeleton */}
        <div className="text-center mb-8 space-y-3">
          <div className="h-7 w-64 rounded-lg bg-slate-200 dark:bg-slate-700 animate-pulse mx-auto" />
          <div className="h-4 w-48 rounded bg-slate-200 dark:bg-slate-700 animate-pulse mx-auto" />
        </div>
        {/* Messages skeleton */}
        <div className="space-y-6">
          <SkeletonMessage align="right" />
          <SkeletonMessage align="left" />
          <SkeletonMessage align="right" />
          <SkeletonMessage align="left" />
        </div>
      </div>
    </div>
  );
}

// ─── 404 / Expired Page ──────────────────────────────────────────────────

function NotFoundPage() {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center p-6">
      <div className="text-center max-w-md">
        <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-amber-100 dark:bg-amber-500/10 mx-auto mb-6">
          <AlertTriangle className="w-8 h-8 text-amber-500" />
        </div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white mb-3">
          Link Not Found
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mb-8 leading-relaxed">
          This shared conversation link doesn't exist, has expired, or has been removed.
          The owner may need to generate a new link.
        </p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 px-6 py-3 text-sm font-medium rounded-xl text-white bg-emerald-600 hover:bg-emerald-500 shadow-lg shadow-emerald-500/20 transition-all"
        >
          Try SupremeAI
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </div>
  );
}

// ─── Component ───────────────────────────────────────────────────────────

export default function SharedConversationPage() {
  const { shareId } = useParams<{ shareId: string }>();
  const [data, setData] = useState<SharedConversationData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!shareId) {
      setNotFound(true);
      setIsLoading(false);
      return;
    }

    const fetchSharedConversation = async () => {
      try {
        const response = await apiClient.get<SharedConversationData>(`/api/share/${shareId}`);
        if (response) {
          setData(response);
        } else {
          setNotFound(true);
        }
      } catch {
        setNotFound(true);
      } finally {
        setIsLoading(false);
      }
    };

    fetchSharedConversation();
  }, [shareId]);

  if (isLoading) return <SkeletonPage />;
  if (notFound || !data) return <NotFoundPage />;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex flex-col">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
        <div className="max-w-3xl mx-auto px-4 py-6 text-center">
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <div className="flex items-center justify-center gap-2 mb-2">
              <Sparkles className="w-5 h-5 text-emerald-500" />
              <span className="text-xs font-medium text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                Shared by SupremeAI
              </span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white mb-3">
              {data.title || 'Shared Conversation'}
            </h1>
            <div className="flex items-center justify-center gap-4 text-xs text-slate-400 dark:text-slate-500">
              <div className="flex items-center gap-1.5">
                <Eye className="w-3.5 h-3.5" />
                <span>{data.view_count} {data.view_count === 1 ? 'view' : 'views'}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5" />
                <span>{formatDate(data.created_at)}</span>
              </div>
            </div>
          </motion.div>
        </div>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 py-8">
          <div className="space-y-6">
            {data.messages.map((message, index) => {
              const isUser = message.role === 'user';
              return (
                <motion.div
                  key={message.id || index}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25, delay: index * 0.05 }}
                  className={'flex gap-3 ' + (isUser ? 'flex-row-reverse' : '')}
                >
                  {/* Avatar */}
                  <div
                    className={
                      'flex items-center justify-center w-8 h-8 rounded-full flex-shrink-0 mt-1 ' +
                      (isUser
                        ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                        : 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300')
                    }
                  >
                    {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                  </div>

                  {/* Bubble */}
                  <div className={'max-w-[75%] min-w-0 ' + (isUser ? 'text-right' : '')}>
                    <p className="text-xs text-slate-400 dark:text-slate-500 mb-1.5 px-1">
                      {isUser ? 'You' : 'SupremeAI'}
                      <span className="ml-2">{formatTime(message.timestamp)}</span>
                    </p>
                    <div
                      className={
                        'inline-block text-left px-4 py-3 rounded-2xl text-sm leading-relaxed ' +
                        (isUser
                          ? 'bg-emerald-600 text-white rounded-tr-md'
                          : 'bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100 border border-slate-200 dark:border-slate-700 rounded-tl-md shadow-sm')
                      }
                    >
                      <span dangerouslySetInnerHTML={{ __html: formatMessageContent(message.content) }} />
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      </main>

      {/* CTA Footer */}
      <footer className="flex-shrink-0 border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
        <div className="max-w-3xl mx-auto px-4 py-6 text-center">
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
            Powered by SupremeAI — have your own AI conversations
          </p>
          <Link
            to="/"
            className={
              'inline-flex items-center gap-2 px-6 py-3 text-sm font-medium rounded-xl transition-all ' +
              'text-white bg-emerald-600 hover:bg-emerald-500 shadow-lg shadow-emerald-500/20'
            }
          >
            Try SupremeAI
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </footer>
    </div>
  );
}
