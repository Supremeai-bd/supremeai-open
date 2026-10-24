import { useEffect, useRef } from 'react';

// বাংলা মন্তব্য: logParser.worker কে সেফলি র‍্যাপ করা হয়েছে। worker পাওয়া না গেলে
// (যেমন SSR বা পুরোনো ব্রাউজার) caller নিজেই fallback কম্পিউট করবে।
type WorkerResponse = { action: string; result?: unknown; error?: string };

export function useLogParserWorker() {
  const workerRef = useRef<Worker | null>(null);

  useEffect(() => {
    try {
      workerRef.current = new Worker(
        new URL('../workers/logParser.worker.ts', import.meta.url),
        { type: 'module' },
      );
    } catch {
      workerRef.current = null;
    }
    return () => {
      workerRef.current?.terminate();
      workerRef.current = null;
    };
  }, []);

  function filterLogs(
    logs: string[],
    level: 'ALL' | 'INFO' | 'WARN' | 'ERROR',
    searchTerm: string,
  ): Promise<string[]> {
    const worker = workerRef.current;
    if (!worker) {
      // মেইন থ্রেড fallback (সেফ)
      const term = searchTerm.toLowerCase();
      return Promise.resolve(
        logs.filter((log) => {
          const up = log.toUpperCase();
          const matchesSearch = log.toLowerCase().includes(term);
          if (level === 'ALL') return matchesSearch;
          if (level === 'INFO') return matchesSearch && up.includes('INFO');
          if (level === 'WARN') return matchesSearch && (up.includes('WARN') || up.includes('WARNING'));
          if (level === 'ERROR') return matchesSearch && (up.includes('ERROR') || up.includes('ERR') || up.includes('FAIL'));
          return matchesSearch;
        }),
      );
    }
    return new Promise<string[]>((resolve) => {
      const onMessage = (ev: MessageEvent<WorkerResponse>) => {
        if (ev.data.action === 'FILTERED_LOGS') {
          worker.removeEventListener('message', onMessage);
          resolve((ev.data.result as string[]) ?? []);
        }
      };
      worker.addEventListener('message', onMessage);
      worker.postMessage({ action: 'FILTER_LOGS', payload: { logs, level, searchTerm } });
    });
  }

  return { filterLogs };
}
