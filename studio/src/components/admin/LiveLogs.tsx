import { useEffect, useState } from 'react';
import { useLogParserWorker } from '../../hooks/useLogParserWorker';

interface LiveLogsProps {
  liveLogs: string[];
  setLiveLogs: (logs: string[]) => void;
}

export function LiveLogs({ liveLogs, setLiveLogs }: LiveLogsProps) {
  const [filterLevel, setFilterLevel] = useState<'ALL' | 'INFO' | 'WARN' | 'ERROR'>('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [filteredLogs, setFilteredLogs] = useState<string[]>([]);
  const { filterLogs } = useLogParserWorker();

  // বাংলা মন্তব্য: লগ filter/search কাজটি web worker-এ অফলোড করা হয় (বড় লগ অ্যারেতে main thread block রোধ)।
  // worker না থাকলে filterLogs নিজেই মেইন থ্রেডে সেফ fallback করে।
  useEffect(() => {
    let cancelled = false;
    filterLogs(liveLogs, filterLevel, searchTerm)
      .then((res) => {
        if (!cancelled) setFilteredLogs(res);
      })
      .catch((err: unknown) => {
        // Log parser worker failure — keep existing filteredLogs rather than blanking the panel.
        console.error('[LiveLogs] filterLogs worker failed:', err);
      });
    return () => {
      cancelled = true;
    };
  }, [liveLogs, filterLevel, searchTerm, filterLogs]);

  // Extract log level counters
  const safeLogs = Array.isArray(liveLogs) ? liveLogs : [];
  const infoCount = safeLogs.filter(log => log.toUpperCase().includes('INFO')).length;
  const warnCount = safeLogs.filter(log => log.toUpperCase().includes('WARN') || log.toUpperCase().includes('WARNING')).length;
  const errCount = safeLogs.filter(log => log.toUpperCase().includes('ERROR') || log.toUpperCase().includes('ERR') || log.toUpperCase().includes('FAIL')).length;

  return (
    <div className="flex-grow flex flex-col bg-[#030611] p-4 font-mono text-xs overflow-y-auto text-[var(--foreground)]">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-3 mb-4 pb-3 border-b border-[var(--border-color)]">
        <div className="flex flex-col gap-1">
          <span className="text-slate-400 font-bold uppercase tracking-wider text-[10px]">Real-time Live Stream (supremeai.log)</span>
          <div className="flex gap-2 text-[10px] text-slate-400 mt-1">
            <span>Total: {safeLogs.length}</span>
            <span className="text-emerald-500">Info: {infoCount}</span>
            <span className="text-yellow-500">Warn: {warnCount}</span>
            <span className="text-red-500">Error: {errCount}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 items-center w-full md:w-auto">
          <input
            type="text"
            placeholder="Filter logs..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="bg-[var(--input-bg)] border border-[var(--input-border)] rounded px-2 py-1 text-[11px] text-[var(--foreground)] focus:outline-none focus:border-[#00f3ff] w-full md:w-40"
          />
          <div className="flex bg-[var(--sidebar-bg)] rounded border border-[var(--border-color)] p-0.5">
            {(['ALL', 'INFO', 'WARN', 'ERROR'] as const).map(lvl => (
              <button
                key={lvl}
                onClick={() => setFilterLevel(lvl)}
                className={`px-2 py-0.5 text-[9px] font-bold rounded transition-colors ${
                  filterLevel === lvl ? 'bg-[#00f3ff]/20 text-[#00f3ff]' : 'text-slate-400 hover:text-[var(--foreground)]'
                }`}
              >
                {lvl}
              </button>
            ))}
          </div>
          <button
            onClick={() => setLiveLogs([])}
            className="text-red-400 hover:text-red-300 font-bold text-[10px] ml-auto md:ml-2 uppercase"
          >
            Clear Screen
          </button>
        </div>
      </div>
      <div className="flex-grow flex flex-col gap-1 overflow-y-auto max-h-[70vh]">
        {filteredLogs.length === 0 ?
          <div className="text-slate-400 italic">Listening for incoming server logs or no matching logs found...</div>
          :
          filteredLogs.map((log, idx) => {
            let logColor = 'text-[#00ff66]';
            if (log.toUpperCase().includes('ERROR') || log.toUpperCase().includes('FAIL')) {
              logColor = 'text-red-400';
            } else if (log.toUpperCase().includes('WARN')) {
              logColor = 'text-yellow-400';
            } else if (log.toUpperCase().includes('INFO')) {
              logColor = 'text-cyan-400';
            }
            return (
              <div key={idx} className={`${logColor} whitespace-pre-wrap`}>{log}</div>
            );
          })
        }
      </div>
    </div>
  );
}
