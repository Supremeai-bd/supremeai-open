import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuthStore } from '../../../store/authStore';
import { LogStream, EmptyState } from '../../kit';

interface LogEntry {
  timestamp: string;
  level: string;
  source: string;
  message: string;
}

export function LiveLogs() {
  const [autoScroll, setAutoScroll] = useState(true);
  const [levelFilter, setLevelFilter] = useState<string>('all');
  const [keyword, setKeyword] = useState('');

  // Issue #1831 fixes (2 of them here):
  // 1. Gate: 'admin_token' localStorage key is NEVER written anywhere in the
  //    repo (canonical session token lives in tokenStorage as
  //    'supreme_admin_jwt') — the module was permanently disabled for
  //    everyone. Gate on the auth store instead (same pattern as
  //    SecretsHealth.tsx).
  // 2. Source: GET /admin-api/logs does not exist (404). The old
  //    CommandCenter realtime provider (the only filler of the ['cmd','logs']
  //    cache) was zero-importer dead code — deleted in #2553. Until a live
  //    log source is wired, this cache subscription renders the empty state
  //    (enabled:false → observer-only, no fetching).
  const isAdminAuthenticated = useAuthStore((s) => s.role === 'admin' && s.status === 'loggedIn');
  const { data: logs, isLoading } = useQuery<LogEntry[]>({
    queryKey: ['cmd', 'logs'],
    queryFn: () => [], // cache-only query — no live filler since #2553 (see comment above)
    enabled: false,
    initialData: [],
    refetchOnMount: false,
  });


  const filtered = logs?.filter((log) => {
    if (levelFilter !== 'all' && log.level !== levelFilter) return false;
    if (keyword && !log.message.toLowerCase().includes(keyword.toLowerCase())) return false;
    return true;
  }) ?? [];

  if (!isAdminAuthenticated) {
    return (
      <EmptyState
        title="অ্যাক্সেস নেই"
        message="Live Logs শুধু authenticated admin-দের জন্য — অ্যাডমিন হিসেবে লগইন করুন।"
      />
    );
  }

  if (isLoading && !logs) {
    return <EmptyState title="লগ লোড হচ্ছে..." message="SSE স্ট্রিম সংযোগ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Live Logs</h2>
        <div className="flex items-center gap-2">
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
            className="bg-[var(--sa-bg-1)] border border-[var(--sa-line)] text-[10px] font-mono rounded px-2 py-1"
          >
            <option value="all">ALL</option>
            <option value="error">ERROR</option>
            <option value="warn">WARN</option>
            <option value="info">INFO</option>
            <option value="debug">DEBUG</option>
          </select>
          <input
            type="text"
            placeholder="Keyword..."
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            className="bg-[var(--sa-bg-1)] border border-[var(--sa-line)] text-[10px] font-mono rounded px-2 py-1 w-32"
          />
          <label className="flex items-center gap-1 text-[10px] font-mono text-[var(--sa-text-2)]">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="rounded"
            />
            Auto-scroll
          </label>
        </div>
      </div>
      <LogStream logs={filtered} autoScroll={autoScroll} maxHeight={500} />
    </div>
  );
}
